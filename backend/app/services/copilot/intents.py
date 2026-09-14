"""Copilot intents + deterministic question parser.

This upgrades the existing NLQ layer (``app/nlq.py``) into a case-scoped
copilot. It keeps the same contract and spirit as ``QueryParser`` — an
intent-based, deterministic parser that always returns an
``interpretation`` (a plain restatement of what it understood) so a wrong
reading is visible instead of silently producing a confident wrong answer —
but it resolves names against the *case's* confirmed entities (any script)
and adds the investigation intents (contradictions, gaps, hypotheses,
impact, search).

Twelve intents:

    case_overview        "summarize the case" / "what do we know"
    entity_profile       "show me <person>" / "<person>'s profile"
    relationship_path    "how is A connected to B"
    neighbourhood        "who is connected to A" / "A's network"
    timeline             "what happened to A" / "timeline of the case"
    contradictions       "what contradictions are there"
    gaps                 "what is missing / what data do we lack"
    hypotheses           "what are the competing hypotheses"
    evidence_lookup      "find evidence about A" / "what is E17"
    location_query       "where was A" / "what locations are recorded"
    impact_simulation    "what happens if we remove E17"   (simulator only)
    entity_search        "search for <term>" (multilingual, confirmed data)

Convention: ``E17`` (or ``evidence 17``) means evidence row id 17.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

HOPS = re.compile(r"within\s+(\d+)\s*(?:-|\s)?hops?", re.I)
EVID = re.compile(r"\bE(\d+)\b")
EVID_WORD = re.compile(r"\bevidence\s+(?:row\s+|id\s+|#)?(\d+)\b", re.I)
_SEARCH_PREFIX = re.compile(
    r"^\s*(please\s+)?(can you\s+|could you\s+|would you\s+)?\s*"
    r"(search for|search|find me|find|look up|look for|who is|is there)\s+",
    re.I)

# Multilingual intent anchors (high-precision forms in the supported
# scripts). Entity names resolve in any script via the case gazetteer,
# so only the verb/keyword anchors need per-language coverage; these are
# added to the English anchors in each intent rule.
_ML_RELATION = "\u091c\u094b\u0921\u0932\u0947|\u091c\u094b\u0921\u0923|\u091c\u0941\u0921\u093c\u093e|\u091c\u0941\u0921\u093c\u093f|\u091c\u094b\u0921\u093c\u0940|\u091c\u094b\u0921\u093c|\u0938\u0902\u092c\u0927|\u062c\u0691|\u0631\u0627\u0628\u0637\u06c1|\u062a\u0639\u0644\u0642"
_ML_TIMELINE = "\u0915\u093e\u092f \u0918\u0921\u0932\u0947|\u0915\u092f\u094d\u092f \u092b\u0941\u093e|\u06a9\u06cc\u0627 \u06c1\u0648\u0627"
_ML_CONTRA = "\u0935\u093f\u0938\u0902\u0917\u0924\u093f|\u0935\u093f\u0930\u094b\u0927\u093e\u092d\u093e\u0938|\u062a\u0636\u0627\u062f"
_ML_GAPS = "\u0917\u093e\u092b\u0933|\u0917\u0941\u092e|\u0631\u0627\u06cc\u0628"
_ML_HYP = "\u0917\u0943\u092b\u093f\u0924\u0915|\u0915\u0932\u094d\u092a\u0928\u093e|\u0645\u0641\u0631\u0648\u0636\u06c1"
_ML_OVERVIEW = "\u0938\u093e\u0930\u093e\u0902\u0936|\u0938\u0902\u0915\u094d\u0937\u0947\u092a|\u062e\u0644\u0627\u0635\u06c1"
_ML_LOCATION = "\u0920\u093f\u0915\u093e\u0923|\u0938\u094d\u0925\u093e\u0928|\u0645\u0642\u0627\u0645|\u0915\u0941\u0921\u094d\u092b\u0947|\u0915\u092b\u093e\u0902|\u06a9\u06c1\u0627\u069b"
_ML_EVIDENCE = "\u092a\u0941\u0930\u093e\u0935|\u0938\u093e\u0915\u094d\u0937|\u062b\u062d\u0628\u0648"
_ML_IMPACT = "\u0915\u093e\u092f \u0939\u094b\u0940\u0932|\u0915\u092f\u094d\u092f \u0939\u094b\u0917\u093e|\u06a9\u06cc\u0627 \u06c1\u0648\u06af\u0627"


def _search_term(t: str) -> str:
    """Strip a leading search verb and trailing punctuation to get the term
    the investigator actually wants to search for."""
    s = _SEARCH_PREFIX.sub("", t.strip())
    s = s.strip().strip("?!.\"'")
    return s or t.strip()


@dataclass
class Intent:
    intent: str
    interpretation: str
    params: dict = field(default_factory=dict)
    confidence: float = 0.9
    unresolved: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class CopilotQuestionParser:
    """Deterministic, case-scoped question parser (NLQ-layer upgrade)."""

    def __init__(self, ctx):
        self.ctx = ctx

    # ------------------------------------------------------------------
    def _names(self, text: str) -> list[tuple[str, str]]:
        """[(surface_form, canonical_name)] for confirmed entities, in
        reading order, first mention of each entity kept."""
        low = text.lower()
        hits: list[tuple[int, int, str, str]] = []
        # iterate over known surface forms (longest first) — canonical + aliases
        forms: list[tuple[str, str]] = []   # (surface, canonical)
        for e in self.ctx.data.entities:
            forms.append((e.canonical_name, e.canonical_name))
            for a in (self.ctx.data.entity_metadata.get(e.id, {}).get("aliases")
                      or []):
                if isinstance(a, str):
                    forms.append((a, e.canonical_name))
        for surf, canon in sorted(set(forms), key=lambda x: len(x[0]),
                                  reverse=True):
            s = surf.lower()
            if len(s) < 2:
                continue
            start = 0
            while True:
                i = low.find(s, start)
                if i < 0:
                    break
                # word-ish boundary: not part of a longer word run
                before = text[i - 1] if i > 0 else " "
                after = text[i + len(s)] if i + len(s) < len(text) else " "
                ok = not (before.isalnum() or after.isalnum())
                if ok and not any(hs < i + len(s) and i < he
                                  for hs, he, _, _ in hits):
                    hits.append((i, i + len(s), surf, canon))
                start = i + 1
        hits.sort()
        seen, out = set(), []
        for _, _, surf, canon in hits:
            if canon in seen:
                continue
            seen.add(canon)
            out.append((surf, canon))
        return out

    def _evidence_id(self, text: str) -> int | None:
        m = EVID.search(text) or EVID_WORD.search(text)
        return int(m.group(1)) if m else None

    # ------------------------------------------------------------------
    def parse(self, text: str) -> Intent:
        """Parse a question, then stamp the question's language so the
        provider can answer in the investigator's language (stage-5
        multilingual QA). English/undetectable -> 'en' (the canonical
        layer)."""
        intent = self._parse(text)
        try:
            from ..language.detect import detect_question_language

            intent.params["question_language"] = detect_question_language(text)
        except Exception:  # noqa: BLE001 — detection must never break parse
            intent.params.setdefault("question_language", "en")
        return intent

    def _parse(self, text: str) -> Intent:
        t = text.strip()
        low = t.lower()
        names = self._names(t)
        hops = int(HOPS.search(t).group(1)) if HOPS.search(t) else None
        eid = self._evidence_id(t)

        def nm(i: int) -> str | None:
            return names[i][1] if len(names) > i else None

        # 1. impact simulation (E-id + what-if verbs) — most specific first
        if eid is not None and re.search(
                r"impact|remove|remov|reclassif|discard|lose|without|what if|"
                r"what happens|simulat|"+ _ML_IMPACT, low):
            return Intent(
                "impact_simulation",
                f"Simulate removing evidence {eid} from the confirmed graph "
                "(simulation only — nothing is changed)",
                {"evidence_id": eid}, 0.86)

        # 1b. any other question about a specific E-id → evidence lookup
        if eid is not None:
            return Intent("evidence_lookup",
                          f"Describe evidence record {eid}",
                          {"evidence_id": eid}, 0.85)

        # 2. relationship path (two names + connection verbs)
        if len(names) >= 2 and re.search(
                r"connect|link|relation|path|between|associated with|"
                r"how (is|are)|"+ _ML_RELATION, low):
            return Intent(
                "relationship_path",
                f"Find how {names[0][1]} is connected to {names[1][1]}"
                + (f", within {hops} hops" if hops else ""),
                {"a": names[0][1], "b": names[1][1], "cutoff": hops or 5}, 0.9)

        # 3. neighbourhood
        if names and re.search(
                r"connected to|linked to|associates|around|network of|"
                r"neighbou?rhood|who.*(with|near)|"+ _ML_RELATION, low):
            return Intent(
                "neighbourhood",
                f"Show everyone connected to {names[0][1]} "
                f"within {hops or 2} hops",
                {"node": names[0][1], "hops": hops or 2}, 0.85)

        # 4. contradictions
        if re.search(r"contradiction|inconsisten|conflict|discrepan|clash|"+ _ML_CONTRA, low):
            return Intent("contradictions",
                          "List the potential contradictions detected in the "
                          "confirmed records", {}, 0.88)

        # 4. explicit profile request — the target may be unconfirmed; the
        #    provider then answers honestly (unsupported). Placed before the
        #    thematic rules so "profile for X" is not swallowed by a keyword.
        pm = re.search(r"profile\s+(?:of|for)\s+(.+?)(?:[?!.]|$)", low)
        if pm and not re.search(
                r"connect|link|path|between|evidence|search|who\b|timeline",
                pm.group(1)):
            target = pm.group(1).strip().strip(", ")
            return Intent("entity_profile", f"Show the profile for {target}",
                          {"node": target}, 0.75)
        sm = re.search(r"show\s+(?:me\s+)?(?!everyone)(.+?)(?:[?!.]|$)", low)
        if sm and not re.search(
                r"connect|link|path|between|evidence|search|who\b|timeline|"
                r"location|profile|every|all|me\b", sm.group(1)):
            target = sm.group(1).strip().strip(", ")
            if 1 < len(target.split()) <= 4:
                return Intent("entity_profile",
                              f"Show the profile for {target}",
                              {"node": target}, 0.6)

        # 5. gaps
        if re.search(r"\bgap|missing|lack|insufficient|data (we )?need|"+ _ML_GAPS, low):
            return Intent("gaps",
                          "List the investigation gaps — where the confirmed "
                          "data is insufficient", {}, 0.86)

        # 6. hypotheses
        if re.search(r"hypothes|explanation|competing|theory|rebuttal|alternativ|"+ _ML_HYP,
                     low):
            return Intent("hypotheses",
                          "List the competing hypotheses with their "
                          "deterministic scores", {}, 0.87)

        # 7. timeline
        if re.search(r"timeline|chronolog|sequence|what happened|when |"
                     r"order of events|events|"+ _ML_TIMELINE, low):
            return Intent("timeline",
                          f"Show the timeline"
                          + (f" for {names[0][1]}" if names else " of the case"),
                          {"node": names[0][1] if names else None}, 0.84)

        # 8. evidence lookup
        if re.search(r"evidence|prove|support|cite|source|document|"+ _ML_EVIDENCE, low):
            if eid is not None:
                return Intent("evidence_lookup",
                              f"Describe evidence record {eid}",
                              {"evidence_id": eid}, 0.85)
            return Intent("evidence_lookup",
                          "Find evidence"
                          + (f" about {names[0][1]}" if names else
                             " in the case"),
                          {"node": names[0][1] if names else None}, 0.8)

        # 9. location query
        if re.search(r"where|location|place|locat|geograph|mov|"+ _ML_LOCATION, low):
            return Intent("location_query",
                          f"Show locations"
                          + (f" recorded for {names[0][1]}" if names else
                             " in the case"),
                          {"node": names[0][1] if names else None}, 0.82)

        # 10. case overview
        if re.search(r"summar|overview|outline|big picture|what do we (know|"
                     r"have)|case (so far|status)|brief me|recap|state of|"+ _ML_OVERVIEW, low):
            return Intent("case_overview", "Summarize the case so far", {}, 0.83)

        # 11. counts / overview (numeric)
        if re.search(r"how (many|much)|count|total|number of", low):
            return Intent("case_overview",
                          "Report the confirmed-record counts for the case",
                          {}, 0.8)

        # 12. entity profile (single named entity)
        if names:
            return Intent("entity_profile",
                          f"Show the profile for {names[0][1]}",
                          {"node": names[0][1]}, 0.7)

        # 13. entity search (free term, multilingual)
        if re.search(r"search|find|look up|who is", low):
            return Intent("entity_search",
                          f"Search confirmed records for “{_search_term(t)}”",
                          {"query": _search_term(t)}, 0.6)

        # fallback: treat as a search over the whole question
        return Intent("entity_search",
                      f"Search confirmed records for “{_search_term(t)}”",
                      {"query": _search_term(t)}, 0.5,
                      unresolved=[w for w in re.findall(r"[A-Z][a-z]{3,}", t)])
