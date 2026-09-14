"""Stage 6 — end-to-end demonstration case (CASE-DEMO-END2END-01).

Everything in this module is SYNTHETIC DEMONSTRATION DATA. The case walks
the COMPLETE document-to-investigation workflow through the REAL pipeline:

    FIR.pdf -> Investigation_Report.pdf -> CDR.csv -> Vehicle_Report.pdf
    -> Location_Report.pdf

Each file goes through upload -> async processing -> rule extraction ->
entity/relationship/claim candidates -> match suggestions -> the
investigator acceptance workflow (the same service calls the API uses).
Nothing is inserted as "confirmed" by hand. The story contains exactly
one genuine conflict — Vikram Sethi is claimed at Bhiwandi Godown at
22:30 (FIR) and at Kurla at 22:45 (surveillance report): the R4
evidence-contradiction engine flags that pair as POTENTIAL, and the
investigator sees it in the review queue / findings, never a fake verdict.

The PDFs are generated with reportlab (a real text layer the pypdf
extractor reads); the CDR is a real CSV the structured extractor parses.

Idempotent: if the case already exists it is returned untouched.
"""
from __future__ import annotations

import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth_service import record_audit
from .demo_multiling import _accept_all_for_document, _demo_current
from .document_service import (process_document, upload_document)
from ..models import Case

CASE_NUMBER = "CASE-DEMO-END2END-01"

_SYN = "SYNTHETIC DEMONSTRATION DATA"


# ------------------------------------------------------------------- PDFs

def _pdf_bytes(title: str, lines: list[str]) -> bytes:
    """A real one-page PDF (reportlab) with a searchable text layer."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as _canvas

    buf = io.BytesIO()
    c = _canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    c.setFont("Helvetica-Bold", 13)
    c.drawString(56, height - 64, title)
    c.setFont("Helvetica", 10)
    y = height - 92
    for line in lines:
        # simple wrapping for long lines
        while len(line) > 88:
            cut = line.rfind(" ", 0, 88)
            if cut <= 0:
                cut = 88
            c.drawString(56, y, line[:cut])
            line = line[cut:].lstrip()
            y -= 14
        c.drawString(56, y, line)
        y -= 14
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(56, 40, f"[{_SYN}] Fictional persons, places and numbers.")
    c.showPage()
    c.save()
    return buf.getvalue()


class _MemoryUpload:
    """In-memory uploaded file (same attributes the storage layer reads)."""

    def __init__(self, filename: str, data: bytes, content_type: str):
        self.filename = filename
        self.file = io.BytesIO(data)
        self.content_type = content_type


# --------------------------------------------------------------- the story
# Timestamps are chosen so that EXACTLY ONE spatial conflict exists:
# Bhiwandi Godown @ 22:30 (FIR) vs Kurla @ 22:45 (Location_Report) sit
# inside the R4 tolerance window for the same subject; every other
# sighting is either consistent or unlinked.

_FIR_LINES = [
    f"FIR Summary — Case No. 221/2026 ({_SYN})",
    "",
    "On 2026-07-20 22:30, Vikram Sethi was seen at Bhiwandi Godown.",
    "The accused was carrying vehicle MH01AB1234 and mobile number",
    "9000000101. The complainant reported goods worth Rs. 400000 missing",
    "from the godown.",
]

_INVES_LINES = [
    f"Investigation Report ({_SYN})",
    "",
    "On 2026-07-21 09:15, Sanjay Bhosle was observed at Chembur.",
    "Earlier, on 2026-07-20 23:05, Vikram Sethi called Sanjay Bhosle.",
    "Sanjay Bhosle arrived in vehicle GJ02CD5678 with driver Nadeem Ansari.",
    "Sanjay Bhosle uses mobile number 9000000102. The complainant,",
    "Kiran Deshpande, signed the case record on 2026-07-21.",
]

_CDR_CSV = (
    "call_id,caller,callee,start_time,duration_sec,cell_tower\n"
    "C0901,9000000101,9000000102,2026-07-20 23:05:00,185,Kurla\n"
    "C0902,9000000102,9000000103,2026-07-21 08:40:00,64,Chembur\n"
)

_VEH_LINES = [
    f"Vehicle Report ({_SYN})",
    "",
    "Vehicle MH01AB1234 is registered to Vikram Sethi.",
    "Vehicle GJ02CD5678 is registered to Sanjay Bhosle.",
    "Both registrations were verified against the records office extract.",
]

_LOC_LINES = [
    f"Location Surveillance Report ({_SYN})",
    "",
    "On 2026-07-20 22:45, Vikram Sethi was seen at Kurla.",
    "Footage shows him boarding a local train at 22:52.",
    "Separately, a transfer from ACCT100200 to ACCT100300 of Rs. 250000",
    "was recorded on 2026-07-21 and linked to the case accounts.",
]


def _documents() -> list[tuple[str, bytes, str]]:
    return [
        ("FIR.pdf",
         _pdf_bytes("FIR — Case No. 221/2026", _FIR_LINES),
         "application/pdf"),
        ("Investigation_Report.pdf",
         _pdf_bytes("Investigation Report", _INVES_LINES),
         "application/pdf"),
        ("CDR.csv", _CDR_CSV.encode("utf-8"), "text/csv"),
        ("Vehicle_Report.pdf",
         _pdf_bytes("Vehicle Report", _VEH_LINES),
         "application/pdf"),
        ("Location_Report.pdf",
         _pdf_bytes("Location Surveillance Report", _LOC_LINES),
         "application/pdf"),
    ]


# ------------------------------------------------------------------ seed

def seed_demo_e2e(db: Session) -> Case | None:
    """Create the end-to-end demonstration case (idempotent)."""
    existing = db.scalars(select(Case).where(
        Case.case_number == CASE_NUMBER)).first()
    if existing is not None:
        return existing

    current = _demo_current(db)
    if current is None:
        return None

    case = Case(case_number=CASE_NUMBER,
                title="End-to-end demonstration — five documents, one "
                      "conflict (SYNTHETIC DEMONSTRATION DATA)",
                description=(
                    f"{_SYN}. Five synthetic documents (three PDFs, one "
                    "CSV, one surveillance report) processed through the "
                    "real pipeline: extraction, candidate review, entity "
                    "resolution, relationship confirmation, graph and "
                    "intelligence. The FIR places Vikram Sethi at Bhiwandi "
                    "Godown at 22:30 while the surveillance report places "
                    "him at Kurla at 22:45 — a POTENTIAL contradiction "
                    "flagged by the engine, never auto-decided. All names, "
                    "places, numbers and accounts are fictional."),
                status="OPEN", priority="HIGH", is_synthetic=True,
                created_by=current.user.id)
    db.add(case)
    db.flush()

    for filename, data, ctype in _documents():
        doc = upload_document(db, case, current,
                              _MemoryUpload(filename, data, ctype))
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
