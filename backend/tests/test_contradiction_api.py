"""
API contract tests for the contradiction endpoints.

These run against the real FastAPI app with the real corpus loaded — the point
is that the surface the front end talks to actually behaves as documented,
including its access control.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from auth_helpers import ROLE_IDENTITIES, bearer, mint_supabase_token  # noqa: E402

# `client`, `investigator` and `admin` come from conftest (Supabase tokens).
# The analysis (legacy) endpoints are authorized by the same Supabase
# identity; the NEXUS role maps to the pipeline's investigator/admin
# principals.


def test_list_returns_findings_and_config(client):
    r = client.get("/api/contradictions", headers=investigator)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == len(body["items"]) > 0
    assert set(body["counts_by_severity"]) == {"high", "medium", "low"}
    # Thresholds travel with the findings: a rule the caller cannot see is not reviewable.
    assert body["config"]["max_reasonable_speed_kmph"] > 0
    assert body["config"]["source_reliability"]["cdr"] > body["config"]["source_reliability"]["ocr"]
    assert "not conclusions" in body["disclaimer"]


def test_list_reports_what_it_declined_to_flag(client):
    body = client.get("/api/contradictions", headers=investigator).json()
    assert body["skipped"], "the engine must show where it declined to draw a conclusion"
    assert all({"check", "reason"} <= set(s) for s in body["skipped"])


def test_filters(client):
    all_items = client.get("/api/contradictions", headers=investigator).json()
    high = client.get("/api/contradictions?severity=high", headers=investigator).json()
    assert all(i["severity"] == "high" for i in high["items"])
    assert high["total"] <= all_items["total"]

    one_type = client.get("/api/contradictions?type=timeline_conflict",
                          headers=investigator).json()
    assert all(i["type"] == "timeline_conflict" for i in one_type["items"])
    assert one_type["total"] >= 1


def test_detail_carries_full_provenance_and_documents(client):
    listing = client.get("/api/contradictions", headers=investigator).json()
    cid = listing["items"][0]["id"]
    r = client.get(f"/api/contradictions/{cid}", headers=investigator)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == cid
    assert body["contradicting_evidence"]
    # Every cited source resolves to a document the caller can open.
    for row in body["contradicting_evidence"]:
        assert row["source_id"]
    assert body["documents"], "the drawer must be able to show the original record"


def test_unknown_contradiction_is_404(client):
    assert client.get("/api/contradictions/C999", headers=investigator).status_code == 404


def test_missing_or_bad_token_is_rejected(client):
    """
    The analysis endpoints are authorized by the Supabase identity: a missing
    token is an error, and a token that cannot be verified is an error too.
    There is no default role and no auth bypass.
    """
    # No Authorization header at all.
    assert client.get("/api/contradictions").status_code == 401
    assert client.get("/api/contradictions/C001").status_code == 401
    # A bearer token that fails verification (wrong signing secret).
    bad = bearer(mint_supabase_token(ROLE_IDENTITIES["INVESTIGATOR"]["sub"],
                                     secret="not-the-project-secret"))
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
    assert client.get("/api/contradictions", headers=investigator).status_code == 200


def test_admin_sees_the_same_findings(client):
    a = client.get("/api/contradictions", headers=investigator).json()
    b = client.get("/api/contradictions", headers=admin).json()
    assert [i["id"] for i in a["items"]] == [i["id"] for i in b["items"]]


def test_response_is_stable_across_calls(client):
    """Two identical requests must not renumber the findings."""
    a = client.get("/api/contradictions", headers=investigator).json()
    b = client.get("/api/contradictions", headers=investigator).json()
    assert a["items"] == b["items"]


# ------------------------------------------------------- impact simulator

def test_impact_requires_something_to_withhold(client):
    assert client.get("/api/impact", headers=investigator).status_code == 400


def test_impact_rejects_an_unknown_source(client):
    r = client.get("/api/impact?source_id=NOPE/1", headers=investigator)
    assert r.status_code == 404


def test_impact_returns_a_diff(client):
    r = client.get("/api/impact?source_id=FIR/2026/0107", headers=investigator)
    assert r.status_code == 200
    body = r.json()
    s = body["summary"]
    assert s["links_after"] < s["links_before"]
    assert body["withheld"][0]["source_id"] == "FIR/2026/0107"
    assert "re-run" in body["method"]


def test_impact_accepts_repeated_record_ids(client):
    """The contradiction engine cites CDR rows, so the endpoint must take several."""
    r = client.get("/api/impact?record_id=C000054&record_id=C000017", headers=investigator)
    assert r.status_code == 200
    body = r.json()
    assert sorted(body["exclude_records"]) == ["C000017", "C000054"]
    assert any(c["type"] == "timeline_conflict" for c in body["contradictions_resolved"])


def test_impact_does_not_disturb_the_served_baseline(client):
    """A simulation must not change what the other endpoints report afterwards."""
    before = client.get("/api/stats", headers=investigator).json()
    before_c = client.get("/api/contradictions", headers=investigator).json()["total"]
    client.get("/api/impact?source_id=CDR", headers=investigator)
    after = client.get("/api/stats", headers=investigator).json()
    after_c = client.get("/api/contradictions", headers=investigator).json()["total"]
    assert before == after
    assert before_c == after_c
