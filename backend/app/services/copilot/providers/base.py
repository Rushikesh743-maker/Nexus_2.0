"""Provider contract for the investigator copilot.

Two provider families share this contract:

* ``DeterministicProvider`` — always available, offline, never fabricates.
  It computes every number from confirmed case records and returns typed,
  cited answers. This is the source of truth for claims, citations and
  confidence, *always* — even when a language model is present.

* ``GeminiProvider`` — optional (env-configured). It may write the
  *prose* of an answer, but it can never invent data: its output is
  validated (citations must be a subset of the retrieved context, names
  must exist in the case, language must stay neutral) and any violation
  falls back to the deterministic provider. It is never claimed to have
  been used when it was not.

The no-hallucination guarantee lives here: a provider answers from a
``CaseContext`` (retrieved, confirmed records) and every record it
mentions must appear in ``answer.citations``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict


@dataclass
class Citation:
    """A validated reference to a record that exists in the case.

    ``record`` is a minimal, read-only snapshot of the fields the answer
    actually uses, so the UI can render a citation card without a second
    round-trip and an audit trail of *what* was cited.
    """
    kind: str            # entity|relationship|evidence|finding|hypothesis|event|location|claim
    id: int
    label: str
    record: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "id": self.id, "label": self.label,
                "record": self.record}


@dataclass
class CopilotAnswer:
    """The provider-agnostic result of a copilot question.

    ``answer_text`` is the prose a human reads. For the deterministic
    provider it is generated from the structured ``data`` payload with a
    fixed, neutral template (no language model). ``confidence`` and
    ``confidence_basis`` are computed per intent from retrieved data —
    never invented.
    """
    intent: str
    interpretation: str
    status: str = "answered"        # answered|not_enough_data|unsupported|error
    answer_text: str | None = None
    confidence: float = 0.0
    confidence_basis: str = ""
    citations: list[Citation] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    provider: str = "deterministic"
    fallback: bool = False
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["citations"] = [c.to_dict() for c in self.citations]
        return d


class ProviderStatus:
    """What the frontend can truthfully say about the active provider."""
    __slots__ = ("id", "name", "active", "reason")

    def __init__(self, id: str, name: str, active: bool, reason: str):
        self.id = id
        self.name = name
        self.active = active
        self.reason = reason

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name,
                "active": self.active, "reason": self.reason}


class CopilotProvider(ABC):
    """A provider answers one parsed intent against one CaseContext."""

    #: stable identifier reported in answers + status + audit
    id: str = "base"
    #: human-readable name
    name: str = "base"

    @abstractmethod
    def answer(self, ctx, intent) -> CopilotAnswer:
        """Return a CopilotAnswer for `intent` against `ctx`.

        Implementations must only reference records present in `ctx` and
        must cite every record they mention.
        """
        raise NotImplementedError
