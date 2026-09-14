"""Copilot providers: the deterministic engine (always) and the optional,
validated Gemini prose provider."""

from __future__ import annotations

from .base import Citation, CopilotAnswer, CopilotProvider, ProviderStatus
from .deterministic import DeterministicProvider
from .gemini import GeminiProvider

__all__ = [
    "Citation", "CopilotAnswer", "CopilotProvider", "ProviderStatus",
    "DeterministicProvider", "GeminiProvider",
]
