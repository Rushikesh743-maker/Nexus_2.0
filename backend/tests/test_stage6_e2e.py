"""Stage 6 — the ONE end-to-end workflow test.

CREATE CASE -> upload 3+ documents -> poll real processing state ->
extraction -> entity resolution (matches) -> confirm candidates ->
build graph -> run intelligence -> verify findings / timeline /
locations / copilot retrieval -> idempotent re-upload -> upload after
analysis marks findings STALE.

No manual data edits: every confirmed row in the case is created by the
pipeline plus the investigator's API decisions, exactly like the UI.
Runs against the real development PostgreSQL (same convention as the
other API test modules); each run creates its own case with a unique
case number so the suite is re-runnable.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


RUN = time.strftime("%Y%m%d-%H%M%S")
# `client`, `auth` and `analyst` come from conftest (Supabase tokens).

# Synthetic demonstration data — the same fictional corpus names the
# platform's reproducible gazetteer knows (no real persons).
DOC1 = (
    "SYNTHETIC TEST DOCUMENT 1\n"
    "On 2026-09-01 10:00, Suresh Yadav was seen at Chembur.\n"
    "Mobile 9000000901 was found in the records.\n"
    "Vehicle MH09ZZ9999 was parked nearby.\n"
)
DOC2 = (
    "SYNTHETIC TEST DOCUMENT 2\n"
    "On 2026-09-01 10:10, Suresh Yadav was seen at Kurla.\n"
    "Suresh Yadav called Altaf Khan at 10:12.\n"
)
DOC3 = (
    "call_id,caller,callee,start_time,duration_sec,cell_tower\n"
    "T1,9000000901,9000000902,2026-09-01 10:12:00,30,Chembur\n"
)
DOC4 = (
    "SYNTHETIC TEST DOCUMENT 4\n"
    "On 2026-09-01 11:00, Suresh Yadav was seen at Worli.\n"
)


CREATED_CASE_IDS: list[int] = []


@pytest.fixture(autouse=True)
def _cleanup_created_cases(client):
    """Remove this module's cases after EACH test.

    Other modules (e.g. test_v1_api) assert on the shared case list, so
    no test-created case may survive into the next module.
    """
    from app.core.database import SessionLocal
    from app.models import Case as _Case
    before = len(CREATED_CASE_IDS)
    yield
    fresh = CREATED_CASE_IDS[before:]
    if fresh:
        db = SessionLocal()
        try:
            for cid in sorted(set(fresh), reverse=True):
                db.query(_Case).filter(_Case.id == cid).delete()
            db.commit()
        finally:
            db.close()


def _unique_case_number(client, headers):
    for attempt in range(20):
        number = f"CASE-2026-{int(time.strftime('%M%S')) % 900 + 100}{attempt % 10}"
        r = client.post(
            "/api/v1/cases",
            json={"case_number": number,
                  "title": f"Stage-6 E2E test case ({RUN}) — synthetic",
                  "description": "SYNTHETIC DEMONSTRATION DATA",
                  "priority": "MEDIUM"},
            headers=headers)
        if r.status_code == 201:
            body = r.json()
            CREATED_CASE_IDS.append(body["id"])
            return body
        if r.status_code != 409:
            assert r.status_code == 400, r.text  # number pattern
    raise AssertionError("could not allocate a unique case number")


def _upload(client, headers, case_id, filename, content, ctype):
    return client.post(
        f"/api/v1/cases/{case_id}/documents",
        files={"file": (filename, content.encode("utf-8"), ctype)},
        headers=headers)


def _wait_all_processed(client, headers, case_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/v1/cases/{case_id}/processing/status",
                       headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()
        if data["all_processed"]:
            return data
        time.sleep(0.2)
    raise AssertionError("documents did not finish processing")


def _review_queue(client, headers, case_id):
    r = client.get(f"/api/v1/cases/{case_id}/review/queue", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _accept_everything(client, headers, case_id, max_rounds=25):
    """Walk the review queue exactly like the UI: matches, then entities,
    then relationships, until nothing is pending."""
    accepted = {"matches": 0, "entities": 0, "relationships": 0}
    for _ in range(max_rounds):
        q = _review_queue(client, headers, case_id)
        progressed = False
        for m in q["potential_duplicates"]:
            r = client.post(
                f"/api/v1/documents/{m['document_id']}/extraction/"
                f"matches/{m['match_id']}/accept", headers=headers)
            assert r.status_code == 200, r.text
            accepted["matches"] += 1
            progressed = True
        for e in q["new_entities"]:
            r = client.post(
                f"/api/v1/documents/{e['document_id']}/extraction/"
                f"candidates/{e['id']}/accept", headers=headers)
            assert r.status_code == 200, r.text
            accepted["entities"] += 1
            progressed = True
        for rel in q["candidate_relationships"]:
            r = client.post(
                f"/api/v1/documents/{rel['document_id']}/extraction/"
                f"relationships/{rel['id']}/accept", headers=headers)
            assert r.status_code == 200, r.text
            accepted["relationships"] += 1
            progressed = True
        if not progressed:
            break
    return accepted


def test_full_document_to_intelligence_workflow(client, auth):
    # 1 — CREATE CASE
    case = _unique_case_number(client, auth)
    case_id = case["id"]

    # 2 — UPLOAD 3 documents (TXT, TXT, CSV)
    r = _upload(client, auth, case_id, "doc1.txt", DOC1, "text/plain")
    assert r.status_code == 201, r.text
    r = _upload(client, auth, case_id, "doc2.txt", DOC2, "text/plain")
    assert r.status_code == 201, r.text
    r = _upload(client, auth, case_id, "cdr.csv", DOC3, "text/csv")
    assert r.status_code == 201, r.text

    # 3 — PROCESSING: real async state, polled (no fake progress)
    data = _wait_all_processed(client, auth, case_id)
    assert data["total"] == 3
    assert data["by_status"].get("PROCESSED") == 3

    # 4 — EXTRACTION happened: candidates exist in the review queue
    q = _review_queue(client, auth, case_id)
    assert q["total_pending"] > 0
    names = {e["name"] for e in q["new_entities"]}
    assert "Suresh Yadav" in names
    assert "9000000901" in names
    assert "MH09ZZ9999" in names
    assert any(r["relationship_type"] == "CALLED"
               for r in q["candidate_relationships"])

    # 5 — RESOLVE + CONFIRM (matches first, then entities, then rels)
    accepted = _accept_everything(client, auth, case_id)
    assert accepted["entities"] >= 4
    assert accepted["relationships"] >= 2
    q = _review_queue(client, auth, case_id)
    assert q["total_pending"] == 0

    # confirmed data now exists
    r = client.get(f"/api/v1/cases/{case_id}/entities", headers=auth)
    entities = r.json()
    assert any(e["canonical_name"] == "Suresh Yadav" for e in entities)
    assert any(e["entity_type"] == "phone" for e in entities)
    r = client.get(f"/api/v1/cases/{case_id}/relationships", headers=auth)
    rels = r.json()
    assert any(x["relationship_type"] == "CALLED" for x in rels)

    # 6 — BUILD GRAPH
    r = client.post(f"/api/v1/cases/{case_id}/graph/build", headers=auth)
    assert r.status_code == 200, r.text
    built = r.json()
    assert built["nodes"] >= 4 and built["edges"] >= 2

    # 7 — RUN INTELLIGENCE (one call)
    r = client.post(f"/api/v1/cases/{case_id}/analysis/run", headers=auth)
    assert r.status_code == 200, r.text
    run1 = r.json()
    assert run1["status"] == "completed"
    assert run1["graph_nodes"] == built["nodes"]
    assert run1["findings_count"] >= 1  # the spatial contradiction
    version1 = run1["graph_version"]

    # the contradiction is real and explainable
    r = client.get(f"/api/v1/cases/{case_id}/investigation/findings",
                   headers=auth)
    findings = r.json()["current_findings"]
    contra = [f for f in findings if f["finding_type"] == "CONTRADICTION"]
    assert contra, "expected the evidence-contradiction finding"
    assert any("Chembur" in (f["title"] + str(f.get("details", {})))
               or "Kurla" in (f["title"] + str(f.get("details", {})))
               for f in contra)

    # 8 — TIMELINE + LOCATIONS from the case data
    r = client.get(f"/api/v1/cases/{case_id}/timeline", headers=auth)
    events = r.json()
    assert len(events) >= 2
    r = client.get(f"/api/v1/cases/{case_id}/locations", headers=auth)
    locations = r.json()
    assert any(l["name"] == "Chembur" for l in locations)
    assert any(l["name"] == "Kurla" for l in locations)

    # 9 — COPILOT is case-aware after analysis
    r = client.post(f"/api/v1/cases/{case_id}/copilot/ask",
                    json={"question": "Who is connected to Suresh Yadav?"},
                    headers=auth)
    assert r.status_code == 200, r.text
    answer = r.json()
    assert answer["status"] in ("answered", "not_enough_data")
    assert answer["answer_text"]

    # 10 — IDEMPOTENT RE-UPLOAD: same file, same case -> 409, no dupes
    r = _upload(client, auth, case_id, "doc1.txt", DOC1, "text/plain")
    assert r.status_code == 409
    data = _wait_all_processed(client, auth, case_id)
    assert data["total"] == 3  # unchanged
    r = client.get(f"/api/v1/cases/{case_id}/summary", headers=auth)
    assert r.json()["counts"]["documents"] == 3

    # re-running the analysis on the same snapshot is a no-op
    r = client.post(f"/api/v1/cases/{case_id}/analysis/run", headers=auth)
    run1b = r.json()
    assert run1b["recomputed"] is False
    assert run1b["graph_version"] == version1

    # 11 — UPLOAD AFTER ANALYSIS: process the new doc, confirm it,
    #     re-run -> previous snapshot's findings are STALE, state
    #     returns to up-to-date
    r = _upload(client, auth, case_id, "doc4.txt", DOC4, "text/plain")
    assert r.status_code == 201, r.text
    _wait_all_processed(client, auth, case_id)

    # The new document's data is still candidates — confirmed data (the
    # versioned snapshot) is unchanged, so the state honestly stays
    # up-to-date. Staleness appears once the new data is confirmed.
    r = client.get(f"/api/v1/cases/{case_id}/analysis/status", headers=auth)
    assert r.json()["state"] == "up-to-date"

    _accept_everything(client, auth, case_id)
    r = client.get(f"/api/v1/cases/{case_id}/analysis/status", headers=auth)
    assert r.json()["state"] == "stale"
    r = client.post(f"/api/v1/cases/{case_id}/graph/build", headers=auth)
    assert r.json()["nodes"] > built["nodes"] or r.json()["edges"] >= built["edges"]
    r = client.post(f"/api/v1/cases/{case_id}/analysis/run", headers=auth)
    run2 = r.json()
    assert run2["status"] == "completed"
    assert run2["recomputed"] is True
    assert run2["graph_version"] != version1
    assert run2["stale_findings"] >= 1  # the old snapshot is kept, stale

    r = client.get(f"/api/v1/cases/{case_id}/analysis/status", headers=auth)
    status = r.json()
    assert status["state"] == "up-to-date"
    assert status["findings"]["stale"] >= 1

    # 12 — AUDIT trail recorded the whole workflow
    r = client.get(f"/api/v1/cases/{case_id}/audit", headers=auth)
    actions = {e["action"] for e in r.json()["entries"]}
    for expected in ("CREATE_CASE", "DOCUMENT_UPLOADED",
                     "DOCUMENT_PROCESSING_COMPLETED", "ENTITY_ACCEPTED",
                     "RELATIONSHIP_ACCEPTED", "GRAPH_BUILD", "ANALYSIS_RUN"):
        assert expected in actions, f"missing audit action {expected}"


def test_workflow_rbac_and_isolation(client, analyst, auth):
    # analyst may read but may not run analysis or build the graph...
    r = client.get("/api/v1/cases", headers=analyst)
    case_id = r.json()[0]["id"]
    r = client.post(f"/api/v1/cases/{case_id}/analysis/run", headers=analyst)
    assert r.status_code == 403
    # ...and unauthenticated requests are rejected everywhere
    r = client.get(f"/api/v1/cases/{case_id}/analysis/status")
    assert r.status_code == 401
    r = client.post(f"/api/v1/cases/{case_id}/analysis/run")
    assert r.status_code == 401
    # unknown case -> 404, never a cross-case read
    r = client.get("/api/v1/cases/999999/summary", headers=auth)
    assert r.status_code == 404
    # insufficient-data cases return an honest state, not an error page
    r = client.post("/api/v1/cases/999999/graph/build", headers=auth)
    assert r.status_code == 404


def test_empty_case_analysis_is_honest(client, auth):
    case = _unique_case_number(client, auth)
    case_id = case["id"]
    r = client.post(f"/api/v1/cases/{case_id}/analysis/run", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "insufficient"
    assert body["findings_count"] == 0
    r = client.get(f"/api/v1/cases/{case_id}/analysis/status", headers=auth)
    assert r.json()["state"] == "insufficient"
