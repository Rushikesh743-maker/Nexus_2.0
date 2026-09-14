"""Cross-case connection analysis.

A cross-case connection exists only when CONFIRMED data links the cases:

1. **Shared confirmed entity** — the same (entity type, normalized name)
   appears as a confirmed entity in both cases (in the merged graph this is
   a node with two or more case ids).
2. **Confirmed path through a shared entity** — a relationship in case A
   touches the shared entity AND a relationship in case B touches it, so a
   confirmed path runs  entity(case A) → shared entity → entity(case B).

Cases that merely contain similar words, similar timestamps, or look-alike
*unverified* candidates are never reported — candidates are outside the
analysis graph entirely, and text similarity is not a connection.

For each connected pair the engine reports the shared entities plus up to
one example path (deterministic: shared entities in normalized-name order,
neighbour order by entity id, first complete path wins).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .graph_builder import ConfirmedGraph


@dataclass
class CrossCaseResult:
    case_a_id: int
    case_a_number: str
    case_b_id: int
    case_b_number: str
    connection_kind: str                     # shared_entity | shared_path
    shared_entities: list[dict] = field(default_factory=list)
    example_path: list[dict] = field(default_factory=list)
    example_path_relationships: list[str] = field(default_factory=list)
    evidence_count: int = 0
    explanation: str = ""


def _example_path(graph: ConfirmedGraph, case_a: int, case_b: int,
                  shared_node: str) -> tuple[list[dict], list[str]]:
    """Find one confirmed path from an entity in case A to an entity in
    case B that goes through the shared node (depth ≤ 2 hops on each side).
    Deterministic neighbour ordering (entity id, then node id)."""
    g = graph.graph
    shared = graph.nodes[shared_node]

    def neighbours_of_case(n: str, case_id: int) -> list[str]:
        hits = []
        for m in sorted(g.neighbors(n)):
            info = graph.nodes[m]
            if case_id in info.case_ids and m != n:
                hits.append(m)
        return hits

    for left in neighbours_of_case(shared_node, case_a):
        for right in neighbours_of_case(shared_node, case_b):
            if left == right:
                continue
            l, r = graph.nodes[left], graph.nodes[right]
            edge_lr = graph.edges.get(tuple(sorted((shared_node, left))))
            edge_rr = graph.edges.get(tuple(sorted((shared_node, right))))
            return (
                [
                    {"name": l.display_name, "entity_type": l.entity_type,
                     "case_id": case_a, "node_id": left},
                    {"name": shared.display_name, "entity_type": shared.entity_type,
                     "case_id": None, "node_id": shared_node, "shared": True},
                    {"name": r.display_name, "entity_type": r.entity_type,
                     "case_id": case_b, "node_id": right},
                ],
                [edge_lr.relationship_type if edge_lr else "?",
                 edge_rr.relationship_type if edge_rr else "?"],
            )
    return [], []


def analyze_cross_case(graph: ConfirmedGraph,
                       case_number_by_id: dict[int, str],
                       primary_case_id: int,
                       max_results: int = 12) -> list[CrossCaseResult]:
    """Connections between the primary case and every other case."""
    # Collect, per other case, the shared merged nodes.
    shared_by_case: dict[int, list[str]] = {}
    for n, info in graph.nodes.items():
        if primary_case_id not in info.case_ids:
            continue
        for other in info.case_ids:
            if other != primary_case_id:
                shared_by_case.setdefault(other, []).append(n)

    out: list[CrossCaseResult] = []
    for other in sorted(shared_by_case):
        shared_nodes = sorted(shared_by_case[other],
                              key=lambda n: (graph.nodes[n].entity_type,
                                             graph.nodes[n].display_name.casefold()))
        shared = [
            {"name": graph.nodes[n].display_name,
             "entity_type": graph.nodes[n].entity_type,
             "entity_ids": list(graph.nodes[n].entity_ids)}
            for n in shared_nodes
        ]
        # look for an example path through any shared entity
        example, rel_types = [], []
        for n in shared_nodes:
            example, rel_types = _example_path(graph, primary_case_id, other, n)
            if example:
                break

        if example:
            kind = "shared_path"
            ev = sum(graph.nodes[step["node_id"]].evidence_count for step in example)
        else:
            kind = "shared_entity"
            ev = sum(graph.nodes[n].evidence_count for n in shared_nodes)

        a_num = case_number_by_id.get(primary_case_id, f"case {primary_case_id}")
        b_num = case_number_by_id.get(other, f"case {other}")
        names = ", ".join(s["name"] for s in shared[:4])
        extra = f" (+{len(shared) - 4} more)" if len(shared) > 4 else ""
        explanation = (f"{a_num} and {b_num} share {len(shared)} confirmed "
                       f"entit{'y' if len(shared) == 1 else 'ies'}: {names}{extra}.")
        if example:
            hops = " → ".join(
                f"{step['name']}{' [shared]' if step.get('shared') else ''}"
                for step in example)
            explanation += (f" A confirmed path connects them: {hops} "
                            f"({', '.join(rel_types)}).")
        out.append(CrossCaseResult(
            case_a_id=primary_case_id, case_a_number=a_num,
            case_b_id=other, case_b_number=b_num,
            connection_kind=kind, shared_entities=shared,
            example_path=example, example_path_relationships=rel_types,
            evidence_count=ev, explanation=explanation))
        if len(out) >= max_results:
            break
    return out
