"""Bridge-entity detection: entities whose removal separates the graph.

A bridge entity is computed from three real NetworkX properties, combined
with a documented, deterministic formula:

    bridge_score = 0.45 * betweenness_norm
                 + 0.35 * connectivity_impact_norm
                 + 0.20 * cross_case_reach_norm

* ``betweenness_norm`` — the entity's normalized betweenness centrality
  (how often it sits on shortest paths between other entities) relative to
  the most central entity in the graph.
* ``connectivity_impact_norm`` — for articulation points, how many ADDITIONAL
  connected components appear when the node is removed, relative to the
  largest such impact in the graph; non-articulation points score 0.
* ``cross_case_reach_norm`` — (number of distinct confirmed cases the
  entity's identity appears in − 1) relative to the graph's maximum.

Only nodes with degree ≥ 2 and a score of at least ``BRIDGE_THRESHOLD``
are reported (a degree-1 node cannot connect two regions). Nothing here is
random and every reported bullet is derived from the computed values.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from .graph_builder import MAX_BRIDGES, ConfirmedGraph

BRIDGE_THRESHOLD = 0.25
MIN_BRIDGE_DEGREE = 2


@dataclass
class BridgeResult:
    node_id: str
    display_name: str
    entity_type: str
    degree: int
    is_articulation_point: bool
    betweenness: float
    connectivity_impact: int
    cross_case_reach: int
    bridge_score: float
    reasons: list[str] = field(default_factory=list)
    entity_ids: list[int] = field(default_factory=list)


def connectivity_impact(g: nx.Graph, node: str) -> int:
    """How many extra connected components removing `node` creates."""
    try:
        before = nx.number_connected_components(g)
        without = g.copy()
        without.remove_node(node)
        return nx.number_connected_components(without) - before
    except (nx.NodeNotFound, nx.NetworkXException):
        return 0


def analyze_bridges(graph: ConfirmedGraph,
                     reach_by_node: dict[str, int] | None = None) -> list[BridgeResult]:
    """`reach_by_node` maps case-graph node ids to the number of distinct
    confirmed cases the entity's identity appears in (from the merged
    graph); without it the cross-case term is 0."""
    g = graph.graph
    if g.number_of_nodes() < 3:
        return []

    articulation = set(nx.articulation_points(g))
    try:
        betweenness = nx.betweenness_centrality(g)
    except nx.NetworkXException:
        betweenness = {n: 0.0 for n in g.nodes}

    max_betweenness = max(betweenness.values()) if betweenness else 0.0

    impacts = {n: (connectivity_impact(g, n) if n in articulation else 0)
               for n in g.nodes if g.degree(n) >= MIN_BRIDGE_DEGREE}
    max_impact = max(impacts.values()) if impacts else 0

    reach_by_node = reach_by_node or {
        n: len(info.case_ids) for n, info in graph.nodes.items()}
    max_reach = max(reach_by_node.values()) or 1

    results: list[BridgeResult] = []
    for n, info in graph.nodes.items():
        degree = g.degree(n)
        if degree < MIN_BRIDGE_DEGREE:
            continue
        b_norm = betweenness.get(n, 0.0) / max_betweenness if max_betweenness > 0 else 0.0
        i_norm = impacts.get(n, 0) / max_impact if max_impact > 0 else 0.0
        reach = reach_by_node.get(n, 1)
        r_norm = (reach - 1) / (max_reach - 1) if max_reach > 1 else 0.0
        score = round(0.45 * b_norm + 0.35 * i_norm + 0.20 * r_norm, 3)
        if score < BRIDGE_THRESHOLD:
            continue

        reasons: list[str] = []
        if n in articulation:
            reasons.append(
                f"Removing this entity increases the graph's connected "
                f"components from {nx.number_connected_components(g)} to "
                f"{nx.number_connected_components(g) + impacts.get(n, 0)} "
                f"(it is an articulation point).")
        if b_norm >= 0.5:
            reasons.append(
                f"It lies on a high share of shortest paths between other "
                f"entities (betweenness centrality {betweenness.get(n, 0):.3f}, "
                f"the highest in this graph).")
        elif betweenness.get(n, 0) > 0:
            reasons.append(
                f"It appears on shortest paths between other entities "
                f"(betweenness centrality {betweenness.get(n, 0):.3f}).")
        reasons.append(f"It has {degree} direct confirmed connections.")
        if reach > 1:
            reasons.append(f"It appears in {reach} confirmed cases "
                           f"({', '.join('case ' + str(c) for c in info.case_ids)}).")
        results.append(BridgeResult(
            node_id=n, display_name=info.display_name,
            entity_type=info.entity_type, degree=degree,
            is_articulation_point=n in articulation,
            betweenness=round(betweenness.get(n, 0.0), 4),
            connectivity_impact=impacts.get(n, 0),
            cross_case_reach=reach, bridge_score=score,
            reasons=reasons, entity_ids=list(info.entity_ids)))

    results.sort(key=lambda r: (-r.bridge_score, -r.degree, r.node_id))
    return results[:MAX_BRIDGES]
