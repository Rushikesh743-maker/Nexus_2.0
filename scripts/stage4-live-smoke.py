#!/usr/bin/env python3
"""Stage 4 live smoke verification (run against the live dev stack).

Covers the spec's final-verification checklist:
  1. analyze on the SYNTHETIC DEMONSTRATION contradiction case
     -> at least one of each implemented contradiction type
  2. competing hypotheses with visible score components
  3. evidence-impact + in-memory simulation (zero DB writes)
  4. timeline / geospatial / gap insights
  5. empty case -> explicit INSUFFICIENT_CONFIRMED_DATA (409)
  6. stale after data change -> re-analyze restores current results
  7. review/dismiss + audit rows; re-review blocked (409)
  8. candidate exclusion (outputs reference confirmed entities only)
  9. RBAC (ANALYST read 200 / analyze 403)
 10. stage-3 regression (graph endpoints unchanged, own finding types)

Usage:  python3 scripts/stage4-live-smoke.py
Requires: API on http://127.0.0.1:8000 and a seeded development database.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"
ADMIN = ("admin@nexus.local", "nexus2026")
ANALYST = ("sneha.joshi@nexus.gov.in", "nexus2026")
FAILS: list[str] = []


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


def login(email, pw):
    s, b = req("POST", "/auth/login", body={"email": email, "password": pw})
    assert s == 200, (email, s, b)
    return b["access_token"]


def check(name: str, cond: bool, detail: str = ""):
    mark = "ok  " if cond else "FAIL"
    print(f"  {mark} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def main() -> int:
    from sqlalchemy import select
    sys.path.insert(0, "backend")
    from app.core.database import SessionLocal
    from app.models import Case, Entity, Evidence, Relationship

    admin = login(*ADMIN)
    analyst = login(*ANALYST)

    db = SessionLocal()
    c_demo = db.execute(select(Case).where(Case.case_number == "CASE-DEMO-CONTRA-01")).scalar_one()
    c_empty = db.execute(select(Case).where(Case.case_number == "CASE-DEMO-EMPTY-01")).scalar_one()
    c_meridian = db.execute(select(Case).where(Case.case_number == "CASE-2026-021")).scalar_one()
    c_spec1 = db.execute(select(Case).where(Case.case_number == "CASE-2026-001")).scalar_one()
    confirmed = {e.id for e in db.execute(select(Entity).where(Entity.case_id == c_meridian.id)).scalars()}
    db.close()
    demo, empty, meridian, spec1 = c_demo.id, c_empty.id, c_meridian.id, c_spec1.id

    print(f"cases: demo={demo} empty={empty} meridian={meridian} spec1={spec1}")

    # 1) analyze -> up-to-date
    #    (rerun-tolerant: the first run on a fresh seed sees not-analyzed;
    #     later runs start from up-to-date or stale — both are valid pre-states)
    s, b = req("GET", f"/cases/{demo}/investigation/status", admin)
    check("pre-run status is a valid state (not-analyzed / up-to-date / stale)",
          s == 200 and b["state"] in ("not-analyzed", "up-to-date", "stale"), b.get("state"))
    s, b = req("POST", f"/cases/{demo}/investigation/analyze", admin)
    contra = [f for f in b.get("findings", []) if f["finding_type"] == "CONTRADICTION"]
    types = {f["details"]["contradiction_type"] for f in contra}
    check("analyze 200 with 3 contradiction types",
          s == 200 and types == {"TIMELINE_CONTRADICTION", "LOCATION_CONTRADICTION",
                                 "RELATIONSHIP_CONTRADICTION"}, str(types))
    hyps = b.get("hypotheses", [])
    check("competing hypotheses with visible components",
          len(hyps) >= 4 and all("factor_values" in h["score_components"] for h in hyps),
          f"n={len(hyps)}")
    #    (generated hypotheses only: investigator-created rows carry the
    #     investigator's own text, which the engine does not append to)
    gen_hyps = [h for h in hyps if h.get("hypothesis_type", "").startswith("GENERATED")]
    check("hypothesis disclaimer (analytical support, not proof)",
          len(gen_hyps) >= 4 and
          all("analytical support" in h["explanation"][-1].lower() for h in gen_hyps))
    ver1 = b["graph_version"]

    # 2) idempotent re-run
    s, b = req("POST", f"/cases/{demo}/investigation/analyze", admin)
    check("idempotent re-run (recomputed=False, same counts)",
          s == 200 and b["recomputed"] is False and b["graph_version"] == ver1
          and len(b["findings"]) == 9 and len(b["hypotheses"]) == len(hyps))

    # 3) empty case -> 409 INSUFFICIENT_CONFIRMED_DATA
    s, b = req("POST", f"/cases/{empty}/investigation/analyze", admin)
    check("empty case -> 409 INSUFFICIENT_CONFIRMED_DATA",
          s == 409 and b.get("error", {}).get("code") == "INSUFFICIENT_CONFIRMED_DATA", str(b)[:120])
    s, b = req("GET", f"/cases/{empty}/investigation/status", admin)
    check("empty case status=insufficient", s == 200 and b["state"] == "insufficient")

    # 4) honest analysis on seeded cases
    s, b = req("POST", f"/cases/{spec1}/investigation/analyze", admin)
    check("spec case 1 analyzes (no contradictions in its data)",
          s == 200 and not [f for f in b["findings"] if f["finding_type"] == "CONTRADICTION"])
    s, b = req("POST", f"/cases/{meridian}/investigation/analyze", admin)
    geo = [f for f in b.get("findings", []) if f["finding_type"] == "GEO_INSIGHT"]
    check("meridian case: geospatial insights + gaps present",
          s == 200 and len(geo) > 0 and
          any(f["finding_type"] == "INVESTIGATION_GAP" for f in b["findings"]),
          f"geo={len(geo)}")

    # 5) engine endpoints
    s, b = req("GET", f"/cases/{demo}/investigation/timeline", analyst)
    check("timeline endpoint (analyst)", s == 200 and b["events_total"] >= 5)
    s, b = req("GET", f"/cases/{demo}/investigation/geospatial", analyst)
    check("geospatial endpoint (analyst)", s == 200 and b["observations_count"] >= 5)
    s, b = req("GET", f"/cases/{meridian}/investigation/gaps", analyst)
    check("gaps endpoint (meridian)", s == 200 and len(b["current_findings"]) > 0)

    # 6) evidence impact + simulation (zero DB writes)
    def counts():
        d = SessionLocal()
        try:
            from sqlalchemy import func
            ev = d.execute(select(func.count()).select_from(Evidence).where(Evidence.case_id == meridian)).scalar()
            rl = d.execute(select(func.count()).select_from(Relationship).where(Relationship.case_id == meridian)).scalar()
            return (ev, rl)
        finally:
            d.close()

    s, b = req("GET", f"/cases/{meridian}/investigation/evidence-impact", admin)
    check("evidence-impact summary", s == 200 and b["evidence_count"] > 0)
    target = b["evidence_impacts"][0]["evidence_id"]
    before = counts()
    s, b = req("POST", f"/cases/{meridian}/investigation/evidence/{target}/simulate-impact", admin)
    check("simulate-impact returns simulation-only diff",
          s == 200 and b["simulation_only"] is True and "not modified" in b["message"]
          and "diff" in b)
    check("simulation wrote nothing to the database", counts() == before)

    # 7) review / dismiss / audit (rerun-tolerant: earlier smoke runs may
    #    have already acted on the same rows — the 409 path is valid too)
    s, b = req("GET", f"/cases/{demo}/investigation/contradictions", admin)
    f_target = next((x for x in b["current_findings"] if x["status"] == "ACTIVE"),
                    b["current_findings"][0])
    s, b = req("POST", f"/cases/{demo}/investigation/findings/{f_target['id']}/review", admin,
               body={"note": "smoke review"})
    check("review finding (or already-acted -> 409)",
          (s == 200 and b["status"] == "REVIEWED") or s == 409, f"{s} {b.get('status')}")
    s, b = req("POST", f"/cases/{demo}/investigation/findings/{f_target['id']}/review", admin,
               body={"note": "again"})
    check("re-review blocked (409)", s == 409)
    s, b = req("GET", f"/cases/{demo}/investigation/hypotheses", admin)
    h_target = next((x for x in b["hypotheses"] if x["status"] == "ACTIVE"),
                    b["hypotheses"][0])
    s, b = req("POST", f"/cases/{demo}/investigation/hypotheses/{h_target['id']}/dismiss", admin,
               body={"note": "smoke dismiss"})
    check("dismiss hypothesis (or already-acted -> 409)",
          (s == 200 and b["status"] == "DISMISSED") or s == 409, f"{s} {b.get('status')}")
    s, b = req("POST", f"/cases/{demo}/investigation/hypotheses/{h_target['id']}/dismiss", admin,
               body={"note": "again"})
    check("re-dismiss blocked (409)", s == 409)
    db = SessionLocal()
    try:
        from app.models import AuditLog
        acts = {r.action for r in db.query(AuditLog).filter(
            AuditLog.action.in_(["CONTRADICTION_DETECTED", "HYPOTHESIS_GENERATED",
                                 "EVIDENCE_IMPACT_ANALYZED", "TIMELINE_ANALYSIS_COMPLETED",
                                 "GEO_ANALYSIS_COMPLETED", "INVESTIGATION_GAP_DETECTED",
                                 "FINDING_REVIEWED", "HYPOTHESIS_DISMISSED"]))}
        check("audit actions present",
              {"CONTRADICTION_DETECTED", "HYPOTHESIS_GENERATED", "FINDING_REVIEWED",
               "HYPOTHESIS_DISMISSED"} <= acts, str(acts))
    finally:
        db.close()

    # 8) candidate exclusion
    s, b = req("GET", f"/cases/{meridian}/investigation/findings", admin)
    all_ids = [eid for f in b["current_findings"] + b["stale_findings"]
               for eid in f["involved_entity_ids"]]
    check("findings reference confirmed entities only", all(eid in confirmed for eid in all_ids))

    # 9) RBAC
    s, b = req("POST", f"/cases/{demo}/investigation/analyze", analyst)
    check("ANALYST cannot analyze (403 FORBIDDEN)",
          s == 403 and b.get("error", {}).get("code") == "FORBIDDEN")
    s, b = req("GET", f"/cases/{demo}/investigation/findings", analyst)
    check("ANALYST can read (200)", s == 200)
    s, b = req("GET", f"/cases/{demo}/investigation/findings")
    check("no token rejected", s in (401, 403))

    # 10) stale -> re-analyze restores current results
    #     (unique name per run so a rerun also changes the confirmed
    #     snapshot and genuinely exercises the stale path)
    from datetime import datetime, timezone
    db = SessionLocal()
    try:
        from app.models import Location
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        db.add(Location(case_id=demo, name=f"Stale-check site (smoke {stamp})",
                        latitude=18.6104, longitude=73.7966,
                        meta={"synthetic": True, "demonstration": "stage4-smoke-stale"}))
        db.commit()
    finally:
        db.close()
    s, b = req("GET", f"/cases/{demo}/investigation/status", admin)
    check("status=stale after data change", s == 200 and b["state"] == "stale", b.get("state"))
    s, b = req("POST", f"/cases/{demo}/investigation/analyze", admin)
    check("re-analyze restores current results",
          s == 200 and b["recomputed"] is True and b["graph_version"] != ver1
          and len(b["stale_findings"]) >= 9 and len(b["findings"]) == 9)
    s, b = req("GET", f"/cases/{demo}/investigation/status", admin)
    check("status=up-to-date after re-analyze", s == 200 and b["state"] == "up-to-date", b.get("state"))

    # 11) stage-3 regression
    s, b = req("GET", f"/cases/{meridian}/graph/findings", admin)
    stage3_types = {"HIDDEN_CONNECTION", "BRIDGE_ENTITY", "CROSS_CASE_CONNECTION",
                    "NETWORK_CLUSTER", "HIGH_CONNECTIVITY"}
    check("stage-3 findings list only stage-3 types",
          s == 200 and all(f["finding_type"] in stage3_types
                           for f in b["current_findings"] + b["stale_findings"]))
    s, b = req("POST", f"/cases/{meridian}/graph/analyze", admin)
    check("stage-3 analyze still works", s == 200 and
          all(f["finding_type"] in stage3_types for f in b["findings"]))

    print()
    if FAILS:
        print(f"SMOKE: {len(FAILS)} check(s) FAILED: {FAILS}")
        return 1
    print("SMOKE: all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
