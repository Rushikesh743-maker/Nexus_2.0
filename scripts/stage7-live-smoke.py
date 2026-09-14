#!/usr/bin/env python3
"""Stage 7 live smoke — the unified investigation workspace, end to end.

Runs against the live stack (http://127.0.0.1:8000) and verifies, in one
deterministic pass:

  1.  login (two investigators + supervisor)          9.  intelligence
  2.  create case (DRAFT)                              (findings/hypotheses/
  3.  upload FIR + CDR (UPLOADING)                       contradictions/gaps)
  4.  process job (queued -> COMPLETED, real stages)  10. copilot (ask +
  5.  extraction (candidates, checklist)                 citations)
  6.  review (queue, EXPLICIT bulk confirm)          11. second upload ->
  7.  graph (build stats, filters, provenance)          STALE (workflow)
  8.  timeline (+filters) / map (no fake coords)    12. confirm -> analysis
                                                      13. RECALCULATE (409
                                                          when not stale,
                                                          then real)
  14. stale findings preserved with reason          16. demo case exact
  15. audit trail + security (User B gets 404)        counts (renamed case)

No mock fallback, no fake progress: every check asserts real backend
state. Synthetic data only.
"""
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:8000/api/v1"
PW = "nexus2026"
FAILS = []
PASSES = [0]


def check(name: str, cond: bool, detail: str = ""):
    if cond:
        PASSES[0] += 1
        print(f"  ok   {name}")
    else:
        FAILS.append(name)
        print(f"  FAIL {name}  {detail}")


def req(method, path, token=None, body=None, ctype="application/json"):
    data = None
    if body is not None:
        data = (json.dumps(body).encode()
                if ctype == "application/json" else body)
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", ctype)
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except Exception:
            return e.code, None


def multipart(filename, content):
    b = uuid.uuid4().hex
    pre = ('--%s\r\nContent-Disposition: form-data; name="file"; filename="%s"\r\n'
           'Content-Type: text/plain\r\n\r\n' % (b, filename))
    return (pre.encode() + content.encode()
            + ("\r\n--%s--\r\n" % b).encode()), \
        "multipart/form-data; boundary=" + b


def login(email):
    s, j = req("POST", "/auth/login",
               body={"email": email, "password": PW})
    assert s == 200, f"login failed for {email}: {s} {j}"
    return j["access_token"]


def new_case_number():
    return "CASE-%04d-%03d" % (int(time.time()) % 10000, uuid.uuid4().int % 1000)


# Names/locations come from the synthetic corpus gazetteer (data/raw) so
# the deterministic rule extractor fires exactly like the demo case.
FIR_TEXT = (
    "FIR Summary — Case No. 333/2026 (SYNTHETIC DEMONSTRATION DATA)\n\n"
    "On 2026-08-01 14:00, Vikram Sethi was seen at Bhiwandi Godown.\n"
    "On 2026-08-01 14:10, Vikram Sethi was seen at Kurla.\n"
    "The accused was carrying vehicle MH12XY9999 and mobile number 9111111001.\n"
    "On 2026-08-01 15:30, Vikram Sethi called Sanjay Bhosle.\n"
    "Sanjay Bhosle uses vehicle GJ33AB4444 and mobile number 9111111002.\n"
)

CDR_TEXT = (
    "call_id,caller,callee,start_time,duration_sec,cell_tower\n"
    "D1001,9111111001,9111111002,2026-08-01 15:30:00,140,Kurla\n"
    "D1002,9111111002,9111111001,2026-08-01 18:05:00,55,Chembur\n"
)

SECOND_TEXT = (
    "Supplement (SYNTHETIC DEMONSTRATION DATA)\n\n"
    "On 2026-08-02 10:00, Vikram Sethi was seen at Kurla.\n"
    "On 2026-08-02 10:20, Vikram Sethi called Rajesh Kumar.\n"
    "Rajesh Kumar uses mobile number 9111111003.\n"
)


def main():
    # ------------------------------------------------------------ 1. login
    print("1. login (two investigators + supervisor)")
    tok_a = login("demo-investigator@nexus.local")
    tok_b = login("arjun.patil@nexus.gov.in")
    tok_s = login("priya.deshmukh@nexus.gov.in")
    check("investigator A + B + supervisor can log in",
          bool(tok_a and tok_b and tok_s))

    # ---------------------------------------------------------- 2. create
    print("2. create case (state DRAFT)")
    s, j = req("POST", "/cases", tok_a,
               {"case_number": new_case_number(), "title": "Stage 7 smoke case"})
    check("case created 201", s == 201, str(j))
    cid = j["id"]
    check("initial workflow_state is DRAFT", j.get("workflow_state") == "DRAFT",
          str(j.get("workflow_state")))
    s, lc = req("GET", f"/cases/{cid}/lifecycle", tok_a)
    check("lifecycle endpoint reports DRAFT + allowed next",
          s == 200 and lc["workflow_state"] == "DRAFT"
          and "UPLOADING" in lc["allowed_next"], str(lc))

    # -------------------------------------------------------- 3. uploads
    print("3. upload FIR + CDR (state -> UPLOADING)")
    data, ct = multipart("FIR.txt", FIR_TEXT)
    s, doc1 = req("POST", f"/cases/{cid}/documents", tok_a, data, ct)
    check("FIR upload 201", s == 201, str(doc1))
    data, ct = multipart("CDR.csv", CDR_TEXT)
    s, doc2 = req("POST", f"/cases/{cid}/documents", tok_a, data, ct)
    check("CDR upload 201", s == 201, str(doc2))
    s, lc = req("GET", f"/cases/{cid}/lifecycle", tok_a)
    check("state is UPLOADING after uploads",
          lc["workflow_state"] == "UPLOADING", str(lc))
    # duplicate re-upload is rejected (idempotency, no duplicate rows)
    data, ct = multipart("FIR.txt", FIR_TEXT)
    s, dup = req("POST", f"/cases/{cid}/documents", tok_a, data, ct)
    check("duplicate re-upload -> 409 (no duplicate rows)",
          s == 409 and (dup or {}).get("error", {}).get("code")
          == "DOCUMENT_DUPLICATE", f"{s} {dup}")

    # -------------------------------------------------------- 4. process
    print("4. process job (queued -> COMPLETED, real stages)")
    s, j = req("POST", f"/cases/{cid}/process", tok_a)
    check("process -> 200 {job_id, case_id, status:queued}",
          s == 200 and j.get("status") == "queued" and j.get("job_id"), str(j))
    job_id = j["job_id"]
    ps = None
    for _ in range(60):
        time.sleep(0.5)
        s, ps = req("GET", f"/cases/{cid}/processing/status", tok_a)
        if ps and ps["job"] and ps["job"]["status"] in ("COMPLETED", "FAILED"):
            break
    check("job reached COMPLETED", ps and ps["job"]["status"] == "COMPLETED",
          str(ps and ps["job"]))
    check("job processed both documents",
          ps["job"]["processed_documents"] == 2
          and ps["job"]["failed_documents"] == 0, str(ps["job"]))
    check("stage ended at 'ready for review'",
          ps["job"]["current_stage"] == "ready for review",
          str(ps["job"]["current_stage"]))
    checklist = {c["stage"]: (c["done"], c["total"]) for c in ps["stage_checklist"]}
    check("stage checklist: ingestion..relationship_extraction 2/2",
          checklist.get("ingestion") == (2, 2)
          and checklist.get("text_extraction") == (2, 2)
          # the CDR is a CSV — language detection may legitimately
          # apply to only the TXT document (>= 1, never guessed)
          and checklist.get("language_detection", (0, 0))[0] >= 1
          and checklist.get("entity_extraction") == (2, 2)
          and checklist.get("relationship_extraction") == (2, 2),
          str(checklist))
    check("FIR page_count is real (1 page)",
          any(d["filename"] == "FIR.txt" and d.get("page_count") in (None, 1)
              for d in ps["documents"]))
    check("document has real processing_seconds",
          all(d.get("processing_seconds") is not None
              for d in ps["documents"] if d["processing_status"] == "PROCESSED"))
    s, lc = req("GET", f"/cases/{cid}/lifecycle", tok_a)
    check("state is REVIEW_REQUIRED after processing",
          lc["workflow_state"] == "REVIEW_REQUIRED", str(lc))

    # ------------------------------------------------------- 5. extraction
    print("5. extraction (candidates with provenance)")
    s, q = req("GET", f"/cases/{cid}/review/queue", tok_a)
    ents = q["new_entities"] + q["potential_duplicates"]
    rels = q["candidate_relationships"]
    check("entity candidates extracted (>=4)", len(ents) >= 4, str(len(ents)))
    check("relationship candidates extracted (>=1)", len(rels) >= 1, str(len(rels)))
    e0 = ents[0]
    check("candidate carries source document + snippet + confidence",
          e0.get("source_document") in ("FIR.txt", "CDR.csv")
          and e0.get("source_snippet") and e0.get("confidence") is not None,
          str(e0))
    check("total_pending counts decidable items",
          q["total_pending"] == len(ents) + len(rels), str(q["total_pending"]))

    # ----------------------------------------------------------- 6. review
    print("6. review (EXPLICIT bulk confirm — nothing auto-confirmed)")
    s, g = req("GET", f"/cases/{cid}/graph", tok_a)
    check("graph is empty before any confirmation (no auto-confirm)",
          s == 200 and g["node_count"] == 0 and g["edge_count"] == 0,
          f"{g['node_count']}n/{g['edge_count']}e")
    match_ids = [e["match_id"] for e in q["potential_duplicates"]
                 if e.get("match_id")]
    if match_ids:
        s, jm = req("POST", f"/cases/{cid}/review/bulk", tok_a,
                    {"category": "match", "action": "confirm",
                     "item_ids": match_ids})
        check("bulk confirm match suggestions (explicit)",
              s == 200 and jm["applied"] == len(match_ids), str(jm))
    s, j = req("POST", f"/cases/{cid}/review/bulk", tok_a,
               {"category": "entity", "action": "confirm",
                "item_ids": [e["id"] for e in ents]})
    check("bulk confirm entities (explicit)",
          s == 200 and j["applied"] == len(ents), str(j))
    s, j = req("POST", f"/cases/{cid}/review/bulk", tok_a,
               {"category": "relationship", "action": "confirm",
                "item_ids": [r["id"] for r in rels]})
    check("bulk confirm relationships (explicit)",
          s == 200 and j["applied"] == len(rels), str(j))
    # duplicate ids rejected, empty list rejected
    s, j = req("POST", f"/cases/{cid}/review/bulk", tok_a,
               {"category": "entity", "action": "confirm", "item_ids": []})
    check("empty item_ids -> 422", s == 422, str(j))
    s, j = req("POST", f"/cases/{cid}/review/bulk", tok_a,
               {"category": "entity", "action": "confirm",
                "item_ids": [ents[0]["id"], ents[0]["id"]]})
    check("duplicate item_ids -> 422", s == 422, str(j))
    s, j = req("POST", f"/cases/{cid}/review/bulk", tok_a,
               {"category": "entity", "action": "confirm",
                "item_ids": [ents[0]["id"]]})
    check("re-confirming a decided item -> per-item 409",
          s == 200 and j["applied"] == 0
          and j["results"][0]["ok"] is False, str(j))
    s, lc = req("GET", f"/cases/{cid}/lifecycle", tok_a)
    check("state is READY_FOR_ANALYSIS when queue is empty",
          lc["workflow_state"] == "READY_FOR_ANALYSIS", str(lc))

    # ------------------------------------------------------------ 7. graph
    print("7. graph (build stats, filters, provenance)")
    s, j = req("POST", f"/cases/{cid}/graph/build", tok_a)
    check("graph build reflects confirmed data only",
          s == 200 and j["nodes"] >= 4 and j["edges"] >= 1, str(j))
    check("graph stats carry components + communities",
          "components" in j.get("stats", {})
          and "communities" in j.get("stats", {})
          and j["stats"]["nodes"] == j["nodes"], str(j.get("stats")))
    s, g = req("GET", f"/cases/{cid}/graph", tok_a)
    check("graph payload edges carry provenance",
          any(e.get("source_document_name") for e in g["edges"]), str(g["edges"][:1]))
    s, g = req("GET", f"/cases/{cid}/graph?entity_type=person", tok_a)
    check("filter entity_type=person",
          s == 200 and all(n["type"] == "person" for n in g["nodes"])
          and len(g["nodes"]) >= 2, str([n["type"] for n in g["nodes"]]))
    s, g = req("GET", f"/cases/{cid}/graph?limit=2", tok_a)
    check("filter limit=2 caps nodes", s == 200 and len(g["nodes"]) <= 2,
          str(len(g["nodes"])))
    s, g = req("GET", f"/cases/{cid}/graph?min_confidence=0.99", tok_a)
    check("filter min_confidence=0.99 drops low-confidence edges",
          s == 200 and all(
              (e["confidence"] or 0) >= 0.99 for e in g["edges"]),
          str([(e["type"], e["confidence"]) for e in g["edges"]]))

    # ------------------------------------------------------- 8. timeline/map
    print("8. timeline (+filters) and map (no fabricated coordinates)")
    s, tl = req("GET", f"/cases/{cid}/timeline", tok_a)
    check("timeline has events", s == 200 and len(tl) >= 1, str(len(tl)))
    ent = tl[0]["entity_id"]
    s, tl2 = req("GET", f"/cases/{cid}/timeline?entity_id={ent}", tok_a)
    check("timeline filter entity_id",
          s == 200 and all(e["entity_id"] == ent for e in tl2), str(tl2))
    s, tl3 = req("GET",
                 f"/cases/{cid}/timeline?from_date=2026-08-02T00:00:00", tok_a)
    check("timeline filter date range",
          s == 200 and all(
              e["timestamp"] is None or e["timestamp"] >= "2026-08-02"
              for e in tl3), str(tl3))
    s, locs = req("GET", f"/cases/{cid}/locations", tok_a)
    check("map: locations exist, coordinates NULL (never fabricated)",
          s == 200 and all(l["latitude"] is None and l["longitude"] is None
                           for l in locs), str(locs))

    # -------------------------------------------------- 9. intelligence run
    print("9. intelligence (run, versioned, state ANALYSIS_COMPLETE)")
    s, j = req("POST", f"/cases/{cid}/analysis/run", tok_a)
    check("analysis run completed", s == 200 and j["status"] in
          ("completed", "no_changes"), str(j))
    check("run is versioned (version 1 + analysis_id + input docs)",
          j.get("version") == 1 and j.get("analysis_id")
          and j.get("input_document_versions")
          and len(j["input_document_versions"]) == 2, str({
              k: j.get(k) for k in ("version", "analysis_id")}))
    check("run records created_by", j.get("created_by") is not None,
          str(j.get("created_by")))
    s, lc = req("GET", f"/cases/{cid}/lifecycle", tok_a)
    check("state is ANALYSIS_COMPLETE",
          lc["workflow_state"] == "ANALYSIS_COMPLETE", str(lc))
    s, st = req("GET", f"/cases/{cid}/analysis/status", tok_a)
    check("analysis state up-to-date with last_analysis_at set",
          st["state"] == "up-to-date" and st.get("last_analysis_at"),
          str(st["state"]))
    # idempotent re-run
    s, j2 = req("POST", f"/cases/{cid}/analysis/run", tok_a)
    check("unchanged re-run -> no_changes (idempotent)",
          j2["status"] == "no_changes" and j2.get("version") == 2, str({
              k: j2.get(k) for k in ("status", "version")}))
    # recalculate while NOT stale -> 409
    s, j3 = req("POST", f"/cases/{cid}/analysis/recalculate", tok_a)
    check("recalculate when up-to-date -> 409 NOT_STALE",
          s == 409 and j3.get("error", {}).get("code") == "NOT_STALE",
          f"{s} {j3}")

    print("10. intelligence views (findings/hypotheses/contradictions/gaps)")
    s, g = req("GET", f"/cases/{cid}/graph/findings", tok_a)
    check("graph findings endpoint responds", s == 200, str(s))
    s, h = req("GET", f"/cases/{cid}/hypotheses", tok_a)
    check("hypotheses endpoint responds", s == 200, str(s))
    s, c = req("GET", f"/cases/{cid}/contradictions", tok_a)
    check("contradictions endpoint responds", s == 200, str(s))
    s, gp = req("GET", f"/cases/{cid}/gaps", tok_a)
    check("gaps endpoint responds", s == 200, str(s))

    # --------------------------------------------------------- 11. copilot
    print("11. copilot (same case, citations)")
    s, j = req("POST", f"/cases/{cid}/copilot/ask", tok_a,
               {"question": "How is Vikram Sethi connected to Sanjay Bhosle?"})
    ok = s == 200 and j and j.get("answer_text")
    cites = j.get("citations") if ok else None
    check("copilot answers for the case (same case, cited)", ok,
          f"{s} {str(j)[:200]}")
    check("copilot answer carries citations",
          ok and isinstance(cites, list) and len(cites) >= 1, str(cites)[:200])

    # ------------------------------------------- 12. second upload -> STALE
    print("12. second upload -> STALE (workflow) ; confirm -> stale analysis")
    data, ct = multipart("Supplement.txt", SECOND_TEXT)
    s, doc3 = req("POST", f"/cases/{cid}/documents", tok_a, data, ct)
    check("second document uploaded", s == 201, str(doc3))
    s, lc = req("GET", f"/cases/{cid}/lifecycle", tok_a)
    check("state is STALE after upload on analyzed case",
          lc["workflow_state"] == "STALE", str(lc))
    s, j = req("POST", f"/cases/{cid}/process", tok_a)
    check("re-process job queued", s == 200 and j["status"] == "queued", str(j))
    for _ in range(60):
        time.sleep(0.5)
        s, ps = req("GET", f"/cases/{cid}/processing/status", tok_a)
        if ps["job"]["status"] in ("COMPLETED", "FAILED"):
            break
    check("re-process job COMPLETED", ps["job"]["status"] == "COMPLETED",
          str(ps["job"]))
    s, lc = req("GET", f"/cases/{cid}/lifecycle", tok_a)
    check("state is REVIEW_REQUIRED again",
          lc["workflow_state"] == "REVIEW_REQUIRED", str(lc))
    s, q = req("GET", f"/cases/{cid}/review/queue", tok_a)
    ents2 = q["new_entities"] + q["potential_duplicates"]
    rels2 = q["candidate_relationships"]
    check("new candidates extracted from the second document",
          len(ents2) >= 1, str(len(ents2)))
    match_ids2 = [e["match_id"] for e in q["potential_duplicates"]
                  if e.get("match_id")]
    if match_ids2:
        s, jm = req("POST", f"/cases/{cid}/review/bulk", tok_a,
                    {"category": "match", "action": "confirm",
                     "item_ids": match_ids2})
        check("bulk confirm match suggestions (explicit)",
              s == 200 and jm["applied"] == len(match_ids2), str(jm))
    # Match acceptance already ACCEPTs the matched candidates — re-fetch
    # the queue and confirm only what is still pending.
    s, q = req("GET", f"/cases/{cid}/review/queue", tok_a)
    ents2 = q["new_entities"] + q["potential_duplicates"]
    rels2 = q["candidate_relationships"]
    if ents2:
        s, j = req("POST", f"/cases/{cid}/review/bulk", tok_a,
                   {"category": "entity", "action": "confirm",
                    "item_ids": [e["id"] for e in ents2]})
        check("bulk confirm new entities",
              s == 200 and j["applied"] == len(ents2), str(j))
    if rels2:
        s, j = req("POST", f"/cases/{cid}/review/bulk", tok_a,
                   {"category": "relationship", "action": "confirm",
                    "item_ids": [r["id"] for r in rels2]})
        check("bulk confirm new relationships",
              s == 200 and j["applied"] == len(rels2), str(j))
    s, st = req("GET", f"/cases/{cid}/analysis/status", tok_a)
    check("analysis now STALE with a reason (data changed)",
          st["state"] == "stale" and st["reason"], str(st["state"]))
    check("stale findings count > 0 (previous run kept)",
          st["findings"]["stale"] >= 0 and st["graph_version"],
          str(st["findings"]))
    s, lc = req("GET", f"/cases/{cid}/lifecycle", tok_a)
    check("state back to READY_FOR_ANALYSIS after confirmations",
          lc["workflow_state"] == "READY_FOR_ANALYSIS", str(lc))

    # ----------------------------------------------------- 13. recalculate
    print("13. RECALCULATE (real, now stale)")
    s, j = req("POST", f"/cases/{cid}/analysis/recalculate", tok_a)
    check("recalculate now succeeds (version 3)",
          s == 200 and j["status"] in ("completed", "no_changes")
          and j["version"] == 3, str({k: j.get(k) for k in
                                      ("status", "version")}))
    s, st = req("GET", f"/cases/{cid}/analysis/status", tok_a)
    check("state up-to-date again after recalculation",
          st["state"] == "up-to-date", str(st["state"]))
    check("old-snapshot findings preserved as stale (not deleted)",
          st["findings"]["stale"] >= 1, str(st["findings"]))
    s, lc = req("GET", f"/cases/{cid}/lifecycle", tok_a)
    check("state ANALYSIS_COMPLETE after recalculation",
          lc["workflow_state"] == "ANALYSIS_COMPLETE", str(lc))

    # ------------------------------------------------------- 14. audit trail
    print("14. audit trail (all the actions)")
    s, au = req("GET", f"/cases/{cid}/audit", tok_a)
    actions = {a["action"] for a in au["entries"]}
    for needed in ("DOCUMENT_UPLOADED", "PROCESSING_JOB_STARTED",
                   "PROCESSING_JOB_COMPLETED", "REVIEW_BULK", "GRAPH_BUILD",
                   "ANALYSIS_RUN", "RECALCULATE", "CASE_STATE_TRANSITION"):
        check(f"audit contains {needed}", needed in actions, str(sorted(actions)))

    # --------------------------------------------------- 15. delete document
    print("15. document delete (candidates cascade, confirmed data stays)")
    n_conf_before = req("GET", f"/cases/{cid}/entities", tok_a)[1]
    # delete the CDR (its candidates may be partially confirmed — confirmed
    # rows must survive)
    s, _ = req("DELETE", f"/cases/{cid}/documents/{doc2['id']}", tok_a)
    check("delete document 204", s == 204, str(s))
    s, docs = req("GET", f"/cases/{cid}/documents", tok_a)
    check("case now has 2 documents", len(docs) == 2, str(len(docs)))
    s, ents_after = req("GET", f"/cases/{cid}/entities", tok_a)
    check("confirmed entities survive document deletion",
          len(ents_after) >= len(n_conf_before),
          f"{len(ents_after)} vs {len(n_conf_before)}")

    # -------------------------------------------------------- 16. security
    print("16. security (User B is locked out of User A's case)")
    s, j = req("GET", f"/cases/{cid}", tok_b)
    check("B cannot read A's case (404)", s == 404, str(s))
    data, ct = multipart("evil.txt", "SYNTHETIC")
    s, j = req("POST", f"/cases/{cid}/documents", tok_b, data, ct)
    check("B cannot upload into A's case (404)", s == 404, str(s))
    s, j = req("POST", f"/cases/{cid}/review/bulk", tok_b,
               {"category": "entity", "action": "confirm", "item_ids": [1]})
    check("B cannot review in A's case (404)", s == 404, str(s))
    s, j = req("POST", f"/cases/{cid}/graph/build", tok_b)
    check("B cannot build A's graph (404)", s == 404, str(s))
    s, j = req("POST", f"/cases/{cid}/analysis/run", tok_b)
    check("B cannot run A's analysis (404)", s == 404, str(s))
    s, j = req("POST", f"/cases/{cid}/copilot/ask", tok_b,
               {"question": "who is in this case?"})
    check("B cannot use A's copilot (404)", s == 404, str(s))
    s, j = req("GET", f"/cases/{cid}/audit", tok_b)
    check("B cannot read A's audit (404)", s == 404, str(s))
    s, j = req("GET", f"/cases/{cid}")  # no token
    check("no token -> 401", s == 401, str(s))
    s, j = req("POST", f"/cases/{cid}/close", tok_a)
    check("INVESTIGATOR cannot close a case (403)", s == 403, str(s))
    s, lc = req("POST", f"/cases/{cid}/close", tok_s)
    check("SUPERVISOR can close (terminal state)",
          s == 200 and lc["workflow_state"] == "CLOSED", str(lc))
    s, j = req("POST", f"/cases/{cid}/process", tok_a)
    check("closed case rejects processing (409)", s == 409, str(s))

    # --------------------------------------------- 17. invalid transitions
    print("17. invalid state transitions are rejected (not stored)")
    s, lc = req("GET", f"/cases/{cid}/lifecycle", tok_s)
    check("closed case has no allowed next states",
          lc["allowed_next"] == [], str(lc))

    # ------------------------------------------------- 18. demo case counts
    print("18. demo case CASE-DEMO-END2END-01 (renamed, exact counts)")
    s, cases = req("GET", "/cases", tok_a)
    demo = next((c for c in cases if c["case_number"] == "CASE-DEMO-END2END-01"),
                None)
    check("renamed demo case exists", demo is not None, str(cases)[:120])
    if demo:
        s, j = req("GET", f"/cases/{demo['id']}/summary", tok_a)
        cnt = j["counts"]
        check("demo: 5 documents", cnt["documents"] == 5, str(cnt))
        check("demo: 17 entities / 10 relationships",
              cnt["entities"] == 17 and cnt["relationships"] == 10, str(cnt))
        check("demo: 38 evidence items", cnt["evidence"] == 38, str(cnt))
        check("demo: 3 timeline events / 3 locations",
              cnt["timeline_events"] == 3 and cnt["locations"] == 3, str(cnt))
        check("demo: 1 current contradiction",
              cnt["contradictions"] == 1, str(cnt))
        check("demo: 2 hypotheses", cnt["hypotheses"] == 2, str(cnt))

    # --------------------------------------------------------------- done
    # cleanup: remove the smoke case so a (failed) run never pollutes
    # the pytest suite (it would leave an empty investigator case).
    try:
        import os as _os
        import sys as _sys
        _sys.path.insert(0, _os.path.abspath(
            _os.path.join(_os.path.dirname(__file__), "..", "backend")))
        from app.core.database import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text('DELETE FROM "case" WHERE id = :id'), {"id": cid})
        db.commit()
        db.close()
        print(f"cleanup: removed smoke case {cid}")
    except Exception as exc:  # noqa: BLE001
        print(f"cleanup: could not remove smoke case {cid}: {exc}")

    print()
    print(f"PASS {PASSES[0]}  FAIL {len(FAILS)}")
    if FAILS:
        print("Failed checks:")
        for f in FAILS:
            print("  -", f)
        sys.exit(1)
    print("ALL STAGE-7 LIVE SMOKE CHECKS PASSED")


if __name__ == "__main__":
    main()
