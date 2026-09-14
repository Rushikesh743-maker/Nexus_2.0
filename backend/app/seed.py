"""Development seed: synthetic dataset + Meridian corpus.

RUNS ONLY AGAINST THE LOCAL DEVELOPMENT DATABASE. Everything it writes is
labeled synthetic. The seed is idempotent — re-running it never duplicates
rows (it checks for the sentinel case numbers first).

Authentication identities are **not** seeded here. NEXUS uses Supabase Auth
for login; real users are provisioned in Supabase and mapped to a NEXUS
user/role server-side (see README). The seed only writes *synthetic
investigation data*, which is kept separate from authentication identities:

1. **Synthetic-data owner** — a single, clearly-labelled, non-authenticatable
   NEXUS user (no Supabase identity, so it can never log in) that owns the
   seeded synthetic cases. This keeps the synthetic investigation data
   intact and attributed, without any demo login accounts.

2. **Spec dataset** — the small demonstration case set (Aarav Mehta,
   Rohan Deshmukh, Kabir Shah, Neha Patil, Vikram Rao; vehicles MH12AB1234,
   MH14CD5678; locations Pune Central / Industrial Area / Station Road /
   Airport Road; cases CASE-2026-001..003) with documents, entities,
   relationships, evidence, timeline, hypotheses, contradictions, gaps and
   a baseline simulation.

3. **Operation Meridian import** — the existing analysis corpus
   (data/raw, the seeded pipeline) projected into the relational model:
   graph nodes → entities, edges → relationships, source documents →
   documents + evidence + timeline events, engine contradictions and
   high-severity findings → contradictions/hypotheses, plus genuinely
   computed investigation gaps (CDR quiet window, unchecked subjects).

Part 3 reuses the real pipeline (`app.graph.build.build_graph`) — no
hand-copied facts.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (Case, Contradiction, Document, Entity, Evidence,
                     Hypothesis, InvestigationGap, Location, Relationship,
                     Simulation, TimelineEvent, User)

logger = logging.getLogger("nexus.seed")

HERE = os.path.dirname(os.path.abspath(__file__))                       # backend/app
BACKEND_DIR = os.path.dirname(HERE)                                     # backend
ROOT = os.path.dirname(BACKEND_DIR)                                     # repository root
RAW = os.path.join(ROOT, "data", "raw")

SYNTHETIC = "[SYNTHETIC DEMONSTRATION DATA] "

# The single owner of seeded synthetic investigation data. It has NO
# Supabase identity (supabase_id is NULL), so it can never authenticate —
# it exists only to keep the synthetic data attributed without any demo
# login accounts. Role is deliberately not ADMIN.
SYNTHETIC_OWNER_EMAIL = "synthetic-data@nexus.local"
SYNTHETIC_OWNER_NAME = "Synthetic Data Seed"

# Synthetic Pune-region coordinates (demonstration only — not surveyed).
_LOCS = {
    "Pune Central": (18.5269, 73.8646),
    "Industrial Area": (18.5648, 73.8261),
    "Station Road": (18.5204, 73.8752),
    "Airport Road": (18.5196, 73.8453),
}


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


# ------------------------------------------------------------------- users

def seed_users(db: Session) -> list[User]:
    """Create (idempotently) the synthetic-data owner.

    No authentication identities are seeded. The owner has no Supabase
    identity and therefore can never log in; it only owns the synthetic
    investigation data below.
    """
    user = db.scalars(select(User).where(
        User.email == SYNTHETIC_OWNER_EMAIL)).first()
    if user is None:
        user = User(email=SYNTHETIC_OWNER_EMAIL, name=SYNTHETIC_OWNER_NAME,
                    role="INVESTIGATOR", officer_id=None, supabase_id=None)
        db.add(user)
        db.flush()
        logger.info("Seeded synthetic-data owner %s", SYNTHETIC_OWNER_EMAIL)
    return [user]


def get_synthetic_owner(db: Session) -> User:
    """The synthetic-data owner (created if missing). Shared by the demo
    case seeders so synthetic data stays attributed to a non-login identity."""
    user = db.scalars(select(User).where(
        User.email == SYNTHETIC_OWNER_EMAIL)).first()
    if user is None:
        user = User(email=SYNTHETIC_OWNER_EMAIL, name=SYNTHETIC_OWNER_NAME,
                    role="INVESTIGATOR", officer_id=None, supabase_id=None)
        db.add(user)
        db.flush()
    return user


# --------------------------------------------------------------- spec cases

def _spec_case(db: Session, number: str, title: str, description: str,
               status: str, priority: str, creator: User,
               days_ago: int) -> Case:
    case = db.scalars(select(Case).where(Case.case_number == number)).first()
    if case is not None:
        return case
    base = datetime.utcnow() - timedelta(days=days_ago)
    case = Case(case_number=number, title=title,
                description=SYNTHETIC + description,
                status=status, priority=priority, created_by=creator.id,
                created_at=base, updated_at=base + timedelta(hours=3))
    db.add(case)
    db.flush()
    return case


def seed_spec_dataset(db: Session, users: list[User]) -> None:
    investigator = get_synthetic_owner(db)

    # ------------------------------------------------------------------ data
    cases = {
        "CASE-2026-001": _spec_case(
            db, "CASE-2026-001",
            "Unauthorised vehicle movement — Pune ring road",
            "Two unregistered vehicles observed moving together between Pune "
            "Central and the Industrial Area across three days. Subscriber "
            "verification requested for both plates.",
            "ACTIVE", "HIGH", investigator, 12),
        "CASE-2026-002": _spec_case(
            db, "CASE-2026-002",
            "Fraud network — Industrial Area",
            "Series of small-value transfers converging on two bank accounts "
            "linked to an industrial unit. Persons of interest identified "
            "from call records and site visits.",
            "OPEN", "MEDIUM", investigator, 8),
        "CASE-2026-003": _spec_case(
            db, "CASE-2026-003",
            "Cross-region supply route",
            "Vehicle movement pattern suggests a supply corridor between the "
            "Industrial Area and Airport Road. Under review; no charges "
            "framed yet.",
            "ON_HOLD", "LOW", investigator, 4),
    }

    persons = {
        "Aarav Mehta": "person", "Rohan Deshmukh": "person", "Kabir Shah": "person",
        "Neha Patil": "person", "Vikram Rao": "person",
    }
    vehicles = {"MH12AB1234": "vehicle", "MH14CD5678": "vehicle"}

    docs = {
        "fir_2026_001.txt": ("text", "en", 4211),
        "cdr_extract.csv": ("csv", "en", 18733),
        "site_visit_notes.txt": ("text", "en", 2110),
        "transfer_log.csv": ("csv", "en", 9650),
        "patrol_report.txt": ("text", "en", 3322),
    }

    # ------------------------------------------------------------- entities
    def ent(case: Case, name: str, etype: str, **meta) -> Entity:
        existing = db.scalars(select(Entity).where(
            Entity.case_id == case.id, Entity.canonical_name == name)).first()
        if existing is not None:
            return existing
        e = Entity(case_id=case.id, entity_type=etype, canonical_name=name,
                   meta={"synthetic": True, **meta})
        db.add(e)
        db.flush()
        return e

    e = {}
    for number, case in cases.items():
        for name, etype in {**persons, **vehicles}.items():
            e[(number, name)] = ent(case, name, etype)

    # ----------------------------------------------------------- documents
    def doc(case: Case, filename: str, ftype: str, lang: str, size: int,
            when: datetime, status: str = "PROCESSED") -> Document:
        existing = db.scalars(select(Document).where(
            Document.case_id == case.id, Document.filename == filename)).first()
        if existing is not None:
            return existing
        d = Document(case_id=case.id, filename=filename, file_type=ftype,
                     language=lang, file_size=size, uploaded_at=when,
                     processing_status=status)
        db.add(d)
        db.flush()
        return d

    base = datetime.utcnow()
    d = {
        ("CASE-2026-001", "fir_2026_001.txt"): doc(cases["CASE-2026-001"], "fir_2026_001.txt", *docs["fir_2026_001.txt"], when=base - timedelta(days=12)),
        ("CASE-2026-001", "cdr_extract.csv"): doc(cases["CASE-2026-001"], "cdr_extract.csv", *docs["cdr_extract.csv"], when=base - timedelta(days=11)),
        ("CASE-2026-002", "transfer_log.csv"): doc(cases["CASE-2026-002"], "transfer_log.csv", *docs["transfer_log.csv"], when=base - timedelta(days=8)),
        ("CASE-2026-002", "site_visit_notes.txt"): doc(cases["CASE-2026-002"], "site_visit_notes.txt", *docs["site_visit_notes.txt"], when=base - timedelta(days=7)),
        ("CASE-2026-003", "patrol_report.txt"): doc(cases["CASE-2026-003"], "patrol_report.txt", *docs["patrol_report.txt"], when=base - timedelta(days=4)),
    }

    # ----------------------------------------------------------- locations
    def loc(case: Case, name: str) -> Location:
        existing = db.scalars(select(Location).where(
            Location.case_id == case.id, Location.name == name)).first()
        if existing is not None:
            return existing
        lat, lon = _LOCS[name]
        l = Location(case_id=case.id, name=name, latitude=lat, longitude=lon,
                     meta={"synthetic": True, "note": "demonstration coordinates"})
        db.add(l)
        db.flush()
        return l

    l1 = {n: loc(cases["CASE-2026-001"], n) for n in ("Pune Central", "Industrial Area", "Station Road")}
    l2 = {n: loc(cases["CASE-2026-002"], n) for n in ("Industrial Area", "Station Road")}
    l3 = {n: loc(cases["CASE-2026-003"], n) for n in ("Industrial Area", "Airport Road")}

    # ------------------------------------------------------------ evidence
    def ev(case: Case, document: Document | None, etype: str,
           description: str, source_ref: str, confidence: float | None) -> Evidence:
        existing = db.scalars(select(Evidence).where(
            Evidence.case_id == case.id,
            Evidence.source_reference == source_ref)).first()
        if existing is not None:
            return existing
        v = Evidence(case_id=case.id, document_id=document.id if document else None,
                     evidence_type=etype, description=description,
                     source_reference=source_ref, confidence=confidence)
        db.add(v)
        db.flush()
        return v

    c1, c2, c3 = cases["CASE-2026-001"], cases["CASE-2026-002"], cases["CASE-2026-003"]

    ev1 = [
        ev(c1, d[("CASE-2026-001", "fir_2026_001.txt")], "fir",
           "FIR records the complaint about coordinated vehicle movement near Pune Central.",
           "FIR/2026/001", 0.9),
        ev(c1, d[("CASE-2026-001", "cdr_extract.csv")], "cdr",
           "CDR extract: 14 calls between the two subscriber numbers over 6 days.",
           "CDR-2026-001", 0.85),
        ev(c1, None, "site_observation",
           "Patrol observation: both vehicles parked at the same loading bay, Industrial Area.",
           "OBS-2026-001", 0.7),
    ]
    ev2 = [
        ev(c2, d[("CASE-2026-002", "transfer_log.csv")], "financial",
           "Transfer log: 23 transfers below the reporting threshold converging on two accounts.",
           "TXN-2026-001", 0.8),
        ev(c2, d[("CASE-2026-002", "site_visit_notes.txt")], "site_visit",
           "Site visit notes: courier activity at the industrial unit, two named staff.",
           "SV-2026-001", 0.75),
    ]
    ev3 = [
        ev(c3, d[("CASE-2026-003", "patrol_report.txt")], "patrol_report",
           "Patrol report: vehicle MH14CD5678 on Airport Road twice in one week.",
           "PR-2026-001", 0.7),
    ]

    # ------------------------------------------------------- relationships
    def rel(case: Case, src: Entity, tgt: Entity, rtype: str,
            confidence: float | None, **meta) -> Relationship:
        existing = db.scalars(select(Relationship).where(
            Relationship.case_id == case.id,
            Relationship.source_entity_id == src.id,
            Relationship.target_entity_id == tgt.id,
            Relationship.relationship_type == rtype)).first()
        if existing is not None:
            return existing
        r = Relationship(case_id=case.id, source_entity_id=src.id,
                         target_entity_id=tgt.id, relationship_type=rtype,
                         confidence=confidence,
                         meta={"synthetic": True, **meta})
        db.add(r)
        db.flush()
        return r

    P = lambda n, k: e[(n, k)]
    rel(c1, P("CASE-2026-001", "Aarav Mehta"), P("CASE-2026-001", "MH12AB1234"), "OWNS", 0.9,
        evidence_refs=["FIR/2026/001"])
    rel(c1, P("CASE-2026-001", "Aarav Mehta"), P("CASE-2026-001", "Rohan Deshmukh"), "CALLED", 0.85,
        evidence_refs=["CDR-2026-001"])
    rel(c1, P("CASE-2026-001", "Rohan Deshmukh"), P("CASE-2026-001", "MH14CD5678"), "USED", 0.7,
        evidence_refs=["OBS-2026-001"])
    rel(c1, P("CASE-2026-001", "MH12AB1234"), l1["Pune Central"], "LOCATED_AT", 0.8,
        evidence_refs=["FIR/2026/001"])
    rel(c1, P("CASE-2026-001", "MH14CD5678"), l1["Industrial Area"], "LOCATED_AT", 0.7,
        evidence_refs=["OBS-2026-001"])
    rel(c2, P("CASE-2026-002", "Kabir Shah"), P("CASE-2026-002", "Vikram Rao"), "ASSOCIATED_WITH", 0.75,
        evidence_refs=["TXN-2026-001"])
    rel(c2, P("CASE-2026-002", "Vikram Rao"), P("CASE-2026-002", "Neha Patil"), "CALLED", 0.8,
        evidence_refs=["TXN-2026-001"])
    rel(c2, P("CASE-2026-002", "Kabir Shah"), l2["Industrial Area"], "LOCATED_AT", 0.8,
        evidence_refs=["SV-2026-001"])
    rel(c3, P("CASE-2026-003", "Neha Patil"), P("CASE-2026-003", "MH14CD5678"), "USED", 0.6,
        evidence_refs=["PR-2026-001"])
    rel(c3, P("CASE-2026-003", "MH14CD5678"), l3["Airport Road"], "LOCATED_AT", 0.7,
        evidence_refs=["PR-2026-001"])
    rel(c3, P("CASE-2026-003", "Rohan Deshmukh"), P("CASE-2026-003", "Kabir Shah"), "CONNECTED_TO", 0.5,
        evidence_refs=["PR-2026-001"], note="cross-case name overlap")

    # --------------------------------------------------------- timeline
    def tev(case: Case, etype: str, when: datetime, description: str,
            entity: Entity | None = None, location: Location | None = None,
            evidence: Evidence | None = None) -> TimelineEvent:
        existing = db.scalars(select(TimelineEvent).where(
            TimelineEvent.case_id == case.id,
            TimelineEvent.description == description)).first()
        if existing is not None:
            return existing
        t = TimelineEvent(case_id=case.id, event_type=etype, timestamp=when,
                          description=description, entity_id=entity.id if entity else None,
                          location_id=location.id if location else None,
                          evidence_id=evidence.id if evidence else None)
        db.add(t)
        db.flush()
        return t

    tev(c1, "document_filed", base - timedelta(days=12),
        "FIR filed: coordinated vehicle movement reported near Pune Central.",
        entity=P("CASE-2026-001", "Aarav Mehta"), location=l1["Pune Central"], evidence=ev1[0])
    tev(c1, "cdr_window_start", base - timedelta(days=11),
        "CDR window opens: 14 calls between the two subscriber numbers.", evidence=ev1[1])
    tev(c1, "site_observation", base - timedelta(days=9),
        "Both vehicles observed at the same loading bay, Industrial Area.",
        entity=P("CASE-2026-001", "MH12AB1234"), location=l1["Industrial Area"], evidence=ev1[2])
    tev(c2, "financial_pattern", base - timedelta(days=8),
        "Transfer log shows 23 sub-threshold transfers converging on two accounts.",
        entity=P("CASE-2026-002", "Kabir Shah"), evidence=ev2[0])
    tev(c2, "site_visit", base - timedelta(days=7),
        "Site visit at the industrial unit; courier activity noted.",
        location=l2["Industrial Area"], evidence=ev2[1])
    tev(c3, "patrol_sighting", base - timedelta(days=4),
        "Vehicle MH14CD5678 sighted on Airport Road (second sighting).",
        entity=P("CASE-2026-003", "MH14CD5678"), location=l3["Airport Road"], evidence=ev3[0])

    # -------------------------------------------- hypotheses/contradictions/gaps
    def hyp(case: Case, title: str, description: str, score: float | None, status: str) -> None:
        exists = db.scalars(select(Hypothesis).where(Hypothesis.case_id == case.id,
                                                     Hypothesis.title == title)).first()
        if exists is None:
            db.add(Hypothesis(case_id=case.id, title=title, description=description,
                              score=score, status=status))

    def con(case: Case, title: str, description: str, severity: str, status: str) -> None:
        exists = db.scalars(select(Contradiction).where(
            Contradiction.case_id == case.id, Contradiction.title == title)).first()
        if exists is None:
            db.add(Contradiction(case_id=case.id, title=title, description=description,
                                 severity=severity, status=status))

    def gap(case: Case, title: str, description: str, priority: str, status: str) -> None:
        exists = db.scalars(select(InvestigationGap).where(
            InvestigationGap.case_id == case.id, InvestigationGap.title == title)).first()
        if exists is None:
            db.add(InvestigationGap(case_id=case.id, title=title, description=description,
                                    priority=priority, status=status))

    hyp(c1, "The two vehicles are moved by the same crew",
        "Shared parking, timing overlap and call proximity suggest coordinated movement rather than coincidence.",
        0.62, "OPEN")
    hyp(c2, "The sub-threshold transfers are layering of proceeds",
        "Pattern is consistent with layering, but the industrial unit may be a legitimate front for smaller flows.",
        0.48, "OPEN")
    con(c1, "Stated alibi conflicts with CDR timing",
        "Rohan Deshmukh states he was at Station Road at 19:40, but the CDR places his handset in the "
        "Industrial Area cell for the same window.", "HIGH", "OPEN")
    con(c2, "Site visit notes disagree with the transfer log on dates",
        "The notes date the courier activity two days before the first transfer the log records.",
        "MEDIUM", "OPEN")
    gap(c1, "No CDR coverage for the third vehicle",
        "A third plate was seen in the FIR sketch; no CDR has been pulled for its subscriber.",
        "MEDIUM", "OPEN")
    gap(c2, "Second account holder not yet identified",
        "Transfers converge on two accounts; the second holder's identity is still unknown.",
        "HIGH", "OPEN")
    gap(c3, "Corridor direction unconfirmed",
        "Movement is recorded one way only; return legs are missing from the patrol data.",
        "LOW", "OPEN")

    # ------------------------------------------------------------ simulation
    exists = db.scalars(select(Simulation).where(Simulation.case_id == c1.id)).first()
    if exists is None:
        db.add(Simulation(case_id=c1.id,
                          name="Baseline — all evidence present",
                          description="Reference point for counterfactual runs (later stage): "
                                     "what the case looks like with every record in play.",
                          created_by=investigator.id))

    db.flush()
    logger.info("Spec dataset staged (3 cases, 5 persons, 2 vehicles, 4 locations).")


# -------------------------------------------------------- Meridian import

_TYPE_MAP = {"PERSON": "person", "ORG": "organization", "VEHICLE": "vehicle",
             "LOCATION": "location", "CASE": "case_reference"}


def _meridian_exists(db: Session) -> bool:
    return db.scalars(select(Case).where(Case.case_number == "CASE-2026-021")).first() is not None


def seed_meridian(db: Session, users: list[User]) -> None:
    """Project the existing analysis corpus into the relational model.

    Re-runs the real pipeline — extraction, resolution, analytics,
    contradiction detection — and stores its output. If the corpus is
    absent (fresh clone before `data/generator.py` has run) this logs and
    skips rather than inventing data.
    """
    if _meridian_exists(db):
        return
    if not os.path.isfile(os.path.join(RAW, "firs.json")):
        logger.warning("data/raw corpus not found — Meridian import skipped. "
                       "Run `python3 data/generator.py` first.")
        return

    from .graph.build import build_graph
    from .graph.analytics import NetworkAnalytics
    from .intelligence.contradiction_engine import ContradictionEngine
    from .intelligence.impact_simulator import ImpactSimulator  # noqa: F401 (future)

    logger.info("Building Meridian graph for import…")
    g = build_graph()
    an = NetworkAnalytics(g)
    findings = g.findings if hasattr(g, "findings") else None
    if findings is None:
        from .graph.anomaly import AnomalyDetector
        findings = AnomalyDetector(g, an).run_all()
    engine = ContradictionEngine(g)
    contradictions, _skipped = engine.run_all(), engine.skipped

    investigator = get_synthetic_owner(db)
    base = datetime.utcnow()
    case = Case(case_number="CASE-2026-021",
                title="Operation Meridian — cross-source network (synthetic)",
                description=SYNTHETIC + "Multi-source synthetic corpus: FIRs, CDR, "
                                        "transactions, criminal records, surveillance and "
                                        "social media. All records fictional; phone numbers "
                                        "from reserved ranges.",
                status="ACTIVE", priority="CRITICAL", created_by=investigator.id,
                created_at=base - timedelta(days=30), updated_at=base)
    db.add(case)
    db.flush()

    # documents
    doc_rows: dict[str, Document] = {}
    for doc_id, doc in g.raw["documents"].items():
        d = Document(case_id=case.id, filename=doc_id,
                     file_type=doc.get("source_type", "text"),
                     language=doc.get("language") or doc.get("script"),
                     file_size=None, uploaded_at=base - timedelta(days=30),
                     processing_status="PROCESSED")
        db.add(d)
        doc_rows[doc_id] = d
    db.flush()

    # entities
    entity_rows: dict[str, Entity] = {}
    for node_id, data in g.G.nodes(data=True):
        etype = _TYPE_MAP.get(data.get("type", ""), "other")
        meta = {"source_id": node_id, "synthetic": True}
        if data.get("aliases"):
            meta["aliases"] = data["aliases"]
        if data.get("phones"):
            meta["phones"] = data["phones"]
        if data.get("prior_cases") is not None:
            meta["prior_cases"] = data["prior_cases"]
        if data.get("lat") is not None:
            meta["lat"] = data["lat"]
            meta["lon"] = data.get("lon")
        entity_rows[node_id] = Entity(case_id=case.id, entity_type=etype,
                                      canonical_name=data.get("label", node_id),
                                      metadata=meta)
        db.add(entity_rows[node_id])
    db.flush()

    # relationships
    for a, b, data in g.G.edges(data=True):
        rtype = (data.get("types") or ["CONNECTED_TO"])[0]
        db.add(Relationship(
            case_id=case.id,
            source_entity_id=entity_rows[a].id,
            target_entity_id=entity_rows[b].id,
            relationship_type=rtype,
            confidence=data.get("confidence"),
            meta={"types": data.get("types"),
                      "first_seen": data.get("first_seen"),
                      "last_seen": data.get("last_seen"),
                      "evidence": [s.get("source_id") for s in data.get("sources", [])][:5],
                      "synthetic": True},
        ))

    # locations (from location nodes with coordinates)
    for node_id, data in g.G.nodes(data=True):
        if data.get("type") == "LOCATION" and data.get("lat") is not None:
            db.add(Location(case_id=case.id, name=data.get("label", node_id),
                            latitude=data["lat"], longitude=data.get("lon"),
                            meta={"source_id": node_id, "synthetic": True}))

    # evidence + timeline (one row per source document, honest provenance).
    # Timestamps come from the document record itself; feeds that carry only
    # a row count (cdr, transaction) get evidence but no invented timestamp.
    ts_key = {"fir": "registered_on", "fir_scan": "registered_on",
              "surveillance": "observed_on", "social_media": "posted_on"}
    for doc_id, doc in g.raw["documents"].items():
        record = doc.get("record") if isinstance(doc.get("record"), dict) else {}
        if "rows" in record:
            description = f"{doc.get('source_type')} feed ({record.get('rows')} records)"
        else:
            description = (record.get("fir_id") or record.get("report_id")
                           or record.get("post_id") or record.get("name") or doc_id)
        evidence = Evidence(case_id=case.id, document_id=doc_rows[doc_id].id,
                            evidence_type=doc.get("source_type", "document"),
                            description=description,
                            source_reference=doc_id, confidence=None)
        db.add(evidence)
        db.flush()
        key = ts_key.get(doc.get("source_type"))
        ts = _parse_ts(record.get(key)) if key else None
        if ts is not None:
            db.add(TimelineEvent(case_id=case.id,
                                 event_type=doc.get("source_type", "document"),
                                 timestamp=ts,
                                 description=f"{description} entered the case record.",
                                 evidence_id=evidence.id))
    db.flush()

    # contradictions from the engine
    for c in contradictions:
        db.add(Contradiction(case_id=case.id,
                             title=(c.get("title") or c.get("id") or "Contradiction")[:255],
                             description=c.get("explanation") or c.get("description"),
                             severity=str(c.get("severity", "MEDIUM")).upper(),
                             status="OPEN"))

    # hypotheses from high-severity findings
    sev_score = {"high": 0.8, "medium": 0.55, "low": 0.35}
    for f in findings:
        sev = f.get("severity", "medium")
        if sev != "high":
            continue
        db.add(Hypothesis(case_id=case.id,
                          title=(f.get("title") or "Finding")[:255],
                          description=f.get("explanation") or f.get("description"),
                          score=sev_score.get(sev, 0.5), status="OPEN"))

    # computed gaps — real, from the corpus
    cdr_times = sorted(t for t in (_parse_ts(r.get("start_time")) for r in _read_cdr_rows())
                       if t is not None)
    if len(cdr_times) >= 2:
        quiet, quiet_at = timedelta(0), None
        for prev, cur in zip(cdr_times, cdr_times[1:]):
            delta = cur - prev
            if delta > quiet:
                quiet, quiet_at = delta, prev
        if quiet > timedelta(hours=24):
            db.add(InvestigationGap(
                case_id=case.id,
                title=f"CDR quiet window: {int(quiet.total_seconds() // 3600)}h with no recorded calls",
                description=f"Longest gap between consecutive CDR records, starting "
                            f"{quiet_at.isoformat()}. Movement in this window is unexplained.",
                priority="HIGH", status="OPEN"))

    unchecked = [d["label"] for _, d in g.G.nodes(data=True)
                 if d.get("type") == "PERSON" and "prior_cases" not in d]
    if unchecked:
        db.add(InvestigationGap(
            case_id=case.id,
            title=f"{len(unchecked)} subjects not yet checked against criminal records",
            description="Subjects with no prior-record check on file: "
                        + ", ".join(sorted(unchecked)),
            priority="MEDIUM", status="OPEN"))

    db.add(Simulation(case_id=case.id, name="Baseline — all sources in play",
                      description="Reference state for the impact simulator: every "
                                  "source document active.",
                      created_by=investigator.id))

    db.flush()
    _assert_entity_ids_present(db, case.id, set(entity_rows.values()))
    logger.info("Meridian corpus staged: %d entities, %d relationships, "
                "%d documents, %d contradictions, %d findings.",
                len(entity_rows), g.G.number_of_edges(), len(doc_rows),
                len(contradictions), len([f for f in findings if f.get('severity') == 'high']))


def _read_cdr_rows() -> list[dict]:
    path = os.path.join(RAW, "cdr.csv")
    if not os.path.isfile(path):
        return []
    import csv
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _assert_entity_ids_present(db: Session, case_id: int, entities) -> None:
    """Fail loudly with context if an entity vanished after flush — an FK
    violation mid-seed used to leave partial state behind; with the atomic
    commit below the whole seed rolls back, and this message says why."""
    missing = [e.canonical_name for e in entities if db.get(Entity, e.id) is None]
    if missing:
        raise RuntimeError(f"seed inconsistency in case {case_id}: entities "
                           f"missing after flush: {missing[:5]}")


def seed_if_empty(db: Session) -> bool:
    """Idempotent entry point used at startup and by tests.

    The sentinel is the first spec case — not "any case" — because a
    partially interrupted seed must be able to finish on the next start.
    Every insert in the seed is individually idempotent.
    """
    if db.scalars(select(Case).where(Case.case_number == "CASE-2026-001")).first() is not None:
        return False
    try:
        users = seed_users(db)
        seed_spec_dataset(db, users)
        seed_meridian(db, users)
        db.commit()                      # single atomic commit for the whole seed
    except Exception:
        db.rollback()
        raise
    return True
