"""
Contradiction engine tests.

The negative tests matter more than the positive ones. An engine that flags
every subject who appears in two places is worse than no engine at all: it
buries the one real conflict in noise and trains the investigator to ignore it.
Most of what follows therefore checks that the engine stays quiet.
"""

import pytest

from app.intelligence import config
from app.intelligence.contradiction_engine import ContradictionEngine
from app.intelligence.observations import (Sighting, ClaimSet, haversine_km,
                                           stated_time_for)
from app.intelligence.scoring import assess, record_weight
from conftest import by_type


# --------------------------------------------------------------- helpers

_UNSET = object()


def _sighting(entity, place, lat, lon, ts, precision=config.PRECISION_EXACT,
              source_id="CDR", source_type="cdr", record_id=_UNSET):
    """
    `record_id=None` means "this claim came out of a document, not a row", which
    is what makes two claims share a record — so an explicit None must survive
    rather than being replaced by a generated id.
    """
    if record_id is _UNSET:
        record_id = f"{place}-{ts}"
    return Sighting(entity_id=entity, place=place, lat=lat, lon=lon, timestamp=ts,
                    time_precision=precision, source_id=source_id,
                    source_type=source_type, evidence="test", confidence=0.95,
                    record_id=record_id)


PUNE = (18.5204, 73.8567)
MUMBAI = (19.0760, 72.8777)
KURLA = (19.0726, 72.8790)
GHATKOPAR = (19.0860, 72.9080)


def _engine_over(case_graph, sightings, **kw):
    """Run the engine over a hand-built claim set, keeping the real graph."""
    claims = ClaimSet(sightings=list(sightings), **kw)
    return ContradictionEngine(case_graph, claims=claims)


# ============================================================ positive cases

def test_timeline_conflict(findings):
    """Pune 10:30 -> Mumbai 10:35 is the textbook case, and the corpus has one."""
    items = by_type(findings, "timeline_conflict")
    assert items, "the corpus contains a subject on two cell sites 36 seconds apart"
    f = items[0]
    assert f["basis"]["implied_speed_kmph"] > config.MAX_REASONABLE_SPEED_KMPH
    assert f["basis"]["distance_km"] > config.MIN_SEPARATION_KM
    assert len(f["events"]) == 2
    assert f["severity"] in ("high", "medium", "low")


def test_timeline_conflict_synthetic_pune_mumbai(case_graph):
    """The scenario from the specification: 150 km in 5 minutes must be flagged."""
    eid = next(iter(case_graph.G.nodes))
    e = _engine_over(case_graph, [
        _sighting(eid, "Pune", *PUNE, "2026-06-01T10:30:00", record_id="r1"),
        _sighting(eid, "Mumbai", *MUMBAI, "2026-06-01T10:35:00", record_id="r2"),
    ])
    items = by_type(e.run_all(), "timeline_conflict")
    assert len(items) == 1
    assert items[0]["basis"]["implied_speed_kmph"] > 1000
    assert items[0]["severity"] == "high"


def test_location_inconsistency(findings):
    items = by_type(findings, "location_inconsistency")
    assert items, "surveillance and CDR disagree for one subject in the corpus"
    f = items[0]
    srcs = {e["source_type"] for e in f["contradicting_evidence"]}
    assert len(srcs) == 2, "a location inconsistency is a disagreement between two systems"
    assert "does not" in f["description"] or "not agree" in f["description"]


def test_vehicle_association_conflict(findings):
    items = by_type(findings, "vehicle_association_conflict")
    assert items
    f = items[0]
    assert f["basis"]["transfer_record_found"] is False
    assert f["basis"]["window_hours"] <= config.VEHICLE_WINDOW_HOURS
    assert len(f["entity_ids"]) == 2


def test_device_conflict(findings):
    items = by_type(findings, "device_conflict")
    assert items
    f = items[0]
    assert f["basis"]["name_similarity"] < f["basis"]["name_match_threshold"]
    assert len(f["possible_explanations"]) >= 4, "alternatives are listed, not chosen"


def test_identity_conflict(findings):
    items = by_type(findings, "identity_conflict")
    assert items
    f = items[0]
    assert len(f["basis"]["values"]) >= 2
    assert f["basis"]["attribute"] in config.IDENTITY_ATTRIBUTES


def test_all_five_types_are_detected(findings):
    got = {f["type"] for f in findings}
    assert got == {
        "timeline_conflict", "location_inconsistency",
        "vehicle_association_conflict", "device_conflict", "identity_conflict",
    }


# ============================================================ negative cases

def test_no_false_contradiction_over_two_days(case_graph):
    """Pune -> Mumbai two days apart is a journey, not a conflict."""
    eid = next(iter(case_graph.G.nodes))
    e = _engine_over(case_graph, [
        _sighting(eid, "Pune", *PUNE, "2026-06-01T10:00:00", record_id="r1"),
        _sighting(eid, "Mumbai", *MUMBAI, "2026-06-03T10:00:00", record_id="r2"),
    ])
    assert by_type(e.run_all(), "timeline_conflict") == []


def test_no_false_contradiction_for_ordinary_commute(case_graph):
    """14 km in 40 minutes is ordinary traffic and must stay silent."""
    eid = next(iter(case_graph.G.nodes))
    e = _engine_over(case_graph, [
        _sighting(eid, "Kurla", *KURLA, "2026-06-01T09:00:00", record_id="r1"),
        _sighting(eid, "Ghatkopar", *GHATKOPAR, "2026-06-01T09:40:00", record_id="r2"),
    ])
    assert by_type(e.run_all(), "timeline_conflict") == []


def test_adjacent_cells_are_one_locality(case_graph):
    """Two towers 300 m apart are not a journey however fast the switch."""
    eid = next(iter(case_graph.G.nodes))
    e = _engine_over(case_graph, [
        _sighting(eid, "A", 19.0726, 72.8790, "2026-06-01T09:00:00", record_id="r1"),
        _sighting(eid, "B", 19.0750, 72.8790, "2026-06-01T09:00:30", record_id="r2"),
    ])
    assert by_type(e.run_all(), "timeline_conflict") == []


def test_document_dated_records_never_raise_a_timing_conflict(case_graph):
    """
    The single most important control. Most FIRs stamp every location they
    mention with the document's filing time; reading those as observations
    would manufacture an impossible journey out of one narrative.
    """
    eid = next(iter(case_graph.G.nodes))
    e = _engine_over(case_graph, [
        _sighting(eid, "Dongri", 18.96, 72.837, "2026-06-01T08:00:00",
                  precision=config.PRECISION_DOCUMENT, source_id="FIR/X", source_type="fir"),
        _sighting(eid, "Bhiwandi Godown", 19.296, 73.063, "2026-06-01T08:00:00",
                  precision=config.PRECISION_DOCUMENT, source_id="FIR/Y", source_type="fir"),
    ])
    findings = e.run_all()
    assert by_type(findings, "timeline_conflict") == []
    assert any(s["reason"] == "insufficient_evidence" for s in e.skipped)


def test_two_places_in_one_record_are_not_a_conflict(case_graph):
    """One narrative naming two places is a narrative, not evidence against itself."""
    eid = next(iter(case_graph.G.nodes))
    e = _engine_over(case_graph, [
        _sighting(eid, "Pune", *PUNE, "2026-06-01T10:30:00",
                  precision=config.PRECISION_STATED, source_id="SUR/1",
                  source_type="surveillance", record_id=None),
        _sighting(eid, "Mumbai", *MUMBAI, "2026-06-01T10:35:00",
                  precision=config.PRECISION_STATED, source_id="SUR/1",
                  source_type="surveillance", record_id=None),
    ])
    assert by_type(e.run_all(), "timeline_conflict") == []
    assert by_type(e.run_all(), "location_inconsistency") == []


def test_missing_coordinates_yield_insufficient_evidence(case_graph):
    eid = next(iter(case_graph.G.nodes))
    e = _engine_over(case_graph, [
        _sighting(eid, "Unknown", None, None, "2026-06-01T10:30:00", record_id="r1"),
        _sighting(eid, "Mumbai", *MUMBAI, "2026-06-01T10:35:00", record_id="r2"),
    ])
    assert by_type(e.run_all(), "timeline_conflict") == []
    assert any(s["reason"] == "insufficient_evidence" for s in e.skipped)


def test_cross_script_spellings_are_not_a_device_conflict(skipped):
    """
    'Sanjay Bhosle' and 'संजय भोसले' quote one handset and are one person. The
    engine must recognise that through the resolver's own name matcher.
    """
    explained = [s for s in skipped
                 if s["check"] == "device_conflict" and s["reason"] == "explained"]
    assert explained, "the corpus contains cross-script pairs sharing a handset"
    assert any("spellings of one name" in s["detail"] for s in explained)


def test_overlapping_active_periods_are_not_an_identity_conflict(case_graph):
    e = ContradictionEngine(case_graph)
    assert e._ranges_overlap({"2019-2024", "2020-2025"}) is True
    assert e._ranges_overlap({"2017-2018", "2021-2025"}) is False


# ============================================================ source weighting

def test_source_weighting_orders_systems():
    assert config.reliability("cdr") > config.reliability("fir")
    assert config.reliability("fir") > config.reliability("ocr")
    assert config.reliability("ocr") > config.reliability("social_media")
    assert config.reliability("unknown_system") == config.DEFAULT_RELIABILITY


def test_source_weighting_changes_the_verdict():
    """A contradiction from a strong source moves confidence further than a weak one."""
    support = [{"source_id": "S", "source_type": "cdr", "confidence": 0.9}]
    strong = assess(0.9, support, [{"source_id": "X", "source_type": "cdr", "confidence": 0.9}])
    weak = assess(0.9, support, [{"source_id": "Y", "source_type": "social_media",
                                  "confidence": 0.9}])
    assert strong["confidence_after"] < weak["confidence_after"]


def test_repeated_records_from_one_source_have_diminishing_weight():
    first = record_weight("cdr", 0.9, occurrence=1)
    fourth = record_weight("cdr", 0.9, occurrence=4)
    assert fourth == pytest.approx(first / 2, rel=1e-6)


def test_confidence_impact_is_capped_and_never_negative():
    """Conflicting evidence weakens a conclusion; it does not delete it."""
    contradicting = [{"source_id": f"X{i}", "source_type": "cdr", "confidence": 1.0}
                     for i in range(50)]
    out = assess(0.9, [], contradicting)
    assert out["contradiction_ratio"] == 1.0
    assert out["confidence_after"] == pytest.approx(0.9 * (1 - config.CONFIDENCE_IMPACT_CAP))
    assert out["confidence_after"] > 0


def test_no_contradiction_leaves_confidence_untouched():
    out = assess(0.82, [{"source_id": "S", "source_type": "cdr", "confidence": 0.9}], [])
    assert out["confidence_after"] == pytest.approx(0.82)
    assert out["contradiction_ratio"] == 0.0


# ============================================================ provenance

def test_every_finding_carries_provenance(findings):
    """No contradiction may be raised without naming the records behind it."""
    for f in findings:
        assert f["contradicting_evidence"], f"{f['id']} has no contradicting records"
        for row in f["contradicting_evidence"] + f["supporting_evidence"]:
            assert row["source_id"], f"{f['id']} has an evidence row with no source"
            assert row["source_type"]
            assert row["detail"]


def test_evidence_source_ids_resolve_to_real_documents(findings, case_graph):
    docs = case_graph.raw["documents"]
    for f in findings:
        for row in f["contradicting_evidence"]:
            assert row["source_id"] in docs, (
                f"{f['id']} cites {row['source_id']}, which is not an ingested document")


def test_every_finding_is_explainable(findings):
    for f in findings:
        assert f["basis"]["rule"], f"{f['id']} does not state the rule that fired"
        assert f["possible_explanations"], f"{f['id']} offers no alternative explanations"
        assert f["recommended_verification"], f"{f['id']} suggests no verification"
        assert f["assessment"]["formula"]


def test_findings_expose_what_the_impact_simulator_will_need(findings):
    """Phase 2 reads these fields; they are part of the contract now."""
    for f in findings:
        assert set(f["entity_ids"])
        assert "affected_relationships" in f
        assert f["assessment"]["confidence_before"] is not None
        assert f["assessment"]["confidence_after"] is not None
        assert isinstance(f["supporting_evidence"], list)
        assert isinstance(f["contradicting_evidence"], list)


# ============================================================ language

def test_no_finding_overstates_its_conclusion(findings):
    """The engine reports leads. It must never assert guilt or falsity."""
    banned = ["is lying", "committed", "guilty", "fake", "proves", "false statement",
              "definitely", "certainly"]
    for f in findings:
        blob = " ".join([f["title"], f["description"]]).lower()
        for word in banned:
            assert word not in blob, f"{f['id']} overstates: contains '{word}'"


# ============================================================ determinism

def test_engine_is_deterministic(case_graph):
    a = ContradictionEngine(case_graph).run_all()
    b = ContradictionEngine(case_graph).run_all()
    assert [x["id"] for x in a] == [x["id"] for x in b]
    assert [x["title"] for x in a] == [x["title"] for x in b]
    assert [x["assessment"]["confidence_after"] for x in a] == \
           [x["assessment"]["confidence_after"] for x in b]


def test_engine_never_mutates_the_graph(case_graph):
    before_nodes = case_graph.G.number_of_nodes()
    before_edges = case_graph.G.number_of_edges()
    before_conf = {(a, b): d["confidence"] for a, b, d in case_graph.G.edges(data=True)}
    ContradictionEngine(case_graph).run_all()
    assert case_graph.G.number_of_nodes() == before_nodes
    assert case_graph.G.number_of_edges() == before_edges
    after = {(a, b): d["confidence"] for a, b, d in case_graph.G.edges(data=True)}
    assert after == before_conf, "the engine revised a confidence in place"


# ============================================================ unit helpers

def test_haversine_is_sane():
    assert haversine_km(*PUNE, *MUMBAI) == pytest.approx(120, abs=15)
    assert haversine_km(None, None, *MUMBAI) is None


def test_stated_time_requires_the_anchor_to_be_named():
    text = "At 2340 hrs the subject arrived at Bhiwandi Godown."
    assert stated_time_for(text, "Bhiwandi Godown", "2026-05-03") == "2026-05-03T23:40:00"
    # A place the narrative never mentions gets no time, however many are stated.
    assert stated_time_for(text, "Dongri", "2026-05-03") is None
    assert stated_time_for("No clock time here.", "Dongri", "2026-05-03") is None
