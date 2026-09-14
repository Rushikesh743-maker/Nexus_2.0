"""Timeline intelligence (stage 4) — confirmed timeline events only.

Deterministic patterns over the case's confirmed `timeline_event` rows
(events without timestamps are counted and reported, never guessed at):

EVENT_OVERLAP
    Two confirmed events sharing the same timestamp. If both are
    attributed to the same confirmed entity they overlap for that entity;
    if NEITHER is attributed, they are reported as concurrent case-level
    records (stated explicitly — no entity link is implied).

TEMPORAL_PROXIMITY
    Two confirmed events for the same confirmed entity with
    0 < interval <= PROXIMITY_MINUTES.

EVENT_SEQUENCE
    The most active attributed entity (>= 3 dated events; ties by id) —
    its events in chronological order with the computed intervals between
    consecutive events.

TIMELINE_GAP
    Consecutive confirmed events (case-level chronological order) with a
    gap greater than GAP_HOURS on both sides — reported as "potential
    investigation gap". A gap is never described as suspicious.

Every result carries event ids, entity ids, time values, the computed
interval, the analysis method and a deterministic explanation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .data import Stage4Data

PROXIMITY_MINUTES = 30.0   # documented proximity window
GAP_HOURS = 12.0           # documented "notable" gap threshold
MAX_SEQUENCE_EVENTS = 6    # bounded sequence length
MAX_TIMELINE_FINDINGS = 15 # per-case cap for overlap+proximity results


@dataclass
class TimelineResult:
    timeline_type: str
    title: str
    summary: str
    explanation: list[str]
    event_ids: list[int] = field(default_factory=list)
    entity_ids: list[int] = field(default_factory=list)
    interval_minutes: float | None = None
    details: dict = field(default_factory=dict)


METHOD = ("timeline-analysis v1 (confirmed timeline_event rows; "
          "overlap = identical timestamps, proximity <= "
          f"{PROXIMITY_MINUTES:.0f} min, gap > {GAP_HOURS:.0f} h)")


def _fmt(ts: datetime) -> str:
    return ts.isoformat()


def _event_name(d: Stage4Data, ev) -> str:
    ent = d.entities_by_id.get(ev.entity_id) if ev.entity_id else None
    who = ent.canonical_name if ent else None
    base = f"{who} — {ev.event_type}" if who else ev.event_type
    if ev.description:
        base = f"{base}: {ev.description[:80]}"
    return base


def analyze_timeline(d: Stage4Data) -> tuple[list[TimelineResult], dict]:
    events = sorted(d.dated_events, key=lambda e: (e.timestamp, e.id))
    meta = {
        "events_total": len(d.events),
        "events_with_timestamp": len(events),
        "events_without_timestamp": len(d.events) - len(events),
        "insufficient": len(events) < 2,
    }
    if len(events) < 2:
        return [], meta

    out: list[TimelineResult] = []

    # --------------------------------------------- EVENT_OVERLAP
    by_time: dict[datetime, list] = {}
    for ev in events:
        by_time.setdefault(ev.timestamp, []).append(ev)
    for ts in sorted(by_time):
        group = sorted(by_time[ts], key=lambda e: e.id)
        if len(group) < 2:
            continue
        shared_entity = None
        if all(e.entity_id is not None for e in group) \
                and len({e.entity_id for e in group}) == 1:
            shared_entity = group[0].entity_id
        elif all(e.entity_id is None for e in group):
            shared_entity = None  # case-level concurrency, stated as such
        else:
            # mixed attribution — report per pair only when same entity
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    if group[i].entity_id is not None and \
                            group[i].entity_id == group[j].entity_id:
                        _emit_overlap(out, d, group[i], group[j],
                                      group[i].entity_id)
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                _emit_overlap(out, d, group[i], group[j], shared_entity)

    # ------------------------------------------ TEMPORAL_PROXIMITY
    by_entity: dict[int, list] = {}
    for ev in events:
        if ev.entity_id is not None:
            by_entity.setdefault(ev.entity_id, []).append(ev)
    for entity_id in sorted(by_entity):
        evs = by_entity[entity_id]
        pairs = []
        for i in range(len(evs)):
            for j in range(i + 1, len(evs)):
                dt = abs((evs[j].timestamp - evs[i].timestamp).total_seconds()) / 60.0
                if 0 < dt <= PROXIMITY_MINUTES:
                    pairs.append((dt, evs[i], evs[j]))
        pairs.sort(key=lambda p: (p[0], p[1].id, p[2].id))
        for dt, a, b in pairs[:3]:  # top-3 closest per entity
            name = d.entities_by_id[entity_id].canonical_name
            out.append(TimelineResult(
                timeline_type="TEMPORAL_PROXIMITY",
                title=f"Temporal proximity: {name}",
                summary=(f"{name}: two confirmed events "
                         f"{dt:.0f} min apart "
                         f"({a.timestamp.strftime('%H:%M')} → "
                         f"{b.timestamp.strftime('%H:%M')})."),
                explanation=[
                    f"Event {a.id} ({a.event_type}) at {_fmt(a.timestamp)}.",
                    f"Event {b.id} ({b.event_type}) at {_fmt(b.timestamp)}.",
                    f"Interval {dt:.0f} min <= documented "
                    f"{PROXIMITY_MINUTES:.0f} min proximity window.",
                    "Temporal proximity is an analytical observation, not "
                    "an inference of intent."],
                event_ids=[a.id, b.id], entity_ids=[entity_id],
                interval_minutes=round(dt, 1),
                details={"window_minutes": PROXIMITY_MINUTES,
                         "events": {"a": a.id, "b": b.id}}))

    # --------------------------------------------- EVENT_SEQUENCE
    if by_entity:
        focal_id = max(by_entity, key=lambda k: (len(by_entity[k]), -k))
        if len(by_entity[focal_id]) >= 3:
            name = d.entities_by_id[focal_id].canonical_name
            seq = by_entity[focal_id][:MAX_SEQUENCE_EVENTS]
            intervals = [
                round((b.timestamp - a.timestamp).total_seconds() / 60.0, 1)
                for a, b in zip(seq, seq[1:])]
            out.append(TimelineResult(
                timeline_type="EVENT_SEQUENCE",
                title=f"Event sequence: {name}",
                summary=(f"{len(seq)} confirmed events involving {name}, "
                         f"{seq[0].timestamp.strftime('%Y-%m-%d %H:%M')} → "
                         f"{seq[-1].timestamp.strftime('%Y-%m-%d %H:%M')}."),
                explanation=[
                    f"Chronological sequence of the {len(seq)} confirmed "
                    f"events attributed to {name}:"
                    + " | ".join(
                        f"{e.timestamp.strftime('%Y-%m-%d %H:%M')} "
                        f"{e.event_type}" for e in seq),
                    "Intervals between consecutive events: "
                    + (", ".join(f"{x:.0f} min" for x in intervals)
                       if intervals else "n/a"),
                    "Sequence is descriptive (confirmed order), not "
                    "causal."],
                event_ids=[e.id for e in seq], entity_ids=[focal_id],
                interval_minutes=round(
                    (seq[-1].timestamp - seq[0].timestamp).total_seconds() / 60.0, 1),
                details={"intervals_minutes": intervals,
                         "max_events": MAX_SEQUENCE_EVENTS}))

    # --------------------------------------------- TIMELINE_GAP
    gaps: list[tuple[float, int, int]] = []
    for a, b in zip(events, events[1:]):
        gap_h = (b.timestamp - a.timestamp).total_seconds() / 3600.0
        if gap_h > GAP_HOURS:
            gaps.append((gap_h, a.id, b.id))
    gaps.sort(key=lambda g: (-g[0], g[1]))
    for gap_h, a_id, b_id in gaps[:5]:
        a = next(e for e in events if e.id == a_id)
        b = next(e for e in events if e.id == b_id)
        out.append(TimelineResult(
            timeline_type="TIMELINE_GAP",
            title="Potential investigation gap",
            summary=(f"No confirmed activity recorded between "
                     f"{a.timestamp.strftime('%Y-%m-%d %H:%M')} (event "
                     f"{a.id}) and {b.timestamp.strftime('%Y-%m-%d %H:%M')} "
                     f"(event {b.id}) — a {gap_h / 24:.1f} day gap."),
            explanation=[
                f"Last confirmed event before the gap: {a.id} "
                f"({_event_name(d, a)}) at {_fmt(a.timestamp)}.",
                f"Next confirmed event: {b.id} ({_event_name(d, b)}) at "
                f"{_fmt(b.timestamp)}.",
                f"Gap of {gap_h:.1f} h exceeds the documented "
                f"{GAP_HOURS:.0f} h threshold.",
                "This is a potential investigation gap — it describes "
                "coverage of the confirmed record, not suspicious "
                "activity."],
            event_ids=[a_id, b_id],
            entity_ids=[x for x in (a.entity_id, b.entity_id) if x],
            interval_minutes=round(gap_h * 60.0, 1),
            details={"gap_hours": round(gap_h, 2),
                     "threshold_hours": GAP_HOURS,
                     "events": {"before": a_id, "after": b_id}}))

    order = {"EVENT_OVERLAP": 0, "TEMPORAL_PROXIMITY": 1,
             "EVENT_SEQUENCE": 2, "TIMELINE_GAP": 3}
    out.sort(key=lambda r: (order[r.timeline_type], r.title))
    return out[:MAX_TIMELINE_FINDINGS], meta


def _emit_overlap(out, d, a, b, shared_entity) -> None:
    if shared_entity is not None:
        name = d.entities_by_id[shared_entity].canonical_name
        title = f"Event overlap: {name}"
        summary = (f"Two confirmed events for {name} share the same "
                   f"recorded timestamp.")
        scope = f"both attributed to {name}"
    else:
        title = "Concurrent records"
        summary = ("Two confirmed records share the same recorded "
                   "timestamp; neither carries entity attribution, so no "
                   "common subject is implied.")
        scope = "neither event carries entity attribution"
    out.append(TimelineResult(
        timeline_type="EVENT_OVERLAP",
        title=title,
        summary=summary,
        explanation=[
            f"Event {a.id} ({a.event_type}) at "
            f"{_fmt(a.timestamp)}.",
            f"Event {b.id} ({b.event_type}) at {_fmt(b.timestamp)}.",
            f"Identical recorded timestamps ({scope}); whether they "
            "describe the same moment requires investigator review."],
        event_ids=[a.id, b.id],
        entity_ids=[shared_entity] if shared_entity else [],
        interval_minutes=0.0,
        details={"events": {"a": a.id, "b": b.id},
                 "shared_entity": shared_entity}))
