"""Stage 5 — multilingual QA tests (acceptance #11–12).

An investigator who asks in Marathi, Hindi or Urdu gets an answer in that
language with the SAME confirmed facts, citations and neutral register —
the LLM-free deterministic provider re-renders its structured answer via
the localization layer. English questions are unaffected.

Non-Latin strings are written as explicit unicode escapes: Devanagari and
Perso-Arabic have multiple visually-identical codepoint forms, and
byte-stable escapes keep these assertions deterministic.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal, db_ready, init_database  # noqa: E402
from app.models import Case, Entity  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.services.language.detect import detect_question_language  # noqa: E402
from app.services.copilot.context import load_case_context  # noqa: E402
from app.services.copilot.intents import CopilotQuestionParser  # noqa: E402
from app.services.copilot.localize import (LOCALIZED_LANGUAGES,  # noqa: E402
                                           render_answer)
from app.services.document_service import _fold_aliases  # noqa: E402

RUN = time.strftime("%Y%m%d-%H%M%S")


def U(cps: list[int]) -> str:
    return "".join(chr(c) for c in cps)


# -- explicit-codepoint words (hi/mr/ur) --------------------------------------
AN_I = U([0x0906, 0x0928, 0x093F])               # anI  (mr: and)
AHE = U([0x0906, 0x0939, 0x0947])                # ahe  (mr: is)
KAY = U([0x0915, 0x093E, 0x092F])                # kAy  (mr: what)
GHA_DLE = U([0x0918, 0x0921, 0x0932, 0x0947])    # ghaDLe (mr: happened)
KOTH_E = U([0x0915, 0x0941, 0x0921, 0x094D, 0x092B, 0x0947])  # koTHe (mr: where)
JO_DLE = U([0x091C, 0x094B, 0x0921, 0x0932, 0x0947])  # joDLe (mr: joined)
JOD_LE = U([0x091C, 0x094B, 0x0921, 0x0932, 0x0947])
KE = U([0x0915, 0x0947])                         # ke   (hi)
KA = U([0x0915, 0x093E])                         # kA   (hi)
ME = U([0x092E, 0x0947, 0x0902])                 # meM  (hi)
SE = U([0x0938, 0x0947])                         # se   (hi)
HAI = U([0x0939, 0x0948])                        # hai  (hi)
KIN = U([0x0915, 0x093F, 0x0928])                # kiN  (hi)
LOG = U([0x0932, 0x094B, 0x0917, 0x094B, 0x0902])  # logM (hi)
SA_M_BA_N_DHA = U([0x0938, 0x0902, 0x092C, 0x0927])  # saMbANdha (hi)
IS = U([0x0907, 0x0938])                         # iS   (hi)
KES = U([0x0915, 0x0947, 0x0938])                # keS  (hi)
VI_SA_NGATI = U([0x0935, 0x093F, 0x0938, 0x0902, 0x0917, 0x0924, 0x093F])  # viSaNgati (hi)
SA_RA_NSA = U([0x0938, 0x093E, 0x0930, 0x093E, 0x0902, 0x0936])  # saAraNSa (hi)
DO = U([0x0926, 0x094B])                         # Do   (hi: give)
AUR = U([0x0648, 0x0631, 0x0631])                # aur  (ur: and)
KISAY = U([0x06A9, 0x06CC, 0x0633, 0x06D2])      # kisay (ur: how)
JARR = U([0x062C, 0x0691])                       # jaRR (ur: connected)
YE = U([0x06D2])                                 # ye (ur: -e suffix)
HUAY = U([0x06C1, 0x0648, 0x06BA])               # huay (ur: is)
HAIN = U([0x06C1, 0x06BA, 0x06BA])               # hain (ur: are)
P = U([0x061F])                                  # ? (ur)


def _has_script(text: str, lo: int, hi: int) -> bool:
    return any(lo <= ord(c) <= hi for c in text)


# =============================================================================
# 1. question-language resolution (script-aware)
# =============================================================================
class TestQuestionLanguage:
    def test_marathi_question(self):
        assert detect_question_language(f"{AN_I} {AHE}?") == "mr"

    def test_hindi_question(self):
        assert detect_question_language(
            f"{KE} {ME} {KIN} {SE} {HAI}?") == "hi"

    def test_urdu_question(self):
        assert detect_question_language(f"{KISAY} {HUAY} {P}") == "ur"

    def test_english_question(self):
        assert detect_question_language("Where was Rajesh Kumar?") == "en"

    def test_mixed_script_latin_names_stay_local(self):
        # the acceptance scenario: Latin-script entity names must not flip a
        # Devanagari question to 'en' (character-count dominance)
        q = f"Rajesh Kumar {AN_I} Vikram Rao {JO_DLE} {KAY} {AHE}?"
        assert detect_question_language(q) == "mr"

    def test_empty_is_english(self):
        assert detect_question_language("") == "en"
        assert detect_question_language("   ") == "en"


# =============================================================================
# 2. multilingual intent parsing on the seeded multilingual demo case
# =============================================================================
@pytest.fixture(scope="module")
def multiling_ctx():
    assert db_ready() or init_database(), "PostgreSQL must be reachable"
    db = SessionLocal()
    case = db.execute(select(Case).where(
        Case.case_number == "CASE-DEMO-MULTILING-01")).scalar_one_or_none()
    assert case, "multilingual demo case must be seeded"
    ctx = load_case_context(db, case)
    yield case, ctx
    db.close()


def _surface(ctx, canonical: str, lo: int, hi: int) -> str:
    for e in ctx.data.entities:
        if e.canonical_name != canonical:
            continue
        for a in (ctx.data.entity_metadata.get(e.id, {}).get("aliases") or []):
            if isinstance(a, str) and not a.isascii() and all(
                    lo <= ord(c) <= hi or c == " " for c in a):
                return a
    pytest.fail(f"no {canonical} alias in script {lo:#x}-{hi:#x}")


class TestMultilingualIntents:
    def test_mr_relationship_two_names(self, multiling_ctx):
        case, ctx = multiling_ctx
        rk = _surface(ctx, "Rajesh Kumar", 0x0900, 0x097F)
        vr = _surface(ctx, "Vikram Rao", 0x0900, 0x097F)
        p = CopilotQuestionParser(ctx)
        intent = p.parse(f"{rk} {AN_I} {vr} {JO_DLE} {KAY} {AHE}?")
        assert intent.intent == "relationship_path"
        assert intent.params["question_language"] == "mr"

    def test_mr_neighbourhood_one_name(self, multiling_ctx):
        case, ctx = multiling_ctx
        rk = _surface(ctx, "Rajesh Kumar", 0x0900, 0x097F)
        p = CopilotQuestionParser(ctx)
        intent = p.parse(f"{rk} {AN_I} {JO_DLE}?")
        assert intent.intent == "neighbourhood"
        assert intent.params["question_language"] == "mr"

    def test_mr_location(self, multiling_ctx):
        case, ctx = multiling_ctx
        rk = _surface(ctx, "Rajesh Kumar", 0x0900, 0x097F)
        p = CopilotQuestionParser(ctx)
        intent = p.parse(f"{rk} {KOTH_E} {KAY}?")
        assert intent.intent == "location_query"
        assert intent.params["question_language"] == "mr"

    def test_hi_neighbourhood(self, multiling_ctx):
        case, ctx = multiling_ctx
        rk = _surface(ctx, "Rajesh Kumar", 0x0900, 0x097F)
        p = CopilotQuestionParser(ctx)
        intent = p.parse(f"{IS} {KES} {ME} {rk} {KIN} {LOG} {SE} "
                         f"{SA_M_BA_N_DHA} {HAI}?")
        assert intent.intent == "neighbourhood"
        assert intent.params["question_language"] == "hi"

    def test_hi_contradictions(self, multiling_ctx):
        case, ctx = multiling_ctx
        p = CopilotQuestionParser(ctx)
        intent = p.parse(f"{IS} {KES} {ME} {VI_SA_NGATI} {HAIN}?")
        assert intent.intent == "contradictions"

    def test_hi_overview(self, multiling_ctx):
        case, ctx = multiling_ctx
        p = CopilotQuestionParser(ctx)
        intent = p.parse(f"{KES} {KA} {SA_RA_NSA} {DO}")
        assert intent.intent == "case_overview"

    def test_ur_relationship_two_names(self, multiling_ctx):
        case, ctx = multiling_ctx
        rk = _surface(ctx, "Rajesh Kumar", 0x0600, 0x06FF)
        vr = _surface(ctx, "Vikram Rao", 0x0600, 0x06FF)
        p = CopilotQuestionParser(ctx)
        intent = p.parse(f"{rk} {AUR} {vr} {KISAY} {JARR}{YE} {HUAY} "
                         f"{HAIN}{P}")
        assert intent.intent == "relationship_path"
        assert intent.params["question_language"] == "ur"

    def test_english_unaffected(self, multiling_ctx):
        case, ctx = multiling_ctx
        p = CopilotQuestionParser(ctx)
        intent = p.parse("How are Rajesh Kumar and Vikram Rao connected?")
        assert intent.intent == "relationship_path"
        assert intent.params.get("question_language") in ("en", None)


# =============================================================================
# 3. localization rendering (offline, no DB)
# =============================================================================
class TestRenderAnswer:
    @staticmethod
    def _rel_data(ctx):
        # the provider's real payload shape: entity IDS, not names
        a_id, a_name = ctx.resolve_all("Rajesh Kumar")
        b_id, b_name = ctx.resolve_all("Vikram Rao")
        assert a_id and b_id and a_id != b_id
        return {"a": a_id, "b": b_id, "hops": 1, "path": [a_id, b_id],
                "edges": [{"from": a_id, "to": b_id,
                           "relationship_type": "CALLED"}]}, (a_name, b_name)

    def test_supported_languages(self):
        assert LOCALIZED_LANGUAGES == ("hi", "mr", "ur")

    def test_mr_renders_devanagari_with_facts(self, multiling_ctx):
        case, ctx = multiling_ctx
        data, (a, b) = self._rel_data(ctx)
        text = render_answer("relationship_path", data, "mr", ctx)
        assert text
        assert _has_script(text, 0x0900, 0x097F), "must be Devanagari"
        assert a in text and b in text

    def test_ur_renders_arabic_with_facts(self, multiling_ctx):
        case, ctx = multiling_ctx
        data, (a, b) = self._rel_data(ctx)
        text = render_answer("relationship_path", data, "ur", ctx)
        assert text
        assert _has_script(text, 0x0600, 0x06FF), "must be Perso-Arabic"
        assert a in text and b in text

    def test_hi_renders_devanagari_with_facts(self, multiling_ctx):
        case, ctx = multiling_ctx
        data, (a, b) = self._rel_data(ctx)
        text = render_answer("relationship_path", data, "hi", ctx)
        assert text
        assert _has_script(text, 0x0900, 0x097F), "must be Devanagari"
        assert a in text and b in text

    def test_unsupported_language_returns_none(self, multiling_ctx):
        case, ctx = multiling_ctx
        data, _ = self._rel_data(ctx)
        assert render_answer("relationship_path", data, "fr", ctx) is None

    def test_unknown_intent_returns_none(self):
        assert render_answer("no_such_intent", {}, "mr", None) is None

    def test_missing_data_never_raises(self):
        # the contract is "never raise" (the provider then keeps the
        # validated English text); the degraded output may be None or a
        # dash-filled string for artificial empty payloads
        for intent_name, lang in [("relationship_path", "mr"),
                                  ("entity_profile", "ur"),
                                  ("case_overview", "hi"),
                                  ("contradictions", "mr")]:
            text = render_answer(intent_name, {}, lang, None)
            assert text is None or isinstance(text, str)


# =============================================================================
# 4. E2E — ask in MR/HI/UR, get that language back with the same citations
# =============================================================================
# `client` and `auth` come from conftest (Supabase tokens).


def _ask(client, auth, case_id: int, question: str) -> dict:
    r = client.post(f"/api/v1/cases/{case_id}/copilot/ask", headers=auth,
                    json={"question": question})
    assert r.status_code == 200, r.text
    return r.json()


def _cites(b: dict) -> set:
    return {(c["kind"], c["id"]) for c in b.get("citations", [])}


class TestMultilingualAskE2E:
    def test_mr_answer_matches_english_citations(self, client, auth,
                                                 multiling_ctx):
        case, _ = multiling_ctx
        client.post(f"/api/v1/cases/{case.id}/investigation/analyze",
                    headers=auth)
        rk = _surface(_ctx_of(client, auth, case.id), "Rajesh Kumar",
                      0x0900, 0x097F)
        vr = _surface(_ctx_of(client, auth, case.id), "Vikram Rao",
                      0x0900, 0x097F)
        mr_q = f"{rk} {AN_I} {vr} {JO_DLE} {KAY} {AHE}?"
        en_q = "How are Rajesh Kumar and Vikram Rao connected?"
        b_mr = _ask(client, auth, case.id, mr_q)
        b_en = _ask(client, auth, case.id, en_q)
        assert b_mr["intent"] == b_en["intent"] == "relationship_path"
        assert b_mr["data"]["answer_language"] == "mr"
        assert b_en["data"]["answer_language"] == "en"
        txt = b_mr["answer_text"]
        assert _has_script(txt, 0x0900, 0x097F), "MR answer must be Devanagari"
        assert "Rajesh Kumar" in txt and "Vikram Rao" in txt
        # same confirmed facts → same citations
        assert _cites(b_mr) == _cites(b_en) and _cites(b_en)

    def test_ur_answer(self, client, auth, multiling_ctx):
        case, _ = multiling_ctx
        rk = _surface(_ctx_of(client, auth, case.id), "Rajesh Kumar",
                      0x0600, 0x06FF)
        vr = _surface(_ctx_of(client, auth, case.id), "Vikram Rao",
                      0x0600, 0x06FF)
        ur_q = f"{rk} {AUR} {vr} {KISAY} {JARR}{YE} {HUAY} {HAIN}{P}"
        b = _ask(client, auth, case.id, ur_q)
        assert b["intent"] == "relationship_path"
        assert b["data"]["answer_language"] == "ur"
        assert _has_script(b["answer_text"], 0x0600, 0x06FF)

    def test_hi_answer(self, client, auth, multiling_ctx):
        case, _ = multiling_ctx
        rk = _surface(_ctx_of(client, auth, case.id), "Rajesh Kumar",
                      0x0900, 0x097F)
        hi_q = (f"{IS} {KES} {ME} {rk} {KIN} {LOG} {SE} "
                f"{SA_M_BA_N_DHA} {HAI}?")
        b = _ask(client, auth, case.id, hi_q)
        assert b["intent"] == "neighbourhood"
        assert b["data"]["answer_language"] == "hi"
        assert _has_script(b["answer_text"], 0x0900, 0x097F)

    def test_english_answer_unchanged(self, client, auth, multiling_ctx):
        case, _ = multiling_ctx
        b = _ask(client, auth, case.id, "Where was Rajesh Kumar?")
        assert b["intent"] == "location_query"
        assert b["data"]["answer_language"] == "en"
        assert not _has_script(b["answer_text"], 0x0900, 0x097F)


def _ctx_of(client, auth, case_id: int):
    # rebuild a read-only context for surface-form lookup
    db = SessionLocal()
    try:
        case = db.get(Case, case_id)
        return load_case_context(db, case)
    finally:
        db.close()


# =============================================================================
# 5. original-script alias preservation on confirmed entities
# =============================================================================
class TestAliasPreservation:
    def test_fold_aliases_adds_surface_forms(self):
        class _E:
            canonical_name = "Rajesh Kumar"
            meta = {"extracted": True, "aliases": ["Rajesh Kumar"]}
        e = _E()
        _fold_aliases(e, ["Rajesh Kumar", U([0x0930, 0x093E, 0x091C, 0x0947,
                                             0x0936])])
        assert U([0x0930, 0x093E, 0x091C, 0x0947, 0x0936]) in e.meta["aliases"]
        before = list(e.meta["aliases"])
        _fold_aliases(e, [U([0x0930, 0x093E, 0x091C, 0x0947, 0x0936])])
        assert e.meta["aliases"] == before, "must be idempotent"

    def test_accept_entity_candidate_preserves_devanagari(self, client, auth):
        # SYNTHETIC DEMONSTRATION DATA — same text as the claims E2E suite
        from tests.test_evidence_claims import TestClaimMaterializationE2E
        doc_a = TestClaimMaterializationE2E.DOC_A
        r = client.post("/api/v1/cases", headers=auth, json={
            "case_number": f"ALIAS-2026-{int(time.time()) % 1000000:06d}",
            "title": f"alias preservation {RUN}",
            "description": "SYNTHETIC DEMONSTRATION DATA"})
        assert r.status_code == 201, r.text
        cid = r.json()["id"]
        try:
            up = client.post(f"/api/v1/cases/{cid}/documents",
                             files={"file": (f"alias_{RUN}.txt",
                                             doc_a.encode(), "text/plain")},
                             headers=auth)
            assert up.status_code == 201, up.text
            did = up.json()["id"]
            for _ in range(30):
                time.sleep(1)
                st = client.get(f"/api/v1/documents/{did}/status",
                                headers=auth).json()
                if st.get("processing_status") == "PROCESSED":
                    break
            # accept the person candidate (match first if suggested)
            for _ in range(12):
                ex = client.get(f"/api/v1/documents/{did}/extraction",
                                headers=auth).json()
                progressed = False
                for m in ex["matches"]:
                    if m["status"] == "PENDING":
                        client.post(f"/api/v1/documents/{did}/extraction/"
                                    f"matches/{m['id']}/accept", headers=auth)
                        progressed = True
                for c in ex["entities"]:
                    if c["status"] != "PENDING":
                        continue
                    if c.get("match") and c["match"]["status"] == "PENDING":
                        continue
                    client.post(f"/api/v1/documents/{did}/extraction/"
                                f"candidates/{c['id']}/accept", headers=auth)
                    progressed = True
                if not progressed:
                    break
            db = SessionLocal()
            try:
                ents = db.execute(select(Entity).where(
                    Entity.case_id == cid,
                    Entity.entity_type == "person")).scalars().all()
                assert ents, "person entity must be confirmed"
                e = next(e for e in ents if "Rajesh" in e.canonical_name)
                dev = [a for a in (e.meta or {}).get("aliases", [])
                       if _has_script(a, 0x0900, 0x097F)]
                assert dev, (f"original-script alias missing: "
                             f"{e.meta.get('aliases')}")
            finally:
                db.close()
        finally:
            db = SessionLocal()
            try:
                c = db.get(Case, cid)
                if c:
                    db.delete(c)
                    db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
            finally:
                db.close()
