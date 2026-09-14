"""Network-cluster analysis over a confirmed graph.

Primary method: connected-component analysis (deterministic, always
explainable: "these entities are linked to each other through confirmed
relationships and nothing connects them to the rest of the graph").

Secondary (optional) method: greedy modularity communities, attempted only
on components large enough to make the split meaningful (≥ 8 members) and
reported only when the result is a real partition (≥ 2 communities, each ≥ 3
members). If the community detection does not produce a meaningful split,
it is omitted — the component itself remains the cluster.

Terminology is deliberately neutral: "connected group" / "network cluster".
Nothing here labels a cluster as a criminal organization.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from .graph_builder import MAX_CLUSTERS, ConfirmedGraph


@dataclass
class ClusterResult:
    cluster_index: int
    node_ids: list[str]
    display_names: list[str]
    entity_ids: list[int]
    entity_count: int
    relationship_count: int
    type_breakdown: dict[str, int]
    case_ids: list[int]
    cross_case: bool
    key_bridge: dict | None = None      # highest-scoring bridge inside the cluster
    subgroups: list[list[str]] | None = None  # display names per modularity community
    description: str = ""


def _subgroups(component: nx.Graph) -> list[list[str]] | None:
    """Greedy modularity communities — only when they split meaningfully."""
    if component.number_of_nodes() < 8:
        return None
    try:
        communities = list(nx.community.greedy_modularity_communities(component))
    except (AttributeError, nx.NetworkXException):
        return None
    if len(communities) < 2:
        return None
    big = [c for c in communities if len(c) >= 3]
    if len(big) < 2:
        return None
    return [sorted(c) for c in communities]


def analyze_clusters(graph: ConfirmedGraph,
                     bridges_by_node: dict[str, dict] | None = None) -> list[ClusterResult]:
    g = graph.graph
    components = sorted(nx.connected_components(g),
                        key=lambda c: (-len(c), min(c)))
    out: list[ClusterResult] = []
    for i, comp in enumerate(components, start=1):
        if len(comp) < 2:
            continue  # isolated singletons are not clusters
        sub = g.subgraph(comp)
        type_breakdown: dict[str, int] = {}
        case_ids: set[int] = set()
        entity_ids: list[int] = []
        names: list[str] = []
        for n in sorted(comp):
            info = graph.nodes[n]
            type_breakdown[info.entity_type] = type_breakdown.get(info.entity_type, 0) + 1
            case_ids.update(info.case_ids)
            entity_ids.extend(info.entity_ids)
            names.append(info.display_name)
        rels = sub.number_of_edges()
        case_ids = sorted(case_ids)

        key_bridge = None
        if bridges_by_node:
            best = max((bridges_by_node[n] for n in comp if n in bridges_by_node),
                       key=lambda b: b["bridge_score"], default=None)
            key_bridge = best

        subgroups = _subgroups(sub)
        members = ", ".join(sorted(names)[:6])
        more = f" (+{len(names) - 6} more)" if len(names) > 6 else ""
        span = ("spans " + str(len(case_ids)) + " cases" if len(case_ids) > 1
                else "within a single case")
        description = (f"{len(comp)} confirmed entities and {rels} confirmed "
                       f"relationships form one connected group of the confirmed "
                       f"graph ({span}). Members: {members}{more}.")
        out.append(ClusterResult(
            cluster_index=i, node_ids=sorted(comp), display_names=sorted(names),
            entity_ids=sorted(set(entity_ids)), entity_count=len(comp),
            relationship_count=rels, type_breakdown=type_breakdown,
            case_ids=case_ids, cross_case=len(case_ids) > 1,
            key_bridge=key_bridge, subgroups=subgroups, description=description))
        if len(out) >= MAX_CLUSTERS:
            break
    return out
