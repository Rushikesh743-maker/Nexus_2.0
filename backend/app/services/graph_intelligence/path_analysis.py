"""Connection-path analysis over a confirmed graph.

Everything here is bounded and deterministic:

* depth is capped at ``MAX_PATH_DEPTH`` (default 4 hops),
* at most ``MAX_PATHS`` paths are returned,
* shortest paths only (NetworkX BFS — no exponential enumeration),
* cycles cannot occur: NetworkX simple paths never repeat nodes.

Every returned path is accompanied by a deterministic explanation generated
from the actual hops — no free-text invention, no LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from .graph_builder import (MAX_INDIRECT_PAIRS, MAX_PATHS, MAX_PATH_DEPTH,
                            ConfirmedGraph)


@dataclass
class PathResult:
    path_length: int                      # number of hops
    node_ids: list[str] = field(default_factory=list)
    nodes: list[str] = field(default_factory=list)          # display names
    node_types: list[str] = field(default_factory=list)
    relationship_types: list[str] = field(default_factory=list)
    relationship_ids: list[int] = field(default_factory=list)
    evidence_count: int = 0
    explanation: str = ""


def _edge_for(graph: ConfirmedGraph, a: str, b: str):
    return graph.edges.get(tuple(sorted((a, b))))


def _explain(graph: ConfirmedGraph, node_ids: list[str]) -> str:
    """Deterministic human explanation built from the actual path."""
    names = [graph.nodes[n].display_name for n in node_ids]
    if len(node_ids) == 2:
        return (f"{names[0]} and {names[1]} have a direct confirmed "
                f"relationship ({_edge_for(graph, node_ids[0], node_ids[1]).relationship_type}).")
    middle = " and ".join(names[1:-1])
    steps = "\n".join(
        f"{names[i]} → {r} → {names[i+1]}"
        for i, r in enumerate(_hop_types(graph, node_ids))
    )
    return (f"{names[0]} is indirectly connected to {names[-1]} through {middle} "
            f"({len(node_ids) - 1} hops):\n{steps}")


def _hop_types(graph: ConfirmedGraph, node_ids: list[str]) -> list[str]:
    out = []
    for a, b in zip(node_ids, node_ids[1:]):
        e = _edge_for(graph, a, b)
        out.append(e.relationship_type if e else "?")
    return out


def find_paths(graph: ConfirmedGraph, source_node: str, target_node: str,
               max_depth: int = MAX_PATH_DEPTH,
               max_paths: int = MAX_PATHS) -> list[PathResult]:
    """All shortest paths between two nodes (BFS, depth-capped).

    Returns [] when there is no path within the depth limit. The caller
    validates that both nodes exist in the graph before calling.
    """
    if source_node == target_node:
        return []
    max_depth = max(1, min(max_depth, MAX_PATH_DEPTH))
    max_paths = max(1, min(max_paths, MAX_PATHS))
    # Step 1: bounded BFS from the source (cutoff = depth limit); the
    # target is absent from the result dict when no path fits the limit.
    lengths = nx.single_source_shortest_path_length(
        graph.graph, source_node, cutoff=max_depth)
    if target_node not in lengths:
        return []
    # Step 2: enumerate shortest paths only (all have exactly `dist` hops)
    # and stop after `max_paths` — the generator is consumed lazily.
    results = []
    for node_ids in nx.all_shortest_paths(graph.graph, source_node, target_node):
        if len(results) >= max_paths:
            break
        if len(node_ids) - 1 > max_depth:
            continue
        rel_types: list[str] = []
        rel_ids: list[int] = []
        evidence = 0
        for a, b in zip(node_ids, node_ids[1:]):
            e = _edge_for(graph, a, b)
            if e:
                rel_types.append(e.relationship_type)
                rel_ids.append(e.relationship_id)
                evidence += e.evidence_count
        results.append(PathResult(
            path_length=len(node_ids) - 1,
            node_ids=node_ids,
            nodes=[graph.nodes[n].display_name for n in node_ids],
            node_types=[graph.nodes[n].entity_type for n in node_ids],
            relationship_types=rel_types,
            relationship_ids=rel_ids,
            evidence_count=evidence,
            explanation=_explain(graph, node_ids),
        ))
    return results


def find_indirect_connections(graph: ConfirmedGraph, min_length: int = 2,
                              max_length: int = 3,
                              max_pairs: int = MAX_INDIRECT_PAIRS,
                              prefer_person_pairs: bool = True) -> list[dict]:
    """Entity pairs with NO direct relationship but a short confirmed path.

    This is the "hidden indirect connection" detector. Pairs are scored by
    (path length ascending, then node ids ascending) for a stable order,
    and person↔person pairs are preferred. The whole search is bounded:
    one BFS per source node, depth-capped, capped number of reported pairs.
    """
    g = graph.graph
    if g.number_of_nodes() < 3:
        return []
    # Precompute shortest-path tree from each node (bounded BFS).
    pair_paths: list[tuple[int, str, str, list[str]]] = []
    sources = [n for n in g.nodes if g.degree(n) > 0]
    for s in sources:
        try:
            lengths = nx.single_source_shortest_path_length(g, s, cutoff=max_length)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue
        for t, length in lengths.items():
            if t <= s or length < min_length:
                continue  # each unordered pair once; skip direct edges
            if g.has_edge(s, t):
                continue  # direct relationship — not "hidden"
            pair_paths.append((length, s, t, None))

    def score(p):
        _, s, t, _ = p
        types = (graph.nodes[s].entity_type, graph.nodes[t].entity_type)
        both_person = types == ("person", "person")
        any_person = "person" in types
        # person pairs first, then any pair touching a person, then the rest
        class_rank = 0 if both_person else (1 if any_person else 2)
        return (p[0], class_rank, s, t)

    pair_paths.sort(key=score)

    out: list[dict] = []
    seen: set[frozenset] = set()
    for length, s, t, _ in pair_paths:
        if len(out) >= max_pairs:
            break
        key = frozenset((s, t))
        if key in seen:
            continue
        seen.add(key)
        node_ids = list(nx.shortest_path(g, s, t))
        paths = find_paths(graph, s, t, max_depth=length, max_paths=1)
        if not paths:
            continue
        p = paths[0]
        out.append({
            "source": graph.nodes[s],
            "target": graph.nodes[t],
            "path": p,
            "path_length": length,
        })
    return out
