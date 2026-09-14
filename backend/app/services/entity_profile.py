"""Phase 2 (work item C): the per-entity intelligence profile.

``GET /cases/{id}/entities/{eid}`` resolves ONE confirmed entity to
everything the case knows about it — connections (with provenance back to
source document/snippet), evidence + structured claims, timeline events,
locations (coordinates only from confirmed Location rows, never guessed),
findings involving it, and computed metrics (degree, distinct documents,
first/last seen, time span). Confirmed data only; the case's analysis
freshness (state + graph_version) travels with the profile so the UI can
mark it stale (work item E).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.errors import ApiError, not_found
from .entity_resolution import normalize_multilingual
from ..models import (Case, Document, Entity, EntityCandidate, Evidence,
                      EvidenceClaim, GraphFinding, Location, Relationship,
                      TimelineEvent)
from .case_analysis import _stage4_state

_UTC = timezone.utc
_MIN_UTC = datetime.min.replace(tzinfo=_UTC)


def _ts_key(t: datetime | None):
    """Chronological sort key that never mixes naive/aware datetimes."""
    if t is None:
        return (True, _MIN_UTC)
    return (False, t.astimezone(_UTC))


def _require_entity(db: Session, case_id: int, entity_id: int) -> Entity:
    entity = db.get(Entity, entity_id)
    if entity is not None:
        if entity.case_id == case_id:
            return entity
        # A confirmed entity from another case is simply not in this case —
        # case-scoped isolation (do NOT fall through to the candidate check,
        # which shares the id space and would misreport a 400).
        not_found("ENTITY_NOT_FOUND", f"Entity {entity_id} not found in this case.")
    cand = db.get(EntityCandidate, entity_id)
    if cand is not None and cand.case_id == case_id:
        raise ApiError("ENTITY_NOT_CONFIRMED",
                       f"Entity id {entity_id} is an extraction candidate "
                       f"(status {cand.status}), not a confirmed entity. "
                       "The profile uses confirmed entities only.", 400)
    not_found("ENTITY_NOT_FOUND", f"Entity {entity_id} not found in this case.")


def _location_rows(db: Session, case_id: int) -> dict[str, Location]:
    """normalized name -> Location row (the same documented join rule the
    geospatial engine uses — coordinates are only ever read from rows)."""
    out: dict[str, Location] = {}
    for loc in db.scalars(select(Location).where(
            Location.case_id == case_id)).all():
        key = normalize_multilingual(loc.name or "")
        if key:
            out.setdefault(key, loc)
    return out


def _doc_names(db: Session, doc_ids: list[int]) -> dict[int, str]:
    if not doc_ids:
        return {}
    rows = db.scalars(select(Document).where(Document.id.in_(doc_ids))).all()
    return {d.id: d.filename for d in rows}


def _ent_ref(e: Entity) -> dict:
    return {"id": e.id, "entity_type": e.entity_type,
            "canonical_name": e.canonical_name}


def entity_profile(db: Session, case: Case, entity_id: int) -> dict:
    entity = _require_entity(db, case.id, entity_id)
    state = _stage4_state(db, case)
    version = state["graph_version"]

    # ---------------- connections (confirmed edges only) ----------------
    rels = db.scalars(select(Relationship).where(
        Relationship.case_id == case.id,
        (Relationship.source_entity_id == entity.id)
        | (Relationship.target_entity_id == entity.id))).all()
    peer_ids = ({r.source_entity_id for r in rels}
                | {r.target_entity_id for r in rels}) - {entity.id}
    peers = {e.id: e for e in db.scalars(select(Entity).where(
        Entity.id.in_(sorted(peer_ids)))).all()} if peer_ids else {}

    doc_ids: set[int] = set()
    ev_ids: set[int] = set()
    connections = []
    for r in rels:
        outgoing = r.source_entity_id == entity.id
        peer_id = r.target_entity_id if outgoing else r.source_entity_id
        peer = peers.get(peer_id)
        meta = r.meta or {}
        prov_doc = meta.get("source_document_id")
        if prov_doc:
            doc_ids.add(prov_doc)
        ev = meta.get("source_evidence_id")
        if ev:
            ev_ids.add(ev)
        connections.append({
            "relationship_id": r.id,
            "relationship_type": r.relationship_type,
            "direction": "outgoing" if outgoing else "incoming",
            "confidence": r.confidence,
            "peer": _ent_ref(peer) if peer else None,
            "provenance": {
                "document_id": prov_doc,
                "location": meta.get("source_location"),
                "snippet": meta.get("source_snippet"),
                "extraction_method": meta.get("extraction_method"),
                "evidence_id": ev,
            },
        })
    connections.sort(key=lambda c: (c["direction"], c["relationship_type"],
                                    c["relationship_id"]))

    # ---------------- claims touching this entity -------------------------
    claims = db.scalars(select(EvidenceClaim).where(
        EvidenceClaim.case_id == case.id,
        EvidenceClaim.subject_entity_id == entity.id)).all()
    touching = db.scalars(select(EvidenceClaim).where(
        EvidenceClaim.case_id == case.id,
        (EvidenceClaim.subject_entity_id == entity.id)
        | (EvidenceClaim.object_entity_id == entity.id))).all()
    for c in touching:
        ev_ids.add(c.evidence_id)

    claim_obj_ids = {c.object_entity_id for c in claims if c.object_entity_id}
    claim_objs = {e.id: e for e in db.scalars(select(Entity).where(
        Entity.id.in_(sorted(claim_obj_ids)))).all()} if claim_obj_ids else {}

    # ---------------- evidence rows that back this entity -----------------
    events = db.scalars(select(TimelineEvent).where(
        TimelineEvent.case_id == case.id,
        TimelineEvent.entity_id == entity.id)).all()
    for ev in events:
        if ev.evidence_id:
            ev_ids.add(ev.evidence_id)

    evidence_rows = {e.id: e for e in db.scalars(select(Evidence).where(
        Evidence.id.in_(sorted(ev_ids)))).all()} if ev_ids else {}
    for e in evidence_rows.values():
        if e.document_id:
            doc_ids.add(e.document_id)
    doc_names = _doc_names(db, sorted(doc_ids))

    claims_by_ev: dict[int, list[EvidenceClaim]] = {}
    for c in touching:
        claims_by_ev.setdefault(c.evidence_id, []).append(c)

    # ---------------- locations -------------------------------------------
    loc_rows = _location_rows(db, case.id)
    locations: dict[str, dict] = {}

    def _note_location(name: str | None) -> None:
        if not name:
            return
        key = normalize_multilingual(name)
        if not key:
            return
        row = loc_rows.get(key)
        entry = locations.setdefault(key, {
            "name": row.name if row else name,
            "latitude": row.latitude if row else None,
            "longitude": row.longitude if row else None,
        })
        if row:  # a confirmed Location row wins over raw claim text
            entry["name"] = row.name

    if entity.entity_type == "location":
        _note_location(entity.canonical_name)
    for c in touching:
        if c.location_id:
            row = next((l for l in loc_rows.values()
                        if l.id == c.location_id), None)
            _note_location(row.name if row else None)
        elif c.predicate in ("was_at", "present_at", "located_at"):
            obj = claim_objs.get(c.object_entity_id)
            _note_location(obj.canonical_name if obj else c.object_value)
    for c in claims:
        if c.location_id:
            row = next((l for l in loc_rows.values()
                        if l.id == c.location_id), None)
            _note_location(row.name if row else None)
    for r in rels:
        if r.relationship_type == "LOCATED_AT":
            peer_id = r.target_entity_id if r.source_entity_id == entity.id \
                else r.source_entity_id
            peer = peers.get(peer_id)
            if peer is not None and peer.entity_type == "location":
                _note_location(peer.canonical_name)

    # ---------------- timeline events + time span -------------------------
    events_out = []
    stamps: list[datetime] = []
    for c in claims:
        if c.event_time:
            stamps.append(c.event_time)
    for ev in sorted(events, key=lambda e: _ts_key(e.timestamp) + (e.id,)):
        if ev.timestamp:
            stamps.append(ev.timestamp)
        loc = None
        if ev.location_id:
            row = next((l for l in loc_rows.values()
                        if l.id == ev.location_id), None)
            loc = row.name if row else None
            _note_location(loc)
        events_out.append({
            "id": ev.id,
            "event_type": ev.event_type,
            "timestamp": ev.timestamp.isoformat() if ev.timestamp else None,
            "location": loc,
            "description": ev.description,
            "evidence_id": ev.evidence_id,
        })

    def _claim_out(c: EvidenceClaim) -> dict:
        obj = claim_objs.get(c.object_entity_id)
        loc = None
        if c.location_id:
            row = next((l for l in loc_rows.values()
                        if l.id == c.location_id), None)
            loc = row.name if row else None
        return {
            "id": c.id,
            "predicate": c.predicate,
            "object_value": c.object_value,
            "object_entity": _ent_ref(obj) if obj else None,
            "event_time": c.event_time.isoformat() if c.event_time else None,
            "original_text": c.original_text,
            "language": c.language,
            "location": loc,
        }

    claims_out = [_claim_out(c) for c in
                  sorted(claims, key=lambda c: _ts_key(c.event_time) + (c.id,))]

    # ---------------- findings involving this entity ----------------------
    findings_rows = db.scalars(select(GraphFinding).where(
        GraphFinding.case_id == case.id)).all()
    findings_out = [{
        "id": f.id,
        "finding_type": f.finding_type,
        "title": f.title,
        "graph_version": f.graph_version,
        "stale": f.graph_version != version,
        "status": f.status,
    } for f in findings_rows
        if entity.id in (f.involved_entity_ids or [])]
    findings_out.sort(key=lambda f: (f["stale"], f["id"]))

    # ---------------- metrics ----------------------------------------------
    first_seen = min(stamps) if stamps else None
    last_seen = max(stamps) if stamps else None
    span = (round((last_seen - first_seen).total_seconds() / 3600.0, 2)
            if first_seen and last_seen else None)

    return {
        "entity": {"id": entity.id, "case_id": entity.case_id,
                   "entity_type": entity.entity_type,
                   "canonical_name": entity.canonical_name,
                   "metadata": entity.meta,
                   "created_at": entity.created_at},
        "connections": connections,
        "evidence": [
            {"id": e.id, "evidence_type": e.evidence_type,
             "description": e.description, "confidence": e.confidence,
             "document_id": e.document_id,
             "document": doc_names.get(e.document_id)
             if e.document_id else None,
             "claims": [_claim_out(c) for c in
                        sorted(claims_by_ev.get(e.id, []),
                               key=lambda c: _ts_key(c.event_time) + (c.id,))]
            } for e in sorted(evidence_rows.values(), key=lambda e: e.id)],
        "claims": claims_out,
        "events": events_out,
        "locations": [locations[k] for k in
                      sorted(locations, key=lambda k: locations[k]["name"])],
        "findings": findings_out,
        "metrics": {"degree": len(rels),
                    "documents": len(doc_names),
                    "first_seen": first_seen.isoformat()
                    if first_seen else None,
                    "last_seen": last_seen.isoformat() if last_seen else None,
                    "time_span_hours": span},
        "analysis": {"state": state["state"],
                     "graph_version": version,
                     "reason": state["reason"],
                     "analyzed": state["analyzed"]},
    }
