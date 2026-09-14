"""Competing-hypothesis engine (stage 4).

NEXUS never claims a hypothesis is "true". It generates COMPETING
explanations of the confirmed data and scores each with a transparent,
deterministic formula whose every component is visible in the API and UI.

**Score (documented, tested):**

    score = 0.30 * evidence
          + 0.20 * relationships
          + 0.20 * consistency
          + 0.15 * provenance
          + 0.15 * connectivity          (clamped to 0..1)

    evidence      = min(1, n_supporting_evidence / 4)
    relationships = min(1, n_supporting_relationships / 3)
    consistency   = 1 - min(1, n_contradicting_signals / 2)
    provenance    = (supporting evidence with document provenance)
                    / max(1, n_supporting_evidence)
    connectivity  = min(1, n_involved_entities / 5)

`n_contradicting_signals` = contradicting evidence records + detected
contradictions involving the hypothesis. The score represents ANALYTICAL
SUPPORT, not probability and not proof. Bands: LOW < 0.34 <= MEDIUM
< 0.67 <= HIGH.

**Generation (deterministic, bounded):**

1. Per detected contradiction (max 3, 2 hypotheses each):
   - "the conservative analysis assumptions explain the apparent
     conflict" — consistency = margin (recorded interval / minimum
     travel time; 0 for identical-timestamp conflicts);
   - "at least one involved record is inaccurate or misattributed" —
     consistency = 1 - margin.
   For relationship contradictions both sides start at the neutral 0.5
   margin (no physical model applies); evidence decides.
2. For the first RELATIONSHIP_GAP person-pair (indirect confirmed path,
   no direct link):
   - "the two are connected through the recorded confirmed links"
     (path relationships as support);
   - "the connection runs through the intermediate entity";
   - and, only when the two scores differ by < 0.15, an explicit
     "insufficient to distinguish" hypothesis.

Investigator-created hypotheses (POST) are scored with the same formula
over the records they reference plus the data-backed records of their
involved entities.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .data import Stage4Data
from .contradiction_engine import ContradictionResult

MAX_GENERATED_HYPOTHESES = 12
MAX_CONTRADICTIONS_FOR_HYPO = 3
SCORE_GAP_THRESHOLD = 0.15

WEIGHTS = {"evidence": 0.30, "relationships": 0.20, "consistency": 0.20,
           "provenance": 0.15, "connectivity": 0.15}
METHOD = ("hypothesis-score v1 (0.30*evidence + 0.20*relationships + "
          "0.20*consistency + 0.15*provenance + 0.15*connectivity; each "
          "factor min(1, n/cap), consistency = 1 - min(1, conflicts/2))")


@dataclass
class HypothesisSpec:
    title: str
    description: str
    hypothesis_type: str            # GENERATED_CONTRADICTION | GENERATED_STRUCTURE | INVESTIGATOR
    involved_entity_ids: list[int] = field(default_factory=list)
    supporting_relationship_ids: list[int] = field(default_factory=list)
    supporting_evidence_ids: list[int] = field(default_factory=list)
    contradicting_evidence_ids: list[int] = field(default_factory=list)
    supporting_finding_ids: list[int] = field(default_factory=list)
    contradiction_ids: list[int] = field(default_factory=list)
    # analysis-specific consistency override (e.g. the margin for a
    # speed-assumption explanation); None => formula default
    consistency_override: float | None = None
    explanation_prefix: str = ""


@dataclass
class ScoredHypothesis:
    spec: HypothesisSpec
    analytical_score: float
    confidence_band: str
    score_components: dict
    explanation: list[str]


def band_for(score: float) -> str:
    if score < 0.34:
        return "LOW"
    if score < 0.67:
        return "MEDIUM"
    return "HIGH"


def _provenance_ratio(d: Stage4Data, evidence_ids: list[int]) -> float:
    if not evidence_ids:
        return 0.0
    with_doc = sum(1 for v in d.evidence if v.id in set(evidence_ids)
                   and v.document_id is not None)
    return with_doc / len(evidence_ids)


def score_spec(d: Stage4Data, spec: HypothesisSpec) -> ScoredHypothesis:
    n_ev = len(spec.supporting_evidence_ids)
    n_con_ev = len(spec.contradicting_evidence_ids)
    n_rel = len(spec.supporting_relationship_ids)
    conflicts = n_con_ev + len(spec.contradiction_ids)
    connected = len(spec.involved_entity_ids)

    evidence = min(1.0, n_ev / 4)
    relationships = min(1.0, n_rel / 3)
    consistency = (spec.consistency_override
                   if spec.consistency_override is not None
                   else 1.0 - min(1.0, conflicts / 2))
    provenance = _provenance_ratio(d, spec.supporting_evidence_ids)
    connectivity = min(1.0, connected / 5)

    score = (WEIGHTS["evidence"] * evidence
             + WEIGHTS["relationships"] * relationships
             + WEIGHTS["consistency"] * consistency
             + WEIGHTS["provenance"] * provenance
             + WEIGHTS["connectivity"] * connectivity)
    score = round(max(0.0, min(1.0, score)), 3)
    band = band_for(score)

    signals: list[str] = []
    if n_ev:
        signals.append(f"+ {n_ev} directly linked evidence record(s)")
    if n_rel:
        signals.append(f"+ {n_rel} confirmed relationship(s)")
    if conflicts == 0 and (n_ev or n_rel):
        signals.append("+ timeline-consistent records (no detected conflicts)")
    if n_con_ev:
        signals.append(f"- {n_con_ev} contradicting evidence record(s)")
    if spec.contradiction_ids:
        signals.append(f"- {len(spec.contradiction_ids)} detected contradiction(s)")
    if spec.consistency_override is not None:
        signals.append(f"~ assumption-consistency factor {spec.consistency_override:.2f}")
    if not signals:
        signals.append("+ no measured signals (insufficient linked records)")

    explanation = [
        f"Analytical score: {score:.2f} (band {band}).",
        *signals,
        "This score represents analytical support, not probability or "
        "proof."]
    if spec.explanation_prefix:
        explanation.insert(1, spec.explanation_prefix)

    components = {
        "supporting_evidence": n_ev,
        "contradicting_evidence": n_con_ev,
        "supporting_relationships": n_rel,
        "contradicting_signals": conflicts,
        "involved_entities": connected,
        "evidence_with_document_provenance": round(provenance, 3),
        "factor_values": {"evidence": round(evidence, 3),
                          "relationships": round(relationships, 3),
                          "consistency": round(consistency, 3),
                          "provenance": round(provenance, 3),
                          "connectivity": round(connectivity, 3)},
    }
    return ScoredHypothesis(spec=spec, analytical_score=score,
                            confidence_band=band,
                            score_components=components,
                            explanation=explanation)


def generate_hypotheses(d: Stage4Data,
                        contradictions: list[ContradictionResult]) -> list[HypothesisSpec]:
    out: list[HypothesisSpec] = []
    name_of = {e.id: e.canonical_name for e in d.entities}

    # ---------------------------------- 1) contradiction explanations
    for c in contradictions[:MAX_CONTRADICTIONS_FOR_HYPO]:
        ev_ids = list(c.supporting_evidence_ids)
        if c.contradiction_type in ("TIMELINE_CONTRADICTION",
                                    "LOCATION_CONTRADICTION"):
            margin = c.details.get("margin", 0.0)
            if c.contradiction_type == "LOCATION_CONTRADICTION":
                margin = 0.0
            ev_a, ev_b = c.details["events"]["a"], c.details["events"]["b"]
            loc_a, loc_b = c.details["locations"]["a"], c.details["locations"]["b"]
            out.append(HypothesisSpec(
                title="Explanations for the apparent conflict (assumptions)",
                description=(f"Regarding events {ev_a}/{ev_b} at locations "
                             f"{loc_a}/{loc_b}: the apparent conflict is "
                             "explained by the conservative assumptions "
                             "used in the analysis (e.g. the upper "
                             "movement-speed assumption or timestamp "
                             "precision) rather than by a record error."),
                hypothesis_type="GENERATED_CONTRADICTION",
                involved_entity_ids=list(c.involved_entity_ids),
                supporting_evidence_ids=ev_ids,
                contradiction_ids=[],   # finding ids assigned post-persist
                consistency_override=round(margin, 3),
                explanation_prefix=(
                    "Detected contradiction: " + c.title + ".")))
            out.append(HypothesisSpec(
                title="Explanations for the apparent conflict (record accuracy)",
                description=(f"Regarding events {ev_a}/{ev_b}: at least one "
                             "of the involved confirmed records may be "
                             "inaccurate or misattributed, and the "
                             "conflict reflects a record error rather "
                             "than assumptions."),
                hypothesis_type="GENERATED_CONTRADICTION",
                involved_entity_ids=list(c.involved_entity_ids),
                supporting_evidence_ids=ev_ids,
                consistency_override=round(1.0 - margin, 3),
                explanation_prefix=(
                    "Detected contradiction: " + c.title + ".")))
        elif c.contradiction_type == "EVIDENCE_CONTRADICTION":
            # stage 5 R4 — structured-claim conflict (spatial or value)
            ev = c.details.get("evidence", {})
            ev_a, ev_b = ev.get("a"), ev.get("b")
            margin = c.details.get("margin", 0.5)
            subj = name_of.get(c.involved_entity_ids[0], "?") \
                if c.involved_entity_ids else "?"
            out.append(HypothesisSpec(
                title="Explanations for the apparent evidence conflict (attribution)",
                description=(f"Regarding the {subj} claims tied to evidence "
                             f"{ev_a}/{ev_b}: the apparent conflict is "
                             "explained by a misattribution — the two "
                             "records refer to different people who share a "
                             "name, or one claim was linked to the wrong "
                             "confirmed entity — rather than by a record "
                             "error."),
                hypothesis_type="GENERATED_CONTRADICTION",
                involved_entity_ids=list(c.involved_entity_ids),
                supporting_evidence_ids=list(c.supporting_evidence_ids),
                contradiction_ids=[],   # finding ids assigned post-persist
                consistency_override=round(margin, 3),
                explanation_prefix=(
                    "Detected contradiction: " + c.title + ".")))
            out.append(HypothesisSpec(
                title="Explanations for the apparent evidence conflict (record accuracy)",
                description=(f"Regarding the {subj} claims tied to evidence "
                             f"{ev_a}/{ev_b}: at least one of the confirmed "
                             "claims may be inaccurate (wrong time, place, or "
                             "object), and the conflict reflects a record "
                             "error rather than an attribution error."),
                hypothesis_type="GENERATED_CONTRADICTION",
                involved_entity_ids=list(c.involved_entity_ids),
                supporting_evidence_ids=list(c.supporting_evidence_ids),
                contradiction_ids=[],   # finding ids assigned post-persist
                consistency_override=round(1.0 - margin, 3),
                explanation_prefix=(
                    "Detected contradiction: " + c.title + ".")))
        elif c.contradiction_type == "RELATIONSHIP_CONTRADICTION":
            ents = name_of.get(c.involved_entity_ids[0], "?") if c.involved_entity_ids else "?"
            other = name_of.get(c.involved_entity_ids[1], "?") if len(c.involved_entity_ids) > 1 else "?"
            out.append(HypothesisSpec(
                title=f"Mutual-ownership records: data-entry duplication ({ents}/{other})",
                description=(f"The mutual OWNS records between {ents} and "
                             f"{other} most likely reflect a data-entry "
                             "duplication rather than a genuine dual "
                             "ownership."),
                hypothesis_type="GENERATED_CONTRADICTION",
                involved_entity_ids=list(c.involved_entity_ids),
                supporting_relationship_ids=list(c.involved_relationship_ids),
                consistency_override=0.5,
                explanation_prefix="Detected contradiction: " + c.title + "."))
            out.append(HypothesisSpec(
                title=f"Mutual-ownership records: genuine dual recording ({ents}/{other})",
                description=(f"The mutual OWNS records between {ents} and "
                             f"{other} may both be genuine and require "
                             "source-document review."),
                hypothesis_type="GENERATED_CONTRADICTION",
                involved_entity_ids=list(c.involved_entity_ids),
                supporting_relationship_ids=list(c.involved_relationship_ids),
                consistency_override=0.5,
                explanation_prefix="Detected contradiction: " + c.title + "."))

    # ---------------------------------- 2) structural focal pair
    # first person-pair with an indirect path 2-3 and no direct link
    from ..graph_intelligence.graph_builder import build_case_graph
    from ..graph_intelligence.path_analysis import find_indirect_connections
    graph = build_case_graph(d.entities, d.relationships, d.evidence_index,
                             d.accepted_candidates)
    pair = None
    for hit in find_indirect_connections(graph, min_length=2, max_length=3,
                                         max_pairs=8):
        if hit["source"].entity_type == "person" \
                and hit["target"].entity_type == "person":
            pair = hit
            break
    if pair and len(out) < MAX_GENERATED_HYPOTHESES - 3:
        s, t, p = pair["source"], pair["target"], pair["path"]
        intermediates = p.node_ids[1:-1]
        inter_names = ", ".join(graph.nodes[n].display_name for n in intermediates)
        ev = set()
        for a, b in zip(p.node_ids, p.node_ids[1:]):
            e = graph.edges.get(tuple(sorted((a, b))))
            if e:
                ev.update(e.evidence_ids)
        h_direct = HypothesisSpec(
            title=f"Connection {s.display_name} ↔ {t.display_name}: recorded links",
            description=(f"The confirmed data shows {s.display_name} and "
                         f"{t.display_name} connected through the recorded "
                         f"links {' → '.join(p.nodes)} (no direct "
                         "relationship between the two)."),
            hypothesis_type="GENERATED_STRUCTURE",
            involved_entity_ids=sorted({s.entity_ids[0], t.entity_ids[0],
                                        *(graph.nodes[n].entity_ids[0]
                                          for n in intermediates)}),
            supporting_relationship_ids=list(p.relationship_ids),
            supporting_evidence_ids=sorted(ev),
            explanation_prefix=(
                "Basis: no confirmed direct relationship; shortest "
                f"indirect path has {p.path_length} hop(s)."))
        inter0_name = (graph.nodes[intermediates[0]].display_name
                       if intermediates else "an intermediate")
        h_bridge = HypothesisSpec(
            title=(f"Connection {s.display_name} ↔ {t.display_name}: "
                   f"mediated by {inter0_name}"),
            description=(f"The link between {s.display_name} and "
                         f"{t.display_name} runs through "
                         f"{inter_names}; the intermediate is the "
                         "analytically relevant node."),
            hypothesis_type="GENERATED_STRUCTURE",
            involved_entity_ids=[graph.nodes[intermediates[0]].entity_ids[0]]
            if intermediates else [],
            supporting_evidence_ids=sorted(ev),
            explanation_prefix=(
                "Basis: intermediate entity on the shortest indirect "
                f"path ({inter_names})."))
        scored_d = score_spec(d, h_direct)
        scored_b = score_spec(d, h_bridge)
        out.append(h_direct)
        out.append(h_bridge)
        if abs(scored_d.analytical_score - scored_b.analytical_score) \
                < SCORE_GAP_THRESHOLD and len(out) < MAX_GENERATED_HYPOTHESES:
            out.append(HypothesisSpec(
                title=(f"Connection {s.display_name} ↔ {t.display_name}: "
                       "insufficient to distinguish"),
                description=(f"The available confirmed data does not "
                             f"distinguish between the recorded-links "
                             f"explanation and the {inter_names} mediation "
                             f"explanation for the connection between "
                             f"{s.display_name} and {t.display_name}."),
                hypothesis_type="GENERATED_STRUCTURE",
                involved_entity_ids=sorted({s.entity_ids[0], t.entity_ids[0]}),
                supporting_relationship_ids=list(p.relationship_ids),
                explanation_prefix=("Basis: score difference between the "
                                    "competing explanations is below the "
                                    f"documented {SCORE_GAP_THRESHOLD} "
                                    "threshold.")))
    return out[:MAX_GENERATED_HYPOTHESES]
