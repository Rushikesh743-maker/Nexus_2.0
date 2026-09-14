"""Stage 4 data loading + versioning (confirmed data only).

Everything the Stage 4 engines see comes from confirmed platform tables:
`entity`, `relationship`, `evidence`, `timeline_event`, `location`.
Extraction candidates, rejected/pending review items and unresolved match
suggestions are in other tables and never reach these loaders.

**Stage 4 version hash** (documented exactly, per spec §8):
a SHA-256 (16-char prefix) over the case's confirmed

* entities: id, entity_type, normalized name
* relationships: id, relationship_type, source id, target id
* evidence: id, evidence_type, document id, source_reference
* timeline events: id, event_type, timestamp, entity id, location id
* locations: id, name, latitude, longitude
* claims (stage 5): id, subject id, predicate, object id, normalized
  value, event time, location id

Any change to any of those confirmed records changes the hash; findings
and generated hypotheses bound to an older hash are flagged stale (kept,
never deleted) and re-analysis of unchanged data is idempotent.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import (Entity, Evidence, EvidenceClaim, Location,
                       Relationship, TimelineEvent)
from ..graph_intelligence.graph_builder import (EntityRecord,
                                                RelationshipRecord,
                                                normalize_name)
from ..graph_intelligence.finding_service import (
    _candidate_id_from_meta, load_accepted_candidates, load_evidence_index)


@dataclass(frozen=True)
class EvidenceRecord:
    id: int
    case_id: int
    evidence_type: str
    document_id: int | None
    source_reference: str | None


@dataclass(frozen=True)
class EventRecord:
    id: int
    case_id: int
    event_type: str
    timestamp: datetime | None
    description: str | None
    entity_id: int | None
    location_id: int | None
    evidence_id: int | None


@dataclass(frozen=True)
class LocationRecord:
    id: int
    case_id: int
    name: str
    latitude: float | None
    longitude: float | None


@dataclass(frozen=True)
class ClaimRecord:
    """A confirmed structured claim (stage 5) — the only legitimate input
    to the EVIDENCE_CONTRADICTION rule. Loaded from the `evidence_claim`
    table (confirmed-only by construction: rows exist only after their
    subject candidate was accepted)."""
    id: int
    case_id: int
    evidence_id: int
    subject_entity_id: int | None
    predicate: str
    object_entity_id: int | None
    object_value: str | None
    event_time: datetime | None
    location_id: int | None
    normalized_value: str | None


@dataclass
class Stage4Data:
    """All confirmed data for one case, ready for the pure engines."""
    case_id: int
    entities: list[EntityRecord] = field(default_factory=list)
    relationships: list[RelationshipRecord] = field(default_factory=list)
    evidence: list[EvidenceRecord] = field(default_factory=list)
    events: list[EventRecord] = field(default_factory=list)
    locations: list[LocationRecord] = field(default_factory=list)
    # stage 5: confirmed structured claims (evidence_claim table)
    claims: list[ClaimRecord] = field(default_factory=list)
    # source_reference -> [evidence ids]  (the candidate:{id} link index)
    evidence_index: dict[str, list[int]] = field(default_factory=dict)
    # entity_id -> [accepted entity-candidate ids]
    accepted_candidates: dict[int, list[int]] = field(default_factory=dict)
    # name -> location record (case-scoped; the location-entity join rule)
    locations_by_name: dict[str, LocationRecord] = field(default_factory=dict)
    # entity_id -> entity record
    entities_by_id: dict[int, EntityRecord] = field(default_factory=dict)
    # entity_id -> recorded metadata dict (identity-gap analysis)
    entity_metadata: dict[int, dict] = field(default_factory=dict)
    # relationship ids per (source, target) pair, for relationship rules
    rels_by_pair: dict[tuple[int, int], list[int]] = field(default_factory=dict)

    @property
    def has_graph(self) -> bool:
        return bool(self.entities and self.relationships)

    @property
    def dated_events(self) -> list[EventRecord]:
        return [e for e in self.events if e.timestamp is not None]


def load_stage4_data(db: Session, case_id: int) -> Stage4Data:
    ents = db.execute(select(Entity).where(Entity.case_id == case_id)
                      .order_by(Entity.id)).scalars().all()
    rels = db.execute(select(Relationship).where(Relationship.case_id == case_id)
                      .order_by(Relationship.id)).scalars().all()
    evs = db.execute(select(Evidence).where(Evidence.case_id == case_id)
                     .order_by(Evidence.id)).scalars().all()
    evts = db.execute(select(TimelineEvent).where(TimelineEvent.case_id == case_id)
                      .order_by(TimelineEvent.id)).scalars().all()
    locs = db.execute(select(Location).where(Location.case_id == case_id)
                      .order_by(Location.id)).scalars().all()
    claims = db.execute(select(EvidenceClaim).where(
        EvidenceClaim.case_id == case_id).order_by(EvidenceClaim.id)).scalars().all()

    d = Stage4Data(case_id=case_id)
    d.entities = [EntityRecord(e.id, e.case_id, e.entity_type, e.canonical_name)
                  for e in ents]
    d.relationships = [RelationshipRecord(r.id, r.case_id, r.source_entity_id,
                                          r.target_entity_id, r.relationship_type,
                                          _candidate_id_from_meta(r.meta))
                       for r in rels]
    d.evidence = [EvidenceRecord(v.id, v.case_id, v.evidence_type,
                                 v.document_id, v.source_reference)
                  for v in evs]
    d.events = [EventRecord(t.id, t.case_id, t.event_type, t.timestamp,
                            t.description, t.entity_id, t.location_id,
                            t.evidence_id) for t in evts]
    d.locations = [LocationRecord(l.id, l.case_id, l.name, l.latitude, l.longitude)
                   for l in locs]
    d.claims = [ClaimRecord(c.id, c.case_id, c.evidence_id, c.subject_entity_id,
                            c.predicate, c.object_entity_id, c.object_value,
                            c.event_time, c.location_id, c.normalized_value)
                for c in claims]
    d.evidence_index = load_evidence_index(db, case_ids=[case_id])
    d.accepted_candidates = load_accepted_candidates(db, case_ids=[case_id])
    d.locations_by_name = {normalize_name(l.name): l for l in d.locations}
    d.entities_by_id = {e.id: e for e in d.entities}
    d.entity_metadata = {e.id: (e.meta or {}) for e in ents}
    for r in d.relationships:
        d.rels_by_pair.setdefault((r.source_entity_id, r.target_entity_id),
                                  []).append(r.id)
    return d


def compute_stage4_version(d: Stage4Data) -> str:
    """The documented Stage 4 snapshot hash (see module docstring)."""
    h = hashlib.sha256()
    for e in sorted(d.entities, key=lambda x: x.id):
        h.update(f"e{e.id}|{e.entity_type}|{normalize_name(e.canonical_name)}\n".encode())
    for r in sorted(d.relationships, key=lambda x: x.id):
        h.update(f"r{r.id}|{r.relationship_type}|{r.source_entity_id}|{r.target_entity_id}\n".encode())
    for v in sorted(d.evidence, key=lambda x: x.id):
        h.update(f"ev{v.id}|{v.evidence_type}|{v.document_id}|{v.source_reference}\n".encode())
    for t in sorted(d.events, key=lambda x: x.id):
        ts = t.timestamp.isoformat() if t.timestamp else ""
        h.update(f"t{t.id}|{t.event_type}|{ts}|{t.entity_id}|{t.location_id}\n".encode())
    for l in sorted(d.locations, key=lambda x: x.id):
        h.update(f"l{l.id}|{normalize_name(l.name)}|{l.latitude}|{l.longitude}\n".encode())
    # stage 5: confirmed claims are part of the snapshot (a new/changed
    # claim must flag the analysis stale).
    for c in sorted(d.claims, key=lambda x: x.id):
        ts = c.event_time.isoformat() if c.event_time else ""
        h.update(f"c{c.id}|{c.subject_entity_id}|{c.predicate}|"
                 f"{c.object_entity_id}|{normalize_name(c.normalized_value or '')}"
                 f"|{ts}|{c.location_id}\n".encode())
    return h.hexdigest()[:16]
