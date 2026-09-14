"""Stage 4 — Investigation Reasoning & Evidence Intelligence tests.

Part A: engine unit tests — pure functions over synthetic confirmed
records (no database), the same convention as the stage-3 engine tests.
Every rule is deterministic and documented; the engines must never
fabricate records and must report insufficient data explicitly.

Part B: API tests against the real development PostgreSQL (same
conventions as test_graph_intelligence.py): analyze + persistence,
idempotency, contradictions (via the labeled SYNTHETIC DEMONSTRATION
demo case), hypotheses, evidence impact + in-memory simulation,
timeline, geospatial, gaps, finding/hypothesis lifecycle with audit,
RBAC, candidate exclusion, stale -> re-analyze, and stage-3 regression
(the graph endpoint must still list only stage-3 finding types).
"""

import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal  # noqa: E402
from app.services.graph_intelligence.graph_builder import (  # noqa: E402
    EntityRecord, RelationshipRecord)
from app.services.investigation_intelligence import (  # noqa: E401
    contradiction_engine, evidence_impact, gap_engine,
    geospatial_engine, hypothesis_engine, timeline_engine)
from app.services.investigation_intelligence.data import (  # noqa: E402
    EventRecord, EvidenceRecord, LocationRecord, Stage4Data,
    compute_stage4_version)

STAGE4_TYPES = {"CONTRADICTION", "TIMELINE_INSIGHT", "GEO_INSIGHT",
                "INVESTIGATION_GAP"}
STAGE3_TYPES = {"HIDDEN_CONNECTION", "BRIDGE_ENTITY",
                "CROSS_CASE_CONNECTION", "NETWORK_CLUSTER",
                "HIGH_CONNECTIVITY"}


# ----------------------------------------------------------------- helpers
def _data(case_id=999, **kw) -> Stage4Data:
    from app.services.graph_intelligence.graph_builder import normalize_name
    d = Stage4Data(case_id=case_id, **kw)
    d.entities_by_id = {e.id: e for e in d.entities}
    d.locations_by_name = {normalize_name(l.name): l for l in d.locations}
    for r in d.relationships:
        d.rels_by_pair.setdefault((r.source_entity_id, r.target_entity_id),
                                  []).append(r.id)
    return d


def _ents(*pairs):
    return [EntityRecord(i, 999, t, n) for i, (t, n) in enumerate(pairs, 1)]


def _evts(*rows):
    """rows: (id, entity_id, location_id, ts, type)"""
    return [EventRecord(r[0], 999, r[4], r[3], None, r[1], r[2], None)
            for r in rows]


def _loc(name, lat, lon, loc_id=1, case_id=999):
    return LocationRecord(loc_id, case_id, name, lat, lon)


# ================================================================== part A
class TestVersioning:
    def test_version_deterministic(self):
        d1 = _data(entities=_ents(("person", "A")),
                   relationships=[RelationshipRecord(1, 999, 1, 2, "OWNS")])
        d2 = _data(entities=_ents(("person", "A")),
                   relationships=[RelationshipRecord(1, 999, 1, 2, "OWNS")])
        assert compute_stage4_version(d1) == compute_stage4_version(d2)

    def test_version_extends_stage3_hash_with_evidence_events_locations(self):
        base = dict(entities=_ents(("person", "A"), ("person", "B")),
                    relationships=[RelationshipRecord(1, 999, 1, 2, "OWNS")])
        v0 = compute_stage4_version(_data(**base))
        v_ev = compute_stage4_version(_data(
            evidence=[EvidenceRecord(1, 999, "document", 1, "x")], **base))
        v_ts = compute_stage4_version(_data(
            events=[EventRecord(1, 999, "sighting",
                                datetime(2026, 1, 1, 9, 0), None, 1, 1, None)],
            **base))
        v_loc = compute_stage4_version(_data(
            locations=[_loc("L", 1.0, 2.0)], **base))
        assert len({v0, v_ev, v_ts, v_loc}) == 4

    def test_version_changes_when_event_time_changes(self):
        d = _data(entities=_ents(("person", "A")),
                  events=[EventRecord(1, 999, "sighting",
                                      datetime(2026, 1, 1, 9, 0), None, 1,
                                      None, None)])
        v1 = compute_stage4_version(d)
        d.events[0] = EventRecord(1, 999, "sighting",
                                  datetime(2026, 1, 1, 9, 30), None, 1,
                                  None, None)
        assert compute_stage4_version(d) != v1


class TestContradictionEngine:
    def test_r1_speed_violation_detected(self):
        d = _data(
            entities=_ents(("person", "Aarav")),
            locations=[_loc("Pune", 18.52, 73.86, 1),
                       _loc("Mumbai", 18.94, 72.84, 2)],
            events=_evts((1, 1, 1, datetime(2026, 6, 10, 9, 0), "a"),
                         (2, 1, 2, datetime(2026, 6, 10, 9, 20), "b")))
        out, insufficient = contradiction_engine.detect_contradictions(d)
        types = [c.contradiction_type for c in out]
        assert "TIMELINE_CONTRADICTION" in types
        c = next(c for c in out if c.contradiction_type == "TIMELINE_CONTRADICTION")
        assert c.details["time_difference_min"] == 20.0
        assert c.details["min_travel_min"] > 20.0
        assert c.details["margin"] < 1.0
        assert "100" in " ".join(c.explanation)  # documented speed shown

    def test_r1_no_violation_when_reachable(self):
        d = _data(
            entities=_ents(("person", "Aarav")),
            locations=[_loc("Pune", 18.52, 73.86, 1),
                       _loc("Mumbai", 18.94, 72.84, 2)],
            events=_evts((1, 1, 1, datetime(2026, 6, 10, 9, 0), "a"),
                         (2, 1, 2, datetime(2026, 6, 11, 9, 0), "b")))
        out, _ = contradiction_engine.detect_contradictions(d)
        assert out == []

    def test_r2_identical_timestamp_different_locations(self):
        d = _data(
            entities=_ents(("person", "Rohan")),
            locations=[_loc("Pune A", 18.52, 73.86, 1),
                       _loc("Pune B", 18.58, 73.83, 2)],
            events=_evts((1, 1, 1, datetime(2026, 6, 10, 14, 0), "a"),
                         (2, 1, 2, datetime(2026, 6, 10, 14, 0), "b")))
        out, _ = contradiction_engine.detect_contradictions(d)
        assert [c.contradiction_type for c in out] == ["LOCATION_CONTRADICTION"]
        assert out[0].details["time_difference_min"] == 0

    def test_r3_mutual_owns_only(self):
        d = _data(
            entities=_ents(("person", "V"), ("vehicle", "MH1")),
            relationships=[RelationshipRecord(1, 999, 1, 2, "OWNS"),
                           RelationshipRecord(2, 999, 2, 1, "OWNS")])
        out, _ = contradiction_engine.detect_contradictions(d)
        assert [c.contradiction_type for c in out] == \
            ["RELATIONSHIP_CONTRADICTION"]
        # one-directional ownership is not a contradiction
        d2 = _data(
            entities=_ents(("person", "V"), ("vehicle", "MH1")),
            relationships=[RelationshipRecord(1, 999, 1, 2, "OWNS")])
        assert contradiction_engine.detect_contradictions(d2)[0] == []
        # mutual non-OWNS is not a contradiction (no invented rules)
        d3 = _data(
            entities=_ents(("person", "V"), ("person", "W")),
            relationships=[RelationshipRecord(1, 999, 1, 2, "MET"),
                           RelationshipRecord(2, 999, 2, 1, "MET")])
        assert contradiction_engine.detect_contradictions(d3)[0] == []

    def test_no_coords_is_insufficient_not_contradiction(self):
        d = _data(
            entities=_ents(("person", "A")),
            locations=[LocationRecord(1, 999, "NoCoords", None, None),
                       LocationRecord(2, 999, "NoCoords2", None, None)],
            events=_evts((1, 1, 1, datetime(2026, 6, 10, 9, 0), "a"),
                         (2, 1, 2, datetime(2026, 6, 10, 9, 5), "b")))
        out, insufficient = contradiction_engine.detect_contradictions(d)
        assert out == []
        assert insufficient["pairs_skipped_no_coords"] == 1

    def test_unattributed_events_are_ignored(self):
        d = _data(
            locations=[_loc("Pune", 18.52, 73.86, 1),
                       _loc("Mumbai", 18.94, 72.84, 2)],
            events=_evts((1, None, 1, datetime(2026, 6, 10, 9, 0), "a"),
                         (2, None, 2, datetime(2026, 6, 10, 9, 10), "b")))
        out, _ = contradiction_engine.detect_contradictions(d)
        assert out == []

    def test_cap_fifteen(self):
        ents = _ents(*[("person", f"P{i}") for i in range(16)])
        locs = [_loc(f"L{i}a", 18.0 + i * 0.1, 73.0, i * 10 + 1)
                for i in range(16)] + \
               [_loc(f"L{i}b", 19.0 + i * 0.1, 72.0, i * 10 + 2)
                for i in range(16)]
        evs = []
        for i in range(16):
            evs.append((i * 2 + 1, i + 1, i * 10 + 1,
                        datetime(2026, 6, 10, 9, 0), "a"))
            evs.append((i * 2 + 2, i + 1, i * 10 + 2,
                        datetime(2026, 6, 10, 9, 1), "b"))
        d = _data(entities=ents, locations=locs, events=_evts(*evs))
        out, _ = contradiction_engine.detect_contradictions(d)
        assert len(out) == 15


class TestTimelineEngine:
    def test_overlap_case_level_unattributed(self):
        d = _data(events=_evts(
            (1, None, None, datetime(2026, 6, 10, 8, 0), "fir"),
            (2, None, None, datetime(2026, 6, 10, 8, 0), "surv")))
        out, meta = timeline_engine.analyze_timeline(d)
        overlaps = [r for r in out if r.timeline_type == "EVENT_OVERLAP"]
        assert len(overlaps) == 1
        assert overlaps[0].entity_ids == []  # no common subject implied
        assert overlaps[0].interval_minutes == 0.0

    def test_proximity_window(self):
        d = _data(
            entities=_ents(("person", "A")),
            events=_evts((1, 1, None, datetime(2026, 6, 10, 9, 0), "a"),
                         (2, 1, None, datetime(2026, 6, 10, 9, 29), "b"),
                         (3, 1, None, datetime(2026, 6, 10, 10, 0), "c")))
        out, _ = timeline_engine.analyze_timeline(d)
        prox = [r for r in out if r.timeline_type == "TEMPORAL_PROXIMITY"]
        assert len(prox) == 1
        assert prox[0].interval_minutes == 29.0  # 9:00->9:29 only (30>30)

    def test_gap_reported_as_potential(self):
        d = _data(events=_evts(
            (1, None, None, datetime(2026, 6, 10, 9, 0), "a"),
            (2, None, None, datetime(2026, 6, 11, 9, 1), "b")))
        out, _ = timeline_engine.analyze_timeline(d)
        gaps = [r for r in out if r.timeline_type == "TIMELINE_GAP"]
        assert len(gaps) == 1
        assert "potential investigation gap" in gaps[0].title.lower()
        text = " ".join(gaps[0].explanation).lower()
        # neutral: describes record coverage, explicitly not a suspicion
        assert "coverage of the confirmed record" in text
        assert "not suspicious" in text

    def test_sequence_needs_three_events(self):
        d = _data(
            entities=_ents(("person", "A")),
            events=_evts((1, 1, None, datetime(2026, 6, 10, 9, 0), "a"),
                         (2, 1, None, datetime(2026, 6, 10, 10, 0), "b"),
                         (3, 1, None, datetime(2026, 6, 10, 12, 0), "c")))
        out, _ = timeline_engine.analyze_timeline(d)
        seq = [r for r in out if r.timeline_type == "EVENT_SEQUENCE"]
        assert len(seq) == 1
        assert seq[0].entity_ids == [1]

    def test_insufficient_when_fewer_than_two_dated_events(self):
        d = _data(events=_evts(
            (1, None, None, datetime(2026, 6, 10, 9, 0), "a"),
            (2, None, None, None, "undated")))
        out, meta = timeline_engine.analyze_timeline(d)
        assert out == []
        assert meta["insufficient"] is True
        assert meta["events_without_timestamp"] == 1


class TestGeospatialEngine:
    def test_co_location_same_location_two_entities(self):
        # two persons observed at the same location-typed entity, which
        # joins to the confirmed location record by (case, name)
        d = _data(
            entities=_ents(("person", "A"), ("person", "B"),
                           ("location", "Station")),
            locations=[_loc("Station", 18.52, 73.86, 1)],
            relationships=[RelationshipRecord(1, 999, 1, 3, "SEEN_AT"),
                           RelationshipRecord(2, 999, 2, 3, "SEEN_AT")])
        out, obs, meta = geospatial_engine.analyze_geospatial(d)
        co = [r for r in out if r.geo_type == "CO_LOCATION"]
        assert len(co) == 1
        assert sorted(co[0].entity_ids) == [1, 2]
        assert "no meeting or contact is implied" in \
            " ".join(co[0].explanation).lower()
        assert meta["observations"] == 2
        assert meta["location_data_insufficient"] is False

    def test_proximity_band(self):
        d = _data(
            entities=_ents(("person", "A"), ("person", "B"),
                           ("location", "X"), ("location", "Y")),
            locations=[_loc("X", 18.500, 73.800, 1),
                       _loc("Y", 18.510, 73.800, 2)],
            relationships=[RelationshipRecord(1, 999, 1, 3, "SEEN_AT"),
                           RelationshipRecord(2, 999, 2, 4, "SEEN_AT")])
        out, _, _ = geospatial_engine.analyze_geospatial(d)
        prox = [r for r in out if r.geo_type == "LOCATION_PROXIMITY"]
        assert len(prox) == 1
        assert 0.05 < prox[0].distance_km <= 2.0

    def test_sequence_with_and_without_times(self):
        ents = _ents(("person", "A"), ("location", "X"), ("location", "Y"))
        locs = [_loc("X", 18.50, 73.80, 1), _loc("Y", 18.55, 73.85, 2)]
        # no timestamps -> unordered, stated explicitly
        d1 = _data(entities=ents, locations=locs,
                   relationships=[RelationshipRecord(1, 999, 1, 2, "SEEN_AT"),
                                  RelationshipRecord(2, 999, 1, 3, "SEEN_AT")])
        out1, _, _ = geospatial_engine.analyze_geospatial(d1)
        seq1 = [r for r in out1 if r.geo_type == "LOCATION_SEQUENCE"]
        assert len(seq1) == 1
        text1 = seq1[0].summary + " " + " ".join(seq1[0].explanation)
        assert "order not determinable" in text1 or \
            "order of these observations is not determinable" in text1
        # with timestamps -> chronological + intervals
        d2 = _data(
            entities=ents, locations=locs,
            events=_evts((1, 1, 1, datetime(2026, 6, 10, 9, 0), "a"),
                         (2, 1, 2, datetime(2026, 6, 10, 10, 30), "b")))
        out2, _, _ = geospatial_engine.analyze_geospatial(d2)
        seq2 = [r for r in out2 if r.geo_type == "LOCATION_SEQUENCE"]
        assert len(seq2) == 1
        assert seq2[0].time_difference_minutes == 90.0

    def test_insufficient_when_no_observations(self):
        d = _data(entities=_ents(("person", "A")),
                  locations=[_loc("X", 18.50, 73.80, 1)])
        out, obs, meta = geospatial_engine.analyze_geospatial(d)
        assert out == [] and obs == []
        assert meta["location_data_insufficient"] is True

    def test_location_entity_without_coords_is_skipped(self):
        d = _data(
            entities=_ents(("person", "A"), ("location", "Unknown")),
            locations=[],  # no location row -> join yields no coordinates
            relationships=[RelationshipRecord(1, 999, 1, 2, "SEEN_AT")])
        out, obs, meta = geospatial_engine.analyze_geospatial(d)
        assert obs == []
        assert meta["location_data_insufficient"] is True


class TestGapEngine:
    def test_evidence_gap_degree3_no_evidence(self):
        d = _data(
            entities=_ents(("person", "A"), ("person", "B"),
                           ("person", "C"), ("person", "D")),
            relationships=[RelationshipRecord(1, 999, 1, 2, "MET"),
                           RelationshipRecord(2, 999, 1, 3, "MET"),
                           RelationshipRecord(3, 999, 1, 4, "MET")])
        gaps = gap_engine.detect_gaps(d)
        evg = [g for g in gaps if g.gap_type == "EVIDENCE_GAP"]
        assert any(g.involved_entity_ids == [1] for g in evg)

    def test_relationship_gap_indirect_only(self):
        # A and B are connected only via C (no direct link); both also
        # relate to X so they meet the documented degree >= 2 threshold
        d = _data(
            entities=_ents(("person", "A"), ("person", "B"),
                           ("person", "C"), ("person", "X")),
            relationships=[RelationshipRecord(1, 999, 1, 3, "MET"),
                           RelationshipRecord(2, 999, 3, 2, "MET"),
                           RelationshipRecord(3, 999, 1, 4, "MET"),
                           RelationshipRecord(4, 999, 2, 4, "MET")])
        gaps = gap_engine.detect_gaps(d)
        rlg = [g for g in gaps if g.gap_type == "RELATIONSHIP_GAP"]
        assert any(sorted(g.involved_entity_ids) == [1, 2] for g in rlg)

    def test_identity_gap_person_no_identifying_meta(self):
        d = _data(
            entities=_ents(("person", "A"), ("person", "B"),
                           ("person", "C")),
            relationships=[RelationshipRecord(1, 999, 1, 2, "MET"),
                           RelationshipRecord(2, 999, 1, 3, "MET")],
            entity_metadata={1: {"synthetic": True},
                             2: {"phone": "000"},
                             3: {}})
        gaps = gap_engine.detect_gaps(d)
        idg = [g for g in gaps if g.gap_type == "IDENTITY_GAP"]
        assert [g.involved_entity_ids for g in idg] == [[1]]

    def test_empty_graph_no_gaps(self):
        gaps = gap_engine.detect_gaps(_data())
        assert gaps == []


class TestHypothesisEngine:
    def _spec(self, **kw):
        base = dict(title="t", description="d", hypothesis_type="TEST")
        base.update(kw)
        return hypothesis_engine.HypothesisSpec(**base)

    def test_score_formula_and_components(self):
        d = _data(evidence=[
            EvidenceRecord(1, 999, "document", 7, "x"),
            EvidenceRecord(2, 999, "document", 7, "y"),
            EvidenceRecord(3, 999, "document", None, None),
            EvidenceRecord(4, 999, "document", None, None)])
        spec = self._spec(involved_entity_ids=[1, 2, 3],
                          supporting_relationship_ids=[1, 2, 3],
                          supporting_evidence_ids=[1, 2, 3, 4])
        s = hypothesis_engine.score_spec(d, spec)
        # evidence min(1,4/4)=1; rels min(1,3/3)=1; consistency=1;
        # provenance 2/4=0.5; connectivity min(1,3/5)=0.6
        expected = (0.30 * 1.0 + 0.20 * 1.0 + 0.20 * 1.0
                    + 0.15 * 0.5 + 0.15 * 0.6)
        assert abs(s.analytical_score - round(expected, 3)) < 1e-9
        assert s.score_components["supporting_evidence"] == 4
        assert s.score_components["factor_values"]["provenance"] == 0.5
        assert "not probability or proof" in s.explanation[-1]

    def test_bands(self):
        assert hypothesis_engine.band_for(0.10) == "LOW"
        assert hypothesis_engine.band_for(0.34) == "MEDIUM"
        assert hypothesis_engine.band_for(0.67) == "HIGH"

    def test_contradiction_explanations_split_by_margin(self):
        from app.services.investigation_intelligence.contradiction_engine \
            import ContradictionResult
        c = ContradictionResult(
            contradiction_type="TIMELINE_CONTRADICTION",
            title="Potential timeline contradiction: Aarav",
            summary="s", explanation=["e"], severity="HIGH",
            involved_entity_ids=[1], supporting_evidence_ids=[1],
            details={"margin": 0.25, "events": {"a": 1, "b": 2},
                     "locations": {"a": 1, "b": 2}})
        specs = hypothesis_engine.generate_hypotheses(
            _data(entities=_ents(("person", "Aarav"))), [c])
        assert len(specs) == 2
        margins = sorted(sp.consistency_override for sp in specs)
        assert margins == [0.25, 0.75]

    def test_generated_bounded(self):
        d = _data(
            entities=_ents(("person", "A"), ("person", "B"),
                           ("person", "C"), ("person", "D")),
            relationships=[RelationshipRecord(1, 999, 1, 3, "MET"),
                           RelationshipRecord(2, 999, 3, 2, "MET")])
        specs = hypothesis_engine.generate_hypotheses(d, [])
        assert len(specs) <= hypothesis_engine.MAX_GENERATED_HYPOTHESES
        assert all(sp.hypothesis_type in ("GENERATED_CONTRADICTION",
                                          "GENERATED_STRUCTURE")
                   for sp in specs)


class TestEvidenceImpact:
    def _sim_case(self):
        """A-B (proven only by ev 1) and B-C (proven by ev 2)."""
        ev_index = {"candidate:11": [1], "candidate:22": [2]}
        d = _data(
            entities=_ents(("person", "A"), ("person", "B"),
                           ("person", "C")),
            relationships=[RelationshipRecord(1, 999, 1, 2, "MET", 11),
                           RelationshipRecord(2, 999, 2, 3, "MET", 22)],
            evidence=[EvidenceRecord(1, 999, "document", None,
                                     "candidate:11"),
                      EvidenceRecord(2, 999, "document", None,
                                     "candidate:22")],
            evidence_index=ev_index,
            accepted_candidates={})
        return d

    def test_linked_record_geometry(self):
        d = self._sim_case()
        assert evidence_impact._linked_relationships(d, 1) == [1]
        assert evidence_impact._linked_relationships(d, 2) == [2]
        assert evidence_impact._linked_events(d, 1) == []
        assert evidence_impact._linked_entities(d, 1) == []

    def test_simulation_removes_sole_provenance_edge(self):
        d = self._sim_case()
        out = evidence_impact.simulate_removal(None, d, 1)
        assert out["simulation_only"] is True
        assert "not modified" in out["message"]
        assert out["diff"]["components_before"] == 1
        assert out["diff"]["components_after"] == 2
        assert len(out["edges_removed"]) == 1
        assert out["newly_isolated_entities"][0]["node"] == "e1"

    def test_simulation_cuts_only_simulated_edges(self):
        d = self._sim_case()
        out = evidence_impact.simulate_removal(None, d, 2)
        assert out["diff"]["components_before"] == 1
        assert out["diff"]["components_after"] == 2  # only B-C cut
        assert [e["edge"] for e in out["edges_removed"]] == [["e2", "e3"]]
        isolated = [n["node"] for n in out["newly_isolated_entities"]]
        assert isolated == ["e3"]  # A-B remains intact

    def test_simulation_keeps_unproven_edges(self):
        d = _data(
            entities=_ents(("person", "A"), ("person", "B"),
                           ("person", "C")),
            relationships=[RelationshipRecord(1, 999, 1, 2, "MET", None),
                           RelationshipRecord(2, 999, 2, 3, "MET", 11)],
            evidence=[EvidenceRecord(1, 999, "document", None,
                                     "candidate:11")],
            evidence_index={"candidate:11": [1]})
        out = evidence_impact.simulate_removal(None, d, 1)
        # B-C is solely proven by ev 1 -> cut; A-B has NO provenance ->
        # kept (no fabrication of absence). A stays in the main component.
        assert [e["edge"] for e in out["edges_removed"]] == [["e2", "e3"]]
        assert out["diff"]["components_after"] == 2
        isolated = [n["node"] for n in out["newly_isolated_entities"]]
        assert isolated == ["e3"]


# ================================================================== part B
# `client`, `investigator` and `analyst` come from conftest (Supabase tokens).


def _case_id_by_number(client, headers, number):
    r = client.get("/api/v1/cases", headers=headers)
    assert r.status_code == 200
    for c in r.json():
        if c["case_number"] == number:
            return c["id"]
    pytest.skip(f"{number} not present in this database")


@pytest.fixture(scope="session")
def demo_empty_case(client, analyst):
    return _case_id_by_number(client, analyst, "CASE-DEMO-EMPTY-01")


@pytest.fixture(scope="session")
def demo_contra_case(client, analyst):
    return _case_id_by_number(client, analyst, "CASE-DEMO-CONTRA-01")


@pytest.fixture(scope="session")
def case4(client, investigator):
    return _case_id_by_number(client, investigator, "CASE-2026-021")


class TestInsufficientState:
    def test_empty_case_status_insufficient(self, client, analyst,
                                            demo_empty_case):
        r = client.get(f"/api/v1/cases/{demo_empty_case}/investigation/status",
                       headers=analyst)
        assert r.status_code == 200
        body = r.json()
        assert body["state"] == "insufficient"
        assert body["insufficient"] is True
        assert body["analyzed"] is False

    def test_empty_case_analyze_409(self, client, investigator,
                                    demo_empty_case):
        r = client.post(f"/api/v1/cases/{demo_empty_case}/investigation/analyze",
                        headers=investigator)
        assert r.status_code == 409
        err = r.json()["error"]
        assert err["code"] == "INSUFFICIENT_CONFIRMED_DATA"
        assert err["message"]

    def test_unknown_case_404(self, client, investigator):
        r = client.get("/api/v1/cases/999999/investigation/status",
                       headers=investigator)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "CASE_NOT_FOUND"


class TestDemoContradictions:
    @pytest.fixture(scope="class")
    def analyzed(self, client, investigator, demo_contra_case):
        r = client.post(
            f"/api/v1/cases/{demo_contra_case}/investigation/analyze",
            headers=investigator)
        assert r.status_code == 200, r.text
        return r.json()

    def test_all_three_contradiction_types_detected(self, analyzed):
        contra = [f for f in analyzed["findings"]
                  if f["finding_type"] == "CONTRADICTION"]
        types = {f["details"]["contradiction_type"] for f in contra}
        assert types == {"TIMELINE_CONTRADICTION", "LOCATION_CONTRADICTION",
                         "RELATIONSHIP_CONTRADICTION"}
        for f in contra:
            assert f["stale"] is False
            assert f["status"] in ("ACTIVE", "REVIEWED", "DISMISSED")
            assert f["explanation"]
            assert f["analysis_method"]

    def test_finding_neutral_language(self, analyzed):
        contra = [f for f in analyzed["findings"]
                  if f["finding_type"] == "CONTRADICTION"]
        text = " ".join(" ".join(f["explanation"]) + f["summary"]
                        for f in contra).lower()
        for banned in ("proves", "guilty", "is guilty", "definitely",
                       "confirmed that they did"):
            assert banned not in text

    def test_hypotheses_generated_with_components(self, analyzed):
        hyps = [h for h in analyzed["hypotheses"]
                if h["hypothesis_type"].startswith("GENERATED_")]
        assert len(hyps) >= 4
        for h in hyps:
            assert 0.0 <= h["analytical_score"] <= 1.0
            assert h["confidence_band"] in ("LOW", "MEDIUM", "HIGH")
            assert h["score_components"]["supporting_evidence"] >= 0
            assert "factor_values" in h["score_components"]
            assert h["explanation"]
            assert "analytical support" in h["explanation"][-1].lower()

    def test_idempotent_rerun(self, client, investigator, demo_contra_case):
        r1 = client.post(f"/api/v1/cases/{demo_contra_case}/investigation/analyze",
                         headers=investigator)
        assert r1.status_code == 200
        b1 = r1.json()
        r2 = client.post(f"/api/v1/cases/{demo_contra_case}/investigation/analyze",
                         headers=investigator)
        b2 = r2.json()
        assert b2["recomputed"] is False
        assert b2["graph_version"] == b1["graph_version"]
        assert len(b2["findings"]) == len(b1["findings"])
        assert len(b2["hypotheses"]) == len(b1["hypotheses"])

    def test_status_up_to_date(self, client, analyst, demo_contra_case):
        r = client.get(f"/api/v1/cases/{demo_contra_case}/investigation/status",
                       headers=analyst)
        assert r.status_code == 200
        assert r.json()["state"] in ("up-to-date", "stale")
        assert r.json()["current_findings"] >= 9 or \
            r.json()["stale_findings"] >= 9


class TestRbac:
    def test_analyst_cannot_analyze(self, client, analyst, demo_contra_case):
        r = client.post(f"/api/v1/cases/{demo_contra_case}/investigation/analyze",
                        headers=analyst)
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "FORBIDDEN"

    def test_analyst_can_read(self, client, analyst, demo_contra_case):
        for path in ("/investigation/findings", "/investigation/contradictions",
                     "/investigation/gaps", "/investigation/hypotheses",
                     "/investigation/evidence-impact", "/investigation/timeline",
                     "/investigation/geospatial"):
            r = client.get(f"/api/v1/cases/{demo_contra_case}{path}",
                           headers=analyst)
            assert r.status_code == 200, (path, r.text)

    def test_no_token_rejected(self, client, demo_contra_case):
        r = client.get(f"/api/v1/cases/{demo_contra_case}/investigation/findings")
        assert r.status_code in (401, 403)


class TestCandidateExclusion:
    def test_only_confirmed_entities_in_outputs(self, client, analyst, case4):
        db = SessionLocal()
        try:
            from sqlalchemy import select
            from app.models import Entity
            confirmed = set(db.execute(
                select(Entity.id).where(
                    Entity.case_id == case4)).scalars())
        finally:
            db.close()
        r = client.get(f"/api/v1/cases/{case4}/investigation/findings",
                       headers=analyst)
        assert r.status_code == 200
        for f in r.json()["current_findings"] + r.json()["stale_findings"]:
            for eid in f["involved_entity_ids"]:
                assert eid in confirmed, (f["id"], eid)
        r = client.get(f"/api/v1/cases/{case4}/investigation/hypotheses",
                       headers=analyst)
        for h in r.json()["hypotheses"]:
            for eid in h["involved_entity_ids"]:
                assert eid in confirmed, (h["id"], eid)


class TestEnginesViaApi:
    def test_timeline_endpoint(self, client, analyst, demo_contra_case):
        r = client.get(f"/api/v1/cases/{demo_contra_case}/investigation/timeline",
                       headers=analyst)
        assert r.status_code == 200
        body = r.json()
        assert body["events_total"] >= 5
        assert body["analysis_method"]
        allowed = {"EVENT_OVERLAP", "TEMPORAL_PROXIMITY", "EVENT_SEQUENCE",
                   "TIMELINE_GAP"}
        assert all(x["timeline_type"] in allowed for x in body["results"])

    def test_geospatial_endpoint(self, client, analyst, demo_contra_case):
        r = client.get(f"/api/v1/cases/{demo_contra_case}/investigation/geospatial",
                       headers=analyst)
        assert r.status_code == 200
        body = r.json()
        assert body["observations_count"] >= 5
        assert all(x["geo_type"] in {"CO_LOCATION", "LOCATION_PROXIMITY",
                                     "LOCATION_SEQUENCE"}
                   for x in body["results"])
        assert body["location_data_insufficient"] is False

    def test_gaps_endpoint(self, client, analyst, case4):
        r = client.get(f"/api/v1/cases/{case4}/investigation/gaps",
                       headers=analyst)
        assert r.status_code == 200
        for g in r.json()["current_findings"]:
            assert g["details"]["gap_type"] in {"EVIDENCE_GAP",
                                                "RELATIONSHIP_GAP",
                                                "TIMELINE_GAP",
                                                "IDENTITY_GAP"}
            assert "potential investigation gap" in g["title"].lower()

    def test_case4_geo_honest_nonempty(self, client, analyst, case4):
        r = client.get(f"/api/v1/cases/{case4}/investigation/geospatial",
                       headers=analyst)
        assert r.status_code == 200
        assert len(r.json()["results"]) > 0  # co-locations exist in case 4


class TestEvidenceImpactApi:
    def test_summary_and_detail(self, client, analyst, case4):
        r = client.get(f"/api/v1/cases/{case4}/investigation/evidence-impact",
                       headers=analyst)
        assert r.status_code == 200
        body = r.json()
        assert body["evidence_count"] > 0
        assert sum(body["distribution"].values()) == body["evidence_count"]
        top = body["evidence_impacts"][0]
        assert top["impact_score"] >= body["evidence_impacts"][-1]["impact_score"]
        r = client.get(f"/api/v1/cases/{case4}/investigation/evidence/"
                       f"{top['evidence_id']}/impact", headers=analyst)
        assert r.status_code == 200
        assert r.json()["evidence_id"] == top["evidence_id"]
        assert r.json()["impact_score"] == top["impact_score"]

    def test_unknown_evidence_404(self, client, analyst, case4):
        r = client.get(f"/api/v1/cases/{case4}/investigation/evidence/999999/impact",
                       headers=analyst)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"

    def test_simulation_never_writes(self, client, investigator, case4):
        db = SessionLocal()
        try:
            from sqlalchemy import select, func
            from app.models import Evidence, Relationship
            before = (db.execute(select(func.count()).select_from(
                Evidence).where(Evidence.case_id == case4)).scalar(),
                db.execute(select(func.count()).select_from(
                    Relationship).where(Relationship.case_id == case4)).scalar())
        finally:
            db.close()
        r = client.get(f"/api/v1/cases/{case4}/investigation/evidence-impact",
                       headers=investigator)
        target = r.json()["evidence_impacts"][0]["evidence_id"]
        s = client.post(
            f"/api/v1/cases/{case4}/investigation/evidence/{target}/simulate-impact",
            headers=investigator)
        assert s.status_code == 200, s.text
        body = s.json()
        assert body["simulation_only"] is True
        assert "not modified" in body["message"]
        assert "metrics_before" in body and "metrics_after" in body
        assert "diff" in body
        db = SessionLocal()
        try:
            from sqlalchemy import select, func
            from app.models import Evidence, Relationship
            after = (db.execute(select(func.count()).select_from(
                Evidence).where(Evidence.case_id == case4)).scalar(),
                db.execute(select(func.count()).select_from(
                    Relationship).where(Relationship.case_id == case4)).scalar())
        finally:
            db.close()
        assert before == after  # zero database writes


class TestLifecycle:
    def test_review_dismiss_finding_and_audit(self, client, investigator,
                                              demo_contra_case):
        from app.models import GraphFinding
        db = SessionLocal()
        f = GraphFinding(case_id=demo_contra_case,
                         finding_type="CONTRADICTION",
                         title="Lifecycle test — review me",
                         summary="synthetic test finding",
                         explanation=["test explanation"],
                         details={"gap_type": None},
                         involved_entity_ids=[],
                         supporting_relationship_ids=[],
                         supporting_evidence_ids=[],
                         related_case_ids=[],
                         analysis_method="test",
                         graph_version="S4LIFECYCLE0000001",
                         status="ACTIVE")
        db.add(f)
        db.commit()
        fid = f.id
        db.close()
        # the lifecycle row is kept after the test (auditability; never
        # delete) — a unique graph_version per test run keeps reruns green
        r = client.post(
            f"/api/v1/cases/{demo_contra_case}/investigation/findings/{fid}/review",
            headers=investigator, json={"note": "checked"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "REVIEWED"
        r = client.post(
            f"/api/v1/cases/{demo_contra_case}/investigation/findings/{fid}/review",
            headers=investigator, json={"note": "again"})
        assert r.status_code == 409
        db = SessionLocal()
        try:
            from app.models import AuditLog
            rows = db.query(AuditLog).filter(
                AuditLog.resource_type == "graph_finding",
                AuditLog.resource_id == str(fid)).all()
            assert any(x.action == "FINDING_REVIEWED" for x in rows)
        finally:
            db.close()

    def test_dismiss_finding(self, client, investigator, demo_contra_case):
        from app.models import GraphFinding
        db = SessionLocal()
        f = GraphFinding(case_id=demo_contra_case,
                         finding_type="INVESTIGATION_GAP",
                         title="Lifecycle test — dismiss me",
                         summary="synthetic test finding",
                         explanation=["test explanation"],
                         details={"gap_type": "EVIDENCE_GAP"},
                         involved_entity_ids=[],
                         supporting_relationship_ids=[],
                         supporting_evidence_ids=[],
                         related_case_ids=[],
                         analysis_method="test",
                         graph_version="S4LIFECYCLE0000002",
                         status="ACTIVE")
        db.add(f)
        db.commit()
        fid = f.id
        db.close()
        r = client.post(
            f"/api/v1/cases/{demo_contra_case}/investigation/findings/{fid}/dismiss",
            headers=investigator, json={"note": "noise"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "DISMISSED"

    def test_stage3_finding_type_rejected_on_stage4_review(self, client,
                                                           investigator,
                                                           case4):
        r = client.get(f"/api/v1/cases/{case4}/graph/findings",
                       headers=investigator)
        assert r.status_code == 200
        stage3 = r.json()["current_findings"]
        if not stage3:  # stage-3 analyze not run in this database yet
            pytest.skip("no stage-3 findings in this database")
        target = stage3[0]["id"]
        r = client.post(
            f"/api/v1/cases/{case4}/investigation/findings/{target}/dismiss",
            headers=investigator, json={"note": "x"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_FINDING_TYPE"

    def test_review_dismiss_hypothesis_and_audit(self, client,
                                                 investigator,
                                                 demo_contra_case):
        from app.models import InvestigationHypothesis
        db = SessionLocal()
        h = InvestigationHypothesis(
            case_id=demo_contra_case, title="Lifecycle test hypothesis",
            description="synthetic", hypothesis_type="INVESTIGATOR",
            analytical_score=0.5, confidence_band="MEDIUM",
            score_components={
                "supporting_evidence": 0, "contradicting_evidence": 0,
                "supporting_relationships": 0, "contradicting_signals": 0,
                "involved_entities": 0,
                "evidence_with_document_provenance": 0.0,
                "factor_values": {"evidence": 0.0, "relationships": 0.0,
                                  "consistency": 0.5, "provenance": 0.0,
                                  "connectivity": 0.0}},
            explanation=["test"],
            analysis_method="test", graph_version="S4LIFECYCLE0000003",
            status="ACTIVE")
        db.add(h)
        db.commit()
        hid = h.id
        db.close()
        r = client.post(
            f"/api/v1/cases/{demo_contra_case}/investigation/hypotheses/{hid}/review",
            headers=investigator, json={"note": "ok"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "REVIEWED"
        db = SessionLocal()
        try:
            from app.models import AuditLog
            rows = db.query(AuditLog).filter(
                AuditLog.resource_type == "investigation_hypothesis",
                AuditLog.resource_id == str(hid)).all()
            assert any(x.action == "HYPOTHESIS_REVIEWED" for x in rows)
        finally:
            db.close()

    def test_investigator_hypothesis_created_and_scored(self, client,
                                                        investigator,
                                                        demo_contra_case):
        r = client.post(
            f"/api/v1/cases/{demo_contra_case}/investigation/hypotheses",
            headers=investigator,
            json={"title": "API test hypothesis",
                  "description": "synthetic test",
                  "involved_entity_ids": [],
                  "supporting_evidence_ids": []})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["hypothesis_type"] == "INVESTIGATOR"
        assert body["analytical_score"] >= 0.0
        assert body["status"] == "ACTIVE"

    def test_investigator_hypothesis_rejects_unknown_ids(self, client,
                                                         investigator,
                                                         demo_contra_case):
        r = client.post(
            f"/api/v1/cases/{demo_contra_case}/investigation/hypotheses",
            headers=investigator,
            json={"title": "bad refs", "involved_entity_ids": [999999]})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "ENTITY_NOT_CONFIRMED"


class TestStage3Regression:
    def test_graph_findings_only_stage3_types(self, client, investigator,
                                              case4):
        r = client.get(f"/api/v1/cases/{case4}/graph/findings",
                       headers=investigator)
        assert r.status_code == 200
        body = r.json()
        for f in body["current_findings"] + body["stale_findings"]:
            assert f["finding_type"] in STAGE3_TYPES

    def test_graph_analyze_still_works(self, client, investigator, case4):
        r = client.post(f"/api/v1/cases/{case4}/graph/analyze",
                        headers=investigator)
        assert r.status_code == 200
        assert all(f["finding_type"] in STAGE3_TYPES
                   for f in r.json()["findings"])
