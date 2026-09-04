"""
API contract tests for the contradiction endpoints.

These run against the real FastAPI app with the real corpus loaded — the point
is that the surface the front end talks to actually behaves as documented,
including its access control.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app  # noqa: E402

INVESTIGATOR = {"X-Auth-Token": "demo-investigator"}
ADMIN = {"X-Auth-Token": "demo-admin"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_list_returns_findings_and_config(client):
    r = client.get("/api/contradictions", headers=INVESTIGATOR)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == len(body["items"]) > 0
    assert set(body["counts_by_severity"]) == {"high", "medium", "low"}
    # Thresholds travel with the findings: a rule the caller cannot see is not reviewable.
    assert body["config"]["max_reasonable_speed_kmph"] > 0
    assert body["config"]["source_reliability"]["cdr"] > body["config"]["source_reliability"]["ocr"]
    assert "not conclusions" in body["disclaimer"]


def test_list_reports_what_it_declined_to_flag(client):
    body = client.get("/api/contradictions", headers=INVESTIGATOR).json()
    assert body["skipped"], "the engine must show where it declined to draw a conclusion"
    assert all({"check", "reason"} <= set(s) for s in body["skipped"])


def test_filters(client):
    all_items = client.get("/api/contradictions", headers=INVESTIGATOR).json()
    high = client.get("/api/contradictions?severity=high", headers=INVESTIGATOR).json()
    assert all(i["severity"] == "high" for i in high["items"])
    assert high["total"] <= all_items["total"]

    one_type = client.get("/api/contradictions?type=timeline_conflict",
                          headers=INVESTIGATOR).json()
    assert all(i["type"] == "timeline_conflict" for i in one_type["items"])
    assert one_type["total"] >= 1


def test_detail_carries_full_provenance_and_documents(client):
    listing = client.get("/api/contradictions", headers=INVESTIGATOR).json()
    cid = listing["items"][0]["id"]
    r = client.get(f"/api/contradictions/{cid}", headers=INVESTIGATOR)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == cid
    assert body["contradicting_evidence"]
    # Every cited source resolves to a document the caller can open.
    for row in body["contradicting_evidence"]:
        assert row["source_id"]
    assert body["documents"], "the drawer must be able to show the original record"


def test_unknown_contradiction_is_404(client):
    assert client.get("/api/contradictions/C999", headers=INVESTIGATOR).status_code == 404


def test_unknown_token_is_rejected(client):
    """
    The demo deliberately defaults a missing header to `demo-investigator` so it
    runs with no identity provider (see `app/auth.py`), so absence of a token is
    not an error here. An unrecognised token still is.
    """
    bad = {"X-Auth-Token": "not-a-real-token"}
    assert client.get("/api/contradictions", headers=bad).status_code == 401
    assert client.get("/api/contradictions/C001", headers=bad).status_code == 401


def test_endpoints_are_permission_checked(client):
    """
    Both endpoints run through `require()` before answering, and both
    permissions they ask for are held by the investigator role — so a
    successful call here is evidence the check ran, not that it was skipped.
    """
    from app.auth import ROLES
    assert "graph:read" in ROLES["investigator"]      # the listing
    assert "evidence:read" in ROLES["investigator"]   # the detail view
    assert client.get("/api/contradictions", headers=INVESTIGATOR).status_code == 200


def test_admin_sees_the_same_findings(client):
    a = client.get("/api/contradictions", headers=INVESTIGATOR).json()
    b = client.get("/api/contradictions", headers=ADMIN).json()
    assert [i["id"] for i in a["items"]] == [i["id"] for i in b["items"]]


def test_response_is_stable_across_calls(client):
    """Two identical requests must not renumber the findings."""
    a = client.get("/api/contradictions", headers=INVESTIGATOR).json()
    b = client.get("/api/contradictions", headers=INVESTIGATOR).json()
    assert a["items"] == b["items"]


# ------------------------------------------------------- impact simulator

def test_impact_requires_something_to_withhold(client):
    assert client.get("/api/impact", headers=INVESTIGATOR).status_code == 400


def test_impact_rejects_an_unknown_source(client):
    r = client.get("/api/impact?source_id=NOPE/1", headers=INVESTIGATOR)
    assert r.status_code == 404


def test_impact_returns_a_diff(client):
    r = client.get("/api/impact?source_id=FIR/2026/0107", headers=INVESTIGATOR)
    assert r.status_code == 200
    body = r.json()
    s = body["summary"]
    assert s["links_after"] < s["links_before"]
    assert body["withheld"][0]["source_id"] == "FIR/2026/0107"
    assert "re-run" in body["method"]


def test_impact_accepts_repeated_record_ids(client):
    """The contradiction engine cites CDR rows, so the endpoint must take several."""
    r = client.get("/api/impact?record_id=C000054&record_id=C000017", headers=INVESTIGATOR)
    assert r.status_code == 200
    body = r.json()
    assert sorted(body["exclude_records"]) == ["C000017", "C000054"]
    assert any(c["type"] == "timeline_conflict" for c in body["contradictions_resolved"])


def test_impact_does_not_disturb_the_served_baseline(client):
    """A simulation must not change what the other endpoints report afterwards."""
    before = client.get("/api/stats", headers=INVESTIGATOR).json()
    before_c = client.get("/api/contradictions", headers=INVESTIGATOR).json()["total"]
    client.get("/api/impact?source_id=CDR", headers=INVESTIGATOR)
    after = client.get("/api/stats", headers=INVESTIGATOR).json()
    after_c = client.get("/api/contradictions", headers=INVESTIGATOR).json()["total"]
    assert before == after
    assert before_c == after_c
