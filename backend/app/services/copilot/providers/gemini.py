"""Optional Gemini copilot provider — prose only, validated, honest.

Activation: ``GEMINI_API_KEY`` in the environment (backend-only; the key is
never sent to the frontend and never logged/audited). ``httpx`` is imported
lazily so the package works with no LLM dependency installed.

Division of labour (the no-hallucination contract):

* the **deterministic provider** always runs first — it produces the
  structured data, the citations and the confidence; those travel with the
  answer unchanged, whatever the LLM writes;
* the **model** only rewrites the *prose* from a bounded context (question,
  interpretation, structured data, citation list — a few KB, never the
  database or the graph);
* every model output is validated before it is served:
    1. it must be plain prose (length-bounded, no markup);
    2. **citation guard** — no evidence ids (``E12``) or entity ids appear
       that are not in the retrieved citation set;
    3. **name guard** — no capitalized names appear that are not a case
       entity name/alias, a citation label, part of the question, or a
       documented generic term;
    4. **neutral-language guard** — no words asserting guilt or certainty
       ("proves", "guilty", "definitely", …);
* any failure (unconfigured, network error, timeout, validation) returns
  the deterministic answer with ``fallback=True`` — and the answer's
  ``provider`` field tells the truth about who wrote the prose.

The provider therefore never claims an LLM was used when it was not, and
never lets an LLM introduce a fact that has no confirmed record behind it.
"""

from __future__ import annotations

import json
import re

from ....core.config import get_settings
from .base import CopilotAnswer, CopilotProvider
from .deterministic import DeterministicProvider

MAX_PROSE_CHARS = 1200
GENERIC_TERMS = {
    "the", "a", "an", "and", "or", "but", "of", "in", "on", "at", "to",
    "for", "by", "with", "case", "evidence", "record", "confirmed",
    "investigation", "analysis", "graph", "network", "person", "people",
    "timeline", "contradiction", "hypothesis", "finding", "location",
    "claim", "document", "this", "that", "these", "those", "it", "its",
    "their", "our", "your", "you", "we", "i", "is", "are", "was", "were",
    "has", "have", "had", "no", "not", "only", "may", "might", "can",
    "could", "would", "should", "nexus", "copilot",
    "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "each", "any", "all", "both", "other", "another",
    "such", "per", "via", "about", "across", "along", "among", "toward",
    "towards", "up", "down", "out", "off", "again", "further", "then",
    "once", "here", "there", "when", "where", "which", "who", "whom",
    "whose", "what", "how", "why", "if", "whether", "than", "too",
    "very", "just", "also", "even", "still", "yet", "now", "today",
    "yesterday", "tonight", "morning", "evening", "night", "afternoon",
    "am", "pm", "new", "same", "top", "first", "second", "third",
    "most", "few", "many", "near", "around", "before", "after", "since",
    "during", "within", "between", "over", "under", "high", "low",
    "recent", "latest", "primary", "direct", "indirect", "potential",
    "possible", "relevant", "linked", "cited", "recorded", "none",
    "source", "page", "type", "value", "time", "date", "count", "total",
    "score", "similarity", "semantic", "keyword", "hybrid", "cluster",
    "report", "statement", "reference", "nearby", "adjacent", "station",
    "area", "road", "street", "city", "town", "village", "vehicle",
    "phone", "call", "transfer", "payment", "account", "money",
    "incident", "sighting", "movement", "activity",
}
NEUTRALITY_BANNED = {
    "proves", "proven", "guilty", "guilt", "criminal", "convict",
    "definitely", "certainly", "obviously", "without doubt", "indisputably",
    "guaranteed", "beyond dispute",
}
_EVID_RE = re.compile(r"\bE(\d+)\b")


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z']*", text)


class GeminiProvider(CopilotProvider):
    id = "gemini"
    name = "Gemini (LLM-assisted prose, validated)"

    def __init__(self):
        self._settings = get_settings()

    # ------------------------------------------------------------- config
    def configured(self) -> bool:
        return bool(self._settings.gemini_api_key)

    def status(self) -> dict:
        if self.configured():
            return {"id": self.id, "name": self.name, "active": True,
                    "reason": (f"Model “{self._settings.gemini_model}” "
                               "configured (env). Prose only — data, "
                               "citations and confidence are always "
                               "deterministic."),
                    "model": self._settings.gemini_model}
        return {"id": self.id, "name": self.name, "active": False,
                "reason": ("Not configured (GEMINI_API_KEY empty). The "
                           "copilot runs fully deterministic — an honest, "
                           "offline mode, not a failure."),
                "model": None}

    # ------------------------------------------------------------- answer
    def answer(self, ctx, intent) -> CopilotAnswer:
        base = DeterministicProvider().answer(ctx, intent)
        if not self.configured():
            base.provider = "deterministic"
            base.fallback = False
            return base
        if base.status not in ("answered",):
            # not_enough_data / unsupported / error: prose adds nothing and
            # could only introduce claims — keep the deterministic text.
            base.provider = "deterministic"
            base.fallback = True
            base.data["llm_note"] = ("Answer state “%s” — the model is "
                                     "skipped; deterministic text is "
                                     "authoritative." % base.status)
            return base

        try:
            prose = self._generate(ctx, intent, base)
        except Exception as exc:  # network/timeout/parse — honest fallback
            base.provider = "deterministic"
            base.fallback = True
            base.data["llm_note"] = (f"Gemini call failed ({type(exc).__name__}); "
                                     "deterministic answer served instead.")
            return base

        reason = self._validate(ctx, intent, base, prose)
        if reason is not None:
            base.provider = "deterministic"
            base.fallback = True
            base.data["llm_note"] = (f"Gemini output rejected ({reason}); "
                                     "deterministic answer served instead.")
            return base

        out = CopilotAnswer(**{**base.to_dict(),
                               "answer_text": prose.strip(),
                               "provider": "gemini", "fallback": False})
        out.citations = base.citations  # validated set, unchanged
        return out

    # ------------------------------------------------------------- prompt
    def _build_context(self, ctx, intent, base) -> str:
        cit_lines = [f"- {c.kind} {c.id}: {c.label}"
                     for c in base.citations[:25]]
        data = dict(base.data)
        # bound the structured payload so the prompt stays small
        payload = json.dumps(data, ensure_ascii=False, default=str)[:6000]
        return (
            "You are an assistant inside NEXUS, an investigative analysis "
            "tool. Rewrite the following pre-computed answer into clear, "
            "concise investigative prose. Rules: use ONLY the facts, "
            "numbers and record references given below; do not invent names, "
            "records, dates or conclusions; keep a neutral analytical tone "
            "(\"potential\", \"the records show\", \"insufficient data\"); "
            "never claim that any person is guilty or that any record is "
            "true or false. Keep evidence references in the exact form "
            "E<id>.\n\n"
            f"Question: {intent.interpretation}\n"
            f"Pre-computed structured data:\n{payload}\n"
            f"Cited records (the only ones you may mention):\n"
            + ("\n".join(cit_lines) if cit_lines else "- (none)") + "\n"
            f"Original deterministic text to reword:\n{base.answer_text}\n\n"
            "Rewritten answer (prose only, no headings, no markup, "
            f"under {MAX_PROSE_CHARS} characters):")

    def _generate(self, ctx, intent, base) -> str:
        import httpx  # lazy: no LLM dependency required offline

        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self._settings.gemini_model}:generateContent")
        body = {"contents": [{"parts": [{"text":
                 self._build_context(ctx, intent, base)}]}],
                "generationConfig": {"temperature": 0.2}}
        resp = httpx.post(
            url, params={"key": self._settings.gemini_api_key},
            json=body, timeout=self._settings.gemini_timeout_seconds)
        resp.raise_for_status()
        data = resp.json()
        parts = data.get("candidates", [{}])[0].get("content", {}) \
            .get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
        if not text.strip():
            raise ValueError("empty model response")
        return text[:MAX_PROSE_CHARS]

    # ------------------------------------------------------------- guard
    def _validate(self, ctx, intent, base, prose) -> str | None:
        low = prose.lower()
        for w in NEUTRALITY_BANNED:
            if w in low:
                return f"non-neutral language ({w!r})"
        if len(prose) > MAX_PROSE_CHARS:
            return "prose over length limit"

        allowed_evid = {c.id for c in base.citations if c.kind == "evidence"}
        for m in _EVID_RE.finditer(prose):
            if int(m.group(1)) not in allowed_evid:
                return f"unknown evidence reference E{m.group(1)}"

        allowed_names: set[str] = set(GENERIC_TERMS)
        for c in base.citations:
            allowed_names.update(w.lower() for w in _words(c.label))
        allowed_names.update(w.lower() for w in _words(intent.interpretation))
        # the deterministic answer is already validated — the model may
        # reuse any word it contains (proper nouns included)
        if base.answer_text:
            allowed_names.update(w.lower()
                                 for w in _words(base.answer_text))
        for e in ctx.data.entities:
            allowed_names.update(w.lower() for w in _words(e.canonical_name))
            for a in (ctx.data.entity_metadata.get(e.id, {}).get("aliases")
                      or []):
                if isinstance(a, str):
                    allowed_names.update(w.lower() for w in _words(a))

        tokens = re.findall(r"[A-Z][A-Za-z']+", prose)
        for tok in tokens:
            # sentence-initial generic words are fine; unknown proper
            # nouns are not.
            if tok.lower() in allowed_names:
                continue
            return f"unknown name {tok!r}"
        return None
