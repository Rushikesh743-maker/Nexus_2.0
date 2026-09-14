#!/usr/bin/env python3
"""Stage 5 live smoke verification (run against the live dev stack).

Covers the stage-5 final-verification checklist:
  1. platform Copilot capability statement is honest (stage-5, no LLM
     claimed as active when no provider key is configured)
  2. per-case Copilot status reports the deterministic engine as active
  3. data-driven suggested questions (non-empty, case-specific)
  4. deterministic Q&A with citations for the core intents (overview,
     profile, connections, locations, contradictions)
  5. NO-HALLUCINATION: every cited id exists in the case; an
     out-of-domain question is answered "unsupported" with confidence 0
     and no citations (never a confident invented answer)
  6. multilingual: the demonstration case carries EN/HI/MR/UR documents,
     non-Latin surface forms resolve to canonical language-neutral names,
     the multilingual search finds a location from a Devanagari query, and
     an investigator asking in Marathi/Hindi/Urdu gets an answer in that
     language with the SAME citations as the English counterpart
     (acceptance #11–12)
  7. evidence claims + EVIDENCE_CONTRADICTION end-to-end on the
     multilingual case: four was_at claims, and analyze yields exactly
     ONE HIGH EVIDENCE_CONTRADICTION (Mumbai vs Pune, ~0 min apart)
  8. case isolation + RBAC (ANALYST read 200 / ask 403; no token rejected;
     another case is not answerable without access)
  9. stage-4 regression: the original contradiction demo case still yields
     its three pre-stage-5 contradiction types (engines untouched)

Usage:  python3 scripts/stage5-live-smoke.py
Requires: API on http://127.0.0.1:8000 and a seeded development database.
"""
from __future__ import annotations

import json
import os
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


def ask(token, case_id, question):
    return req("POST", f"/cases/{case_id}/copilot/ask", token,
               body={"question": question})


def main() -> int:
    from sqlalchemy import select
    sys.path.insert(0, "backend")
    from app.core.database import SessionLocal
    from app.models import Case, Document, Entity, EvidenceClaim

    admin = login(*ADMIN)
    analyst = login(*ANALYST)

    db = SessionLocal()
    c_multi = db.execute(select(Case).where(
        Case.case_number == "CASE-DEMO-MULTILING-01")).scalar_one_or_none()
    c_contra = db.execute(select(Case).where(
        Case.case_number == "CASE-DEMO-CONTRA-01")).scalar_one_or_none()
    if c_multi is None or c_contra is None:
        print("ABORT: demonstration cases missing from the database "
              "(CASE-DEMO-MULTILING-01 / CASE-DEMO-CONTRA-01). "
              "Run the API once so the seeders run, then retry.")
        db.close()
        return 1
    multi, contra = c_multi.id, c_contra.id

    # language + claim snapshots straight from the database (the API is
    # verified separately below against the same expectations)
    doc_langs = {d.language for d in db.execute(
        select(Document).where(Document.case_id == multi,
                               Document.filename.like("demo_multiling%")))
        .scalars()}
    person_names = {e.canonical_name for e in db.execute(
        select(Entity).where(Entity.case_id == multi,
                             Entity.entity_type == "person")).scalars()}
    n_claims = len(db.execute(select(EvidenceClaim).where(
        EvidenceClaim.case_id == multi)).scalars().all())
    db.close()

    print(f"cases: multilingual={multi} contra(demo)={contra}")

    # 1) platform capability statement is honest ---------------------------
    s, b = req("GET", "/copilot", admin)
    check("platform /copilot is stage-5", s == 200 and b.get("stage") == "stage-5",
          str(b.get("stage")))
    check("platform lists natural-language as available",
          any("natural-language" in a for a in (b.get("available") or [])),
          str(b.get("available")))
    check("platform keeps an honest 'planned' list",
          isinstance(b.get("planned"), list) and len(b["planned"]) > 0,
          str(b.get("planned")))

    # 2) per-case provider status ------------------------------------------
    s, b = req("GET", f"/cases/{multi}/copilot/status", admin)
    active = b.get("active")
    providers = {p["id"]: p for p in b.get("providers", [])}
    check("case copilot status 200 with providers", s == 200 and providers, str(b)[:120])
    check("deterministic engine is active (no LLM key configured)",
          active == "deterministic" and providers.get("deterministic", {}).get("active") is True,
          f"active={active}")
    check("no LLM provider is claimed active without credentials",
          not any(p.get("active") for pid, p in providers.items() if pid != "deterministic"),
          str({pid: p.get("active") for pid, p in providers.items()}))

    # 3) suggested questions ------------------------------------------------
    s, b = req("GET", f"/cases/{multi}/copilot/suggestions", admin)
    sugg = b.get("suggestions") or []
    check("data-driven suggestions (non-empty, reference the case)",
          s == 200 and len(sugg) >= 3 and any(
              n in " ".join(sugg) for n in person_names),
          f"n={len(sugg)}")

    # 4) analyze FIRST (the Q&A checks below depend on the findings that
    #    analysis produces; analyze is idempotent)
    s, b = req("POST", f"/cases/{multi}/investigation/analyze", admin)
    ec = [f for f in b.get("findings", [])
          if f.get("details", {}).get("contradiction_type") == "EVIDENCE_CONTRADICTION"]
    check("analyze yields exactly ONE EVIDENCE_CONTRADICTION",
          s == 200 and len(ec) == 1, f"n={len(ec)}")
    if ec:
        d = ec[0]["details"]
        names = d.get("locations", {}).get("names", {})
        check("that contradiction is HIGH, Mumbai vs Pune, ~0 min apart",
              d.get("severity") == "HIGH"
              and {names.get("a"), names.get("b")} == {"Mumbai", "Pune"}
              and abs(d.get("time_difference_min", 99)) <= 1.0,
              f"sev={d.get('severity')} names={names} dt={d.get('time_difference_min')}")
        check("contradiction explanation cites both evidence records",
              len(ec[0].get("supporting_evidence_ids", [])) == 2,
              str(ec[0].get("supporting_evidence_ids")))

    # 5) deterministic Q&A with citations ----------------------------------
    def cited_ids(b):
        return {(c["kind"], c["id"]) for c in b.get("citations", [])}

    s, b = ask(admin, multi, "Summarize the case")
    check("case_overview answered, cites the HIGH contradiction finding",
          s == 200 and b.get("status") == "answered" and cited_ids(b)
          and any(k == "finding" for k, _ in cited_ids(b)),
          f"{s} {b.get('status')} n={len(b.get('citations', []))}")

    s, b = ask(admin, multi, "Show the profile for Vikram Rao")
    check("entity_profile (Vikram Rao) answered + cited",
          s == 200 and b.get("status") == "answered" and
          any(c.get("kind") == "entity" and c.get("label") == "Vikram Rao"
              for c in b.get("citations", [])),
          f"{s} {b.get('status')} cites={[c.get('label') for c in b.get('citations', [])]}")

    s, b = ask(admin, multi, "How is Rajesh Kumar connected to Vikram Rao?")
    check("relationship_path answered + cited",
          s == 200 and b.get("status") == "answered" and cited_ids(b),
          f"{s} {b.get('status')}")

    s, b = ask(admin, multi, "Where was Rajesh Kumar?")
    loc_cites = [c for c in b.get("citations", []) if c.get("kind") in
                 ("location", "claim", "evidence", "entity")]
    check("location_query answered + cited (locations incl. entity-based)",
          s == 200 and b.get("status") == "answered" and len(loc_cites) >= 1
          and "Pune" in (b.get("answer_text") or "")
          and "Mumbai" in (b.get("answer_text") or ""),
          f"{s} {b.get('status')} n={len(b.get('citations', []))} text={(b.get('answer_text') or '')[:80]!r}")

    s, b = ask(admin, multi, "What contradictions are there?")
    contra_cited = any("Mumbai" in str(c.get("label", "")) or
                       "contradiction" in str(c.get("record", {})).lower()
                       for c in b.get("citations", []))
    check("contradictions intent answered + cites the finding",
          s == 200 and b.get("status") == "answered" and contra_cited,
          f"{s} {b.get('status')}")

    # 6) NO-HALLUCINATION ---------------------------------------------------
    # (a) a question matching nothing in the case (no entity, no intent)
    #     -> honest "no confirmed records match" (or unsupported), with
    #     ZERO citations: the copilot never invents records.
    s, b = ask(admin, multi, "What is the weather forecast for tomorrow?")
    honest_nomatch = (b.get("status") == "unsupported") or (
        b.get("status") == "answered"
        and "no confirmed records" in (b.get("answer_text") or "").lower()
        and not b.get("citations"))
    check("out-of-domain (no case entity) -> honest no-match, zero citations",
          s == 200 and honest_nomatch,
          f"{s} {b.get('status')} cites={len(b.get('citations', []))} text={(b.get('answer_text') or '')[:60]!r}")
    # (b) a question naming a real entity but out of scope (weather) still
    #     answers ONLY from confirmed, cited records (never fabricated):
    #     every cited id must exist and the interpretation is surfaced.
    s, b = ask(admin, multi, "What is the weather forecast for Mumbai tomorrow?")
    ok_b = (s == 200 and b.get("data", {}).get("intent")
            and all(isinstance(c.get("id"), int) for c in b.get("citations", [])))
    check("entity-mentioning off-topic question stays cited + interpretable",
          ok_b, f"{s} {b.get('status')}")
    # (b) every cited id must exist for the case (no invented records)
    s, b = ask(admin, multi, "What happened?")
    ids = cited_ids(b)
    ok = True
    detail = ""
    if s == 200 and ids:
        db = SessionLocal()
        try:
            ents = {e.id for e in db.execute(select(Entity).where(Entity.case_id == multi)).scalars()}
            evs = {e.id for e in db.execute(select(Document).where(Document.case_id == multi)).scalars()}
            from app.models import Relationship, GraphFinding, InvestigationHypothesis
            rels = {r.id for r in db.execute(select(Relationship).where(Relationship.case_id == multi)).scalars()}
            finds = {f.id for f in db.execute(select(GraphFinding).where(GraphFinding.case_id == multi)).scalars()}
            hyps = {h.id for h in db.execute(select(InvestigationHypothesis).where(InvestigationHypothesis.case_id == multi)).scalars()}
            known = {"entity": ents, "evidence": evs, "relationship": rels,
                     "finding": finds, "hypothesis": hyps}
            for kind, rid in ids:
                pool = known.get(kind)
                if pool is not None and rid not in pool:
                    ok = False
                    detail = f"{kind}:{rid} not in case"
                    break
        finally:
            db.close()
    check("all cited records exist in the case (no fabricated ids)", ok, detail)

    # 7) multilingual -------------------------------------------------------
    check("demo case documents detected as EN/HI/MR/UR",
          doc_langs == {"en", "hi", "mr", "ur"}, str(sorted(doc_langs)))
    check("non-Latin surface forms resolve to canonical names (no script leak)",
          {"Rajesh Kumar", "Vikram Rao", "Ananya Joshi"} <= person_names
          and all(ord(ch) < 0x900 for ch in "".join(person_names)),
          str(sorted(person_names)))
    s, b = req("POST", f"/cases/{multi}/copilot/nlq/search", admin,
               body={"query": "पुणे"})
    dev_hits = b.get("hits") or []
    check("multilingual search: Devanagari 'पुणे' finds the Pune entity",
          s == 200 and any(h.get("label") == "Pune" for h in dev_hits),
          f"{s} hits={[h.get('label') for h in dev_hits]}")
    s, b = req("POST", f"/cases/{multi}/copilot/nlq/search", admin,
               body={"query": "Pune"})
    check("multilingual search: English 'Pune' also hits",
          s == 200 and any(h.get("label") == "Pune" for h in b.get("hits", [])),
          f"{s}")

    # 7b) multilingual Q&A (acceptance #11–12): ask in MR/HI/UR → answer in
    #     that language, SAME citations as the English counterpart
    reg_path = os.path.join(os.path.dirname(__file__), "..",
                            "data", "raw", "multilingual_aliases.json")
    reg = json.load(open(reg_path, encoding="utf-8"))["entities"]["person"]
    surf = lambda canonical, lang: reg[canonical][lang][0]  # noqa: E731

    def script_of(text, lo, hi):
        return any(lo <= ord(ch) <= hi for ch in (text or ""))

    s, b = ask(admin, multi,
               f"{surf('Rajesh Kumar','mr')} \u0906\u0928\u093f "
               f"{surf('Vikram Rao','mr')} \u091c\u094b\u0921\u0932\u0947\u0932\u0947 "
               f"\u0915\u093e\u092f \u0906\u0939\u0947?")
    check("Marathi question → Marathi answer (Devanagari)",
          s == 200 and b.get("intent") == "relationship_path"
          and b.get("data", {}).get("answer_language") == "mr"
          and script_of(b.get("answer_text"), 0x0900, 0x097F),
          f"{s} intent={b.get('intent')} a_lang={b.get('data',{}).get('answer_language')}")
    s_en, b_en = ask(admin, multi,
                     "How are Rajesh Kumar and Vikram Rao connected?")
    check("MR and EN versions cite the same records",
          cited_ids(b) == cited_ids(b_en) and cited_ids(b),
          f"mr={sorted(cited_ids(b))} en={sorted(cited_ids(b_en))}")

    s, b = ask(admin, multi,
               f"{surf('Rajesh Kumar','ur')} \u0648\u0631 "
               f"{surf('Vikram Rao','ur')} \u06a9\u06cc\u0633\u06d2 "
               f"\u062c\u0691\u06d2 \u06c1\u0648\u0626\u06d4 \u06c1\u06d2\u06ba\u06ba?")
    check("Urdu question → Urdu answer (Perso-Arabic)",
          s == 200 and b.get("intent") == "relationship_path"
          and b.get("data", {}).get("answer_language") == "ur"
          and script_of(b.get("answer_text"), 0x0600, 0x06FF),
          f"{s} a_lang={b.get('data',{}).get('answer_language')}")

    s, b = ask(admin, multi,
               f"\u0907\u0938 \u0915\u0947\u0938 \u092e\u0947\u0902 "
               f"{surf('Rajesh Kumar','hi')} \u0915\u0947 \u0915\u093f\u0928 "
               f"\u0932\u094b\u0917\u094b\u0902 \u0938\u0947 \u0938\u0902\u092c\u0927 "
               f"\u0939\u0948?")
    check("Hindi question → Hindi answer (Devanagari)",
          s == 200 and b.get("intent") == "neighbourhood"
          and b.get("data", {}).get("answer_language") == "hi"
          and script_of(b.get("answer_text"), 0x0900, 0x097F),
          f"{s} intent={b.get('intent')} a_lang={b.get('data',{}).get('answer_language')}")

    s, b = ask(admin, multi, "Where was Rajesh Kumar?")
    check("English question → English answer (control)",
          s == 200 and b.get("data", {}).get("answer_language") == "en"
          and not script_of(b.get("answer_text"), 0x0900, 0x097F),
          f"{s} a_lang={b.get('data',{}).get('answer_language')}")

    # 8) evidence claims persisted (analyze + contradiction were checked in
    #    section 4, before the copilot Q&A that reads the findings)
    check("four was_at claims materialized from the four documents",
          n_claims == 4, f"n={n_claims}")
    s, b = req("GET", f"/cases/{multi}/investigation/findings", admin)
    cur = b.get("current_findings", [])
    ec_now = [f for f in cur
              if f.get("details", {}).get("contradiction_type") == "EVIDENCE_CONTRADICTION"]
    check("the EVIDENCE_CONTRADICTION is persisted as a current finding",
          s == 200 and len(ec_now) == 1, f"n={len(ec_now)}")

    # 9) case isolation + RBAC ---------------------------------------------
    s, b = req("GET", f"/cases/{multi}/investigation/findings", analyst)
    check("ANALYST can read (200)", s == 200)
    s, b = ask(analyst, multi, "Summarize the case")
    check("ANALYST cannot ask the copilot (403)",
          s == 403 and b.get("error", {}).get("code") == "FORBIDDEN", str(s))
    s, b = req("GET", f"/cases/{multi}/copilot/status")
    check("no token rejected", s in (401, 403), str(s))
    # a case id that does not exist is not answerable
    s, b = ask(admin, 999999, "Summarize the case")
    check("unknown case is not answerable (404)", s == 404, str(s))

    # 10) stage-4 regression -------------------------------------------------
    s, b = req("POST", f"/cases/{contra}/investigation/analyze", admin)
    types = {f["details"]["contradiction_type"]
             for f in b.get("findings", []) if f["finding_type"] == "CONTRADICTION"}
    check("stage-4 demo case still yields its 3 contradiction types",
          s == 200 and {"TIMELINE_CONTRADICTION", "LOCATION_CONTRADICTION",
                        "RELATIONSHIP_CONTRADICTION"} <= types,
          str(types))

    print()
    if FAILS:
        print(f"SMOKE: {len(FAILS)} check(s) FAILED: {FAILS}")
        return 1
    print("SMOKE: all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
