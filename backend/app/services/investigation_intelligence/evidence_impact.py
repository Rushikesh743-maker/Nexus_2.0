"""Evidence impact intelligence (stage 4).

Per-evidence analytical linkage over CONFIRMED data only. An evidence
record affects the case analysis through the Stage 3 confirmed-provenance
links (accepted entity-candidate / relationship-candidate rows whose
`source_reference` points at the evidence record), direct
`timeline_event.evidence_id` references, and the findings/hypotheses that
cite it.

**Impact score (documented, deterministic, 0..1):**

    graph_weight     = 0.5 * min(1, linked_relationships / 3)
                     + 0.3 * min(1, linked_entities / 3)
                     + 0.2 * min(1, linked_events / 2)
    finding_weight   = 0.5 if the evidence is cited by >= 1 finding else 0
    hypothesis_weight= 0.5 if cited by >= 1 hypothesis else 0
    impact_score     = clamp(0.5*graph_weight
                             + 0.25*finding_weight
                             + 0.25*hypothesis_weight)

The score measures how much the evidence is STRUCTURALLY LINKED into the
confirmed analysis — it is not a credibility or authenticity judgment.

**Removal simulation** (POST simulate-impact) is pure in-memory:
a copy of the confirmed (entity) graph is made, and for every edge the
engine checks the documented *sole-provenance rule*: the edge (i.e. every
confirmed relationship of that entity pair) is removed in the copy only
if (a) at least one relationship of the pair is proven by this evidence
AND (b) no relationship of the pair is proven by any OTHER evidence AND
(c) no relationship of the pair lacks provenance (an unproven
relationship is kept — no fabrication of absence). Degrees, betweenness
and components are recomputed on the copy and the before/after diff is
returned. **Nothing is ever written or deleted in the database.**
"""

from __future__ import annotations

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import GraphFinding, InvestigationHypothesis
from ..graph_intelligence.graph_builder import build_case_graph
from .data import Stage4Data


def _linked_relationships(d: Stage4Data, evidence_id: int) -> list[int]:
    """Relationships whose candidate provenance points at this evidence."""
    out = []
    for r in d.relationships:
        if r.candidate_id is None:
            continue
        refs = d.evidence_index.get(f"candidate:{r.candidate_id}")
        if refs and evidence_id in refs:
            out.append(r.id)
    return sorted(out)


def _linked_entities(d: Stage4Data, evidence_id: int) -> list[int]:
    ev = next((v for v in d.evidence if v.id == evidence_id), None)
    if ev is None:
        return []
    ids = set()
    for ent_id, cand_ids in d.accepted_candidates.items():
        for cid in cand_ids:
            if ev.source_reference and \
                    ev.source_reference == f"candidate:{cid}":
                ids.add(ent_id)
    return sorted(ids)


def _linked_events(d: Stage4Data, evidence_id: int) -> list[int]:
    return sorted(e.id for e in d.events if e.evidence_id == evidence_id)


def _cited_by(db: Session, case_id: int, evidence_id: int) -> dict:
    findings = db.execute(
        select(GraphFinding).where(GraphFinding.case_id == case_id)
    ).scalars().all()
    fids = sorted(f.id for f in findings
                  if evidence_id in (f.supporting_evidence_ids or []))
    hyps = db.execute(
        select(InvestigationHypothesis).where(
            InvestigationHypothesis.case_id == case_id,
            InvestigationHypothesis.status.in_(["ACTIVE", "REVIEWED"]))
    ).scalars().all()
    hids = sorted(h.id for h in hyps
                  if evidence_id in (h.supporting_evidence_ids or [])
                  or evidence_id in (h.contradicting_evidence_ids or []))
    return {"findings": fids, "hypotheses": hids}


def _clamp01(x: float) -> float:
    return round(max(0.0, min(1.0, x)), 3)


def evidence_impact_payload(d: Stage4Data, db: Session,
                            evidence_id: int) -> dict:
    ents = _linked_entities(d, evidence_id)
    rels = _linked_relationships(d, evidence_id)
    evts = _linked_events(d, evidence_id)
    cited = _cited_by(db, d.case_id, evidence_id)

    graph_weight = _clamp01(0.5 * min(1.0, len(rels) / 3)
                            + 0.3 * min(1.0, len(ents) / 3)
                            + 0.2 * min(1.0, len(evts) / 2))
    finding_weight = 0.5 if cited["findings"] else 0.0
    hypothesis_weight = 0.5 if cited["hypotheses"] else 0.0
    impact = _clamp01(0.5 * graph_weight
                      + 0.25 * finding_weight
                      + 0.25 * hypothesis_weight)
    role = ("HIGH" if impact >= 0.67
            else "MEDIUM" if impact >= 0.34 else "LOW")
    if not ents and not rels and not evts and not cited["findings"] \
            and not cited["hypotheses"]:
        role_label = "standalone record (no direct analytical linkage)"
    else:
        parts = []
        if rels:
            parts.append(f"{len(rels)} confirmed relationship(s)")
        if ents:
            parts.append(f"{len(ents)} confirmed entity(ies)")
        if evts:
            parts.append(f"{len(evts)} timeline event(s)")
        if cited["findings"]:
            parts.append(f"cited by {len(cited['findings'])} finding(s)")
        if cited["hypotheses"]:
            parts.append(f"cited by {len(cited['hypotheses'])} hypothesis(es)")
        role_label = "structural support via " + ", ".join(parts)

    name_of = {e.id: e.canonical_name for e in d.entities}
    return {
        "evidence_id": evidence_id,
        "linked_entities": [{"id": i, "name": name_of.get(i, str(i))}
                            for i in ents],
        "linked_relationships": rels,
        "linked_timeline_events": evts,
        "referenced_by_findings": cited["findings"],
        "referenced_by_hypotheses": cited["hypotheses"],
        "impact_score": impact,
        "impact_band": role,
        "impact_role": role_label,
        "score_components": {
            "graph_weight": graph_weight,
            "finding_weight": finding_weight,
            "hypothesis_weight": hypothesis_weight,
        },
        "explanation": [
            f"Linked confirmed relationships: {len(rels)}; entities: "
            f"{len(ents)}; timeline events: {len(evts)}.",
            f"Cited by {len(cited['findings'])} finding(s) and "
            f"{len(cited['hypotheses'])} hypothesis(es).",
            "Impact measures structural linkage in the confirmed "
            "analysis — not credibility or authenticity.",
        ],
    }


def summary_payload(d: Stage4Data, db: Session) -> dict:
    rows = [evidence_impact_payload(d, db, v.id) for v in d.evidence]
    rows.sort(key=lambda r: (-r["impact_score"], r["evidence_id"]))
    high = sum(1 for r in rows if r["impact_score"] >= 0.67)
    med = sum(1 for r in rows if 0.34 <= r["impact_score"] < 0.67)
    low = len(rows) - high - med
    top = rows[0] if rows else None
    return {
        "evidence_count": len(rows),
        "distribution": {"HIGH": high, "MEDIUM": med, "LOW": low},
        "top_evidence": top,
        "evidence_impacts": rows,
        "analysis_method": ("evidence-impact v1 (impact = "
                            "0.5*graph_weight + 0.25*finding_weight + "
                            "0.25*hypothesis_weight; graph_weight = "
                            "0.5*min(1,rels/3) + 0.3*min(1,ents/3) + "
                            "0.2*min(1,events/2))"),
    }


def _pair_evidence(d: Stage4Data, rel_ids: list[int]) -> set[int]:
    """All evidence ids proven by the given relationship ids."""
    out: set[int] = set()
    for r in d.relationships:
        if r.id not in rel_ids or r.candidate_id is None:
            continue
        out.update(d.evidence_index.get(f"candidate:{r.candidate_id}", []))
    return out


def simulate_removal(db: Session, d: Stage4Data, evidence_id: int) -> dict:
    """In-memory what-if: remove this evidence from the confirmed graph
    and report the diff. No database writes of any kind."""
    ev = next((v for v in d.evidence if v.id == evidence_id), None)
    if ev is None:
        from ...core.errors import not_found
        not_found("EVIDENCE_NOT_FOUND",
                  f"Evidence {evidence_id} not found in this case.")

    graph = build_case_graph(d.entities, d.relationships, d.evidence_index,
                             d.accepted_candidates)
    g0 = graph.graph.copy()
    g1 = g0.copy()

    # group confirmed relationships per (unsorted) node pair
    rels_by_pair: dict[tuple[str, str], list] = {}
    for r in d.relationships:
        a, b = f"e{r.source_entity_id}", f"e{r.target_entity_id}"
        if a not in g0.nodes or b not in g0.nodes or a == b:
            continue
        rels_by_pair.setdefault(tuple(sorted((a, b))), []).append(r)

    removed_edges: list[dict] = []
    for key, rels in sorted(rels_by_pair.items()):
        a, b = key
        if not g1.has_edge(a, b):
            continue
        other_evidence = _pair_evidence(d, [r.id for r in rels]) - {evidence_id}
        has_this = any(evidence_id in (d.evidence_index.get(
            f"candidate:{r.candidate_id}", []) if r.candidate_id else [])
            for r in rels)
        has_unproven = any(r.candidate_id is None for r in rels)
        if has_this and not other_evidence and not has_unproven:
            g1.remove_edge(a, b)
            removed_edges.append({
                "edge": [a, b],
                "relationships": [r.id for r in rels],
                "rule": ("sole-provenance: every relationship of this "
                         "pair is proven only by the simulated-evidence "
                         "record")})

    def _metrics(g: nx.Graph) -> dict:
        bc = nx.betweenness_centrality(g)
        comps = sorted((sorted(c) for c in nx.connected_components(g)),
                       key=len, reverse=True)
        return {
            "degree": {n: g.degree(n) for n in sorted(g.nodes)},
            "betweenness": {n: round(bc[n], 4) for n in sorted(g.nodes)},
            "components": comps,
            "component_count": len(comps),
            "largest_component_size": len(comps[0]) if comps else 0,
        }

    before = _metrics(g0)
    after = _metrics(g1)

    degree_changes, betweenness_changes = [], []
    for n in sorted(set(before["degree"]) & set(after["degree"])):
        if before["degree"][n] != after["degree"][n]:
            degree_changes.append({"node": n,
                                   "before": before["degree"][n],
                                   "after": after["degree"][n]})
        diff = round(before["betweenness"][n] - after["betweenness"][n], 4)
        if abs(diff) > 1e-9:
            betweenness_changes.append(
                {"node": n, "before": before["betweenness"][n],
                 "after": after["betweenness"][n]})
    comp_before = {n: i for i, c in enumerate(before["components"]) for n in c}
    comp_after = {n: i for i, c in enumerate(after["components"]) for n in c}
    disconnected_pairs = []
    for a in sorted(set(after["degree"])):
        for b in sorted(set(after["degree"])):
            if a < b and comp_before.get(a) == comp_before.get(b) \
                    and comp_after.get(a) != comp_after.get(b):
                disconnected_pairs.append([a, b])
    isolated = [n for n in sorted(g1.nodes)
                if g1.degree(n) == 0 and g0.degree(n) > 0]

    name_of = {n: info.display_name for n, info in graph.nodes.items()}
    affected_findings = (_cited_by(db, d.case_id, evidence_id)["findings"]
                         if db is not None else [])

    return {
        "evidence_id": evidence_id,
        "simulation_only": True,
        "message": ("Simulation only — the stored evidence record was not "
                    "modified, deleted, or re-analyzed."),
        "edges_removed": removed_edges,
        "newly_isolated_entities": [
            {"node": n, "name": name_of.get(n)} for n in isolated],
        "metrics_before": before,
        "metrics_after": after,
        "diff": {
            "degree_changes": degree_changes,
            "betweenness_changes": betweenness_changes,
            "components_before": before["component_count"],
            "components_after": after["component_count"],
            "largest_component_before": before["largest_component_size"],
            "largest_component_after": after["largest_component_size"],
            "newly_disconnected_pairs": disconnected_pairs[:25],
        },
        "affected_findings": affected_findings,
        "analysis_method": ("evidence-simulation v1 (in-memory confirmed-"
                            "graph copy; documented sole-provenance edge "
                            "rule; degrees, betweenness and components "
                            "recomputed; zero database writes)"),
    }
