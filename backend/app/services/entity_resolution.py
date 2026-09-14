"""Entity resolution: candidate -> existing entity match suggestions.

Deliberately conservative and explainable. Every suggestion carries the
exact checks that fired (the ``reasons`` list); nothing is suggested
without a data-supported reason, and nothing is merged without an
explicit investigator decision.

Scoring (documented, deterministic):

* 1.00   normalized names identical — including cross-script identity
         after transliteration (stage 5: "राजेश कुमार" normalizes to the
         same matching key as "Rajesh Kumar")
* 0.82   initial + shared tokens: one side writes a name initial ("R.
         Kumar", "Rajesh K.") where the other writes the full word, with
         the remaining tokens identical (the initial may sit at any token
         position, not only the first — stage 5)
* 0.75   near-phonetic: all tokens identical except one pair within edit
         distance 1 (length >= 3) — transliteration/spelling variants
         such as "rav" ~ "rao" (stage 5)
* 0.55+  shared-name-token overlap (Jaccard >= 0.5), scaled 0.55..0.90

Only same-type entities are compared. One best suggestion per candidate
(similarity >= 0.55). All rules run on the multilingual matching key
(transliterated, diacritic-free, casefolded) so Latin, Devanagari and
Urdu surface forms of the same name compare directly.
"""

from __future__ import annotations

import re

from .language import normalize_for_match as _ml_norm


_DIGIT_RE = re.compile(r"\d")


def normalize(name: str) -> str:
    """Legacy Latin normalization (kept for candidate dedup keys)."""
    return re.sub(r"\s+", " ", (name or "").strip().casefold()).strip(".")


def normalize_multilingual(name: str) -> str:
    """Script-aware matching key (see the language module)."""
    return _ml_norm(name)


def _has_non_latin(text: str) -> bool:
    return any(ord(c) > 0x2FF for c in (text or ""))


def _tokens(name: str) -> list[str]:
    return [t for t in normalize_multilingual(name).split(" ") if t]


def _initial(name: str) -> str:
    return name[:1] if name else ""


def _edit_distance_le1(a: str, b: str) -> bool:
    """True when a and b differ by at most one insertion/deletion/substitution."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(1 for x, y in zip(a, b) if x != y) <= 1
    short, long_ = sorted((a, b), key=len)
    i = j = skipped = 0
    while i < len(short) and j < len(long_):
        if short[i] == long_[j]:
            i += 1
            j += 1
        elif skipped:
            return False
        else:
            skipped = 1
            j += 1
    return True


def _initial_rule(ta: list[str], tb: list[str]) -> list[str] | None:
    """Generalized initial rule: one side uses a name initial where the
    other writes the full word; all remaining tokens must be identical."""
    if len(ta) != len(tb) or not ta:
        return None
    for i, (x, y) in enumerate(zip(ta, tb)):
        rest_a = ta[:i] + ta[i + 1:]
        rest_b = tb[:i] + tb[i + 1:]
        if rest_a != rest_b:
            continue
        if len(x) == 1 and len(y) >= 2 and x == _initial(y):
            return [
                "all other name tokens are identical",
                f"name initial matches ({x!r} ~ {y!r})",
            ]
        if len(y) == 1 and len(x) >= 2 and y == _initial(x):
            return [
                "all other name tokens are identical",
                f"name initial matches ({y!r} ~ {x!r})",
            ]
    return None


def _near_phonetic_rule(ta: list[str], tb: list[str]) -> list[str] | None:
    """One token pair within edit distance 1 (length >= 3), rest identical."""
    if len(ta) != len(tb) or not ta:
        return None
    diffs = [(i, x, y) for i, (x, y) in enumerate(zip(ta, tb)) if x != y]
    if len(diffs) == 1 and min(len(diffs[0][1]), len(diffs[0][2])) >= 3 \
            and _edit_distance_le1(diffs[0][1], diffs[0][2]):
        _, x, y = diffs[0]
        return [
            "all other name tokens are identical",
            (f"near-phonetic token match (1 edit): {x!r} ~ {y!r} — likely a "
             "transliteration or spelling variant"),
        ]
    return None


def score_pair(candidate_name: str, existing_name: str) -> tuple[float, list[str]]:
    """Return (similarity, reasons). reasons is empty when similarity < 0.55.

    Only reasons actually supported by the data are emitted.
    """
    a, b = normalize_multilingual(candidate_name), normalize_multilingual(existing_name)
    if not a or not b:
        return 0.0, []
    # Identifiers (phone numbers, accounts, vehicle registrations, case
    # references) are EXACT tokens: the fuzzy name rules below are for
    # human names, and one digit of difference is a different identifier,
    # not a typo of the same one. Exact matches still score 1.0 below.
    if _DIGIT_RE.search(a) or _DIGIT_RE.search(b):
        if a != b:
            return 0.0, []
    if a == b:
        if _has_non_latin(candidate_name) != _has_non_latin(existing_name):
            return 1.0, [
                "cross-script transliteration match: identical after "
                f"normalization ({normalize_multilingual(candidate_name)!r})",
            ]
        return 1.0, ["normalized names are identical"]

    ta, tb = _tokens(candidate_name), _tokens(existing_name)
    if not ta or not tb:
        return 0.0, []

    reasons = _initial_rule(ta, tb)
    if reasons:
        return 0.82, reasons

    reasons = _near_phonetic_rule(ta, tb)
    if reasons:
        return 0.75, reasons

    # Token overlap
    sa, sb = set(ta), set(tb)
    inter = sa & sb
    union = sa | sb
    if inter and union:
        jaccard = len(inter) / len(union)
        if jaccard >= 0.5:
            shared = ", ".join(sorted(inter))
            return 0.55 + 0.35 * jaccard, [
                f"shares name token(s): {shared}",
                f"{len(inter)} of {len(union)} name tokens in common",
            ]
    return 0.0, []


def best_match(candidate_name: str,
               existing_names: list[str]) -> tuple[str | None, float, list[str]]:
    """Best-scoring existing name for a candidate (or None below threshold)."""
    ranked = ranked_matches(candidate_name, existing_names, top_k=1)
    return (ranked[0][0], ranked[0][1], ranked[0][2]) if ranked \
        else (None, 0.0, [])


def ranked_matches(candidate_name: str,
                   existing_names: list[str],
                   top_k: int = 3) -> list[tuple[str, float, list[str]]]:
    """All existing names worth showing as suggestions, best first.

    Every entry has (name, similarity, reasons) with similarity >= 0.55;
    at most ``top_k`` entries, sorted by similarity (ties broken by name
    for determinism). Suggestions only — the investigator decides.
    """
    scored: list[tuple[str, float, list[str]]] = []
    seen: set[str] = set()
    for name in existing_names:
        key = normalize_multilingual(name)
        if not key or key in seen:
            continue
        seen.add(key)
        sim, reasons = score_pair(candidate_name, name)
        if sim >= 0.55:
            scored.append((name, sim, reasons))
    scored.sort(key=lambda t: (-t[1], t[0].casefold()))
    return scored[:max(1, top_k)]


# Phase 2: contextual signals. These compare ASSOCIATED identifiers of the
# candidate (from its document's relationship candidates) with those of an
# existing entity (from confirmed relationships). Deterministic, documented,
# and each bonus emits a human-readable reason — never a silent boost.
CONTEXT_BONUS = {
    "phone": 0.20,
    "vehicle": 0.20,
    "account": 0.15,
    "email": 0.15,
    "location": 0.10,
}


def contextual_signals(cand_assoc: dict[str, set],
                       entity_assoc: dict[str, set]) -> tuple[float, list[str]]:
    """Shared-identifier bonus between a candidate and an existing entity.

    ``cand_assoc`` / ``entity_assoc`` map kind (phone | vehicle | account |
    email | location) to the SET of identifiers on each side. Returns
    (total_bonus, reasons). The caller must cap the final similarity below
    1.0 — context never turns an unconfirmed match into a certain one.
    """
    bonus = 0.0
    reasons: list[str] = []
    for kind in ("phone", "vehicle", "account", "email", "location"):
        shared = {x for x in (cand_assoc.get(kind) or set())
                  if x and x in (entity_assoc.get(kind) or set())}
        if shared:
            bonus += CONTEXT_BONUS[kind]
            shown = ", ".join(sorted(shared)[:3])
            label = {"phone": "same phone number",
                     "vehicle": "same vehicle",
                     "account": "same account",
                     "email": "same email address",
                     "location": "overlapping location"}[kind]
            reasons.append(f"{label}: {shown}")
    return bonus, reasons


def combine_scores(name_sim: float, name_reasons: list[str],
                   ctx_bonus: float, ctx_reasons: list[str]) -> tuple[float, list[str]]:
    """Final suggestion score: name similarity + contextual bonus.

    Without context the name score stands as-is (an exact normalized name
    match is still 1.0). When context IS added the total is capped at
    0.99: contextual similarity can never present an unconfirmed match as
    certain.
    """
    total = min(0.99, name_sim + ctx_bonus) if ctx_bonus > 0 else name_sim
    reasons = list(name_reasons)
    if ctx_reasons:
        reasons.append("contextual signal — " + "; ".join(ctx_reasons))
    return total, reasons
