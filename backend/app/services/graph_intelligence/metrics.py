"""Per-entity graph metrics.

All metrics are computed from confirmed data only, with neutral wording
(a "highly connected entity", never "mastermind"). Evidence counts appear
only as analytical context — they are never presented as proof of guilt.

Metrics:

* ``degree`` — number of distinct confirmed entities directly connected.
* ``weighted_degree`` — each adjacent confirmed relationship counts 1 plus
  its directly-linked evidence records (documented weighting, used to
  rank entities that sit on well-evidenced relationships).
* ``betweenness`` — normalized betweenness centrality (NetworkX).
* ``component_size`` — size of the connected component containing the
  entity in the case graph.
* ``cross_case_reach`` — number of distinct confirmed cases in which the
  entity's identity (type + normalized name) appears (merged graph).
* ``neighbor_types`` — how many neighbours of each type.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from .graph_builder import ConfirmedGraph, MAX_TOP_ENTITIES


@dataclass
class EntityMetrics:
    entity_id: int
    display_name: str
    entity_type: str
    degree: int
    weighted_degree: int
    betweenness: float
    component_size: int
    cross_case_reach: int
    is_articulation_point: bool
    neighbor_types: dict[str, int] = field(default_factory=dict)


def compute_metrics(case_graph: ConfirmedGraph,
                    merged_graph: ConfirmedGraph,
                    case_id: int) -> list[EntityMetrics]:
    g = case_graph.graph
    try:
        betweenness = nx.betweenness_centrality(g)
    except nx.NetworkXException:
        betweenness = {n: 0.0 for n in g.nodes}
    try:
        articulation = set(nx.articulation_points(g))
    except nx.NetworkXException:
        articulation = set()
    components = list(nx.connected_components(g))
    comp_size = {n: len(c) for c in components for n in c}

    out: list[EntityMetrics] = []
    for n, info in case_graph.nodes.items():
        weighted = 0
        neighbor_types: dict[str, int] = {}
        for m in g.neighbors(n):
            e = case_graph.edges.get(tuple(sorted((n, m))))
            weighted += 1 + (e.evidence_count if e else 0)
            t = case_graph.nodes[m].entity_type
            neighbor_types[t] = neighbor_types.get(t, 0) + 1
        # cross-case reach from the merged identity of this entity
        reach = 1
        for mnode, minfo in merged_graph.nodes.items():
            if info.entity_ids and info.entity_ids[0] in minfo.entity_ids:
                reach = len(minfo.case_ids)
                break
        out.append(EntityMetrics(
            entity_id=info.entity_ids[0],
            display_name=info.display_name,
            entity_type=info.entity_type,
            degree=g.degree(n),
            weighted_degree=weighted,
            betweenness=round(betweenness.get(n, 0.0), 4),
            component_size=comp_size.get(n, 1),
            cross_case_reach=reach,
            is_articulation_point=n in articulation,
            neighbor_types=neighbor_types))
    out.sort(key=lambda m: (-m.degree, -m.betweenness, m.entity_id))
    return out


def high_connectivity(metrics: list[EntityMetrics], min_degree: int = 3,
                      top_n: int = MAX_TOP_ENTITIES) -> list[EntityMetrics]:
    """The most directly-connected entities (neutral ranking)."""
    eligible = [m for m in metrics if m.degree >= min_degree]
    return eligible[:top_n]
