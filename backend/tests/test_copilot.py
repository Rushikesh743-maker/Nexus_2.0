"""Stage 5 — investigator copilot tests.

Covers: intent parsing (all 12 intents), the deterministic provider
(confirmed-only answers, citations ⊆ context, computed confidence, neutral
language), the multilingual search endpoint, RBAC (INVESTIGATOR floor for
ask/impact, read floor for status/suggestions/search), honest provider
status, audit logging without secrets, and the Gemini provider's
validation guards (prose-only contract).
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal  # noqa: E402
from app.models import AuditLog  # noqa: E402
from app.services.copilot import (load_case_context, provider_status,  # noqa: E402
                                  suggest_questions)
from app.services.copilot.intents import CopilotQuestionParser  # noqa: E402
from app.services.copilot.providers.deterministic import (  # noqa: E402
    DeterministicProvider)
from app.services.copilot.providers.gemini import GeminiProvider  # noqa: E402
from app.models import Case  # noqa: E402
from sqlalchemy import select  # noqa: E402

RUN = time.strftime("%Y%m%d-%H%M%S")

# CASE-2026-001 is seeded with confirmed entities (Aarav Mehta, Rohan
# Deshmukh, …) — stable fixtures for parser/provider assertions.
CASE_ID = 1

# `client`, `auth` and `analyst` come from conftest (Supabase tokens).


@pytest.fixture(scope="module")
def ctx():
    db = SessionLocal()
    try:
        case = db.get(Case, CASE_ID)
        return load_case_context(db, case)
    finally:
        db.close()


# ================================================================== parser
@pytest.fixture(scope="module")
def parser(ctx):
    return CopilotQuestionParser(ctx)


class TestIntentParser:
    def test_path(self, parser):
        i = parser.parse("How is Aarav Mehta connected to Rohan Deshmukh?")
        assert i.intent == "relationship_path"
        assert i.params["a"] == "Aarav Mehta"
        assert i.params["b"] == "Rohan Deshmukh"

    def test_neighbourhood(self, parser):
        i = parser.parse("Who is connected to Aarav Mehta?")
        assert i.intent == "neighbourhood"
        assert i.params["node"] == "Aarav Mehta"

    def test_profile(self, parser):
        i = parser.parse("Show the profile for Aarav Mehta")
        assert i.intent == "entity_profile"

    def test_timeline(self, parser):
        i = parser.parse("What happened?")
        assert i.intent == "timeline"

    def test_contradictions(self, parser):
        i = parser.parse("What contradictions are there?")
        assert i.intent == "contradictions"

    def test_gaps(self, parser):
        i = parser.parse("What is missing from the case?")
        assert i.intent == "gaps"

    def test_hypotheses(self, parser):
        i = parser.parse("What are the competing hypotheses?")
        assert i.intent == "hypotheses"

    def test_evidence_by_id(self, parser):
        i = parser.parse("What is E1?")
        assert i.intent == "evidence_lookup"
        assert i.params["evidence_id"] == 1

    def test_evidence_word_form(self, parser):
        i = parser.parse("Describe evidence row 12 for me")
        assert i.intent == "evidence_lookup"
        assert i.params["evidence_id"] == 12

    def test_location(self, parser):
        i = parser.parse("What locations are recorded?")
        assert i.intent == "location_query"

    def test_impact(self, parser):
        i = parser.parse("What happens if we remove E1?")
        assert i.intent == "impact_simulation"
        assert i.params["evidence_id"] == 1

    def test_search(self, parser):
        i = parser.parse("Search for Mehta")
        assert i.intent == "entity_search"
        assert i.params["query"] == "Mehta"

    def test_overview(self, parser):
        i = parser.parse("Summarize the case")
        assert i.intent == "case_overview"

    def test_interpretation_always_present(self, parser):
        for q in ["How is Aarav Mehta connected to Rohan Deshmukh?",
                  "zzz qqq", "Summarize"]:
            i = parser.parse(q)
            assert i.interpretation, "interpretation must never be empty"


# ========================================================= deterministic
@pytest.fixture(scope="module")
def provider():
    return DeterministicProvider()


class TestDeterministicProvider:
    def _answer(self, ctx, provider, question: str):
        i = CopilotQuestionParser(ctx).parse(question)
        return provider.answer(ctx, i)

    def test_no_hallucination_citations_subset_of_context(self, ctx,
                                                          provider):
        """Every cited record must exist in the confirmed context."""
        valid = {
            ("entity", e.id) for e in ctx.data.entities
        } | {("relationship", r.id) for r in ctx.data.relationships} | \
            {("evidence", v.id) for v in ctx.data.evidence} | \
            {("event", e.id) for e in ctx.data.events} | \
            {("location", l.id) for l in ctx.data.locations} | \
            {("claim", c.id) for c in ctx.data.claims}
        for q in ["Summarize the case",
                  "How is Aarav Mehta connected to Rohan Deshmukh?",
                  "Who is connected to Aarav Mehta?",
                  "What happened?",
                  "What is E1?",
                  "What locations are recorded?",
                  "Search for Mehta",
                  "What contradictions are there?"]:
            a = self._answer(ctx, provider, q)
            for c in a.citations:
                assert (c.kind, c.id) in valid, \
                    f"{c.kind} {c.id} not in context for {q!r}"

    def test_confidence_bounded_and_documented(self, ctx, provider):
        for q in ["Summarize the case", "What happened?",
                  "Who is connected to Aarav Mehta?"]:
            a = self._answer(ctx, provider, q)
            assert 0.0 <= a.confidence <= 1.0
            assert a.confidence_basis, "confidence must have a basis"

    def test_neutral_language(self, ctx, provider):
        a = self._answer(ctx, provider, "Summarize the case")
        low = (a.answer_text or "").lower()
        for banned in ("proves", "guilty", "definitely", "criminal"):
            assert banned not in low

    def test_path_answer_is_correct(self, ctx, provider):
        a = self._answer(ctx, provider,
                         "How is Aarav Mehta connected to Rohan Deshmukh?")
        assert a.status == "answered"
        assert a.data["hops"] >= 1
        assert a.data["a"] == ctx.entity_id_for("Aarav Mehta")
        assert a.data["b"] == ctx.entity_id_for("Rohan Deshmukh")

    def test_unknown_entity_is_unsupported_not_fabricated(self, ctx,
                                                          provider):
        a = self._answer(ctx, provider, "Show the profile for Zzz Unknown")
        assert a.status in ("unsupported",)
        assert a.confidence == 0.0
        assert a.data.get("entity_id") is None

    def test_impact_is_simulation_only(self, ctx, provider):
        a = self._answer(ctx, provider, "What happens if we remove E1?")
        assert a.status == "answered"
        assert a.data["simulation_only"] is True

    def test_impact_missing_evidence_is_honest(self, ctx, provider):
        a = self._answer(ctx, provider, "What happens if we remove E99999?")
        assert a.status == "not_enough_data"

    def test_suggestions_are_deterministic(self, ctx):
        s = suggest_questions(ctx)
        assert isinstance(s, list) and len(s) <= 8
        assert all(isinstance(x, str) for x in s)


# ================================================================== status
class TestProviderStatus:
    def test_deterministic_always_active(self, ctx):
        st = provider_status(ctx.case)
        by_id = {p["id"]: p for p in st["providers"]}
        assert by_id["deterministic"]["active"] is True
        assert st["case_id"] == CASE_ID

    def test_gemini_offline_is_honest(self, ctx):
        st = provider_status(ctx.case)
        by_id = {p["id"]: p for p in st["providers"]}
        # no key in the test environment -> gemini must report not active
        if not by_id["gemini"]["active"]:
            assert by_id["gemini"]["model"] is None
            assert "GEMINI_API_KEY" in by_id["gemini"]["reason"]


# =================================================================== API
class TestCopilotAPI:
    def test_status_endpoint(self, client, auth):
        r = client.get(f"/api/v1/cases/{CASE_ID}/copilot/status",
                       headers=auth)
        assert r.status_code == 200
        body = r.json()
        assert body["active"] in ("deterministic", "gemini")

    def test_suggestions_endpoint(self, client, auth):
        r = client.get(f"/api/v1/cases/{CASE_ID}/copilot/suggestions",
                       headers=auth)
        assert r.status_code == 200
        assert r.json()["suggestions"]

    def test_ask_endpoint(self, client, auth):
        r = client.post(f"/api/v1/cases/{CASE_ID}/copilot/ask", headers=auth,
                        json={"question": "How is Aarav Mehta connected to "
                                          "Rohan Deshmukh?"})
        assert r.status_code == 200, r.text
        a = r.json()
        assert a["intent"] == "relationship_path"
        assert a["provider"] in ("deterministic", "gemini")
        assert a["citations"], "answers must cite their records"
        assert "question" in a["data"]

    def test_ask_rejects_empty(self, client, auth):
        r = client.post(f"/api/v1/cases/{CASE_ID}/copilot/ask", headers=auth,
                        json={"question": ""})
        assert r.status_code == 422

    def test_impact_endpoint(self, client, auth):
        r = client.post(f"/api/v1/cases/{CASE_ID}/copilot/impact",
                        headers=auth, json={"evidence_id": 1})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["simulation_only"] is True

    def test_search_endpoint(self, client, auth):
        r = client.get(f"/api/v1/cases/{CASE_ID}/search",
                       params={"q": "Mehta"}, headers=auth)
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_nlq_search_endpoint(self, client, auth):
        r = client.post(f"/api/v1/cases/{CASE_ID}/copilot/nlq/search",
                        headers=auth, json={"query": "Mehta"})
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_case_not_found(self, client, auth):
        r = client.get("/api/v1/cases/99999/copilot/status", headers=auth)
        assert r.status_code == 404

    def test_unauthenticated(self, client):
        r = client.get(f"/api/v1/cases/{CASE_ID}/copilot/status")
        assert r.status_code == 401


class TestCopilotRBAC:
    def test_analyst_cannot_ask(self, client, analyst):
        r = client.post(f"/api/v1/cases/{CASE_ID}/copilot/ask",
                        headers=analyst,
                        json={"question": "Summarize the case"})
        assert r.status_code == 403

    def test_analyst_cannot_impact(self, client, analyst):
        r = client.post(f"/api/v1/cases/{CASE_ID}/copilot/impact",
                        headers=analyst, json={"evidence_id": 1})
        assert r.status_code == 403

    def test_analyst_can_status(self, client, analyst):
        assert client.get(f"/api/v1/cases/{CASE_ID}/copilot/status",
                          headers=analyst).status_code == 200

    def test_analyst_can_suggestions(self, client, analyst):
        assert client.get(f"/api/v1/cases/{CASE_ID}/copilot/suggestions",
                          headers=analyst).status_code == 200

    def test_analyst_can_search(self, client, analyst):
        assert client.get(f"/api/v1/cases/{CASE_ID}/search",
                          params={"q": "Mehta"},
                          headers=analyst).status_code == 200


# ================================================================== audit
class TestCopilotAudit:
    def test_ask_is_audited_without_secrets(self, client, auth):
        marker = f"audit-probe-{RUN}"
        r = client.post(f"/api/v1/cases/{CASE_ID}/copilot/ask", headers=auth,
                        json={"question": f"Summarize the case {marker}"})
        assert r.status_code == 200
        db = SessionLocal()
        try:
            row = db.execute(select(AuditLog).where(
                AuditLog.action == "copilot.ask",
                AuditLog.resource_id == str(CASE_ID)
            ).order_by(AuditLog.id.desc()).limit(1)).scalars().first()
            assert row is not None
            meta = row.meta or {}
            assert meta["intent"] == "case_overview"
            assert "provider" in meta and "fallback" in meta
            assert marker in (meta.get("question") or "")
            # no secret ever lands in the audit metadata
            blob = str(meta)
            for banned in ("GEMINI_API_KEY", "api_key", "Bearer "):
                assert banned not in blob
        finally:
            db.close()


# ====================================================== gemini validation
class TestGeminiValidation:
    """The prose-only guards: banned language, unknown evidence refs,
    unknown names. (The network call itself is not exercised offline.)"""

    def _base_answer(self, ctx):
        i = CopilotQuestionParser(ctx).parse("What is E1?")
        return DeterministicProvider().answer(ctx, i)

    def test_banned_language_rejected(self, ctx):
        g = GeminiProvider()
        base = self._base_answer(ctx)
        reason = g._validate(ctx, CopilotQuestionParser(ctx).parse(
            "What is E1?"), base,
            "This record proves he is guilty without doubt.")
        assert reason is not None

    def test_unknown_evidence_ref_rejected(self, ctx):
        g = GeminiProvider()
        base = self._base_answer(ctx)
        allowed = {c.id for c in base.citations if c.kind == "evidence"}
        bad = max(allowed) + 9999 if allowed else 424242
        reason = g._validate(ctx, CopilotQuestionParser(ctx).parse(
            "What is E1?"), base, f"See also evidence E{bad}.")
        assert reason is not None

    def test_unknown_name_rejected(self, ctx):
        g = GeminiProvider()
        base = self._base_answer(ctx)
        reason = g._validate(ctx, CopilotQuestionParser(ctx).parse(
            "What is E1?"), base,
            "The records link Zebulon Fotherington to this matter.")
        assert reason is not None

    def test_clean_prose_accepted(self, ctx):
        g = GeminiProvider()
        i = CopilotQuestionParser(ctx).parse("What is E1?")
        base = DeterministicProvider().answer(ctx, i)
        prose = ("Evidence E1 is a confirmed record of type "
                 f"{base.data['type']}. It is linked to the confirmed "
                 "timeline and cited by the case analysis.")
        reason = g._validate(ctx, i, base, prose)
        assert reason is None

    def test_not_configured_reports_honestly(self, ctx):
        g = GeminiProvider()
        if g.configured():
            pytest.skip("gemini is configured in this environment")
        i = CopilotQuestionParser(ctx).parse("What is E1?")
        a = g.answer(ctx, i)
        assert a.provider == "deterministic"
        assert a.fallback is False  # nothing failed; there is simply no LLM


# ================================================================ phase 2
# P2-F: copilot hardening — every answer/search/suggestion is bound to the
# confirmed-data snapshot it was computed over (graph_version + analysis
# state), answering is strictly read-only, and an empty case is answered
# honestly instead of being padded.

def _current_version(client, headers, case_id):
    st = client.get(f"/api/v1/cases/{case_id}/analysis/status",
                    headers=headers)
    assert st.status_code == 200, st.text
    return st.json()["graph_version"]


def _summary_counts(client, headers, case_id):
    s = client.get(f"/api/v1/cases/{case_id}/summary", headers=headers)
    assert s.status_code == 200, s.text
    return s.json()["counts"]


def test_copilot_answer_bound_to_version_and_analysis_state(client, auth):
    """P2-F: an answer carries the confirmed-data version it was computed
    over plus the case's analysis freshness — a stale answer can be
    flagged instead of silently presented as current."""
    before = _current_version(client, auth, CASE_ID)
    r = client.post(f"/api/v1/cases/{CASE_ID}/copilot/ask",
                    json={"question": "Summarize the case"}, headers=auth)
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["graph_version"] == before, (a["graph_version"], before)
    ab = a["analysis"]
    assert ab["graph_version"] == before
    assert ab["state"] in ("not-analyzed", "up-to-date", "stale",
                           "insufficient")
    # honesty about the provider: what it says it used must match the
    # status endpoint's active provider
    st = client.get(f"/api/v1/cases/{CASE_ID}/copilot/status",
                    headers=auth).json()
    assert a["provider"] == st["active"]
    assert a["provider"] == "deterministic"  # no LLM in this environment


def test_copilot_ask_is_readonly(client, auth):
    """P2-F: asking questions must never mutate the case — no confirmed
    data, no findings, no graph-version movement (audit rows excepted)."""
    counts_before = _summary_counts(client, auth, CASE_ID)
    version_before = _current_version(client, auth, CASE_ID)
    for q in ("Summarize the case",
              "Who is connected to the first confirmed person?",
              "What is missing from the case?",
              "What are the competing hypotheses?"):
        r = client.post(f"/api/v1/cases/{CASE_ID}/copilot/ask",
                        json={"question": q}, headers=auth)
        assert r.status_code == 200, (q, r.text)
    assert _summary_counts(client, auth, CASE_ID) == counts_before
    assert _current_version(client, auth, CASE_ID) == version_before


def test_copilot_no_confirmed_data_is_honest(client, auth):
    """P2-F: a case with no confirmed records gets an explicit
    not-enough-data answer (no citations, no padding) — with the
    version/state block still attached so the UI knows why."""
    import uuid as _uuid
    r = client.post("/api/v1/cases",
                    json={"case_number": f"PHI-2026-{_uuid.uuid4().int % 10**9:09d}",
                          "title": "phase 2 copilot no-data probe",
                          "description": "SYNTHETIC DEMONSTRATION DATA — "
                                         "intentionally empty case."},
                    headers=auth)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    db = SessionLocal()
    try:
        a = client.post(f"/api/v1/cases/{cid}/copilot/ask",
                        json={"question": "Summarize the case"},
                        headers=auth).json()
        assert a["status"] == "not_enough_data", a
        assert a["citations"] == []
        assert "no confirmed" in (a["answer_text"] or "").lower()
        assert a["graph_version"]  # still bound to a snapshot (empty one)
        assert a["analysis"]["state"] == "insufficient"
        assert a["analysis"]["insufficient"] is True
    finally:
        from app.models import Case
        case = db.get(Case, cid)
        if case is not None:
            db.delete(case)
            db.commit()
        db.close()


def test_copilot_search_and_suggestions_carry_analysis_block(client, auth):
    """P2-F: search and suggestion surfaces carry the analysis-state
    block too, so the whole copilot UI shares one freshness model."""
    s = client.get(f"/api/v1/cases/{CASE_ID}/search?q=Kurla", headers=auth)
    assert s.status_code == 200, s.text
    assert s.json()["analysis"]["graph_version"] == \
        _current_version(client, auth, CASE_ID)
    q = client.post(f"/api/v1/cases/{CASE_ID}/copilot/nlq/search",
                    json={"query": "Kurla"}, headers=auth)
    assert q.status_code == 200, q.text
    assert "analysis" in q.json()
    sg = client.get(f"/api/v1/cases/{CASE_ID}/copilot/suggestions",
                    headers=auth)
    assert sg.status_code == 200, sg.text
    assert sg.json()["analysis"]["state"] in ("not-analyzed", "up-to-date",
                                              "stale", "insufficient")


def test_copilot_impact_is_simulation_only_and_version_bound(client, auth):
    """P2-F: the impact endpoint simulates in memory — the evidence row
    still exists afterwards and the confirmed-data version did not move;
    the answer is bound to the version it simulated against."""
    db = SessionLocal()
    try:
        from app.models import Evidence
        ev = db.scalar(select(Evidence).where(Evidence.case_id == CASE_ID)
                       .order_by(Evidence.id).limit(1))
        if ev is None:  # fall back to any seeded case with evidence
            ev = db.scalar(select(Evidence).order_by(Evidence.id).limit(1))
        eid = ev.id
        cid = ev.case_id
    finally:
        db.close()
    version_before = _current_version(client, auth, cid)
    r = client.post(f"/api/v1/cases/{cid}/copilot/impact",
                    json={"evidence_id": eid}, headers=auth)
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["graph_version"] == version_before
    assert a["data"].get("simulation_only") is True or \
        "simulation" in a.get("confidence_basis", "").lower()
    db = SessionLocal()
    try:
        assert db.get(Evidence, eid) is not None  # nothing was deleted
    finally:
        db.close()
    assert _current_version(client, auth, cid) == version_before
