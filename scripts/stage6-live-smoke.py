#!/usr/bin/env python3
"""Stage 6 live smoke verification (run against the live dev stack).

Covers the stage-6 end-to-end workflow checklist against the LIVE API:
  1. full workflow on a fresh case: CREATE CASE -> upload 3 documents
     (2 TXT + 1 CSV) -> poll REAL processing state (no fake progress)
     -> extraction -> resolve matches -> confirm candidates -> build
     graph -> run intelligence (one call)
  2. analysis run returns analysis_id/case_id/status/started/completed/
     findings_count/graph_nodes/graph_edges; the spatial contradiction
     is found and explainable
  3. timeline + locations come from the case data; location rows exist
     with coordinates NULL (never fabricated)
  4. Copilot is case-aware after analysis
  5. idempotent re-upload -> 409, no duplicates; re-run on the same
     snapshot -> recomputed=false
  6. upload after analysis: state stays up-to-date while data is still
     candidates, becomes STALE after confirmation, re-run supersedes the
     old snapshot (stale findings kept, never deleted)
  7. audit trail recorded the whole workflow (CREATE_CASE, uploads,
     processing, confirmations, GRAPH_BUILD, ANALYSIS_RUN)
  8. RBAC + isolation: analyst cannot run analysis (403), no token 401,
     unknown case 404
  9. the seeded demo case CASE-DEMO-END2END-01: five real documents
     (three reportlab PDFs + one CSV), 17 entities, 10 relationships,
     3 locations, exactly ONE EVIDENCE_CONTRADICTION (Bhiwandi vs Kurla)
 10. stage-5 regression: the multilingual demo case still yields exactly
     ONE HIGH EVIDENCE_CONTRADICTION (Mumbai vs Pune)
 11. empty demo case: analysis run is an honest "insufficient", not a crash

Usage:  python3 scripts/stage6-live-smoke.py
Requires: API on http://127.0.0.1:8000 and a seeded development database.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"
ADMIN = ("admin@nexus.local", "nexus2026")
INVESTIGATOR = ("demo-investigator@nexus.local", "nexus2026")
ANALYST = ("sneha.joshi@nexus.gov.in", "nexus2026")
FAILS: list[str] = []

DOC1 = (
    "SYNTHETIC LIVE SMOKE DOC 1\n"
    "On 2026-09-02 08:00, Suresh Yadav was seen at Chembur.\n"
    "Mobile 9000000701 was found in the records.\n"
    "Vehicle MH07YY7777 was parked nearby.\n"
)
DOC2 = (
    "SYNTHETIC LIVE SMOKE DOC 2\n"
    "On 2026-09-02 08:10, Suresh Yadav was seen at Kurla.\n"
    "Suresh Yadav called Altaf Khan at 08:12.\n"
)
DOC3 = (
    "call_id,caller,callee,start_time,duration_sec,cell_tower\n"
    "S1,9000000701,9000000702,2026-09-02 08:12:00,45,Chembur\n"
)
DOC4 = (
    "SYNTHETIC LIVE SMOKE DOC 4\n"
    "On 2026-09-02 09:00, Suresh Yadav was seen at Worli.\n"
)


def req(method: str, path: str, token: str | None = None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def upload(token: str, case_id: int, filename: str, content: str,
           ctype: str) -> int:
    import uuid
    boundary = "----nexus" + uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"'
        f"\r\nContent-Type: {ctype}\r\n\r\n"
    ).encode() + content.encode("utf-8") + f"\r\n--{boundary}--\r\n".encode()
    r = urllib.request.Request(
        f"{BASE}/cases/{case_id}/documents", data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def login(email, pw):
    _, d = req("POST", "/auth/login", body={"email": email, "password": pw})
    return d["access_token"]


def check(name: str, cond: bool, detail: str = ""):
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def wait_processed(tok, case_id, n_docs, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        _, d = req("GET", f"/cases/{case_id}/processing/status", tok)
        if d.get("total") == n_docs and d.get("all_processed"):
            return d
        time.sleep(0.2)
    return {}


def accept_all(tok, case_id, max_rounds=25):
    accepted = {"matches": 0, "entities": 0, "relationships": 0}
    for _ in range(max_rounds):
        _, q = req("GET", f"/cases/{case_id}/review/queue", tok)
        progressed = False
        for m in q.get("potential_duplicates", []):
            s, _ = req("POST",
                       f"/documents/{m['document_id']}/extraction/"
                       f"matches/{m['match_id']}/accept", tok)
            if s == 200:
                accepted["matches"] += 1
                progressed = True
        for e in q.get("new_entities", []):
            s, _ = req("POST",
                       f"/documents/{e['document_id']}/extraction/"
                       f"candidates/{e['id']}/accept", tok)
            if s == 200:
                accepted["entities"] += 1
                progressed = True
        for rel in q.get("candidate_relationships", []):
            s, _ = req("POST",
                       f"/documents/{rel['document_id']}/extraction/"
                       f"relationships/{rel['id']}/accept", tok)
            if s == 200:
                accepted["relationships"] += 1
                progressed = True
        if not progressed:
            break
    return accepted


def main() -> int:
    tok = login(*INVESTIGATOR)
    admin = login(*ADMIN)
    analyst = login(*ANALYST)

    # 1 — fresh case + three uploads
    print("1) full workflow on a fresh case")
    number = f"CASE-2026-{int(time.strftime('%M%S')) % 900 + 100}"
    s, case = req("POST", "/cases", tok, {
        "case_number": number,
        "title": "Stage-6 live smoke case (synthetic)",
        "description": "SYNTHETIC DEMONSTRATION DATA", "priority": "MEDIUM"})
    check("case created", s == 201, str(case))
    case_id = case["id"]
    check("upload doc1", upload(tok, case_id, "s1.txt", DOC1, "text/plain") == 201)
    check("upload doc2", upload(tok, case_id, "s2.txt", DOC2, "text/plain") == 201)
    check("upload csv", upload(tok, case_id, "s3.csv", DOC3, "text/csv") == 201)

    d = wait_processed(tok, case_id, 3)
    check("processing finished (real state, polled)",
          d.get("by_status", {}).get("PROCESSED") == 3, json.dumps(d)[:200])

    _, q = req("GET", f"/cases/{case_id}/review/queue", tok)
    names = {e["name"] for e in q.get("new_entities", [])}
    check("extraction produced candidates",
          {"Suresh Yadav", "9000000701", "MH07YY7777"} <= names,
          str(names))
    check("candidate relationships exist",
          any(r["relationship_type"] == "CALLED"
              for r in q.get("candidate_relationships", [])))

    acc = accept_all(tok, case_id)
    check("matches + entities + relationships confirmed via API",
          acc["entities"] >= 4 and acc["relationships"] >= 2, str(acc))
    _, q = req("GET", f"/cases/{case_id}/review/queue", tok)
    check("review queue drained", q.get("total_pending") == 0,
          str(q.get("total_pending")))

    # 2 — graph build + analysis run
    print("2) graph build + intelligence")
    s, built = req("POST", f"/cases/{case_id}/graph/build", tok)
    check("graph built from confirmed data", s == 200
          and built.get("nodes", 0) >= 4 and built.get("edges", 0) >= 2,
          json.dumps(built)[:200])

    s, run1 = req("POST", f"/cases/{case_id}/analysis/run", tok)
    check("analysis run completed", s == 200 and run1.get("status") == "completed",
          json.dumps(run1)[:200])
    for field in ("analysis_id", "case_id", "started_at", "completed_at",
                  "findings_count", "graph_nodes", "graph_edges"):
        check(f"run payload has {field}", field in run1)
    check("findings found (spatial contradiction)",
          run1.get("findings_count", 0) >= 1, str(run1.get("findings_count")))

    _, fnd = req("GET", f"/cases/{case_id}/investigation/findings", tok)
    contra = [f for f in fnd.get("current_findings", [])
              if f.get("finding_type") == "CONTRADICTION"]
    check("contradiction finding is explainable",
          bool(contra) and any("Chembur" in (f.get("title", "") +
                               str(f.get("details", {})))
                               or "Kurla" in (f.get("title", "") +
                               str(f.get("details", {}))) for f in contra))

    # 3 — timeline + locations (coords never fabricated)
    print("3) timeline + locations")
    _, events = req("GET", f"/cases/{case_id}/timeline", tok)
    check("timeline events from case data", len(events) >= 2, str(len(events)))
    _, locs = req("GET", f"/cases/{case_id}/locations", tok)
    check("locations from case data",
          any(l["name"] == "Chembur" for l in locs)
          and any(l["name"] == "Kurla" for l in locs), str(locs)[:200])
    check("coordinates are NULL (never fabricated)",
          all(l.get("latitude") is None and l.get("longitude") is None
              for l in locs))

    # 4 — copilot case-aware
    print("4) copilot")
    s, ans = req("POST", f"/cases/{case_id}/copilot/ask", tok,
                 {"question": "Who is connected to Suresh Yadav?"})
    check("copilot answers after analysis",
          s == 200 and ans.get("status") in ("answered", "not_enough_data")
          and ans.get("answer_text"))

    # 5 — idempotent re-upload + idempotent re-run
    print("5) idempotency")
    check("re-upload same file -> 409",
          upload(tok, case_id, "s1.txt", DOC1, "text/plain") == 409)
    d = wait_processed(tok, case_id, 3)
    check("no duplicate documents", d.get("total") == 3, str(d.get("total")))
    s, run1b = req("POST", f"/cases/{case_id}/analysis/run", tok)
    check("re-run on same snapshot -> not recomputed",
          run1b.get("recomputed") is False
          and run1b.get("graph_version") == run1.get("graph_version"))

    # 6 — upload after analysis: staleness lifecycle
    print("6) upload after analysis -> STALE -> re-run")
    check("upload doc4", upload(tok, case_id, "s4.txt", DOC4, "text/plain") == 201)
    wait_processed(tok, case_id, 4)
    _, st = req("GET", f"/cases/{case_id}/analysis/status", tok)
    check("still up-to-date while new data is candidates",
          st.get("state") == "up-to-date", st.get("state", ""))
    accept_all(tok, case_id)
    _, st = req("GET", f"/cases/{case_id}/analysis/status", tok)
    check("STALE after the new data is confirmed",
          st.get("state") == "stale", st.get("state", ""))
    req("POST", f"/cases/{case_id}/graph/build", tok)
    s, run2 = req("POST", f"/cases/{case_id}/analysis/run", tok)
    check("re-run supersedes the old snapshot",
          run2.get("status") == "completed" and run2.get("recomputed") is True
          and run2.get("graph_version") != run1.get("graph_version")
          and run2.get("stale_findings", 0) >= 1, json.dumps(run2)[:200])
    _, st = req("GET", f"/cases/{case_id}/analysis/status", tok)
    check("back to up-to-date, stale findings kept",
          st.get("state") == "up-to-date"
          and st.get("findings", {}).get("stale", 0) >= 1)

    # 7 — audit trail
    print("7) audit trail")
    _, audit = req("GET", f"/cases/{case_id}/audit", tok)
    actions = {e["action"] for e in audit.get("entries", [])}
    for expected in ("CREATE_CASE", "DOCUMENT_UPLOADED",
                     "DOCUMENT_PROCESSING_COMPLETED", "ENTITY_ACCEPTED",
                     "RELATIONSHIP_ACCEPTED", "GRAPH_BUILD", "ANALYSIS_RUN"):
        check(f"audit has {expected}", expected in actions, str(actions)[:200])

    # 8 — RBAC + isolation
    print("8) RBAC + isolation")
    s, _ = req("POST", f"/cases/{case_id}/analysis/run", analyst)
    check("analyst cannot run analysis (403)", s == 403, str(s))
    s, _ = req("GET", f"/cases/{case_id}/analysis/status")
    check("no token -> 401", s == 401, str(s))
    s, _ = req("POST", f"/cases/{case_id}/analysis/run")
    check("no token -> 401 on run", s == 401, str(s))
    s, _ = req("GET", "/cases/999999/summary", admin)
    check("unknown case -> 404", s == 404, str(s))

    # 9 — seeded demo case
    print("9) demo case CASE-DEMO-END2END-01")
    _, cases = req("GET", "/cases", admin)
    demo = next((c for c in cases
                 if c["case_number"] == "CASE-DEMO-END2END-01"), None)
    check("demo case present", demo is not None)
    if demo:
        did = demo["id"]
        c = demo["counts"]
        check("five documents", c["documents"] == 5, str(c))
        check("17 entities / 10 relationships",
              c["entities"] == 17 and c["relationships"] == 10, str(c))
        check("3 locations", c["locations"] == 3, str(c))
        # run the intelligence (idempotent) so the checks below hold on a
        # freshly seeded environment too
        s, run = req("POST", f"/cases/{did}/analysis/run", admin)
        check("demo analysis completes", s == 200
              and run.get("status") == "completed", json.dumps(run)[:200])
        _, summary = req("GET", f"/cases/{did}/summary", admin)
        sc = summary.get("counts", {})
        check("summary counts from DB",
              sc.get("findings_current") >= 1
              and sc.get("contradictions") == 1, str(sc))
        _, fnd = req("GET", f"/cases/{did}/investigation/findings", admin)
        contra = [f for f in fnd.get("current_findings", [])
                  if f.get("finding_type") == "CONTRADICTION"]
        check("exactly ONE contradiction (Bhiwandi vs Kurla)",
              len(contra) == 1
              and "Bhiwandi Godown" in contra[0].get("title", "")
              and "Kurla" in contra[0].get("title", ""),
              str([f.get("title") for f in contra]))
        _, locs = req("GET", f"/cases/{did}/locations", admin)
        check("demo locations present, coords NULL",
              len(locs) == 3 and all(l.get("latitude") is None
                                     for l in locs), str(locs)[:200])
        _, graph = req("GET", f"/cases/{did}/graph", admin)
        with_prov = [e for e in graph.get("edges", [])
                     if e.get("source_document_id")]
        check("graph edges carry provenance (source document)",
              graph.get("node_count") == 17 and len(with_prov) >= 5,
              f"nodes={graph.get('node_count')} prov={len(with_prov)}")

    # 10 — stage-5 regression
    print("10) stage-5 regression (multilingual case)")
    _, cases = req("GET", "/cases", admin)
    mling = next((c for c in cases
                  if c["case_number"] == "CASE-DEMO-MULTILING-01"), None)
    check("multilingual case present", mling is not None)
    if mling:
        s, run = req("POST", f"/cases/{mling['id']}/analysis/run", admin)
        check("multilingual analysis completes", s == 200, str(run)[:150])
        _, fnd = req("GET", f"/cases/{mling['id']}/investigation/findings",
                     admin)
        high = [f for f in fnd.get("current_findings", [])
                if f.get("finding_type") == "CONTRADICTION"
                and (f.get("details") or {}).get("severity") == "HIGH"]
        check("exactly ONE HIGH EVIDENCE_CONTRADICTION (Mumbai vs Pune)",
              len(high) == 1 and "Mumbai" in high[0].get("title", "")
              and "Pune" in high[0].get("title", ""),
              str([f.get("title") for f in high]))

    # 11 — empty case honesty
    print("11) empty demo case is honest")
    _, cases = req("GET", "/cases", admin)
    empty = next((c for c in cases
                  if c["case_number"] == "CASE-DEMO-EMPTY-01"), None)
    check("empty demo case present", empty is not None)
    if empty:
        s, run = req("POST", f"/cases/{empty['id']}/analysis/run", admin)
        check("insufficient data -> honest 200 'insufficient'",
              s == 200 and run.get("status") == "insufficient"
              and run.get("findings_count") == 0, json.dumps(run)[:200])

    # cleanup the smoke case (test artifact only)
    import subprocess
    subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", "nexus", "-c",
         f"DELETE FROM \\\"case\\\" WHERE id = {case_id};"],
        capture_output=True)

    print()
    if FAILS:
        print(f"FAILED {len(FAILS)} check(s):")
        for f in FAILS:
            print("  -", f)
        return 1
    print("ALL STAGE-6 LIVE SMOKE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
