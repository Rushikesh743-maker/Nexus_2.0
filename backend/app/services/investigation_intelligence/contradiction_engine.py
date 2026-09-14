"""Contradiction engine (stage 4) — confirmed records only.

Detects situations where CONFIRMED records contain potentially
inconsistent information. The engine never declares a record false and
never resolves the conflict — it reports a "potential contradiction" with
the exact records and computed values behind it, for investigator review.

Implemented rules (each documented; no invented incompatibilities):

R1  TIMELINE_CONTRADICTION
    Two confirmed timeline events for the same confirmed entity, at two
    different confirmed locations with coordinates, where the time
    between them is SHORTER than the conservative minimum travel time
    (haversine distance / MAX_SPEED_KMH). Movement at or below the
    documented speed assumption would not reach.

R2  LOCATION_CONTRADICTION
    Same entity, two confirmed events at two different confirmed
    locations with coordinates at the IDENTICAL timestamp — overlapping
    location records that require investigator review.

R3  RELATIONSHIP_CONTRADICTION
    Mutual OWNS between the same two confirmed entities (A OWNS B and
    B OWNS A both confirmed) — a logically incompatible ownership state
    in the domain vocabulary. This is the only relationship rule: the
    domain model documents no further incompatible relationship states,
    and we do not invent them.

EVIDENCE_CONTRADICTION — implemented in stage 5 as rule R4 in
`claim_contradictions.py`, operating on STRUCTURED claims only
(`evidence_claim` rows). Free-text similarity remains excluded: comparing
prose would be guesswork, and the confirmed-data rule stands.

Insufficient data is not a contradiction: pairs lacking coordinates,
timestamps or entity attribution are reported in `insufficient_pairs`
and never become findings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .data import Stage4Data

MAX_SPEED_KMH = 100.0      # documented conservative upper movement speed
MAX_PAIRS_PER_ENTITY = 10  # bounded comparisons
MAX_CONTRADICTIONS = 15    # per-case cap


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km (deterministic, documented)."""
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass
class ContradictionResult:
    contradiction_type: str
    title: str
    summary: str
    explanation: list[str]
    severity: str                      # LOW | MEDIUM | HIGH (analytical, documented)
    involved_entity_ids: list[int] = field(default_factory=list)
    involved_relationship_ids: list[int] = field(default_factory=list)
    supporting_evidence_ids: list[int] = field(default_factory=list)
    timeline_event_ids: list[int] = field(default_factory=list)
    location_ids: list[int] = field(default_factory=list)
    details: dict = field(default_factory=dict)


def _location_with_coords(d: Stage4Data, location_id: int | None):
    if location_id is None:
        return None
    loc = next((l for l in d.locations if l.id == location_id), None)
    if loc is None or loc.latitude is None or loc.longitude is None:
        return None
    return loc


def detect_contradictions(d: Stage4Data) -> tuple[list[ContradictionResult], dict]:
    out: list[ContradictionResult] = []
    insufficient = {"pairs_skipped_no_coords": 0, "pairs_skipped_no_time": 0}

    # ------------------------------------------------- R1 + R2 (timeline)
    by_entity: dict[int, list] = {}
    for ev in d.dated_events:
        if ev.entity_id is not None:
            by_entity.setdefault(ev.entity_id, []).append(ev)

    for entity_id in sorted(by_entity):
        events = sorted(by_entity[entity_id], key=lambda e: (e.timestamp, e.id))
        pairs_checked = 0
        for i in range(len(events)):
            for j in range(i + 1, len(events)):
                if pairs_checked >= MAX_PAIRS_PER_ENTITY:
                    break
                pairs_checked += 1
                a, b = events[i], events[j]
                la = _location_with_coords(d, a.location_id)
                lb = _location_with_coords(d, b.location_id)
                if la is None or lb is None:
                    insufficient["pairs_skipped_no_coords"] += 1
                    continue
                if la.id == lb.id:
                    continue
                distance = haversine_km(la.latitude, la.longitude,
                                        lb.latitude, lb.longitude)
                delta_min = abs((b.timestamp - a.timestamp).total_seconds()) / 60.0
                travel_min = distance / MAX_SPEED_KMH * 60.0
                entity = d.entities_by_id.get(entity_id)
                name = entity.canonical_name if entity else f"entity {entity_id}"
                ev_ids = [a.id, b.id]
                loc_ids = [la.id, lb.id]
                ev_evidence = sorted({e for e in (a.evidence_id, b.evidence_id) if e})

                if delta_min == 0.0:
                    # R2 — identical timestamps at different places
                    out.append(ContradictionResult(
                        contradiction_type="LOCATION_CONTRADICTION",
                        title=f"Overlapping location records: {name}",
                        summary=(f"Confirmed records place {name} at "
                                 f"{la.name} and {lb.name} at the same "
                                 f"recorded time."),
                        explanation=[
                            f"Event {a.id} records {name} at {la.name} at "
                            f"{a.timestamp.isoformat()}.",
                            f"Event {b.id} records {name} at {lb.name} at "
                            f"{b.timestamp.isoformat()}.",
                            f"The two records share an identical timestamp "
                            f"and the locations are {distance:.1f} km apart "
                            f"(haversine).",
                            "Overlapping location records require "
                            "investigator review. The engine does not "
                            "determine which record is inaccurate."],
                        severity="HIGH",
                        involved_entity_ids=[entity_id],
                        supporting_evidence_ids=ev_evidence,
                        timeline_event_ids=ev_ids, location_ids=loc_ids,
                        details={"distance_km": round(distance, 3),
                                 "time_difference_min": 0,
                                 "events": {"a": a.id, "b": b.id},
                                 "locations": {"a": la.id, "b": lb.id}}))
                elif delta_min < travel_min:
                    # R1 — physically not reachable at the documented speed
                    margin = delta_min / travel_min if travel_min > 0 else 0.0
                    out.append(ContradictionResult(
                        contradiction_type="TIMELINE_CONTRADICTION",
                        title=f"Potential timeline contradiction: {name}",
                        summary=(f"Confirmed records place {name} at "
                                 f"{la.name} and {lb.name} "
                                 f"{delta_min:.0f} min apart — shorter than "
                                 f"the {travel_min:.0f} min minimum travel "
                                 f"time at {MAX_SPEED_KMH:.0f} km/h."),
                        explanation=[
                            f"Event {a.id} records {name} at {la.name} at "
                            f"{a.timestamp.isoformat()}.",
                            f"Event {b.id} records {name} at {lb.name} at "
                            f"{b.timestamp.isoformat()}.",
                            f"Distance {la.name} ↔ {lb.name}: "
                            f"{distance:.1f} km (haversine); minimum travel "
                            f"time at the documented {MAX_SPEED_KMH:.0f} "
                            f"km/h assumption: {travel_min:.0f} min.",
                            f"Recorded interval: {delta_min:.0f} min "
                            f"({margin:.0%} of the minimum travel time).",
                            "Potential timeline contradiction — the records "
                            "are not asserted to be false; possible "
                            "explanations (record inaccuracy, identity "
                            "attribution, faster movement) are left to "
                            "investigator review."],
                        severity="HIGH" if margin < 0.5 else "MEDIUM",
                        involved_entity_ids=[entity_id],
                        supporting_evidence_ids=ev_evidence,
                        timeline_event_ids=ev_ids, location_ids=loc_ids,
                        details={"distance_km": round(distance, 3),
                                 "time_difference_min": round(delta_min, 1),
                                 "min_travel_min": round(travel_min, 1),
                                 "margin": round(margin, 3),
                                 "events": {"a": a.id, "b": b.id},
                                 "locations": {"a": la.id, "b": lb.id}}))

    # ------------------------------------------------- R3 (mutual OWNS)
    rel_type_by_id = {r.id: r.relationship_type for r in d.relationships}
    seen: set[frozenset] = set()
    for (src, tgt), rel_ids in sorted(d.rels_by_pair.items()):
        if frozenset((src, tgt)) in seen:
            continue
        back_ids = d.rels_by_pair.get((tgt, src)) or []
        if not back_ids:
            continue
        seen.add(frozenset((src, tgt)))
        out_ids = [r for r in rel_ids if rel_type_by_id.get(r) == "OWNS"]
        back_out = [r for r in back_ids if rel_type_by_id.get(r) == "OWNS"]
        if not out_ids or not back_out:
            continue
        a = d.entities_by_id.get(src)
        b = d.entities_by_id.get(tgt)
        out.append(ContradictionResult(
            contradiction_type="RELATIONSHIP_CONTRADICTION",
            title=(f"Mutual ownership recorded: "
                   f"{a.canonical_name if a else src} ↔ "
                   f"{b.canonical_name if b else tgt}"),
            summary=("Confirmed relationships record both "
                     f"{a.canonical_name if a else src} OWNS "
                     f"{b.canonical_name if b else tgt} and the reverse — "
                     "a logically incompatible ownership state."),
            explanation=[
                f"Relationship {out_ids[0]} records "
                f"{a.canonical_name if a else src} OWNS "
                f"{b.canonical_name if b else tgt}.",
                f"Relationship {back_out[0]} records the reverse ownership "
                f"between the same two confirmed entities.",
                "In the domain vocabulary an entity cannot simultaneously "
                "own the same entity in both directions; the records "
                "require investigator review."],
            severity="MEDIUM",
            involved_entity_ids=[src, tgt],
            involved_relationship_ids=[out_ids[0], back_out[0]],
            timeline_event_ids=[], location_ids=[],
            details={"relationships": [out_ids[0], back_out[0]],
                     "entities": [src, tgt]}))

    out.sort(key=lambda c: (0 if c.severity == "HIGH" else 1, c.title))
    return out[:MAX_CONTRADICTIONS], insufficient

