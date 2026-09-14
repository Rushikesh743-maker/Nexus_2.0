"""Case-scoped context for the copilot.

Everything a copilot answer may mention must come from here. The context
is loaded from CONFIRMED case records only (the same guarantee the stage
3/4 engines have): candidates, suggestions and unaccepted extraction are
deliberately excluded, so the copilot cannot report something the
investigator has not confirmed.

Multilingual name resolution: an entity's canonical name and its aliases
are each run through the stage-5 normalizer (script-insensitive, so
``राजेश कुमार``, ``راجش کمار`` and ``Rajesh Kumar`` all resolve to the
same confirmed person).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Case, GraphFinding, InvestigationHypothesis
from ..graph_intelligence.graph_builder import build_case_graph
from ..language import normalize_for_match, transliterate
from ..investigation_intelligence.data import Stage4Data, load_stage4_data


def _norm(name: str) -> str:
    """Script-insensitive key for a surface form (stage-5 normalizer)."""
    if not name:
        return ""
    t = transliterate(name)
    return normalize_for_match(t) if t else normalize_for_match(name)


@dataclass
class CaseContext:
    case: Case
    data: Stage4Data
    graph: object                      # ConfirmedGraph (networkx-backed)
    findings: list = field(default_factory=list)     # GraphFinding rows
    hypotheses: list = field(default_factory=list)   # InvestigationHypothesis rows
    db: Session | None = None          # request session (impact simulator)

    # name/alias (normalized) -> entity id
    _name_index: dict[str, int] = field(default_factory=dict)
    # entity id -> [surface forms that matched (for interpretation)]
    _matched_forms: dict[int, list[str]] = field(default_factory=dict)

    def __post_init__(self):
        for e in self.data.entities:
            self._name_index[_norm(e.canonical_name)] = e.id
            for a in (self.data.entity_metadata.get(e.id, {}).get("aliases")
                      or []):
                if isinstance(a, str):
                    self._name_index.setdefault(_norm(a), e.id)

    # ------------------------------------------------------------ lookup
    def entity_id_for(self, surface: str) -> int | None:
        """Resolve a surface form (any script) to a confirmed entity id."""
        return self._name_index.get(_norm(surface))

    def resolve_all(self, surface: str) -> tuple[int | None, str | None]:
        """Return (entity_id, canonical_name) for a surface form, or
        (None, None) when the name is not a confirmed entity."""
        eid = self.entity_id_for(surface)
        if eid is None:
            return None, None
        ent = self.data.entities_by_id.get(eid)
        return eid, (ent.canonical_name if ent else None)

    def name_of(self, entity_id: int | None) -> str:
        if entity_id is None:
            return "unknown entity"
        ent = self.data.entities_by_id.get(entity_id)
        return ent.canonical_name if ent else f"entity {entity_id}"

    def location_name(self, location_id: int | None) -> str:
        if location_id is None:
            return "unknown location"
        loc = next((l for l in self.data.locations if l.id == location_id), None)
        return loc.name if loc else f"location {location_id}"

    # ------------------------------------------------------------ counts
    @property
    def counts(self) -> dict:
        by_type: dict[str, int] = {}
        for e in self.data.entities:
            by_type[e.entity_type] = by_type.get(e.entity_type, 0) + 1
        return {
            "entities": len(self.data.entities),
            "entities_by_type": dict(sorted(by_type.items())),
            "relationships": len(self.data.relationships),
            "evidence": len(self.data.evidence),
            "timeline_events": len(self.data.events),
            "locations": len(self.data.locations),
            "claims": len(self.data.claims),
            "findings": len(self.findings),
            "hypotheses": len(self.hypotheses),
        }


def load_case_context(db: Session, case: Case) -> CaseContext:
    data = load_stage4_data(db, case.id)
    graph = build_case_graph(data.entities, data.relationships,
                             data.evidence_index, data.accepted_candidates)
    findings = db.execute(select(GraphFinding).where(
        GraphFinding.case_id == case.id).order_by(GraphFinding.id)).scalars().all()
    hyps = db.execute(select(InvestigationHypothesis).where(
        InvestigationHypothesis.case_id == case.id
    ).order_by(InvestigationHypothesis.id)).scalars().all()
    return CaseContext(case=case, data=data, graph=graph,
                       findings=list(findings), hypotheses=list(hyps),
                       db=db)
