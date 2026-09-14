"""Thin, DB-backed analysis endpoints used by the graph-intelligence router.

Each function loads confirmed rows, builds the graph(s) and serializes the
engine output to plain dicts. The router stays free of algorithm code.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Case, Entity
from .finding_service import build_graphs
from .graph_builder import merged_reach
from .metrics import compute_metrics
from .path_analysis import find_paths
from .bridge_analysis import analyze_bridges
from .cluster_analysis import analyze_clusters
from .cross_case_analysis import analyze_cross_case


def _case_numbers(db: Session) -> dict[int, str]:
    return {c.id: c.case_number for c in
            db.execute(select(Case)).scalars().all()}


def _require_entity(db: Session, case_id: int, entity_id: int) -> Entity:
    from ...core.errors import ApiError, not_found
    from ...models import EntityCandidate
    entity = db.get(Entity, entity_id)
    if entity is not None and entity.case_id == case_id:
        return entity
    # The id may be an EXTRACTION CANDIDATE — analysis runs on confirmed
    # data only, so say exactly that instead of a bare 404.
    cand = db.get(EntityCandidate, entity_id)
    if cand is not None and cand.case_id == case_id:
        raise ApiError("ENTITY_NOT_CONFIRMED",
                       f"Entity id {entity_id} is an extraction candidate "
                       f"(status {cand.status}), not a confirmed entity. "
                       f"Analysis uses confirmed entities only.", 400)
    not_found("ENTITY_NOT_FOUND",
              f"Entity {entity_id} not found in this case.")


def get_metrics(db: Session, case_id: int) -> dict:
    case_graph, merged, _, _, version = build_graphs(db, case_id)
    metrics_list = compute_metrics(case_graph, merged, case_id)
    return {
        "graph_version": version,
        "nodes": case_graph.node_count,
        "edges": case_graph.edge_count,
        "metrics": [
            {"entity_id": m.entity_id, "name": m.display_name,
             "entity_type": m.entity_type, "degree": m.degree,
             "weighted_degree": m.weighted_degree,
             "betweenness": m.betweenness,
             "component_size": m.component_size,
             "cross_case_reach": m.cross_case_reach,
             "is_articulation_point": m.is_articulation_point,
             "neighbor_types": m.neighbor_types}
            for m in metrics_list],
    }


def get_bridges(db: Session, case_id: int) -> dict:
    case_graph, merged, _, _, version = build_graphs(db, case_id)
    bridges = analyze_bridges(case_graph, merged_reach(case_graph, merged))
    return {
        "graph_version": version,
        "nodes": case_graph.node_count,
        "edges": case_graph.edge_count,
        "insufficient": case_graph.is_insufficient(),
        "bridges": [
            {"entity_id": b.entity_ids[0], "name": b.display_name,
             "entity_type": b.entity_type, "degree": b.degree,
             "is_articulation_point": b.is_articulation_point,
             "betweenness": b.betweenness,
             "connectivity_impact": b.connectivity_impact,
             "cross_case_reach": b.cross_case_reach,
             "bridge_score": b.bridge_score, "reasons": b.reasons}
            for b in bridges],
    }


def get_clusters(db: Session, case_id: int) -> dict:
    case_graph, merged, _, _, version = build_graphs(db, case_id)
    bridges = analyze_bridges(case_graph, merged_reach(case_graph, merged))
    bridges_by_node = {b.node_id: {"display_name": b.display_name,
                                   "bridge_score": b.bridge_score}
                       for b in bridges}
    clusters = analyze_clusters(case_graph, bridges_by_node)
    return {
        "graph_version": version,
        "clusters": [
            {"index": c.cluster_index, "node_ids": c.node_ids,
             "members": c.display_names, "entity_ids": c.entity_ids,
             "entity_count": c.entity_count,
             "relationship_count": c.relationship_count,
             "type_breakdown": c.type_breakdown, "case_ids": c.case_ids,
             "cross_case": c.cross_case, "key_bridge": c.key_bridge,
             "subgroups": c.subgroups, "description": c.description}
            for c in clusters],
    }


def get_cross_case(db: Session, case_id: int,
                   allowed_ids: list[int] | None = None) -> dict:
    case_graph, merged, _, _, version = build_graphs(db, case_id)
    results = analyze_cross_case(merged, _case_numbers(db), case_id)
    if allowed_ids is not None:
        # stage 7: never reveal cross-case links to cases the caller
        # cannot access (existence must not leak through the graph)
        results = [cc for cc in results if cc.case_b_id in allowed_ids]
    return {
        "graph_version": version,
        "connections": [
            {"case_id": cc.case_b_id, "case_number": cc.case_b_number,
             "connection_kind": cc.connection_kind,
             "shared_entities": cc.shared_entities,
             "example_path": cc.example_path,
             "example_path_relationships": cc.example_path_relationships,
             "evidence_count": cc.evidence_count,
             "explanation": cc.explanation}
            for cc in results],
    }


def get_paths(db: Session, case_id: int, source_entity_id: int,
              target_entity_id: int, max_depth: int, max_paths: int) -> dict:
    from ...core.errors import ApiError
    source = _require_entity(db, case_id, source_entity_id)
    target = _require_entity(db, case_id, target_entity_id)
    if source.id == target.id:
        raise ApiError("INVALID_PATH_REQUEST",
                       "Source and target must be two different entities.", 400)
    case_graph, merged, _, _, version = build_graphs(db, case_id)
    s, t = f"e{source.id}", f"e{target.id}"
    results = find_paths(case_graph, s, t, max_depth=max_depth,
                         max_paths=max_paths)
    if not results:
        raise ApiError("PATH_NOT_FOUND",
                       f"No confirmed connection path found between "
                       f"{source.canonical_name} and "
                       f"{target.canonical_name} within {max_depth} hops.",
                       404)
    return {
        "graph_version": version,
        "source": {"entity_id": source.id, "name": source.canonical_name,
                   "entity_type": source.entity_type},
        "target": {"entity_id": target.id, "name": target.canonical_name,
                   "entity_type": target.entity_type},
        "max_depth": max_depth,
        "paths": [
            {"path_length": p.path_length,
             "nodes": [{"entity_id": case_graph.nodes[n].entity_ids[0],
                        "name": case_graph.nodes[n].display_name,
                        "entity_type": case_graph.nodes[n].entity_type}
                       for n in p.node_ids],
             "relationship_types": p.relationship_types,
             "relationship_ids": p.relationship_ids,
             "evidence_count": p.evidence_count,
             "explanation": p.explanation}
            for p in results],
    }
