"""Phase 2 (work item D): immutable case snapshots.

A snapshot is a point-in-time capture of the case's CONFIRMED
intelligence state — entities, relationships, evidence, locations,
findings and hypotheses with their ids/names/types — plus the
``graph_version`` (confirmed-data hash) it was taken against.

The API is deliberately one-way: create, list, read, compare. There is
no update and no delete — version N stays version N, and "what changed
between N and N+1" is a pure diff of two immutable payloads (new /
removed / changed), never a re-derivation.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.errors import not_found
from ..models import (Case, CaseSnapshot, Entity, Evidence, GraphFinding,
                      InvestigationHypothesis, Location, Relationship)
from ..security.rbac import CurrentUser
from .auth_service import record_audit
from .case_analysis import _stage4_findings, _stage4_hypotheses, _stage4_state

FINDING_FIELDS = ("finding_type", "title", "status", "graph_version")
HYPOTHESIS_FIELDS = ("hypothesis_type", "title", "status")


def _payload(db: Session, case: Case) -> dict:
    """Compact capture: ids + names + types + counts, no raw document
    text. Deterministic order (by id) so comparisons are stable."""
    entities = db.scalars(select(Entity).where(
        Entity.case_id == case.id).order_by(Entity.id)).all()
    entity_rows = [{"id": r.id, "entity_type": r.entity_type,
                    "canonical_name": r.canonical_name}
                   for r in entities]
    names = {e.id: e.canonical_name for e in entities}
    rel_rows = db.scalars(select(Relationship).where(
        Relationship.case_id == case.id).order_by(Relationship.id)).all()
    relationships = [{"id": r.id, "relationship_type": r.relationship_type,
                      "source_id": r.source_entity_id,
                      "source_name": names.get(r.source_entity_id),
                      "target_id": r.target_entity_id,
                      "target_name": names.get(r.target_entity_id),
                      "confidence": r.confidence}
                     for r in rel_rows]
    evidence = [{"id": e.id, "evidence_type": e.evidence_type,
                 "description": e.description,
                 "document_id": e.document_id}
                for e in db.scalars(select(Evidence).where(
                    Evidence.case_id == case.id).order_by(Evidence.id)).all()]
    locations = [{"id": l.id, "name": l.name, "latitude": l.latitude,
                  "longitude": l.longitude}
                 for l in db.scalars(select(Location).where(
                     Location.case_id == case.id).order_by(Location.id)).all()]
    findings = [{"id": f.id, "finding_type": f.finding_type, "title": f.title,
                 "status": f.status, "graph_version": f.graph_version}
                for f in _stage4_findings(db, case.id)]
    hypotheses = [{"id": h.id, "hypothesis_type": h.hypothesis_type,
                   "title": h.title, "status": h.status}
                  for h in _stage4_hypotheses(db, case.id)]
    return {"entities": entity_rows, "relationships": relationships,
            "evidence": evidence, "locations": locations,
            "findings": findings, "hypotheses": hypotheses}


def create_snapshot(db: Session, case: Case, current: CurrentUser,
                    label: str | None = None) -> CaseSnapshot:
    """Capture version N+1. The capture is atomic with the sequence
    allocation (single session, single commit)."""
    state = _stage4_state(db, case)
    payload = _payload(db, case)
    sequence = db.scalar(select(func.max(CaseSnapshot.sequence)).where(
        CaseSnapshot.case_id == case.id)) or 0
    snap = CaseSnapshot(
        case_id=case.id,
        sequence=sequence + 1,
        label=(label or "").strip() or None,
        graph_version=state["graph_version"],
        payload=payload,
        entity_count=len(payload["entities"]),
        relationship_count=len(payload["relationships"]),
        evidence_count=len(payload["evidence"]),
        created_by=current.user.id,
    )
    db.add(snap)
    db.flush()
    record_audit(db, current, "CASE_SNAPSHOT_CREATED", "case_snapshot",
                 str(snap.id), {"case_id": case.id,
                                "sequence": snap.sequence,
                                "graph_version": snap.graph_version})
    db.commit()
    db.refresh(snap)
    return snap


def list_snapshots(db: Session, case: Case) -> list[CaseSnapshot]:
    return list(db.scalars(select(CaseSnapshot).where(
        CaseSnapshot.case_id == case.id
    ).order_by(CaseSnapshot.sequence)).all())


def get_snapshot(db: Session, case: Case, snapshot_id: int) -> CaseSnapshot:
    snap = db.get(CaseSnapshot, snapshot_id)
    if snap is None or snap.case_id != case.id:
        not_found("SNAPSHOT_NOT_FOUND",
                  f"Snapshot {snapshot_id} not found in case {case.id}.")
    return snap


def _by_id(rows: list[dict], key: str = "id") -> dict:
    return {r[key]: r for r in rows}


def _diff_section(a: list[dict], b: list[dict],
                  fields: tuple[str, ...] | None = None) -> dict:
    """added / removed / changed between two payload sections.

    Identity is the row ``id``. ``changed`` lists the exact fields whose
    values moved (only when ``fields`` is given — findings and hypotheses
    carry mutable review state, entities/relationships/evidence do not).
    """
    a_by, b_by = _by_id(a), _by_id(b)
    added = [b_by[i] for i in sorted(set(b_by) - set(a_by))]
    removed = [a_by[i] for i in sorted(set(a_by) - set(b_by))]
    changed = []
    if fields:
        for i in sorted(set(a_by) & set(b_by)):
            diffs = {f: {"from": a_by[i].get(f), "to": b_by[i].get(f)}
                     for f in fields
                     if a_by[i].get(f) != b_by[i].get(f)}
            if diffs:
                changed.append({"id": i, "fields": diffs})
    return {"added": added, "removed": removed, "changed": changed}


def compare_snapshots(db: Session, case: Case, from_seq: int,
                      to_seq: int) -> dict:
    """Pure diff of two immutable payloads: what changed N -> M."""
    a = next((s for s in list_snapshots(db, case)
              if s.sequence == from_seq), None)
    b = next((s for s in list_snapshots(db, case)
              if s.sequence == to_seq), None)
    if a is None or b is None:
        have = [s.sequence for s in list_snapshots(db, case)]
        not_found("SNAPSHOT_COMPARE_INVALID",
                  f"Cannot compare versions {from_seq} and {to_seq}; this "
                  f"case has snapshots {have}.")
    pa, pb = a.payload or {}, b.payload or {}
    out = {
        "from": {"sequence": a.sequence, "label": a.label,
                 "graph_version": a.graph_version, "created_at":
                 a.created_at.isoformat() if a.created_at else None},
        "to": {"sequence": b.sequence, "label": b.label,
               "graph_version": b.graph_version, "created_at":
               b.created_at.isoformat() if b.created_at else None},
        "entities": _diff_section(pa.get("entities", []),
                                  pb.get("entities", [])),
        "locations": _diff_section(pa.get("locations", []),
                                   pb.get("locations", [])),
        "evidence": _diff_section(pa.get("evidence", []),
                                  pb.get("evidence", [])),
        "relationships": _diff_section(pa.get("relationships", []),
                                       pb.get("relationships", [])),
        "findings": _diff_section(pa.get("findings", []),
                                  pb.get("findings", []),
                                  fields=FINDING_FIELDS),
        "hypotheses": _diff_section(pa.get("hypotheses", []),
                                    pb.get("hypotheses", []),
                                    fields=HYPOTHESIS_FIELDS),
    }
    summary = {}
    for section in ("entities", "relationships", "evidence", "findings",
                    "hypotheses", "locations"):
        summary[f"{section}_added"] = len(out[section]["added"])
        summary[f"{section}_removed"] = len(out[section]["removed"])
        summary[f"{section}_changed"] = len(out[section]["changed"])
    out["summary"] = summary
    return out
