"""Stage 5 — multilingual demonstration case (CASE-DEMO-MULTILING-01).

Everything in this module is SYNTHETIC DEMONSTRATION DATA: the same
fictional people (Rajesh Kumar, Vikram Rao, Ananya Joshi) and places
(Pune, Mumbai) appear in four languages — English, Hindi, Marathi and
Urdu — and the documents go through the REAL pipeline (upload → language
detection → extraction → candidate/match/relationship review actions),
exactly as an investigator would do. Nothing is inserted as "confirmed"
by hand: confirmed rows exist only because the seeder performs the
acceptance workflow, which is the stage-2 invariant.

The story is deliberately built so the analysis has something real to
say: the English report places Rajesh Kumar at Pune at 21:10, the Hindi
report places him in Mumbai at the same time (a genuine, reviewer-facing
EVIDENCE_CONTRADICTION — the engine flags it as POTENTIAL, it never
decides), and the Marathi + Urdu reports corroborate Pune.

Idempotent: if the case already exists it is returned untouched.
"""

from __future__ import annotations

import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth_service import record_audit  # noqa: F401  (audit comes via the flows)
from .document_service import (accept_entity_candidate,
                               accept_match, accept_relationship_candidate,
                               process_document, upload_document)
from ..models import (Case, EntityCandidate, EntityMatchSuggestion,
                       RelationshipCandidate, User)

CASE_NUMBER = "CASE-DEMO-MULTILING-01"

# (filename, language label, body) — SYNTHETIC DEMONSTRATION DATA.
# The same incident is reported in four languages. The timestamps are
# chosen so that EXACTLY ONE pair collides: EN(21:10 Pune) vs HI(21:10
# Mumbai) sit inside the R4 spatial tolerance and are flagged, while the
# MR(21:27 Pune) and UR(21:30 Pune) sightings corroborate Pune but fall
# outside the tolerance window relative to the Mumbai claim — so they do
# not add further (near-duplicate) contradictions.
# Order matters: the witness statements (HI/MR/UR) arrive first and confirm
# the people; the formal FIR summary (EN) arrives last so its CALLED edge
# can be accepted with both endpoints already confirmed.
_DOCUMENTS: list[tuple[str, str]] = [
    ("demo_multiling_hi_witness.txt",
     "SYNTHETIC DEMONSTRATION DATA\n"
     "राजेश कुमार मुंबई में देखे गए। 2026-08-14 21:10\n"
     "विक्रम राव से बात हुई। 21:25\n"),
    ("demo_multiling_mr_witness.txt",
     "SYNTHETIC DEMONSTRATION DATA\n"
     "राजेश कुमार पुण्यात दिसून आला. 2026-08-14 21:27\n"
     "अनन्या जोशी यांचा फोन आला.\n"),
    ("demo_multiling_ur_witness.txt",
     "SYNTHETIC DEMONSTRATION DATA\n"
     "میں نے راجش کمار کو پونہ میں دیکھا۔ 2026-08-14 21:30\n"
     "وہ وکرم راؤ سے بات کر رہے تھے۔\n"),
    ("demo_multiling_en_fir_summary.txt",
     "FIR SUMMARY — SYNTHETIC DEMONSTRATION DATA\n"
     "On 2026-08-14 21:10, Ananya Joshi reported that Rajesh Kumar was "
     "seen at Pune station.\n"
     "At 21:25 Rajesh Kumar called Vikram Rao.\n"),
]


class _MemoryUpload:
    """In-memory stand-in for an uploaded file (same attributes the
    storage layer reads: ``filename`` and ``file``)."""

    def __init__(self, filename: str, data: bytes):
        self.filename = filename
        self.file = io.BytesIO(data)
        self.content_type = "text/plain"


def _demo_current(db: Session):
    from ..security.rbac import CurrentUser
    # Attribute this synthetic demo case to the non-login synthetic-data
    # owner (never to an authentication identity).
    from ..seed import get_synthetic_owner
    user = get_synthetic_owner(db)
    return CurrentUser(user=user, payload=None)


def _accept_all_for_document(db: Session, doc, current) -> dict:
    """Run the review workflow for one processed document: matches first
    (a match folds a candidate into an existing confirmed entity), then
    entity candidates, then relationship candidates. Bounded loop;
    stops when nothing is left pending."""
    counts = {"matches": 0, "entities": 0, "relationships": 0}
    for _ in range(25):
        progressed = False
        matches = db.scalars(select(EntityMatchSuggestion).join(
            EntityCandidate,
            EntityMatchSuggestion.candidate_id == EntityCandidate.id
        ).where(EntityCandidate.document_id == doc.id,
                EntityMatchSuggestion.status == "PENDING")).all()
        for m in matches:
            # a sibling accepted earlier in this pass may have superseded
            # this suggestion — mirror the UI, which re-reads the queue
            # after every decision
            db.refresh(m)
            if m.status != "PENDING":
                continue
            accept_match(db, doc, m, current)
            counts["matches"] += 1
            progressed = True
        for c in db.scalars(select(EntityCandidate).where(
                EntityCandidate.document_id == doc.id,
                EntityCandidate.status == "PENDING")).all():
            if c.matches and any(m.status == "PENDING" for m in c.matches):
                continue  # match resolution comes first (next iteration)
            accept_entity_candidate(db, doc, c, current)
            counts["entities"] += 1
            progressed = True
        for r in db.scalars(select(RelationshipCandidate).where(
                RelationshipCandidate.document_id == doc.id,
                RelationshipCandidate.status == "PENDING")).all():
            try:
                accept_relationship_candidate(db, doc, r, current)
                counts["relationships"] += 1
                progressed = True
            except Exception:  # noqa: BLE001 — endpoint not confirmed yet
                db.rollback()
        if not progressed:
            break
    return counts


def seed_demo_multiling(db: Session) -> Case | None:
    """Create the multilingual demonstration case (idempotent)."""
    existing = db.scalars(select(Case).where(
        Case.case_number == CASE_NUMBER)).first()
    if existing is not None:
        return existing

    current = _demo_current(db)
    if current is None:
        return None

    case = Case(case_number=CASE_NUMBER,
                title="Multilingual demonstration — one incident, four "
                      "languages (SYNTHETIC DEMONSTRATION DATA)",
                description=(
                    "SYNTHETIC DEMONSTRATION DATA. The same fictional "
                    "incident is reported in English, Hindi, Marathi and "
                    "Urdu. The English and Hindi reports conflict on the "
                    "location (Pune vs Mumbai) at the same recorded time; "
                    "the Marathi and Urdu reports corroborate Pune. All "
                    "people and places are fictional; nothing here refers "
                    "to real persons or real databases."),
                status="OPEN", priority="HIGH", is_synthetic=True,
                created_by=current.user.id)
    db.add(case)
    db.flush()

    for filename, body in _DOCUMENTS:
        doc = upload_document(db, case, current,
                              _MemoryUpload(filename, body.encode("utf-8")))
        result = process_document(doc.id)
        if result.get("status") != "PROCESSED":
            raise RuntimeError(
                f"demo document {filename} failed processing: {result}")
        _accept_all_for_document(db, doc, current)
    db.commit()

    record_audit(db, current, "DEMO_SEED", "case", str(case.id),
                 {"case_number": CASE_NUMBER,
                  "label": "SYNTHETIC DEMONSTRATION DATA"})
    return case
