"""Investigation-gap detection (stage 4).

Deterministic detection of MISSING analytical coverage in the confirmed
data. Every result is a "potential investigation gap" — a description of
what the confirmed record does NOT cover, never an implication.

GAP types (documented rules):

EVIDENCE_GAP
    A confirmed entity with degree >= 3 (well connected in the confirmed
    graph) but zero directly-linked evidence records (the Stage 3
    candidate-provenance link).

RELATIONSHIP_GAP
    A pair of confirmed entities (both degree >= 2, person-pairs
    preferred) that have an indirect confirmed path of length 2-3 but NO
    confirmed direct relationship between them.

TIMELINE_GAP
    Reuses the timeline engine's gap rule (consecutive confirmed events
    > GAP_HOURS apart) so the gaps view is a single source of truth.

IDENTITY_GAP
    A confirmed person with no recorded aliases and no identifying
    metadata (fields beyond provenance flags such as "synthetic") that
    participates in >= 2 confirmed relationships — i.e. the confirmed
    record identifies them by name alone.

All rules are bounded and deterministic; insufficient data yields an
explicit empty state, never a manufactured gap.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..graph_intelligence.graph_builder import build_case_graph
from ..graph_intelligence.path_analysis import find_indirect_connections
from .data import Stage4Data

MIN_EVIDENCE_GAP_DEGREE = 3
MIN_REL_GAP_DEGREE = 2
MIN_IDENTITY_GAP_DEGREES = 2
PROVENANCE_FIELDS = {"synthetic"}   # data-provenance flags, not identifiers
MAX_GAPS_PER_TYPE = 5

METHOD = ("investigation-gap v1 (evidence: degree >= "
          f"{MIN_EVIDENCE_GAP_DEGREE} with 0 linked evidence; relationship: "
          f"indirect path 2-3, no direct link, degree >= "
          f"{MIN_REL_GAP_DEGREE}; identity: person, no aliases/identifying "
          f"metadata, degree >= {MIN_IDENTITY_GAP_DEGREES})")


@dataclass
class GapResult:
    gap_type: str
    title: str
    summary: str
    explanation: list[str]
    involved_entity_ids: list[int] = field(default_factory=list)
    supporting_relationship_ids: list[int] = field(default_factory=list)
    details: dict = field(default_factory=dict)


def detect_gaps(d: Stage4Data, timeline_gaps=None) -> list[GapResult]:
    """`timeline_gaps` = TIMELINE_GAP results from the timeline engine
    (reused verbatim so both views agree)."""
    out: list[GapResult] = []
    if not d.has_graph:
        return out

    graph = build_case_graph(d.entities, d.relationships, d.evidence_index,
                             d.accepted_candidates)

    # --------------------------------------------- EVIDENCE_GAP
    for n, info in sorted(graph.nodes.items(), key=lambda kv: kv[0]):
        degree = graph.graph.degree(n)
        if degree >= MIN_EVIDENCE_GAP_DEGREE and info.evidence_count == 0:
            out.append(GapResult(
                gap_type="EVIDENCE_GAP",
                title=f"Potential investigation gap: {info.display_name}",
                summary=(f"{info.display_name} ({info.entity_type}) has "
                         f"{degree} confirmed connections but no directly "
                         "linked evidence records."),
                explanation=[
                    f"Degree in the confirmed graph: {degree} "
                    f"(degree threshold {MIN_EVIDENCE_GAP_DEGREE}).",
                    "Directly linked evidence records (Stage 3 "
                    "candidate-provenance link): 0.",
                    "This is a coverage observation about the confirmed "
                    "record — it does not assert that evidence is "
                    "missing or that anything is wrong."],
                involved_entity_ids=list(info.entity_ids),
                details={"degree": degree,
                         "linked_evidence": info.evidence_count}))

    # ------------------------------------------ RELATIONSHIP_GAP
    hits = find_indirect_connections(graph, min_length=2, max_length=3,
                                     max_pairs=MAX_GAPS_PER_TYPE)
    for hit in hits:
        s, t, p = hit["source"], hit["target"], hit["path"]
        if graph.graph.degree(s.node_id) < MIN_REL_GAP_DEGREE \
                or graph.graph.degree(t.node_id) < MIN_REL_GAP_DEGREE:
            continue
        path_names = " → ".join(p.nodes)
        out.append(GapResult(
            gap_type="RELATIONSHIP_GAP",
            title=(f"Potential investigation gap: {s.display_name} ↔ "
                   f"{t.display_name} (no direct confirmed link)"),
            summary=(f"{s.display_name} and {t.display_name} are connected "
                     f"only indirectly ({p.path_length} hops) in the "
                     "confirmed graph — no confirmed direct relationship "
                     "exists between them."),
            explanation=[
                f"Indirect confirmed path: {path_names} "
                f"({', '.join(p.relationship_types)}).",
                "No confirmed direct relationship between the two in the "
                "case data.",
                "This describes the current confirmed record; it does not "
                "assert that a relationship is missing."],
            involved_entity_ids=sorted({s.entity_ids[0], t.entity_ids[0]}),
            supporting_relationship_ids=list(p.relationship_ids),
            details={"path": path_names, "path_length": p.path_length}))

    # --------------------------------------------- TIMELINE_GAP
    if timeline_gaps:
        for tg in timeline_gaps[:MAX_GAPS_PER_TYPE]:
            out.append(GapResult(
                gap_type="TIMELINE_GAP",
                title="Potential investigation gap (timeline)",
                summary=tg.summary,
                explanation=tg.explanation,
                involved_entity_ids=list(tg.entity_ids),
                details={"timeline_event_ids": list(tg.event_ids),
                         "interval_minutes": tg.interval_minutes}))

    # --------------------------------------------- IDENTITY_GAP
    for e in sorted(d.entities, key=lambda x: x.id):
        if e.entity_type != "person":
            continue
        degree = graph.graph.degree(f"e{e.id}")
        if degree < MIN_IDENTITY_GAP_DEGREES:
            continue
        meta = _entity_meta(d, e.id) or {}
        identifying = {k for k in meta.keys() if k.lower() not in PROVENANCE_FIELDS}
        aliases = (meta.get("aliases") or [])
        if not aliases and not identifying:
            out.append(GapResult(
                gap_type="IDENTITY_GAP",
                title=f"Potential investigation gap: {e.canonical_name}",
                summary=(f"{e.canonical_name} (person) is confirmed in "
                         f"{degree} relationships with no recorded aliases "
                         "or identifying attributes (phone, address, "
                         "date of birth, etc.)."),
                explanation=[
                    f"Participates in {degree} confirmed relationships "
                    f"(threshold {MIN_IDENTITY_GAP_DEGREES}).",
                    "Recorded aliases: none.",
                    "Identifying metadata fields: none (only data-"
                    "provenance flags).",
                    "The confirmed record identifies this person by name "
                    "alone — a potential investigation gap."],
                involved_entity_ids=[e.id],
                details={"degree": degree}))

    order = {"EVIDENCE_GAP": 0, "RELATIONSHIP_GAP": 1,
             "TIMELINE_GAP": 2, "IDENTITY_GAP": 3}
    out.sort(key=lambda g: (order[g.gap_type], g.title))
    # cap per type
    capped: list[GapResult] = []
    counts: dict[str, int] = {}
    for g in out:
        if counts.get(g.gap_type, 0) >= MAX_GAPS_PER_TYPE:
            continue
        counts[g.gap_type] = counts.get(g.gap_type, 0) + 1
        capped.append(g)
    return capped


def _entity_meta(d: Stage4Data, entity_id: int) -> dict | None:
    return d.entity_metadata.get(entity_id)
