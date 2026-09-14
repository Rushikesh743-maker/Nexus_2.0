"""Stage 7 — the unified investigation workspace, end to end (pytest).

Three tests, all against the real development PostgreSQL via TestClient,
each creating its own case (unique number, cleaned up afterwards) so the
suite is re-runnable and never pollutes the shared seeded data:

1. ``test_stage7_full_lifecycle`` — the spec's E2E chain:
   create -> upload A+B -> process (real job, real stages) -> verify
   extraction -> EXPLICIT bulk confirm -> graph -> intelligence run
   (versioned, ANALYSIS_COMPLETE) -> copilot with citations -> upload C
   -> STALE -> process -> confirm -> analysis STALE with reason ->
   RECALCULATE -> previous findings preserved as stale, new snapshot
   current -> audit trail complete.

2. ``test_failure_isolation_and_retry`` — valid/invalid/valid documents:
   the bad one never stops the case (2 processed, 1 failed), the job
   reports the failure honestly, RETRY FAILED re-runs exactly the failed
   document (it fails again — no masking), and the confirmed workflow
   proceeds for the good documents.

3. ``test_two_user_isolation`` — investigator B cannot read, upload,
   review, build, analyze or copilot on investigator A's case (404
   everywhere, not 403 — no existence leakage), cannot see it in the
   case list, and the platform's demo case is likewise invisible to B.

Synthetic demonstration data only (corpus gazetteer names).
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal  # noqa: E402
from app.models import Case as _Case  # noqa: E402

RUN = time.strftime("%Y%m%d-%H%M%S")
# `client`, `auth`, `analyst` and `investigator_b` come from conftest
# (Supabase tokens).
FIXTURES = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "documents"))

# Synthetic demonstration data — corpus gazetteer names so the
# deterministic rule extractor fires exactly like the demo case.
DOC_A = (
    "FIR Summary — Case No. 777/2026 (SYNTHETIC DEMONSTRATION DATA)\n\n"
    "On 2026-09-05 09:00, Vikram Sethi was seen at Bhiwandi Godown.\n"
    "On 2026-09-05 09:10, Vikram Sethi was seen at Kurla.\n"
    "The accused was carrying vehicle MH12XY7777 and mobile number 9122222001.\n"
    "On 2026-09-05 11:30, Vikram Sethi called Sanjay Bhosle.\n"
    "Sanjay Bhosle uses vehicle GJ33AB7777 and mobile number 9122222002.\n"
)
DOC_B = (
    "call_id,caller,callee,start_time,duration_sec,cell_tower\n"
    "E1,9122222001,9122222002,2026-09-05 11:30:00,140,Kurla\n"
    "E2,9122222002,9122222001,2026-09-05 13:05:00,55,Chembur\n"
)
DOC_C = (
    "Supplement (SYNTHETIC DEMONSTRATION DATA)\n\n"
    "On 2026-09-06 10:00, Vikram Sethi was seen at Kurla.\n"
    "On 2026-09-06 10:20, Vikram Sethi called Rajesh Kumar.\n"
    "Rajesh Kumar uses mobile number 9122222003.\n"
)

CREATED_CASE_IDS: list[int] = []


@pytest.fixture(autouse=True)
def _cleanup_created_cases(client):
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


def _new_case(client, headers, tag):
    # case_number pattern: ^[A-Z]{2,8}-\d{4}-\d{3,}$
    for attempt in range(20):
        number = f"STG-2026-{int(time.time() * 1000) % 1000000:06d}{attempt % 10}"
        r = client.post(
            "/api/v1/cases",
            json={"case_number": number, "title": f"Stage-7 E2E {tag} ({RUN})",
                  "description": "SYNTHETIC DEMONSTRATION DATA",
                  "priority": "MEDIUM"},
            headers=headers)
        if r.status_code == 201:
            body = r.json()
            CREATED_CASE_IDS.append(body["id"])
            return body
        assert r.status_code == 409, r.text
    raise AssertionError("could not allocate a unique case number")


def _upload(client, headers, case_id, filename, content, ctype):
    return client.post(
        f"/api/v1/cases/{case_id}/documents",
        files={"file": (filename, content.encode("utf-8"), ctype)},
        headers=headers)


def _wait_job(client, headers, case_id, timeout=60):
    """Poll the real processing job until it reaches a terminal state."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/v1/cases/{case_id}/processing/status",
                       headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()
        if data["job"]["status"] in ("COMPLETED", "FAILED"):
            return data
        time.sleep(0.2)
    raise AssertionError("processing job did not finish in time")


def _lifecycle(client, headers, case_id):
    r = client.get(f"/api/v1/cases/{case_id}/lifecycle", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _bulk(client, headers, case_id, category, action, item_ids):
    return client.post(f"/api/v1/cases/{case_id}/review/bulk",
                       headers=headers,
                       json={"category": category, "action": action,
                             "item_ids": item_ids})


def _confirm_queue(client, headers, case_id, max_rounds=20):
    """Explicit bulk-confirm the queue exactly like the UI: matches,
    then the still-pending entities, then relationships."""
    accepted = {"matches": 0, "entities": 0, "relationships": 0}
    for _ in range(max_rounds):
        r = client.get(f"/api/v1/cases/{case_id}/review/queue", headers=headers)
        assert r.status_code == 200, r.text
        q = r.json()
        match_ids = [e["match_id"] for e in q["potential_duplicates"]
                     if e.get("match_id")]
        if match_ids:
            r = _bulk(client, headers, case_id, "match", "confirm", match_ids)
            assert r.status_code == 200, r.text
            accepted["matches"] += r.json()["applied"]
            # match acceptance ACCEPTs the matched candidates — re-read
            q = client.get(f"/api/v1/cases/{case_id}/review/queue",
                           headers=headers).json()
        entity_ids = [e["id"] for e in q["new_entities"]
                      + q["potential_duplicates"]]
        if entity_ids:
            r = _bulk(client, headers, case_id, "entity", "confirm",
                      entity_ids)
            assert r.status_code == 200, r.text
            accepted["entities"] += r.json()["applied"]
        rel_ids = [rel["id"] for rel in q["candidate_relationships"]]
        if rel_ids:
            r = _bulk(client, headers, case_id, "relationship", "confirm",
                      rel_ids)
            assert r.status_code == 200, r.text
            accepted["relationships"] += r.json()["applied"]
        q = client.get(f"/api/v1/cases/{case_id}/review/queue",
                       headers=headers).json()
        if q["total_pending"] == 0:
            break
    return accepted


# ====================================================================== 1
def test_stage7_full_lifecycle(client, auth):
    # 1 — CREATE (DRAFT)
    case = _new_case(client, auth, "lifecycle")
    case_id = case["id"]
    assert case["workflow_state"] == "DRAFT"
    lc = _lifecycle(client, auth, case_id)
    assert lc["workflow_state"] == "DRAFT"
    assert "UPLOADING" in lc["allowed_next"]

    # 2 — UPLOAD A + B (-> UPLOADING)
    assert _upload(client, auth, case_id, "fir.txt", DOC_A,
                   "text/plain").status_code == 201
    assert _upload(client, auth, case_id, "cdr.csv", DOC_B,
                   "text/csv").status_code == 201
    assert _lifecycle(client, auth, case_id)["workflow_state"] == "UPLOADING"

    # 3 — PROCESS: real job, real stages, no fake progress
    r = client.post(f"/api/v1/cases/{case_id}/process", headers=auth)
    assert r.status_code == 200, r.text
    job = r.json()
    assert job["status"] == "queued" and job["job_id"]
    ps = _wait_job(client, auth, case_id)
    assert ps["job"]["status"] == "COMPLETED"
    assert ps["job"]["processed_documents"] == 2
    assert ps["job"]["failed_documents"] == 0
    checklist = {c["stage"]: (c["done"], c["total"])
                 for c in ps["stage_checklist"]}
    assert checklist["ingestion"] == (2, 2)
    assert checklist["text_extraction"] == (2, 2)
    assert checklist["entity_extraction"] == (2, 2)
    assert checklist["relationship_extraction"] == (2, 2)
    assert _lifecycle(client, auth, case_id)["workflow_state"] == \
        "REVIEW_REQUIRED"

    # 4 — EXTRACTION (candidates with provenance, nothing auto-confirmed)
    r = client.get(f"/api/v1/cases/{case_id}/graph", headers=auth)
    assert r.json()["node_count"] == 0  # no auto-confirm
    q = client.get(f"/api/v1/cases/{case_id}/review/queue",
                   headers=auth).json()
    assert q["total_pending"] > 0
    names = {e["name"] for e in q["new_entities"]}
    assert "Vikram Sethi" in names
    assert any(rel["relationship_type"] == "CALLED"
               for rel in q["candidate_relationships"])
    e0 = q["new_entities"][0]
    assert e0.get("source_document") and e0.get("source_snippet") \
        and e0.get("confidence") is not None

    # 5 — EXPLICIT bulk confirm (the investigator's decision)
    accepted = _confirm_queue(client, auth, case_id)
    assert accepted["entities"] >= 4 and accepted["relationships"] >= 1
    assert _lifecycle(client, auth, case_id)["workflow_state"] == \
        "READY_FOR_ANALYSIS"

    # 6 — GRAPH from confirmed data only
    r = client.post(f"/api/v1/cases/{case_id}/graph/build", headers=auth)
    assert r.status_code == 200, r.text
    built = r.json()
    assert built["nodes"] >= 4 and built["edges"] >= 1
    assert "components" in built["stats"] and "communities" in built["stats"]

    # 7 — INTELLIGENCE (one call, versioned run)
    r = client.post(f"/api/v1/cases/{case_id}/analysis/run", headers=auth)
    assert r.status_code == 200, r.text
    run1 = r.json()
    assert run1["status"] == "completed"
    assert run1["version"] == 1 and run1["analysis_id"]
    assert run1["findings_count"] >= 1  # the location contradiction
    assert _lifecycle(client, auth, case_id)["workflow_state"] == \
        "ANALYSIS_COMPLETE"
    st = client.get(f"/api/v1/cases/{case_id}/analysis/status",
                    headers=auth).json()
    assert st["state"] == "up-to-date" and st["last_analysis_at"]

    # idempotent re-run on the same snapshot
    r = client.post(f"/api/v1/cases/{case_id}/analysis/run", headers=auth)
    assert r.json()["status"] == "no_changes"
    # recalculate while up-to-date is rejected
    r = client.post(f"/api/v1/cases/{case_id}/analysis/recalculate",
                    headers=auth)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "NOT_STALE"

    # 8 — COPILOT in the same case, with citations
    r = client.post(f"/api/v1/cases/{case_id}/copilot/ask",
                    json={"question":
                          "How is Vikram Sethi connected to Sanjay Bhosle?"},
                    headers=auth)
    assert r.status_code == 200, r.text
    answer = r.json()
    assert answer["answer_text"]
    assert len(answer["citations"]) >= 1

    # 9 — SECOND UPLOAD -> STALE (workflow), re-process
    assert _upload(client, auth, case_id, "supplement.txt", DOC_C,
                   "text/plain").status_code == 201
    assert _lifecycle(client, auth, case_id)["workflow_state"] == "STALE"
    r = client.post(f"/api/v1/cases/{case_id}/process", headers=auth)
    assert r.status_code == 200, r.text
    ps = _wait_job(client, auth, case_id)
    assert ps["job"]["status"] == "COMPLETED"
    assert ps["job"]["processed_documents"] == 3
    assert _lifecycle(client, auth, case_id)["workflow_state"] == \
        "REVIEW_REQUIRED"

    # 10 — confirm the new candidates -> analysis STALE with a reason
    accepted2 = _confirm_queue(client, auth, case_id)
    assert accepted2["entities"] >= 1
    st = client.get(f"/api/v1/cases/{case_id}/analysis/status",
                    headers=auth).json()
    assert st["state"] == "stale"
    assert st["reason"]
    assert _lifecycle(client, auth, case_id)["workflow_state"] == \
        "READY_FOR_ANALYSIS"

    # 11 — RECALCULATE: new snapshot current, old findings kept as stale
    r = client.post(f"/api/v1/cases/{case_id}/analysis/recalculate",
                    headers=auth)
    assert r.status_code == 200, r.text
    run3 = r.json()
    assert run3["status"] in ("completed", "no_changes")
    assert run3["version"] == 3
    st = client.get(f"/api/v1/cases/{case_id}/analysis/status",
                    headers=auth).json()
    assert st["state"] == "up-to-date"
    assert st["findings"]["stale"] >= 1  # previous snapshot preserved
    assert _lifecycle(client, auth, case_id)["workflow_state"] == \
        "ANALYSIS_COMPLETE"

    # 12 — the update is real: the new entity is confirmed and in the graph
    r = client.get(f"/api/v1/cases/{case_id}/entities", headers=auth)
    assert any(e["canonical_name"] == "Rajesh Kumar" for e in r.json())
    g = client.get(f"/api/v1/cases/{case_id}/graph", headers=auth).json()
    assert g["node_count"] >= built["nodes"]

    # 13 — AUDIT trail records the whole workflow
    r = client.get(f"/api/v1/cases/{case_id}/audit", headers=auth)
    actions = {a["action"] for a in r.json()["entries"]}
    for needed in ("DOCUMENT_UPLOADED", "PROCESSING_JOB_STARTED",
                   "PROCESSING_JOB_COMPLETED", "REVIEW_BULK", "GRAPH_BUILD",
                   "ANALYSIS_RUN", "RECALCULATE", "CASE_STATE_TRANSITION"):
        assert needed in actions, f"missing audit action {needed}"


# ====================================================================== 2
def test_failure_isolation_and_retry(client, auth):
    case = _new_case(client, auth, "failure")
    case_id = case["id"]

    # valid / INVALID / valid
    with open(os.path.join(FIXTURES, "synthetic_fir.pdf"), "rb") as fh:
        good = fh.read()
    bad_pdf = good[:120] + b"%corrupt-stage7 " + RUN.encode()
    assert _upload(client, auth, case_id, "ok1.txt", DOC_A,
                   "text/plain").status_code == 201
    r = client.post(f"/api/v1/cases/{case_id}/documents",
                    files={"file": (f"bad_{RUN}.pdf", bad_pdf,
                                    "application/pdf")},
                    headers=auth)
    assert r.status_code == 201, r.text
    assert _upload(client, auth, case_id, "ok2.txt", DOC_C,
                   "text/plain").status_code == 201

    # the job settles the case — it must finish COMPLETED with the real
    # split: 2 processed, 1 failed, never blocked by the failure
    r = client.post(f"/api/v1/cases/{case_id}/process", headers=auth)
    assert r.status_code == 200, r.text
    ps = _wait_job(client, auth, case_id)
    assert ps["job"]["status"] == "COMPLETED"
    assert ps["job"]["processed_documents"] == 2
    assert ps["job"]["failed_documents"] == 1
    assert ps["job"]["error"]  # names the failed document

    # the good documents' candidates were extracted; the bad one produced
    # nothing and is honestly FAILED
    docs = {d["filename"]: d for d in ps["documents"]}
    assert docs["ok1.txt"]["processing_status"] == "PROCESSED"
    assert docs["ok2.txt"]["processing_status"] == "PROCESSED"
    bad = [d for d in docs.values()
           if d["processing_status"] == "FAILED"]
    assert len(bad) == 1 and bad[0]["processing_error"]
    low = bad[0]["processing_error"].lower()
    assert "traceback" not in low and "/home" not in low

    # RETRY FAILED re-runs exactly the failed document — it fails again
    # (honest failure, no masking) and nothing is duplicated
    r = client.post(f"/api/v1/cases/{case_id}/process",
                    params={"retry_failed": "true"}, headers=auth)
    assert r.status_code == 200, r.text
    ps = _wait_job(client, auth, case_id)
    assert ps["job"]["status"] == "COMPLETED"
    assert ps["job"]["failed_documents"] == 1
    assert ps["job"]["processed_documents"] == 2
    docs = {d["filename"]: d for d in
            client.get(f"/api/v1/cases/{case_id}/documents",
                       headers=auth).json()}
    assert len(docs) == 3  # no duplicate rows from the retry

    # ...and the workflow proceeds for the good documents
    accepted = _confirm_queue(client, auth, case_id)
    assert accepted["entities"] >= 4
    assert _lifecycle(client, auth, case_id)["workflow_state"] == \
        "READY_FOR_ANALYSIS"
    r = client.post(f"/api/v1/cases/{case_id}/graph/build", headers=auth)
    assert r.status_code == 200, r.text
    r = client.post(f"/api/v1/cases/{case_id}/analysis/run", headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["status"] in ("completed", "no_changes")
    assert _lifecycle(client, auth, case_id)["workflow_state"] == \
        "ANALYSIS_COMPLETE"


# ====================================================================== 3
def test_two_user_isolation(client, auth, investigator_b, analyst):
    # User A builds a real case with data
    case = _new_case(client, auth, "isol-a")
    case_id = case["id"]
    assert _upload(client, auth, case_id, "fir.txt", DOC_A,
                   "text/plain").status_code == 201
    r = client.post(f"/api/v1/cases/{case_id}/process", headers=auth)
    assert r.status_code == 200, r.text
    _wait_job(client, auth, case_id)
    _confirm_queue(client, auth, case_id)
    r = client.post(f"/api/v1/cases/{case_id}/graph/build", headers=auth)
    assert r.status_code == 200, r.text

    # User B (another INVESTIGATOR) is locked out — 404, never 403 or 200,
    # so the case's existence is not leaked either
    r = client.get(f"/api/v1/cases/{case_id}", headers=investigator_b)
    assert r.status_code == 404
    r = client.get(f"/api/v1/cases/{case_id}/summary", headers=investigator_b)
    assert r.status_code == 404
    r = client.get(f"/api/v1/cases/{case_id}/documents", headers=investigator_b)
    assert r.status_code == 404
    r = client.post(f"/api/v1/cases/{case_id}/documents",
                    files={"file": ("evil.txt", b"x", "text/plain")},
                    headers=investigator_b)
    assert r.status_code == 404
    r = client.post(f"/api/v1/cases/{case_id}/review/bulk",
                    json={"category": "entity", "action": "confirm",
                          "item_ids": [1]},
                    headers=investigator_b)
    assert r.status_code == 404
    r = client.post(f"/api/v1/cases/{case_id}/graph/build", headers=investigator_b)
    assert r.status_code == 404
    r = client.get(f"/api/v1/cases/{case_id}/graph", headers=investigator_b)
    assert r.status_code == 404
    r = client.post(f"/api/v1/cases/{case_id}/analysis/run", headers=investigator_b)
    assert r.status_code == 404
    r = client.get(f"/api/v1/cases/{case_id}/analysis/status",
                   headers=investigator_b)
    assert r.status_code == 404
    r = client.post(f"/api/v1/cases/{case_id}/copilot/ask",
                    json={"question": "who is in this case?"},
                    headers=investigator_b)
    assert r.status_code == 404
    r = client.get(f"/api/v1/cases/{case_id}/audit", headers=investigator_b)
    assert r.status_code == 404
    r = client.get(f"/api/v1/cases/{case_id}/processing/status",
                   headers=investigator_b)
    assert r.status_code == 404

    # A's case does not appear in B's case list (no leakage via listing)
    r = client.get("/api/v1/cases", headers=investigator_b)
    assert r.status_code == 200
    numbers = {c["case_number"] for c in r.json()}
    assert case["case_number"] not in numbers

    # the demo case (owned by A) is likewise invisible to B
    r = client.get("/api/v1/cases", headers=auth)
    demo = next(c for c in r.json()
                if c["case_number"] == "CASE-DEMO-END2END-01")
    r = client.get(f"/api/v1/cases/{demo['id']}/summary", headers=investigator_b)
    assert r.status_code == 404
    r = client.post(f"/api/v1/cases/{demo['id']}/graph/build",
                    headers=investigator_b)
    assert r.status_code == 404

    # unauthenticated: 401 everywhere
    assert client.get(f"/api/v1/cases/{case_id}").status_code == 401
    assert client.post(f"/api/v1/cases/{case_id}/analysis/run").status_code \
        == 401

    # ANALYST: read access to any case (200 — not 404: analysts
    # legitimately know cases), but data-mutating intelligence actions
    # are role-restricted (403, per the role matrix)
    assert client.get(f"/api/v1/cases/{case_id}/summary",
                      headers=analyst).status_code == 200
    assert client.get(f"/api/v1/cases/{case_id}/graph",
                      headers=analyst).status_code == 200
    assert client.post(f"/api/v1/cases/{case_id}/analysis/run",
                       headers=analyst).status_code == 403
    r = client.post(f"/api/v1/cases/{case_id}/process", headers=analyst)
    assert r.status_code == 403
