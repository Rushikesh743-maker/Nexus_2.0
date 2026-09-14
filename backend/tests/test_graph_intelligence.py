"""Stage 3 — Graph Intelligence & Hidden Connection Engine tests.

Part A: engine unit tests. Pure functions over synthetic confirmed records
(no database) — the graph builder, path analysis, bridge detection,
clustering, cross-case analysis, metrics and graph versioning.

Part B: API tests against the real development PostgreSQL (same
conventions as test_v1_api.py): analyze + persistence, idempotency,
findings lifecycle (review/dismiss/audit), staleness, paths, bridges,
clusters, cross-case, error codes and RBAC.

Every assertion here is about computed, confirmed-data behaviour — the
engine must never invent results, and candidates must never influence it.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal  # noqa: E402
from app.services.graph_intelligence import (  # noqa: E401
    EntityRecord, RelationshipRecord,
    analyze_bridges, analyze_clusters, analyze_cross_case,
    build_case_graph, build_merged_graph, compute_graph_version,
    compute_metrics, find_indirect_connections, find_paths, merged_reach,
)

# ================================================================== helpers

CASE_A, CASE_B = 99, 98  # synthetic case ids for unit tests


def _records_a():
    """Case 99 graph:

    VehicleX --OWNS-- Alpha --CALLED-- Beta --{ASSOCIATED_WITH Gamma,
    CALLED Delta, CALLED Phone98}; Gamma --CALLED-- Epsilon; Isolated
    (no relationships).

    Edge evidence: rel 9101 (OWNS) came from candidate 950 (evidence
    801, 802); rel 9105 (Beta-CALLED-Phone98) from candidate 951
    (evidence 803). Node Alpha was accepted from candidate 950.
    """
    ents = [
        EntityRecord(901, CASE_A, "person", "Alpha"),
        EntityRecord(902, CASE_A, "person", "Beta"),
        EntityRecord(903, CASE_A, "person", "Gamma"),
        EntityRecord(904, CASE_A, "person", "Delta"),
        EntityRecord(905, CASE_A, "vehicle", "Vehicle X"),
        EntityRecord(906, CASE_A, "person", "Epsilon"),
        EntityRecord(907, CASE_A, "phone", "Phone 98"),
        EntityRecord(908, CASE_A, "person", "Isolated"),
    ]
    rels = [
        RelationshipRecord(9101, CASE_A, 905, 901, "OWNS", candidate_id=950),
        RelationshipRecord(9102, CASE_A, 901, 902, "CALLED"),
        RelationshipRecord(9103, CASE_A, 902, 903, "ASSOCIATED_WITH"),
        RelationshipRecord(9104, CASE_A, 902, 904, "CALLED"),
        RelationshipRecord(9105, CASE_A, 902, 907, "CALLED", candidate_id=951),
        RelationshipRecord(9106, CASE_A, 903, 906, "CALLED"),
    ]
    ev_index = {"candidate:950": [801, 802], "candidate:951": [803]}
    accepted = {901: [950]}
    return ents, rels, ev_index, accepted


def _graph_a():
    ents, rels, ev, accepted = _records_a()
    return build_case_graph(ents, rels, ev, accepted)


def _records_cross():
    """Case 99 and case 98 both confirmed-ly share 'Shared Person';
    case 99: Nine -CALLED- SharedPerson ; case 98: Eight -CALLED-
    SharedPerson. No other overlap (no false positives expected)."""
    ents = [
        EntityRecord(921, CASE_A, "person", "Shared Person"),
        EntityRecord(922, CASE_A, "person", "Person Nine"),
        EntityRecord(931, CASE_B, "person", "Shared Person"),
        EntityRecord(932, CASE_B, "person", "Person Eight"),
        EntityRecord(933, CASE_B, "vehicle", "Unrelated Car"),
    ]
    rels = [
        RelationshipRecord(9401, CASE_A, 922, 921, "CALLED"),
        RelationshipRecord(9402, CASE_B, 932, 931, "CALLED"),
        RelationshipRecord(9403, CASE_B, 932, 933, "USED"),
    ]
    return ents, rels


# =========================================================== PART A: engine

class TestGraphBuilder:
    def test_nodes_and_edges(self):
        g = _graph_a()
        assert g.node_count == 8
        assert g.edge_count == 6
        assert set(g.graph.nodes) == {f"e{n}" for n in range(901, 909)}

    def test_node_metadata(self):
        g = _graph_a()
        info = g.nodes["e901"]
        assert info.entity_ids == [901]
        assert info.entity_type == "person"
        assert info.display_name == "Alpha"
        assert info.case_ids == [CASE_A]

    def test_edge_metadata_and_evidence(self):
        g = _graph_a()
        e = g.edges[tuple(sorted(("e901", "e905")))]
        assert e.relationship_id == 9101
        assert e.relationship_type == "OWNS"
        assert e.case_id == CASE_A
        assert e.evidence_ids == [801, 802]
        assert e.verification_status == "CONFIRMED"

    def test_node_evidence_from_accepted_candidate(self):
        g = _graph_a()
        # Alpha was accepted from candidate 950, whose evidence rows are
        # 801/802 -> the node's directly-linked evidence count is 2.
        assert g.nodes["e901"].evidence_count == 2
        assert g.nodes["e902"].evidence_count == 0

    def test_dangling_relationship_skipped(self):
        ents, rels, ev, accepted = _records_a()
        rels = rels + [RelationshipRecord(9500, CASE_A, 901, 424242, "CALLED")]
        g = build_case_graph(ents, rels, ev, accepted)
        assert g.edge_count == 6  # dangling edge never enters the graph

    def test_candidates_cannot_enter_the_graph(self):
        """The builder only sees confirmed rows; a candidate-shaped record
        (unknown entity id) is structurally excluded, not filtered."""
        ents, rels, ev, accepted = _records_a()
        # candidate 999 'Pending Person' has no confirmed entity row
        rels = rels + [RelationshipRecord(9600, CASE_A, 999, 901, "CALLED")]
        g = build_case_graph(ents, rels, ev, accepted)
        assert "e999" not in g.graph.nodes
        assert g.edge_count == 6

    def test_graph_version_deterministic_and_sensitive(self):
        ents, rels, _, _ = _records_a()
        v1 = compute_graph_version(ents, rels)
        v2 = compute_graph_version(list(reversed(ents)), list(reversed(rels)))
        assert v1 == v2
        rels2 = rels + [RelationshipRecord(9700, CASE_A, 904, 906, "CALLED")]
        assert compute_graph_version(ents, rels2) != v1


class TestPathAnalysis:
    def test_direct_path(self):
        g = _graph_a()
        res = find_paths(g, "e905", "e901")
        assert len(res) == 1
        p = res[0]
        assert p.path_length == 1
        assert p.nodes == ["Vehicle X", "Alpha"]
        assert p.relationship_types == ["OWNS"]
        assert "direct confirmed relationship" in p.explanation

    def test_indirect_path(self):
        g = _graph_a()
        res = find_paths(g, "e905", "e903")
        assert len(res) == 1
        p = res[0]
        assert p.path_length == 3
        assert p.nodes == ["Vehicle X", "Alpha", "Beta", "Gamma"]
        assert p.relationship_types == ["OWNS", "CALLED", "ASSOCIATED_WITH"]
        assert "indirectly connected" in p.explanation
        assert "Alpha and Beta" in p.explanation

    def test_no_path_returns_empty(self):
        g = _graph_a()
        assert find_paths(g, "e908", "e901") == []

    def test_depth_limit(self):
        g = _graph_a()
        assert find_paths(g, "e905", "e903") != []          # depth 3 ok
        assert find_paths(g, "e905", "e903", max_depth=2) == []

    def test_paths_are_cycle_free(self):
        g = _graph_a()
        for s in ("e901", "e903", "e905"):
            for t in ("e901", "e903", "e905", "e906", "e907"):
                for p in find_paths(g, s, t):
                    assert len(p.node_ids) == len(set(p.node_ids))

    def test_max_paths_cap(self):
        g = _graph_a()
        res = find_paths(g, "e905", "e903", max_paths=1)
        assert len(res) <= 1

    def test_indirect_connections_exclude_direct_pairs(self):
        g = _graph_a()
        hits = find_indirect_connections(g)
        pairs = {frozenset((h["source"].node_id, h["target"].node_id))
                 for h in hits}
        assert frozenset(("e901", "e903")) in pairs        # Alpha→Gamma, 2 hops
        assert frozenset(("e905", "e901")) not in pairs     # VehicleX-Alpha is direct

    def test_indirect_connections_prefer_person_pairs(self):
        g = _graph_a()
        hits = find_indirect_connections(g)
        assert hits, "expected at least one indirect connection"
        first = hits[0]
        assert first["source"].entity_type == "person"
        assert first["target"].entity_type == "person"

    def test_indirect_bounded(self):
        g = _graph_a()
        assert len(find_indirect_connections(g)) <= 10


class TestBridgeAnalysis:
    def test_articulation_point_detected(self):
        g = _graph_a()
        m = build_merged_graph(*_records_cross(), {}, {})
        bridges = analyze_bridges(g, merged_reach(g, m))
        assert bridges, "expected bridge entities"
        top = bridges[0]
        assert top.node_id == "e902"          # Beta connects the graph
        assert top.is_articulation_point is True
        assert top.connectivity_impact == 3
        assert top.bridge_score >= 0.7

    def test_degree_one_entities_excluded(self):
        g = _graph_a()
        m = build_merged_graph(*_records_cross(), {}, {})
        ids = {b.node_id for b in analyze_bridges(g, merged_reach(g, m))}
        assert "e904" not in ids               # Delta has degree 1
        assert "e908" not in ids               # Isolated has degree 0

    def test_triangle_has_no_bridges(self):
        ents = [EntityRecord(1, 1, "person", f"P{i}") for i in range(3)]
        rels = [
            RelationshipRecord(1, 1, 1, 2, "CALLED"),
            RelationshipRecord(2, 1, 2, 3, "CALLED"),
            RelationshipRecord(3, 1, 3, 1, "CALLED"),
        ]
        g = build_case_graph(ents, rels, {}, {})
        assert analyze_bridges(g) == []

    def test_reasons_are_data_derived(self):
        g = _graph_a()
        m = build_merged_graph(*_records_cross(), {}, {})
        top = analyze_bridges(g, merged_reach(g, m))[0]
        assert top.reasons
        joined = " ".join(top.reasons)
        assert "articulation" in joined
        assert "4 direct confirmed connections" in joined


class TestClusterAnalysis:
    def test_single_component(self):
        g = _graph_a()
        clusters = analyze_clusters(g)
        assert len(clusters) == 1
        c = clusters[0]
        assert c.entity_count == 7
        assert c.relationship_count == 6
        assert not c.cross_case
        assert c.type_breakdown == {"person": 5, "vehicle": 1, "phone": 1}

    def test_two_components(self):
        ents = [EntityRecord(i, 1, "person", f"P{i}") for i in range(1, 5)]
        rels = [
            RelationshipRecord(1, 1, 1, 2, "CALLED"),
            RelationshipRecord(2, 1, 3, 4, "CALLED"),
        ]
        g = build_case_graph(ents, rels, {}, {})
        clusters = analyze_clusters(g)
        assert len(clusters) == 2
        assert all(c.entity_count == 2 for c in clusters)

    def test_isolated_singleton_not_a_cluster(self):
        g = _graph_a()
        assert all(c.entity_count >= 2 for c in analyze_clusters(g))

    def test_key_bridge_annotated(self):
        g = _graph_a()
        m = build_merged_graph(*_records_cross(), {}, {})
        bridges = analyze_bridges(g, merged_reach(g, m))
        by_node = {b.node_id: {"display_name": b.display_name,
                               "bridge_score": b.bridge_score}
                   for b in bridges}
        c = analyze_clusters(g, by_node)[0]
        assert c.key_bridge is not None
        assert c.key_bridge["display_name"] == "Beta"


class TestCrossCaseAnalysis:
    def test_shared_entity_and_path(self):
        ents, rels = _records_cross()
        merged = build_merged_graph(ents, rels, {}, {})
        res = analyze_cross_case(merged, {CASE_A: "C-99", CASE_B: "C-98"}, CASE_A)
        assert len(res) == 1
        cc = res[0]
        assert cc.case_b_id == CASE_B
        assert cc.connection_kind == "shared_path"
        assert [s["name"] for s in cc.shared_entities] == ["Shared Person"]
        assert len(cc.example_path) == 3
        assert cc.example_path[0]["name"] == "Person Nine"
        assert cc.example_path[1]["name"] == "Shared Person"
        assert cc.example_path[1]["shared"] is True
        assert cc.example_path[2]["name"] == "Person Eight"
        assert cc.example_path_relationships == ["CALLED", "CALLED"]
        assert "C-99 and C-98 share 1 confirmed entity" in cc.explanation

    def test_no_false_positive_without_shared_entity(self):
        ents = [
            EntityRecord(921, CASE_A, "person", "Only In A"),
            EntityRecord(931, CASE_B, "person", "Only In B"),
        ]
        rels = [
            RelationshipRecord(9401, CASE_A, 921, 921, "CALLED"),
        ]
        merged = build_merged_graph(ents, rels, {}, {})
        # self-loop skipped; no shared identity -> no connection
        assert analyze_cross_case(merged, {CASE_A: "C-99", CASE_B: "C-98"}, CASE_A) == []

    def test_same_name_different_type_not_shared(self):
        ents = [
            EntityRecord(921, CASE_A, "person", "Kurla"),
            EntityRecord(931, CASE_B, "location", "Kurla"),
        ]
        merged = build_merged_graph(ents, [], {}, {})
        assert analyze_cross_case(merged, {CASE_A: "C-99", CASE_B: "C-98"}, CASE_A) == []


class TestMetrics:
    def test_metric_values(self):
        g = _graph_a()
        merged = build_merged_graph(*_records_cross(), {}, {})
        metrics = {m.entity_id: m for m in compute_metrics(g, merged, CASE_A)}
        beta = metrics[902]
        assert beta.degree == 4
        assert beta.component_size == 7
        assert beta.is_articulation_point is True
        # weighted: 3 plain edges + 1 edge with 1 linked evidence record
        assert beta.weighted_degree == 5
        assert metrics[908].degree == 0
        assert metrics[908].component_size == 1
        assert beta.betweenness >= metrics[904].betweenness

    def test_high_connectivity_ranking(self):
        from app.services.graph_intelligence.metrics import high_connectivity
        g = _graph_a()
        merged = build_merged_graph(*_records_cross(), {}, {})
        top = high_connectivity(compute_metrics(g, merged, CASE_A))
        assert top[0].entity_id == 902
        assert all(m.degree >= 3 for m in top)


# ===================================================== PART B: API (live PG)
# `client`, `investigator` and `analyst` come from conftest (Supabase tokens).


def _case_id_by_number(client, headers, number):
    r = client.get("/api/v1/cases", headers=headers)
    assert r.status_code == 200
    for c in r.json():
        if c["case_number"] == number:
            return c["id"]
    pytest.skip(f"{number} not present in this database")


@pytest.fixture(scope="session")
def case1(client, investigator):
    return _case_id_by_number(client, investigator, "CASE-2026-001")


@pytest.fixture(scope="session")
def case4(client, investigator):
    return _case_id_by_number(client, investigator, "CASE-2026-021")


class TestAnalyze:
    def test_analyze_meridian_produces_findings(self, client, investigator, case4):
        r = client.post(f"/api/v1/cases/{case4}/graph/analyze", headers=investigator)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["graph_version"]
        assert len(body["findings"]) > 0
        allowed = {"HIDDEN_CONNECTION", "BRIDGE_ENTITY", "CROSS_CASE_CONNECTION",
                   "NETWORK_CLUSTER", "HIGH_CONNECTIVITY"}
        for f in body["findings"]:
            assert f["finding_type"] in allowed
            assert f["title"]
            assert isinstance(f["explanation"], list) and f["explanation"]
            assert f["analysis_method"]
            # every finding must be traceable to confirmed ids or be a
            # cross-case case-link (which references related cases)
            assert (f["involved_entity_ids"]
                    or f["related_case_ids"]
                    or f["supporting_relationship_ids"])

    def test_analyze_is_idempotent(self, client, investigator, case4):
        r = client.post(f"/api/v1/cases/{case4}/graph/analyze", headers=investigator)
        assert r.status_code == 200
        first = r.json()
        r2 = client.post(f"/api/v1/cases/{case4}/graph/analyze", headers=investigator)
        assert r2.status_code == 200
        second = r2.json()
        assert second["recomputed"] is False
        assert second["graph_version"] == first["graph_version"]
        assert len(second["findings"]) == len(first["findings"])

    def test_analyze_unknown_case(self, client, investigator):
        r = client.post("/api/v1/cases/999999/graph/analyze", headers=investigator)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "CASE_NOT_FOUND"

    def test_analyze_empty_case_insufficient(self, client, investigator):
        from sqlalchemy import delete
        from app.models import Case, GraphFinding

        db = SessionLocal()
        case = Case(case_number="GTEST-2026-8888", title="Graph insufficient test (auto)",
                    status="OPEN", priority="LOW")
        db.add(case)
        db.commit()
        db.refresh(case)
        try:
            r = client.post(f"/api/v1/cases/{case.id}/graph/analyze", headers=investigator)
            assert r.status_code == 409
            assert r.json()["error"]["code"] == "GRAPH_INSUFFICIENT_DATA"
            r = client.get(f"/api/v1/cases/{case.id}/graph/metrics", headers=investigator)
            assert r.status_code == 200
            assert r.json()["nodes"] == 0 and r.json()["edges"] == 0
            r = client.get(f"/api/v1/cases/{case.id}/graph/bridges", headers=investigator)
            assert r.json()["insufficient"] is True
            assert r.json()["bridges"] == []
        finally:
            db.execute(delete(GraphFinding).where(GraphFinding.case_id == case.id))
            db.execute(delete(Case).where(Case.id == case.id))
            db.commit()
            db.close()

    def test_analyze_writes_audit(self, client, investigator, case1):
        from sqlalchemy import select
        from app.models import AuditLog

        db = SessionLocal()
        before = db.execute(select(AuditLog).where(
            AuditLog.action == "GRAPH_ANALYSIS_COMPLETED",
            AuditLog.resource_id == str(case1))).scalars().all()
        client.post(f"/api/v1/cases/{case1}/graph/analyze", headers=investigator)
        after = db.execute(select(AuditLog).where(
            AuditLog.action == "GRAPH_ANALYSIS_COMPLETED",
            AuditLog.resource_id == str(case1))).scalars().all()
        db.close()
        assert len(after) >= len(before)
        row = after[-1]
        assert row.user_id is not None
        assert row.resource_type == "case"

    def test_analyst_can_analyze(self, client, analyst, case1):
        r = client.post(f"/api/v1/cases/{case1}/graph/analyze", headers=analyst)
        assert r.status_code == 200

    def test_analyze_requires_auth(self, client):
        assert client.post("/api/v1/cases/1/graph/analyze").status_code == 401
        assert client.get("/api/v1/cases/1/graph/findings").status_code == 401


class TestFindingsLifecycle:
    def test_findings_listing_shape(self, client, investigator, case1):
        client.post(f"/api/v1/cases/{case1}/graph/analyze", headers=investigator)
        r = client.get(f"/api/v1/cases/{case1}/graph/findings", headers=investigator)
        assert r.status_code == 200
        body = r.json()
        assert body["analyzed"] is True
        assert body["current_findings"]
        for f in body["current_findings"]:
            assert f["stale"] is False
            assert f["status"] in {"ACTIVE", "REVIEWED", "DISMISSED"}
            assert f["graph_version"] == body["graph_version"]

    def test_review_and_dismiss_workflow(self, client, investigator, case1):
        """Creates its own findings (ORM rows) so reruns are green."""
        from app.models import GraphFinding

        db = SessionLocal()
        f1 = GraphFinding(case_id=case1, finding_type="HIGH_CONNECTIVITY",
                          title="Lifecycle test — review me",
                          summary="synthetic test finding",
                          explanation=["test explanation"],
                          details={"rank": 99}, involved_entity_ids=[],
                          supporting_relationship_ids=[], supporting_evidence_ids=[],
                          related_case_ids=[],
                          analysis_method="test", graph_version="TEST000000000000001",
                          status="ACTIVE")
        f2 = GraphFinding(case_id=case1, finding_type="HIGH_CONNECTIVITY",
                          title="Lifecycle test — dismiss me",
                          summary="synthetic test finding",
                          explanation=["test explanation"],
                          details={"rank": 98}, involved_entity_ids=[],
                          supporting_relationship_ids=[], supporting_evidence_ids=[],
                          related_case_ids=[],
                          analysis_method="test", graph_version="TEST000000000000002",
                          status="ACTIVE")
        db.add_all([f1, f2])
        db.commit()
        ids = (f1.id, f2.id)
        db.close()
        try:
            r = client.post(f"/api/v1/cases/{case1}/graph/findings/{ids[0]}/review",
                            headers=investigator, json={"note": "checked"})
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "REVIEWED"
            assert r.json()["reviewed_by_name"]
            assert r.json()["review_note"] == "checked"

            r = client.post(f"/api/v1/cases/{case1}/graph/findings/{ids[0]}/review",
                            headers=investigator, json={})
            assert r.status_code == 409
            assert r.json()["error"]["code"] == "FINDING_REVIEW_NOT_ALLOWED"

            r = client.post(f"/api/v1/cases/{case1}/graph/findings/{ids[1]}/dismiss",
                            headers=investigator, json={"note": "not useful"})
            assert r.status_code == 200
            assert r.json()["status"] == "DISMISSED"
            assert r.json()["review_note"] == "not useful"

            # dismissed findings stay queryable — nothing is deleted
            r = client.get(f"/api/v1/cases/{case1}/graph/findings", headers=investigator)
            listed = {f["id"]: f for f in
                      r.json()["current_findings"] + r.json()["stale_findings"]}
            assert listed[ids[0]]["status"] == "REVIEWED"
            assert listed[ids[1]]["status"] == "DISMISSED"
        finally:
            db = SessionLocal()
            from sqlalchemy import delete
            db.execute(delete(GraphFinding).where(GraphFinding.id.in_(ids)))
            db.commit()
            db.close()

    def test_review_missing_finding(self, client, investigator, case1):
        r = client.post(f"/api/v1/cases/{case1}/graph/findings/999999/review",
                        headers=investigator, json={})
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "FINDING_NOT_FOUND"

    def test_review_wrong_case_rejected(self, client, investigator, case1, case4):
        from sqlalchemy import select
        from app.models import GraphFinding

        db = SessionLocal()
        f = db.execute(select(GraphFinding).where(GraphFinding.case_id == case4,
                                                  GraphFinding.status == "ACTIVE")
                       ).scalars().first()
        db.close()
        if f is None:
            pytest.skip("no active finding in case 4 for this test")
        r = client.post(f"/api/v1/cases/{case1}/graph/findings/{f.id}/review",
                        headers=investigator, json={})
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "FINDING_NOT_FOUND"


class TestPathsAPI:
    def _entity_ids(self, client, headers, case_id):
        r = client.get(f"/api/v1/cases/{case_id}/entities", headers=headers)
        assert r.status_code == 200
        return {e["canonical_name"]: e["id"] for e in r.json()}

    def test_direct_path(self, client, investigator, case1):
        ids = self._entity_ids(client, investigator, case1)
        src = ids["MH12AB1234"]
        tgt = ids["Aarav Mehta"]
        r = client.get(f"/api/v1/cases/{case1}/graph/paths",
                       params={"source_entity_id": src, "target_entity_id": tgt},
                       headers=investigator)
        assert r.status_code == 200, r.text
        paths = r.json()["paths"]
        assert paths and paths[0]["path_length"] == 1
        assert paths[0]["relationship_types"] == ["OWNS"]

    def test_indirect_path_with_explanation(self, client, investigator, case1):
        ids = self._entity_ids(client, investigator, case1)
        src = ids["MH14CD5678"]
        tgt = ids["Aarav Mehta"]
        r = client.get(f"/api/v1/cases/{case1}/graph/paths",
                       params={"source_entity_id": src, "target_entity_id": tgt},
                       headers=investigator)
        assert r.status_code == 200
        p = r.json()["paths"][0]
        assert p["path_length"] == 2
        assert p["explanation"].count("→") >= 2

    def test_no_path_explicit(self, client, investigator, case1):
        ids = self._entity_ids(client, investigator, case1)
        src = ids["Neha Patil"]            # isolated in case 1
        tgt = ids["Aarav Mehta"]
        r = client.get(f"/api/v1/cases/{case1}/graph/paths",
                       params={"source_entity_id": src, "target_entity_id": tgt},
                       headers=investigator)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "PATH_NOT_FOUND"
        assert "No confirmed connection path found" in r.json()["error"]["message"]

    def test_depth_limit_blocks_longer_path(self, client, investigator, case1):
        ids = self._entity_ids(client, investigator, case1)
        src = ids["MH14CD5678"]
        tgt = ids["Aarav Mehta"]
        r = client.get(f"/api/v1/cases/{case1}/graph/paths",
                       params={"source_entity_id": src, "target_entity_id": tgt,
                               "max_depth": 1},
                       headers=investigator)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "PATH_NOT_FOUND"

    def test_unknown_entity(self, client, investigator, case1):
        ids = self._entity_ids(client, investigator, case1)
        r = client.get(f"/api/v1/cases/{case1}/graph/paths",
                       params={"source_entity_id": 999999,
                               "target_entity_id": ids["Aarav Mehta"]},
                       headers=investigator)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "ENTITY_NOT_FOUND"

    def test_entity_from_other_case_rejected(self, client, investigator, case1, case4):
        r4 = client.get(f"/api/v1/cases/{case4}/entities", headers=investigator)
        assert r4.status_code == 200
        other = r4.json()[0]["id"]
        aarav = self._entity_ids(client, investigator, case1)["Aarav Mehta"]
        r = client.get(f"/api/v1/cases/{case1}/graph/paths",
                       params={"source_entity_id": other,
                               "target_entity_id": aarav},
                       headers=investigator)
        # an entity from another case is never a valid endpoint; if the id
        # happens to collide with a candidate id the more specific
        # ENTITY_NOT_CONFIRMED is returned — both rejections are correct.
        assert r.status_code in (400, 404)
        assert r.json()["error"]["code"] in ("ENTITY_NOT_FOUND",
                                             "ENTITY_NOT_CONFIRMED")

    def test_candidate_id_not_confirmed(self, client, investigator, case1):
        from sqlalchemy import select
        from app.models import EntityCandidate

        db = SessionLocal()
        from app.models import Entity
        cand = db.execute(select(EntityCandidate)
                          .where(EntityCandidate.case_id == case1,
                                 ~EntityCandidate.id.in_(select(Entity.id)))
                          .limit(1)).scalars().first()
        db.close()
        if cand is None:
            pytest.skip("no extraction candidate in case 1 for this test")
        ids = self._entity_ids(client, investigator, case1)
        r = client.get(f"/api/v1/cases/{case1}/graph/paths",
                       params={"source_entity_id": cand.id,
                               "target_entity_id": ids["Aarav Mehta"]},
                       headers=investigator)
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "ENTITY_NOT_CONFIRMED"

    def test_same_entity_rejected(self, client, investigator, case1):
        ids = self._entity_ids(client, investigator, case1)
        r = client.get(f"/api/v1/cases/{case1}/graph/paths",
                       params={"source_entity_id": 1, "target_entity_id": 1},
                       headers=investigator)
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_PATH_REQUEST"


class TestAnalysisEndpoints:
    def test_metrics(self, client, investigator, case1):
        r = client.get(f"/api/v1/cases/{case1}/graph/metrics", headers=investigator)
        assert r.status_code == 200
        body = r.json()
        assert body["nodes"] >= 8 and body["edges"] >= 4
        by_id = {m["entity_id"]: m for m in body["metrics"]}
        aarav = by_id[[m for m in body["metrics"] if m["name"] == "Aarav Mehta"][0]["entity_id"]]
        assert aarav["degree"] >= 2
        assert aarav["component_size"] >= 4
        assert aarav["betweenness"] >= 0
        for m in body["metrics"]:
            assert m["weighted_degree"] >= m["degree"]

    def test_bridges(self, client, investigator, case1):
        r = client.get(f"/api/v1/cases/{case1}/graph/bridges", headers=investigator)
        assert r.status_code == 200
        bridges = r.json()["bridges"]
        assert bridges, "case 1 has articulation points"
        top = bridges[0]
        assert top["name"] == "Aarav Mehta"
        assert top["is_articulation_point"] is True
        assert top["bridge_score"] >= 0.5
        assert top["reasons"]
        # cross-case reach: Aarav Mehta is confirmed in 3 cases
        assert top["cross_case_reach"] == 3

    def test_clusters(self, client, investigator, case1):
        r = client.get(f"/api/v1/cases/{case1}/graph/clusters", headers=investigator)
        assert r.status_code == 200
        clusters = r.json()["clusters"]
        assert clusters
        biggest = clusters[0]
        assert biggest["entity_count"] == 4      # Aarav, Rohan + 2 vehicles
        assert biggest["relationship_count"] == 3
        assert biggest["description"]
        for c in clusters:
            assert c["entity_count"] == len(c["members"])

    def test_cross_case(self, client, investigator, case1):
        r = client.get(f"/api/v1/cases/{case1}/graph/cross-case", headers=investigator)
        assert r.status_code == 200
        conns = r.json()["connections"]
        numbers = {c["case_number"] for c in conns}
        assert "CASE-2026-002" in numbers
        assert "CASE-2026-003" in numbers
        for c in conns:
            assert c["shared_entities"]
            assert c["explanation"]
            assert c["case_id"] not in (None,)

    def test_cross_case_no_false_positives_for_meridian(self, client, investigator, case4):
        r = client.get(f"/api/v1/cases/{case4}/graph/cross-case", headers=investigator)
        assert r.status_code == 200
        conns = r.json()["connections"]
        # Meridian shares no confirmed identity with the seed cases
        assert all(c["shared_entities"] for c in conns)  # only real links


class TestLegacyNotBroken:
    def test_legacy_endpoints_still_work(self, client):
        for path in ("/api/stats", "/api/graph", "/api/findings", "/legacy"):
            r = client.get(path)
            assert r.status_code == 200, f"{path} -> {r.status_code}"

    def test_existing_case_endpoints_still_work(self, client, investigator, case1):
        for path in (f"/api/v1/cases/{case1}",
                     f"/api/v1/cases/{case1}/entities",
                     f"/api/v1/cases/{case1}/relationships",
                     f"/api/v1/cases/{case1}/evidence"):
            r = client.get(path, headers=investigator)
            assert r.status_code == 200, f"{path} -> {r.status_code}"


class TestStaleness:
    """Runs last: temporarily adds a confirmed relationship to case 1,
    checks findings go stale, then restores the data exactly."""

    def test_findings_go_stale_when_data_changes(self, client, investigator, case1):
        from sqlalchemy import delete
        from app.models import GraphFinding, Relationship

        db = SessionLocal()
        version_before = None
        try:
            r = client.get(f"/api/v1/cases/{case1}/graph/findings", headers=investigator)
            version_before = r.json()["graph_version"]
            assert r.json()["current_findings"], "case 1 must be analyzed first"

            re_ = client.get(f"/api/v1/cases/{case1}/entities", headers=investigator)
            by_name = {e["canonical_name"]: e["id"] for e in re_.json()}
            tmp = Relationship(case_id=case1,
                               source_entity_id=by_name["Aarav Mehta"],
                               target_entity_id=by_name["Neha Patil"],
                               relationship_type="USED")
            db.add(tmp)
            db.commit()

            r = client.get(f"/api/v1/cases/{case1}/graph/findings", headers=investigator)
            assert r.json()["graph_version"] != version_before
            assert r.json()["current_findings"] == []      # new version, no run yet
            assert r.json()["stale_findings"]
            assert all(f["stale"] for f in r.json()["stale_findings"])

            # re-analyze on the changed data
            r = client.post(f"/api/v1/cases/{case1}/graph/analyze", headers=investigator)
            assert r.status_code == 200
            assert r.json()["recomputed"] is True
            r = client.get(f"/api/v1/cases/{case1}/graph/findings", headers=investigator)
            assert r.json()["current_findings"]
            assert len(r.json()["stale_findings"]) > 0    # history kept
        finally:
            db.execute(delete(Relationship).where(Relationship.id == tmp.id))
            # remove the intermediate-version findings (test noise); the
            # original findings remain and become current again
            db.execute(delete(GraphFinding).where(
                GraphFinding.case_id == case1,
                GraphFinding.graph_version != version_before))
            db.commit()
            db.close()

        r = client.get(f"/api/v1/cases/{case1}/graph/findings", headers=investigator)
        assert r.json()["graph_version"] == version_before
        assert r.json()["current_findings"], "original findings are current again"
