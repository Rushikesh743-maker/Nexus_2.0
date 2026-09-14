"""Copilot service — orchestration, provider chain, audit.

Flow for a question:

    1. load the case context (confirmed records only);
    2. parse the question deterministically (intent + interpretation);
    3. run the provider chain — Gemini (when configured) writes prose only,
       validated against the deterministic answer; any failure falls back
       honestly to the deterministic provider;
    4. audit the usage (user, intent, provider, fallback, confidence,
       citation count) — never the API key or any credential.

The service is case-scoped and stateless: the context is built per request,
so a question always reflects the current confirmed data.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ...models import Case
from ..auth_service import record_audit
from .context import load_case_context
from .intents import CopilotQuestionParser
from .providers.base import CopilotAnswer
from .providers.deterministic import DeterministicProvider
from .providers.gemini import GeminiProvider

_MAX_AUDIT_QUESTION = 500


def provider_status(case: Case) -> dict:
    """What the frontend can truthfully display about the providers."""
    gemini = GeminiProvider().status()
    det = {"id": "deterministic", "name":
           "Deterministic engine (offline, no LLM)", "active": True,
           "reason": "Always available; computes every answer from "
                     "confirmed case records.",
           "model": None}
    return {"providers": [det, gemini],
            "active": gemini["id"] if gemini["active"] else "deterministic",
            "case_id": case.id}


def ask_case(db: Session, case: Case, question: str,
             current) -> CopilotAnswer:
    """Answer one question over one case (see module docstring)."""
    ctx = load_case_context(db, case)
    parsed = CopilotQuestionParser(ctx).parse(question)
    gemini = GeminiProvider()
    provider = gemini if gemini.configured() else DeterministicProvider()
    answer = provider.answer(ctx, parsed)
    answer.data["question"] = question
    answer.data["intent"] = parsed.to_dict()
    # phase 2 (work item F): bind the answer to the confirmed-data snapshot
    # it was computed over (stage-4 version: entities + relationships +
    # evidence + events + locations + claims).
    from ..investigation_intelligence.data import compute_stage4_version
    answer.data["graph_version"] = compute_stage4_version(ctx.data)

    record_audit(db, current, "copilot.ask", resource_type="case",
                 resource_id=str(case.id),
                 metadata={"question": question[:_MAX_AUDIT_QUESTION],
                           "intent": parsed.intent,
                           "interpretation": parsed.interpretation[:300],
                           "status": answer.status,
                           "provider": answer.provider,
                           "fallback": answer.fallback,
                           "confidence": answer.confidence,
                           "citation_count": len(answer.citations)})
    return answer


def suggest_questions(ctx) -> list[str]:
    """Deterministic, data-driven follow-up questions for the UI."""
    d = ctx.data
    out: list[str] = []
    people = [e.canonical_name for e in d.entities if e.entity_type == "person"]
    if not people:
        people = [e.canonical_name for e in d.entities]
    if len(people) >= 2:
        out.append(f"How is {people[0]} connected to {people[1]}?")
    if people:
        out.append(f"Who is connected to {people[0]}?")
        out.append(f"Show the profile for {people[0]}")
    out.append("What happened?")
    if d.claims or d.evidence:
        out.append("What contradictions are there?")
    out.append("What is missing from the case?")
    if d.evidence:
        out.append(f"What is E{d.evidence[0].id}?")
        out.append(f"What happens if we remove E{d.evidence[0].id}?")
    out.append("What are the competing hypotheses?")
    out.append("Summarize the case")
    seen, res = set(), []
    for q in out:
        if q not in seen:
            seen.add(q)
            res.append(q)
    return res[:8]
