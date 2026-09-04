"""
Evidence impact simulator tests.

Two properties matter more than any individual diff:

* the baseline is never touched — a simulation that mutates the case it is
  reasoning about is worse than no simulation;
* the answer is causal, not cosmetic — withholding the records a contradiction
  cites must actually make that contradiction go away.
"""

import pytest

from app.graph.build import build_graph
from app.intelligence.contradiction_engine import ContradictionEngine
from app.intelligence.impact_simulator import ImpactSimulator, simulate_removal


@pytest.fixture(scope="module")
def sim(case_graph):
    return ImpactSimulator(case_graph)


# ------------------------------------------------------------- the contract

def test_simulation_never_mutates_the_baseline(case_graph, sim):
    nodes = case_graph.G.number_of_nodes()
    edges = case_graph.G.number_of_edges()
    conf = {(a, b): d["confidence"] for a, b, d in case_graph.G.edges(data=True)}
    entities = len(case_graph.raw["entities"])

    sim.simulate(exclude_sources={"FIR/2026/0107"})
    sim.simulate(exclude_records={"C000054", "C000017"})
    sim.simulate(exclude_sources={"CDR"})

    assert case_graph.G.number_of_nodes() == nodes
    assert case_graph.G.number_of_edges() == edges
    assert {(a, b): d["confidence"] for a, b, d in case_graph.G.edges(data=True)} == conf
    assert len(case_graph.raw["entities"]) == entities


def test_withholding_nothing_is_rejected(sim):
    with pytest.raises(ValueError):
        sim.simulate()


def test_simulation_is_deterministic(sim):
    a = sim.simulate(exclude_sources={"FIR/2026/0107"})
    b = sim.simulate(exclude_sources={"FIR/2026/0107"})
    assert a["summary"] == b["summary"]
    assert [x["a_label"] for x in a["removed_links"]] == [x["a_label"] for x in b["removed_links"]]
    assert a["influence_changes"] == b["influence_changes"]


# ------------------------------------------------------------ causal answers

def test_withholding_a_contradictions_own_evidence_resolves_it(case_graph, sim):
    """
    The loop the contradiction engine was built to close: its provenance names
    the records, and withholding exactly those records must remove the finding.
    """
    contradictions = ContradictionEngine(case_graph).run_all()
    timeline = next(c for c in contradictions if c["type"] == "timeline_conflict")
    records = {r["record_id"] for r in timeline["contradicting_evidence"] if r["record_id"]}
    assert records, "the timeline conflict cites individual CDR rows"

    out = sim.simulate(exclude_records=records)
    resolved = {(c["type"], c["title"]) for c in out["contradictions_resolved"]}
    assert (timeline["type"], timeline["title"]) in resolved
    assert out["summary"]["contradictions_after"] < out["summary"]["contradictions_before"]


def test_withholding_a_synthetic_claim_resolves_only_its_own_contradiction(sim):
    out = sim.simulate(exclude_sources={"SUR/2026/T03"})
    types = [c["type"] for c in out["contradictions_resolved"]]
    assert types == ["device_conflict"]
    assert out["contradictions_introduced"] == []


def test_withholding_a_feed_removes_the_links_it_supported(sim):
    out = sim.simulate(exclude_sources={"CDR"})
    assert out["summary"]["links_after"] < out["summary"]["links_before"]
    assert out["summary"]["findings_after"] < out["summary"]["findings_before"]
    # Nothing in the counterfactual may still cite the withheld feed.
    for link in out["weakened_links"]:
        assert "cdr" not in link["independent_sources_after"]


def test_removing_an_uninvolved_record_leaves_the_conflict_alone(sim):
    """A record a contradiction does not rest on must not resolve it."""
    out = sim.simulate(exclude_sources={"SUR/2026/T01"})
    resolved = {c["type"] for c in out["contradictions_resolved"]}
    assert "timeline_conflict" not in resolved


# ------------------------------------------------------- entity alignment

def test_person_renumbering_is_not_reported_as_change(sim):
    """
    Person ids are positional, so withholding an early record renumbers
    everyone. Diffing on ids would report the whole network as rebuilt; the
    alignment exists to stop that.
    """
    out = sim.simulate(exclude_sources={"CR9001"})
    # CR9001 adds one attribute row and no links at all.
    assert out["summary"]["links_before"] == out["summary"]["links_after"]
    assert out["removed_links"] == []
    assert out["introduced_links"] == []


def test_alignment_matches_subjects_across_renumbering(case_graph):
    from app.intelligence.impact_simulator import _align_persons
    cf = build_graph(exclude_sources={"CR9001"})
    base_key, cf_key, splits = _align_persons(case_graph, cf)
    base_people = [n for n, d in case_graph.G.nodes(data=True) if d.get("type") == "PERSON"]
    # Every baseline subject is accounted for, and matched keys are shared.
    assert len(base_key) == len(base_people)
    shared = set(base_key.values()) & set(cf_key.values())
    assert len(shared) >= len(base_people) - 1


def test_identity_split_is_reported_when_a_merge_loses_its_only_grounds():
    """
    A merge held together by one record comes apart without it. The corpus has
    no natural instance, so the alignment is exercised directly.
    """
    from app.intelligence.impact_simulator import _align_persons

    class _FakeGraph:
        def __init__(self, nodes):
            import networkx as nx
            self.G = nx.Graph()
            for nid, attrs in nodes.items():
                self.G.add_node(nid, **attrs)

    base = _FakeGraph({"P0001": {"type": "PERSON", "label": "Merged Subject",
                                 "aliases": ["A Name", "B Name"],
                                 "phones": ["9000000000"], "accounts": []}})
    cf = _FakeGraph({
        "P0001": {"type": "PERSON", "label": "A Name", "aliases": [], "phones": [], "accounts": []},
        "P0002": {"type": "PERSON", "label": "B Name", "aliases": [], "phones": [], "accounts": []},
    })
    _, _, splits = _align_persons(base, cf)
    assert len(splits) == 1
    assert splits[0]["subject"] == "Merged Subject"
    assert splits[0]["became"] in (["B Name"], ["A Name"])


# ------------------------------------------------------------- the report

def test_report_states_its_method_and_stays_a_simulation(sim):
    out = sim.simulate(exclude_sources={"FIR/2026/0107"})
    assert "re-run" in out["method"]
    assert "not" in out["disclaimer"].lower()
    blob = (out["method"] + " " + out["disclaimer"]).lower()
    for word in ("guilty", "proves", "is lying", "fake"):
        assert word not in blob


def test_withheld_records_are_described(sim):
    out = sim.simulate(exclude_sources={"FIR/2026/0107"})
    assert out["withheld"][0]["source_id"] == "FIR/2026/0107"
    assert out["withheld"][0]["known"] is True
    assert out["withheld"][0]["source_type"] == "fir"


def test_convenience_wrapper(case_graph):
    out = simulate_removal(case_graph, exclude_sources={"SUR/2026/T03"})
    assert out["summary"]["contradictions_after"] == out["summary"]["contradictions_before"] - 1
