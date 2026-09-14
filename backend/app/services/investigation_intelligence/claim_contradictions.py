"""Evidence-contradiction engine (stage 5, rule R4) — confirmed claims only.

Stage 4 deliberately left EVIDENCE_CONTRADICTION unimplemented: free text
cannot be compared honestly. Stage 5 adds a **structured claim model**
(`evidence_claim`) — subject, predicate, object, time, location — extracted
by the multilingual pipeline and materialized only when the subject
candidate is accepted. Comparing two *structured* claims is legitimate;
comparing prose is not, so this engine never reads free text.

R4a  EVIDENCE_CONTRADICTION (spatial)
    Two confirmed claims with the same subject and predicate ``was_at``,
    both with event times and both resolving to DIFFERENT confirmed
    locations, whose times differ by at most TIME_TOLERANCE_MIN. Same
    entity, near-identical time, different confirmed locations.

R4b  EVIDENCE_CONTRADICTION (value)
    Two confirmed claims with the same subject and a non-spatial predicate
    (e.g. owns / called), both with event times within TIME_TOLERANCE_MIN,
    whose recorded objects differ (different confirmed entity, or different
    normalized value such as two different phone numbers).

Severity is analytical and documented: HIGH when the two times are within
NEAR_MIN of each other (near-simultaneous), otherwise MEDIUM.

Insufficient data is not a contradiction: pairs lacking a time on either
claim, or (for was_at) lacking a confirmed location on either claim, are
counted in `insufficient` and never become findings. Nothing here declares
a record false — a finding is a *potential* contradiction for review.
"""

from __future__ import annotations

import datetime as _dt
import re

from .contradiction_engine import (ContradictionResult, haversine_km,
                                   MAX_CONTRADICTIONS)
from .data import ClaimRecord, Stage4Data

_EPOCH = _dt.datetime.min.replace(tzinfo=_dt.timezone.utc)

TIME_TOLERANCE_MIN = 15.0   # "same time" window for claim comparison
NEAR_MIN = 5.0              # within this -> HIGH severity
MAX_PAIRS_PER_SUBJECT = 10  # bounded comparisons per (subject, predicate)


def _resolve_location(d: Stage4Data, c: ClaimRecord):
    """Resolve a claim's location to a CONFIRMED record.

    Returns (label, location_row_id). Resolution order:
      1. explicit location_id  -> confirmed location row (seeded data);
      2. object_entity_id      -> confirmed location entity (extracted
         locations are confirmed entities; coordinates live on the
         location row only for seeded data);
      3. normalized value match against location rows / location entities;
      4. the claim's own object value — a confirmed claim value is itself
         a confirmed record, so two different values are comparable even
         when no location entity was confirmed.
    """
    if c.location_id is not None:
        row = next((l for l in d.locations if l.id == c.location_id), None)
        if row is not None:
            return row.name, row.id
    if c.object_entity_id is not None:
        ent = d.entities_by_id.get(c.object_entity_id)
        if ent is not None:
            return ent.canonical_name, None
    if c.normalized_value:
        want = re.sub(r"\s+", " ", c.normalized_value).strip()
        row = next((l for l in d.locations
                    if re.sub(r"\s+", " ", l.name.casefold()).strip() == want),
                   None)
        if row is not None:
            return row.name, row.id
        ent = next((e for e in d.entities
                    if e.entity_type == "location"
                    and re.sub(r"\s+", " ",
                               e.canonical_name.casefold()).strip() == want),
                   None)
        if ent is not None:
            return ent.canonical_name, None
    if c.object_value:
        return c.object_value, None
    return None, None


def detect_claim_contradictions(d: Stage4Data):
    out: list[ContradictionResult] = []
    insufficient = {"pairs_skipped_no_time": 0, "pairs_skipped_no_location": 0}
    name_of = {e.id: e.canonical_name for e in d.entities}

    by_key: dict[tuple[int, str], list[ClaimRecord]] = {}
    for c in d.claims:
        if c.subject_entity_id is None:
            continue
        by_key.setdefault((c.subject_entity_id, c.predicate), []).append(c)

    for (subject_id, predicate), claims in sorted(by_key.items()):
        if len(claims) < 2:
            continue
        claims = sorted(claims, key=lambda c: (c.event_time or _EPOCH, c.id))
        subject = name_of.get(subject_id, f"entity {subject_id}")
        pairs_checked = 0
        for i in range(len(claims)):
            for j in range(i + 1, len(claims)):
                if pairs_checked >= MAX_PAIRS_PER_SUBJECT:
                    break
                pairs_checked += 1
                a, b = claims[i], claims[j]
                if a.event_time is None or b.event_time is None:
                    insufficient["pairs_skipped_no_time"] += 1
                    continue
                delta_min = abs((b.event_time - a.event_time).total_seconds()) / 60.0
                if delta_min > TIME_TOLERANCE_MIN:
                    continue

                if predicate == "was_at":
                    name_a, row_a = _resolve_location(d, a)
                    name_b, row_b = _resolve_location(d, b)
                    same = (bool(name_a) and bool(name_b)
                            and re.sub(r"\s+", " ", name_a.casefold()).strip()
                            == re.sub(r"\s+", " ", name_b.casefold()).strip())
                    if not name_a or not name_b or same:
                        insufficient["pairs_skipped_no_location"] += 1
                        continue
                    la = next((l for l in d.locations if l.id == row_a), None)
                    lb = next((l for l in d.locations if l.id == row_b), None)
                    dist = None
                    if la and lb and la.latitude is not None \
                            and lb.latitude is not None:
                        dist = haversine_km(la.latitude, la.longitude,
                                            lb.latitude, lb.longitude)
                    sev = "HIGH" if delta_min <= NEAR_MIN else "MEDIUM"
                    margin = round(1.0 - (delta_min / TIME_TOLERANCE_MIN), 3)
                    title = (f"Potential evidence contradiction: {subject} — "
                             f"{name_a} vs {name_b}")
                    out.append(ContradictionResult(
                        contradiction_type="EVIDENCE_CONTRADICTION",
                        title=title,
                        summary=(f"Two confirmed evidence claims place {subject} "
                                 f"at {name_a} and {name_b} "
                                 f"{delta_min:.0f} minute(s) apart." if dist is None
                                 else f"Two confirmed evidence claims place "
                                      f"{subject} at {name_a} and {name_b} "
                                      f"{dist:.1f} km apart "
                                      f"{delta_min:.0f} minute(s) apart."),
                        explanation=[
                            f"Evidence {a.evidence_id} claims {subject} was at "
                            f"{name_a} at {a.event_time.isoformat()}.",
                            f"Evidence {b.evidence_id} claims {subject} was at "
                            f"{name_b} at {b.event_time.isoformat()}.",
                            f"Same confirmed entity, near-identical time "
                            f"({delta_min:.0f} min apart), different confirmed "
                            f"locations." + (f" Distance {name_a} ↔ {name_b}: "
                                              f"{dist:.1f} km (haversine)."
                                              if dist is not None else ""),
                            "Potential evidence contradiction — both records "
                            "are preserved; the engine does not determine "
                            "which is accurate. Requires investigator review."],
                        severity=sev,
                        involved_entity_ids=[subject_id],
                        supporting_evidence_ids=sorted({a.evidence_id,
                                                        b.evidence_id}),
                        location_ids=[i for i in (row_a, row_b) if i],
                        details={"rule": "R4",
                                 "variant": "spatial",
                                 "time_difference_min": round(delta_min, 1),
                                 "distance_km": round(dist, 3) if dist else None,
                                 "margin": margin,
                                 "tolerance_min": TIME_TOLERANCE_MIN,
                                 "evidence": {"a": a.evidence_id,
                                              "b": b.evidence_id},
                                 "locations": {"a": row_a, "b": row_b,
                                               "names": {"a": name_a,
                                                         "b": name_b}},
                                 "claims": {"a": a.id, "b": b.id}}))
                else:
                    # R4b — non-spatial predicate, different recorded objects
                    obj_a = a.object_entity_id if a.object_entity_id is not None \
                        else a.normalized_value
                    obj_b = b.object_entity_id if b.object_entity_id is not None \
                        else b.normalized_value
                    if obj_a is None or obj_b is None or obj_a == obj_b:
                        continue
                    sev = "HIGH" if delta_min <= NEAR_MIN else "MEDIUM"
                    margin = round(1.0 - (delta_min / TIME_TOLERANCE_MIN), 3)
                    out.append(ContradictionResult(
                        contradiction_type="EVIDENCE_CONTRADICTION",
                        title=(f"Potential evidence contradiction: {subject} — "
                               f"{predicate} {obj_a} vs {obj_b}"),
                        summary=(f"Two confirmed evidence claims record the "
                                 f"same subject and predicate ({predicate}) "
                                 f"with different objects within "
                                 f"{delta_min:.0f} minute(s)."),
                        explanation=[
                            f"Evidence {a.evidence_id} records "
                            f"{subject} {predicate} {obj_a} at "
                            f"{a.event_time.isoformat()}.",
                            f"Evidence {b.evidence_id} records "
                            f"{subject} {predicate} {obj_b} at "
                            f"{b.event_time.isoformat()}.",
                            "Same confirmed entity and predicate, near-"
                            "identical time, different recorded objects.",
                            "Potential evidence contradiction — requires "
                            "investigator review."],
                        severity=sev,
                        involved_entity_ids=[subject_id],
                        supporting_evidence_ids=sorted({a.evidence_id,
                                                        b.evidence_id}),
                        details={"rule": "R4", "variant": "value",
                                 "predicate": predicate,
                                 "time_difference_min": round(delta_min, 1),
                                 "margin": margin,
                                 "tolerance_min": TIME_TOLERANCE_MIN,
                                 "evidence": {"a": a.evidence_id,
                                              "b": b.evidence_id},
                                 "claims": {"a": a.id, "b": b.id}}))
    out.sort(key=lambda c: (0 if c.severity == "HIGH" else 1, c.title))
    return out[:MAX_CONTRADICTIONS], insufficient
