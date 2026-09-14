"""Investigator copilot (stage 5).

A case-scoped, no-hallucination question-answering layer that upgrades the
deterministic NLQ parser into a copilot. It answers only from CONFIRMED
case records, cites every record it mentions, computes confidence from
retrieved data, and offers an optional, validated LLM prose provider
(Gemini) that can never introduce a fact without a confirmed record.

Public surface:
    load_case_context  build the confirmed case context
    ask_case           answer one question (provider chain + audit)
    provider_status    what providers are active (honest)
    suggest_questions  deterministic follow-up suggestions
"""

from __future__ import annotations

from .context import CaseContext, load_case_context
from .intents import CopilotQuestionParser, Intent
from .providers import (Citation, CopilotAnswer, CopilotProvider,
                        DeterministicProvider, GeminiProvider)
from .service import ask_case, provider_status, suggest_questions

__all__ = [
    "CaseContext", "load_case_context",
    "CopilotQuestionParser", "Intent",
    "Citation", "CopilotAnswer", "CopilotProvider",
    "DeterministicProvider", "GeminiProvider",
    "ask_case", "provider_status", "suggest_questions",
]
