"""
Explainable contradiction scoring.

The output of this module is never a bare percentage. Every number it returns
arrives with the terms that produced it, so an investigator can disagree with
the arithmetic rather than with an oracle.

What is being scored
--------------------
Not guilt, and not the truth of any statement. The quantity is *how well the
surviving evidence supports the recorded link*, before and after the
conflicting records are taken into account. The engine calls this an
**evidence-supported relationship confidence**; it carries no evidentiary or
legal meaning.

The formula
-----------
Each record contributes

    weight = reliability(source_type) x record_confidence x diminishing(k)

`reliability` is the prototype source weight from `config`. `diminishing(k)`
is 1/sqrt(k) for the k-th record drawn from the same source system: twenty
calls on one CDR are strongly correlated and are not twenty independent
confirmations, so the twentieth counts for about a fifth of the first.

    support_score       = sum of weights over supporting records
    contradiction_score = sum of weights over contradicting records
    contradiction_ratio = contradiction_score / (support + contradiction)

    adjusted = base x (1 - CONFIDENCE_IMPACT_CAP x contradiction_ratio)

The cap matters. Conflicting evidence weakens a conclusion, it does not delete
the evidence supporting it, so this engine can never drive a confidence to
zero — at most it removes CONFIDENCE_IMPACT_CAP of it.
"""

from __future__ import annotations

import math
from collections import defaultdict

from . import config


def record_weight(source_type: str, confidence: float, occurrence: int = 1) -> float:
    """Weight of one evidence record; `occurrence` is its 1-based rank within its source system."""
    base = config.reliability(source_type) * max(0.0, min(1.0, float(confidence)))
    if config.DIMINISHING_RETURNS and occurrence > 1:
        base /= math.sqrt(occurrence)
    return base


def score_side(records: list[dict]) -> tuple[float, list[dict]]:
    """
    Total weight of one side of the argument, plus a per-record breakdown.

    `records` are dicts carrying at least `source_type` and `confidence`.
    """
    counts: dict[str, int] = defaultdict(int)
    total = 0.0
    breakdown = []
    for r in records:
        st = r.get("source_type") or "inferred"
        counts[st] += 1
        k = counts[st]
        w = record_weight(st, r.get("confidence", 0.8), k)
        total += w
        breakdown.append({
            "source_id": r.get("source_id"),
            "record_id": r.get("record_id"),
            "source_type": st,
            "reliability": round(config.reliability(st), 3),
            "record_confidence": round(float(r.get("confidence", 0.8)), 3),
            "occurrence": k,
            "weight": round(w, 4),
        })
    return total, breakdown


def assess(base_confidence: float, supporting: list[dict],
           contradicting: list[dict]) -> dict:
    """
    Weigh both sides and return the confidence revision with its full working.

    `base_confidence` is the graph's existing edge confidence (0..1).
    """
    support, support_terms = score_side(supporting)
    contra, contra_terms = score_side(contradicting)
    denom = support + contra
    ratio = (contra / denom) if denom > 0 else 0.0
    base = max(0.0, min(1.0, float(base_confidence)))
    adjusted = base * (1 - config.CONFIDENCE_IMPACT_CAP * ratio)

    if ratio >= config.SEVERITY_HIGH_RATIO:
        severity = "high"
    elif ratio >= config.SEVERITY_MEDIUM_RATIO:
        severity = "medium"
    else:
        severity = "low"

    return {
        "support_score": round(support, 4),
        "contradiction_score": round(contra, 4),
        "contradiction_ratio": round(ratio, 4),
        "confidence_before": round(base, 4),
        "confidence_after": round(adjusted, 4),
        "confidence_delta": round(adjusted - base, 4),
        "severity": severity,
        "independent_supporting_sources": sorted({t["source_type"] for t in support_terms}),
        "independent_contradicting_sources": sorted({t["source_type"] for t in contra_terms}),
        "terms": {"supporting": support_terms, "contradicting": contra_terms},
        "formula": ("adjusted = base x (1 - "
                    f"{config.CONFIDENCE_IMPACT_CAP} x contradiction_ratio); "
                    "record weight = reliability x confidence / sqrt(k-th record "
                    "from that source system)"),
    }
