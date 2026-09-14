"""Graph-intelligence service: run, persist, list and review findings.

Flow: API router → this service → graph builder / analysis engines →
repository (PostgreSQL). No algorithm lives in a router.

Freshness model (documented, Option C from the design):
* every analysis stores a ``graph_version`` — a deterministic hash of the
  confirmed entities/relationships it ran on;
* ``POST /graph/analyze`` with unchanged data is idempotent (returns the
  existing run, ``recomputed: false``);
* a finding whose stored version differs from the current hash is *stale*
  and is flagged as such in the API and UI ("the confirmed data changed
  since this analysis");
* re-analyses never delete history — old findings remain for auditability.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.errors import ApiError, not_found
from ...models import (Case, Entity, EntityCandidate, GraphFinding,
                       Relationship)
from ..auth_service import record_audit
from .bridge_analysis import analyze_bridges
from .cluster_analysis import analyze_clusters
from .cross_case_analysis import analyze_cross_case
from .graph_builder import (ConfirmedGraph, EntityRecord, RelationshipRecord,
                            build_case_graph, build_merged_graph,
                            compute_graph_version, merged_reach)
from .metrics import compute_metrics, high_connectivity
from .path_analysis import find_indirect_connections

logger = logging.getLogger(__name__)

METHOD_HIDDEN = ("shortest-path v1 (NetworkX all_shortest_paths, depth 2-3, "
                 "pairs without a direct relationship)")
METHOD_BRIDGE = ("articulation+betweenness v1 (nx.articulation_points, "
                 "nx.betweenness_centrality; score = 0.45*betweenness + "
                 "0.35*connectivity-impact + 0.20*cross-case-reach, normalized)")
METHOD_CROSS_CASE = ("shared-identity v1 (confirmed entities matched by "
                     "entity type + normalized name across cases)")
METHOD_CLUSTER = "connected-components v1 (nx.connected_components)"
METHOD_HUB = "degree-rank v1 (degree with betweenness tiebreak)"

# finding_type -> list order (most investigative-relevant first in the UI)
FINDING_TYPE_ORDER = ["CROSS_CASE_CONNECTION", "BRIDGE_ENTITY", "HIDDEN_CONNECTION",
                      "NETWORK_CLUSTER", "HIGH_CONNECTIVITY"]


# ------------------------------------------------------------- data loading

def _candidate_id_from_meta(meta: dict | None) -> int | None:
    if not meta:
        return None
    cid = meta.get("candidate_id")
    return int(cid) if isinstance(cid, int) else None


def load_case_records(db: Session, case_id: int
                      ) -> tuple[list[EntityRecord], list[RelationshipRecord]]:
    entities = db.execute(
        select(Entity).where(Entity.case_id == case_id)
        .order_by(Entity.id)).scalars().all()
    rels = db.execute(
        select(Relationship).where(Relationship.case_id == case_id)
        .order_by(Relationship.id)).scalars().all()
    return ([EntityRecord(e.id, e.case_id, e.entity_type, e.canonical_name)
             for e in entities],
            [RelationshipRecord(r.id, r.case_id, r.source_entity_id,
                                r.target_entity_id, r.relationship_type,
                                _candidate_id_from_meta(r.meta))
             for r in rels])


def load_merged_records(db: Session) -> tuple[list[EntityRecord], list[RelationshipRecord]]:
    entities = db.execute(select(Entity).order_by(Entity.id)).scalars().all()
    rels = db.execute(select(Relationship).order_by(Relationship.id)).scalars().all()
    return ([EntityRecord(e.id, e.case_id, e.entity_type, e.canonical_name)
             for e in entities],
            [RelationshipRecord(r.id, r.case_id, r.source_entity_id,
                                r.target_entity_id, r.relationship_type,
                                _candidate_id_from_meta(r.meta))
             for r in rels])


def load_evidence_index(db: Session, case_ids: list[int] | None = None
                        ) -> dict[str, list[int]]:
    """source_reference ("candidate:{id}") -> evidence ids, one pass."""
    from ...models import Evidence
    q = select(Evidence.id, Evidence.source_reference)
    if case_ids is not None:
        q = q.where(Evidence.case_id.in_(case_ids))
    index: dict[str, list[int]] = {}
    for ev_id, ref in db.execute(q).all():
        if ref:
            index.setdefault(ref, []).append(ev_id)
    return index


def load_accepted_candidates(db: Session, case_ids: list[int] | None = None
                             ) -> dict[int, list[int]]:
    """entity_id -> [accepted entity-candidate ids] (the evidence link)."""
    q = select(EntityCandidate.id, EntityCandidate.accepted_entity_id).where(
        EntityCandidate.status == "ACCEPTED",
        EntityCandidate.accepted_entity_id.is_not(None))
    if case_ids is not None:
        q = q.where(EntityCandidate.case_id.in_(case_ids))
    mapping: dict[int, list[int]] = {}
    for cid, eid in db.execute(q).all():
        mapping.setdefault(eid, []).append(cid)
    return mapping


def build_graphs(db: Session, case_id: int):
    """Case graph + merged (cross-case) graph for one case, from confirmed
    rows only. Returns (case_graph, merged_graph, entities, relationships,
    current_version)."""
    entities, rels = load_case_records(db, case_id)
    m_entities, m_rels = load_merged_records(db)
    ev_index = load_evidence_index(db, case_ids=None)
    accepted = load_accepted_candidates(db, case_ids=None)
    case_graph = build_case_graph(entities, rels, ev_index, accepted)
    merged = build_merged_graph(m_entities, m_rels, ev_index, accepted)
    version = compute_graph_version(entities, rels)
    return case_graph, merged, entities, rels, version


# -------------------------------------------------------- finding generation

def _node_ref(graph: ConfirmedGraph, node_id: str) -> dict:
    info = graph.nodes[node_id]
    return {"entity_id": info.entity_ids[0] if info.entity_ids else None,
            "name": info.display_name, "entity_type": info.entity_type,
            "case_ids": info.case_ids}


def _generate_hidden(graph: ConfirmedGraph) -> list[dict]:
    out = []
    for hit in find_indirect_connections(graph):
        s, t, p = hit["source"], hit["target"], hit["path"]
        evidence = set()
        for a, b in zip(p.node_ids, p.node_ids[1:]):
            e = graph.edges.get(tuple(sorted((a, b))))
            if e:
                evidence.update(e.evidence_ids)
        out.append({
            "finding_type": "HIDDEN_CONNECTION",
            "title": f"Indirect connection: {s.display_name} → {t.display_name}",
            "summary": (f"{s.display_name} ({s.entity_type}) and "
                        f"{t.display_name} ({t.entity_type}) have no direct "
                        f"confirmed relationship, but a confirmed path of "
                        f"{p.path_length} hop{'s' if p.path_length != 1 else ''} "
                        f"connects them."),
            "explanation": [p.explanation,
                            f"Supporting evidence: {p.evidence_count} evidence "
                            f"record(s) directly linked to the path's confirmed "
                            f"relationships (analytical context, not proof)."],
            "details": {
                "source": _node_ref(graph, s.node_id),
                "target": _node_ref(graph, t.node_id),
                "path": {"length": p.path_length, "nodes": p.nodes,
                         "node_types": p.node_types,
                         "relationship_types": p.relationship_types,
                         "relationship_ids": p.relationship_ids,
                         "evidence_count": p.evidence_count}},
            "involved_entity_ids": sorted({s.entity_ids[0], t.entity_ids[0]}),
            "supporting_relationship_ids": list(p.relationship_ids),
            "supporting_evidence_ids": sorted(evidence),
            "related_case_ids": [],
            "analysis_method": METHOD_HIDDEN,
        })
    return out


def _generate_bridges(graph: ConfirmedGraph, bridges) -> list[dict]:
    out = []
    for b in bridges:
        evidence: set[int] = set()
        for m in graph.graph.neighbors(b.node_id):
            e = graph.edges.get(tuple(sorted((b.node_id, m))))
            if e:
                evidence.update(e.evidence_ids)
        out.append({
            "finding_type": "BRIDGE_ENTITY",
            "title": f"Potential bridge entity: {b.display_name}",
            "summary": (f"{b.display_name} ({b.entity_type}) sits between "
                        f"parts of the confirmed network — bridge score "
                        f"{b.bridge_score:.2f}."),
            "explanation": list(b.reasons),
            "details": {"metrics": {"degree": b.degree,
                                    "betweenness": b.betweenness,
                                    "connectivity_impact": b.connectivity_impact,
                                    "cross_case_reach": b.cross_case_reach,
                                    "bridge_score": b.bridge_score,
                                    "is_articulation_point": b.is_articulation_point},
                        "reasons": list(b.reasons)},
            "involved_entity_ids": list(b.entity_ids),
            "supporting_relationship_ids": [],
            "supporting_evidence_ids": sorted(evidence),
            "related_case_ids": [],
            "analysis_method": METHOD_BRIDGE,
        })
    return out


def _generate_cross_case(graph: ConfirmedGraph, case_number_by_id: dict,
                         case_id: int) -> list[dict]:
    out = []
    for cc in analyze_cross_case(graph, case_number_by_id, case_id):
        entity_ids: list[int] = []
        evidence: set[int] = set()
        for s in cc.shared_entities:
            entity_ids.extend(s["entity_ids"])
        if cc.example_path:
            for step in cc.example_path:
                info = graph.nodes[step["node_id"]]
                evidence.update(info.evidence_ids)
        out.append({
            "finding_type": "CROSS_CASE_CONNECTION",
            "title": (f"Cross-case link: {cc.case_a_number} ↔ "
                      f"{cc.case_b_number} ({len(cc.shared_entities)} shared "
                      f"confirmed entit{'y' if len(cc.shared_entities) == 1 else 'ies'})"),
            "summary": cc.explanation.split(". ")[0] + ".",
            "explanation": [cc.explanation],
            "details": {"related_case": {"case_id": cc.case_b_id,
                                         "case_number": cc.case_b_number},
                        "shared_entities": cc.shared_entities,
                        "example_path": cc.example_path,
                        "example_path_relationships": cc.example_path_relationships,
                        "connection_kind": cc.connection_kind},
            "involved_entity_ids": sorted(set(entity_ids)),
            "supporting_relationship_ids": [],
            "supporting_evidence_ids": sorted(evidence),
            "related_case_ids": [cc.case_b_id],
            "analysis_method": METHOD_CROSS_CASE,
        })
    return out


def _generate_clusters(graph: ConfirmedGraph, clusters) -> list[dict]:
    out = []
    for c in clusters:
        out.append({
            "finding_type": "NETWORK_CLUSTER",
            "title": f"Network cluster: {c.entity_count} connected entities",
            "summary": c.description,
            "explanation": [
                c.description,
                "Entity types: " + ", ".join(
                    f"{k} ×{v}" for k, v in sorted(c.type_breakdown.items())),
                ("This cluster spans "
                 + str(len(c.case_ids)) + " confirmed cases: "
                 + ", ".join("case " + str(x) for x in c.case_ids))
                if c.cross_case else
                "All members belong to a single case.",
                f"Most central member: {c.key_bridge['display_name']} "
                f"(bridge score {c.key_bridge['bridge_score']:.2f})."
                if c.key_bridge else
                "No entity in this cluster scores as a bridge."],
            "details": {"members": c.display_names,
                        "type_breakdown": c.type_breakdown,
                        "case_ids": c.case_ids,
                        "key_bridge": c.key_bridge,
                        "subgroups": c.subgroups},
            "involved_entity_ids": list(c.entity_ids),
            "supporting_relationship_ids": [],
            "supporting_evidence_ids": [],
            "related_case_ids": list(c.case_ids),
            "analysis_method": METHOD_CLUSTER,
        })
    return out


def _generate_hubs(graph: ConfirmedGraph, metrics_list) -> list[dict]:
    out = []
    for rank, m in enumerate(high_connectivity(metrics_list), start=1):
        out.append({
            "finding_type": "HIGH_CONNECTIVITY",
            "title": f"Highly connected entity: {m.display_name}",
            "summary": (f"{m.display_name} ({m.entity_type}) has {m.degree} "
                        f"direct confirmed connections — "
                        f"rank {rank} in this case."),
            "explanation": [
                f"Degree {m.degree}: directly linked to {m.degree} other "
                f"confirmed entities.",
                f"Weighted degree {m.weighted_degree} (each relationship "
                f"counts 1 plus its directly-linked evidence records).",
                f"Betweenness centrality {m.betweenness:.3f}"
                + (" — it lies on many shortest paths between other entities."
                   if m.betweenness >= 0.3 else "."),
                f"Part of a connected group of {m.component_size} entities."
                + (f" Its identity appears in {m.cross_case_reach} confirmed cases."
                   if m.cross_case_reach > 1 else "")],
            "details": {"rank": rank, "degree": m.degree,
                        "weighted_degree": m.weighted_degree,
                        "betweenness": m.betweenness,
                        "component_size": m.component_size,
                        "cross_case_reach": m.cross_case_reach},
            "involved_entity_ids": [m.entity_id],
            "supporting_relationship_ids": [],
            "supporting_evidence_ids": [],
            "related_case_ids": [],
            "analysis_method": METHOD_HUB,
        })
    return out


def _all_findings(case_graph: ConfirmedGraph, merged: ConfirmedGraph,
                  case_id: int, case_number_by_id: dict) -> list[dict]:
    metrics_list = compute_metrics(case_graph, merged, case_id)
    bridges = analyze_bridges(case_graph, merged_reach(case_graph, merged))
    bridges_by_node = {b.node_id: {"display_name": b.display_name,
                                   "bridge_score": b.bridge_score}
                       for b in bridges}
    clusters = analyze_clusters(case_graph, bridges_by_node)
    return (_generate_cross_case(merged, case_number_by_id, case_id)
            + _generate_bridges(case_graph, bridges)
            + _generate_hidden(case_graph)
            + _generate_clusters(case_graph, clusters)
            + _generate_hubs(case_graph, metrics_list))


# ------------------------------------------------------------- API surface

def require_case(db: Session, case_id: int) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        not_found("CASE_NOT_FOUND", f"Case {case_id} does not exist.")
    return case


def current_version(db: Session, case_id: int) -> str:
    entities, rels = load_case_records(db, case_id)
    return compute_graph_version(entities, rels)


def run_analysis(db: Session, case: Case, current_user) -> dict:
    """Run the full engine for a case, persist findings (versioned)."""
    entities, rels = load_case_records(db, case.id)
    if not entities or not rels:
        raise ApiError("GRAPH_INSUFFICIENT_DATA",
                       f"Case {case.case_number} has no confirmed graph data "
                       f"to analyze ({len(entities)} entities, "
                       f"{len(rels)} relationships).", 409)

    case_graph, merged, _, _, version = build_graphs(db, case.id)
    if case_graph.is_insufficient():
        record_audit(db, current_user, "GRAPH_ANALYSIS_STARTED",
                     "case", str(case.id),
                     metadata={"reason": "insufficient_confirmed_data"})
        record_audit(db, current_user, "GRAPH_ANALYSIS_FAILED",
                     "case", str(case.id),
                     metadata={"reason": "insufficient_confirmed_data",
                               "nodes": case_graph.node_count,
                               "edges": case_graph.edge_count})
        raise ApiError("GRAPH_INSUFFICIENT_DATA",
                        "Insufficient confirmed graph data. At least "
                        "3 confirmed entities and 2 confirmed relationships "
                        "are needed for a meaningful analysis.", 409)

    # Idempotent: same confirmed data → same version → keep the existing run.
    existing = db.execute(
        select(GraphFinding).where(GraphFinding.case_id == case.id,
                                   GraphFinding.graph_version == version)
    ).scalars().all()
    if existing:
        record_audit(db, current_user, "GRAPH_ANALYSIS_COMPLETED",
                     "case", str(case.id),
                     metadata={"recomputed": False,
                               "graph_version": version,
                               "findings": len(existing)})
        return {"recomputed": False, "graph_version": version,
                "findings": [_finding_payload(db, case.id, f, version)
                             for f in existing]}

    record_audit(db, current_user, "GRAPH_ANALYSIS_STARTED",
                 "case", str(case.id),
                 metadata={"confirmed_entities": case_graph.node_count,
                           "confirmed_relationships": case_graph.edge_count,
                           "graph_version": version})
    try:
        case_number_by_id = {c.id: c.case_number for c in
                             db.execute(select(Case)).scalars().all()}
        generated = _all_findings(case_graph, merged, case.id, case_number_by_id)
        for f in generated:
            db.add(GraphFinding(case_id=case.id, graph_version=version, **f))
        db.commit()
    except Exception as exc:
        db.rollback()
        record_audit(db, current_user, "GRAPH_ANALYSIS_FAILED",
                     "case", str(case.id),
                     metadata={"error": str(exc)[:300],
                               "graph_version": version})
        raise ApiError("GRAPH_ANALYSIS_FAILED",
                       "Graph analysis failed. Check the server logs.",
                       500, details={"reason": str(exc)[:300]}) from exc

    record_audit(db, current_user, "GRAPH_ANALYSIS_COMPLETED",
                 "case", str(case.id),
                 metadata={"recomputed": True, "graph_version": version,
                           "findings": len(generated),
                           "by_type": {t: sum(1 for f in generated
                                               if f["finding_type"] == t)
                                       for t in FINDING_TYPE_ORDER}})
    rows = (db.execute(select(GraphFinding).where(
        GraphFinding.case_id == case.id,
        GraphFinding.graph_version == version)).scalars().all())
    return {"recomputed": True, "graph_version": version,
            "findings": [_finding_payload(db, case.id, f, version) for f in rows],
            "graph": {"nodes": case_graph.node_count,
                      "edges": case_graph.edge_count}}


def _finding_payload(db: Session, case_id: int, f: GraphFinding,
                     current_version_hash: str) -> dict:
    return {
        "id": f.id,
        "case_id": f.case_id,
        "finding_type": f.finding_type,
        "title": f.title,
        "summary": f.summary,
        "explanation": f.explanation or [],
        "details": f.details or {},
        "involved_entity_ids": f.involved_entity_ids or [],
        "supporting_relationship_ids": f.supporting_relationship_ids or [],
        "supporting_evidence_ids": f.supporting_evidence_ids or [],
        "related_case_ids": f.related_case_ids or [],
        "analysis_method": f.analysis_method,
        "graph_version": f.graph_version,
        "stale": f.graph_version != current_version_hash,
        "status": f.status,
        "reviewed_by_name": f.reviewer.name if f.reviewer else None,
        "reviewed_at": f.reviewed_at.isoformat() if f.reviewed_at else None,
        "review_note": f.review_note,
        "created_at": f.created_at.isoformat(),
    }


def list_findings(db: Session, case: Case, include_stale: bool = True) -> dict:
    version = current_version(db, case.id)
    rows = db.execute(
        select(GraphFinding).where(
            GraphFinding.case_id == case.id,
            # stage 4 (investigation intelligence) shares this table with
            # its own finding types; the stage-3 view lists its own types
            GraphFinding.finding_type.in_(FINDING_TYPE_ORDER),
        )
    ).scalars().all()
    type_rank = {t: i for i, t in enumerate(FINDING_TYPE_ORDER)}
    rows.sort(key=lambda f: (0 if f.graph_version == version else 1,
                             type_rank.get(f.finding_type, 99), f.id))
    current = [_finding_payload(db, case.id, f, version)
               for f in rows if f.graph_version == version]
    stale = [_finding_payload(db, case.id, f, version)
             for f in rows if f.graph_version != version]
    return {"graph_version": version,
            "current_findings": current,
            "stale_findings": stale if include_stale else [],
            "analyzed": bool(current)}


def apply_review(db: Session, case: Case, finding: GraphFinding,
                 current_user, action: str, note: str | None) -> dict:
    """Review or dismiss a finding (audit kept; nothing is deleted)."""
    if action not in ("reviewed", "dismissed"):
        raise ApiError("INVALID_REVIEW_ACTION",
                       "action must be 'reviewed' or 'dismissed'.", 400)
    if finding.status != "ACTIVE":
        raise ApiError("FINDING_REVIEW_NOT_ALLOWED",
                       f"This finding is already {finding.status}; it cannot "
                       f"be re-reviewed.", 409)
    finding.status = "REVIEWED" if action == "reviewed" else "DISMISSED"
    finding.reviewed_by = current_user.user.id
    finding.reviewed_at = datetime.now(timezone.utc)
    finding.review_note = (note or "")[:255] or None
    db.commit()
    record_audit(db, current_user,
                 "FINDING_REVIEWED" if action == "reviewed" else "FINDING_DISMISSED",
                 "graph_finding", str(finding.id),
                 metadata={"case_id": case.id, "finding_type": finding.finding_type,
                           "status": finding.status, "note": finding.review_note})
    return _finding_payload(db, case.id, finding,
                            current_version(db, case.id))


def require_finding(db: Session, case_id: int, finding_id: int) -> GraphFinding:
    finding = db.get(GraphFinding, finding_id)
    if finding is None or finding.case_id != case_id:
        not_found("FINDING_NOT_FOUND", f"Finding {finding_id} not found in this case.")
    return finding
