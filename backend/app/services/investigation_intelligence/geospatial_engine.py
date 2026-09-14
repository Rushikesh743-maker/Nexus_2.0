"""Geospatial / co-location intelligence (stage 4).

Confirmed location data only, no GIS infrastructure:

* coordinate sources: the case's confirmed `location` rows (lat/lon);
* a confirmed **location-typed entity** is joined to a confirmed location
  row by (case, normalized name) — the documented, explicit join rule;
  an unmatched location entity simply has no coordinates (reported, not
  guessed);
* **location observations** are confirmed records tying an entity to a
  location: a dated `timeline_event` with `location_id`, or a confirmed
  relationship whose target is a location-typed entity (time unknown —
  stated explicitly).

Findings (all bounded, all neutral wording):

CO_LOCATION
    >= 2 confirmed entities observed at the same confirmed location
    (distance < CO_LOCATION_RADIUS_KM). If the observations carry
    timestamps, the time difference is computed and reported; otherwise
    "time not recorded" is stated. No meeting or contact is implied.

LOCATION_PROXIMITY
    Two distinct confirmed locations with
    CO_LOCATION_RADIUS_KM < distance <= PROXIMITY_RADIUS_KM, each with
    observed entities/events; distance, entities and (when available)
    time difference are reported.

LOCATION_SEQUENCE
    One confirmed entity observed at >= 2 distinct confirmed locations —
    ordered with intervals and implied travel distance when times are
    available, otherwise explicitly unordered.

If no usable coordinates exist, the result is
`location_data_insufficient: true` with the LOCATION_DATA_INSUFFICIENT
message — never fabricated coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..graph_intelligence.graph_builder import normalize_name
from .contradiction_engine import haversine_km
from .data import Stage4Data

CO_LOCATION_RADIUS_KM = 0.05   # < 50 m => same location
PROXIMITY_RADIUS_KM = 2.0      # documented proximity radius
MAX_GEO_FINDINGS = 10          # per type, per case

METHOD = (f"geospatial-analysis v1 (haversine distance; co-location < "
          f"{CO_LOCATION_RADIUS_KM} km, proximity <= "
          f"{PROXIMITY_RADIUS_KM} km; location entities joined to "
          f"location records by case + normalized name)")


@dataclass
class GeoObservation:
    entity_id: int | None
    location_id: int          # the location-table row used for coordinates
    location_name: str
    lat: float
    lon: float
    timestamp: object | None  # datetime or None
    source_event_id: int | None = None
    source_relationship_id: int | None = None


@dataclass
class GeoResult:
    geo_type: str
    title: str
    summary: str
    explanation: list[str]
    entity_ids: list[int] = field(default_factory=list)
    event_ids: list[int] = field(default_factory=list)
    relationship_ids: list[int] = field(default_factory=list)
    location_ids: list[int] = field(default_factory=list)
    distance_km: float | None = None
    time_difference_minutes: float | None = None
    threshold: str = ""
    details: dict = field(default_factory=dict)


def _location_entity_map(d: Stage4Data) -> dict[int, GeoObservation | None]:
    """entity id (location-typed) -> coordinate holder or None."""
    out: dict[int, GeoObservation | None] = {}
    for e in d.entities:
        if e.entity_type != "location":
            continue
        loc = d.locations_by_name.get(normalize_name(e.canonical_name))
        if loc is None or loc.latitude is None or loc.longitude is None:
            out[e.id] = None
        else:
            out[e.id] = loc
    return out


def collect_observations(d: Stage4Data) -> tuple[list[GeoObservation], dict]:
    obs: list[GeoObservation] = []
    skipped_no_coords = 0
    # 1) dated events with a location_id
    for ev in d.events:
        if ev.location_id is None:
            continue
        loc = next((l for l in d.locations if l.id == ev.location_id), None)
        if loc is None or loc.latitude is None or loc.longitude is None:
            skipped_no_coords += 1
            continue
        obs.append(GeoObservation(
            entity_id=ev.entity_id, location_id=loc.id,
            location_name=loc.name, lat=loc.latitude, lon=loc.longitude,
            timestamp=ev.timestamp, source_event_id=ev.id))
    # 2) confirmed relationships into location-typed entities
    loc_entities = _location_entity_map(d)
    for r in d.relationships:
        if r.target_entity_id not in loc_entities:
            continue
        holder = loc_entities[r.target_entity_id]
        if holder is None:
            skipped_no_coords += 1
            continue
        obs.append(GeoObservation(
            entity_id=r.source_entity_id, location_id=holder.id,
            location_name=holder.name, lat=holder.latitude, lon=holder.longitude,
            timestamp=None, source_relationship_id=r.id))
    meta = {
        "observations": len(obs),
        "dated_observations": sum(1 for o in obs if o.timestamp is not None),
        "skipped_no_coords": skipped_no_coords,
        "locations_total": len(d.locations),
        "locations_with_coords": sum(
            1 for l in d.locations if l.latitude is not None),
        "location_data_insufficient": not obs,
    }
    return obs, meta


def analyze_geospatial(d: Stage4Data) -> tuple[list[GeoResult], list[GeoObservation], dict]:
    obs, meta = collect_observations(d)
    out: list[GeoResult] = []
    if not obs:
        return out, obs, meta

    name_of = {e.id: e.canonical_name for e in d.entities}

    # --------------------------------------------- CO_LOCATION
    by_loc: dict[int, list[GeoObservation]] = {}
    for o in obs:
        by_loc.setdefault(o.location_id, []).append(o)
    co_groups = []
    for loc_id in sorted(by_loc):
        group = by_loc[loc_id]
        entities = {o.entity_id for o in group if o.entity_id is not None}
        if len(entities) >= 2:
            co_groups.append((loc_id, group, sorted(entities)))
    co_groups.sort(key=lambda g: (-len(g[2]), g[0]))
    for loc_id, group, entities in co_groups[:MAX_GEO_FINDINGS]:
        o0 = group[0]
        times = [o.timestamp for o in group if o.timestamp is not None]
        dt = (None if len(times) < 2 else
              round(abs((max(times) - min(times)).total_seconds()) / 60.0, 1))
        ent_names = ", ".join(name_of.get(e, str(e)) for e in entities[:6])
        more = f" (+{len(entities) - 6} more)" if len(entities) > 6 else ""
        out.append(GeoResult(
            geo_type="CO_LOCATION",
            title=f"Potential co-location: {o0.location_name}",
            summary=(f"{len(entities)} confirmed entities are recorded at "
                     f"{o0.location_name}."
                     + (f" Recorded times span {dt:.0f} min." if dt is not None
                        else " No times are recorded for these observations.")),
            explanation=[
                f"{len(group)} confirmed observation(s) reference "
                f"{o0.location_name} (location {loc_id}).",
                f"Entities recorded there: {ent_names}{more}.",
                ("Recorded times span " + f"{dt:.0f} min."
                 if dt is not None else
                 "No timestamps are recorded on these observations, so no "
                 "temporal relationship can be assessed."),
                "Potential co-location — co-presence in the confirmed "
                "record only; no meeting or contact is implied."],
            entity_ids=entities,
            event_ids=[o.source_event_id for o in group if o.source_event_id],
            relationship_ids=[o.source_relationship_id
                              for o in group if o.source_relationship_id],
            location_ids=[loc_id],
            distance_km=0.0,
            time_difference_minutes=dt,
            threshold=f"< {CO_LOCATION_RADIUS_KM} km (same location)",
            details={"location": o0.location_name,
                     "observations": len(group)}))

    # ------------------------------------------ LOCATION_PROXIMITY
    locs_used: dict[int, GeoObservation] = {}
    for o in obs:
        locs_used.setdefault(o.location_id, o)
    loc_ids = sorted(locs_used)
    pairs = []
    for i in range(len(loc_ids)):
        for j in range(i + 1, len(loc_ids)):
            a, b = locs_used[loc_ids[i]], locs_used[loc_ids[j]]
            dist = haversine_km(a.lat, a.lon, b.lat, b.lon)
            if CO_LOCATION_RADIUS_KM < dist <= PROXIMITY_RADIUS_KM:
                pairs.append((dist, a, b))
    pairs.sort(key=lambda p: (p[0], p[1].location_id, p[2].location_id))
    for dist, a, b in pairs[:MAX_GEO_FINDINGS]:
        ent_a = sorted({o.entity_id for o in by_loc[a.location_id]
                        if o.entity_id is not None})
        ent_b = sorted({o.entity_id for o in by_loc[b.location_id]
                        if o.entity_id is not None})
        times = [o.timestamp for lid in (a.location_id, b.location_id)
                 for o in by_loc[lid] if o.timestamp is not None]
        dt = (None if len(times) < 2 else
              round(abs((max(times) - min(times)).total_seconds()) / 60.0, 1))
        out.append(GeoResult(
            geo_type="LOCATION_PROXIMITY",
            title=(f"Potential geographic proximity: {a.location_name} ↔ "
                   f"{b.location_name}"),
            summary=(f"{a.location_name} and {b.location_name} are "
                     f"{dist:.2f} km apart (documented radius "
                     f"{PROXIMITY_RADIUS_KM:.0f} km)."),
            explanation=[
                f"{a.location_name} (location {a.location_id}) has "
                f"{len(ent_a)} confirmed observation(s); entities: "
                + (", ".join(name_of.get(e, str(e)) for e in ent_a[:6])
                   or "unattributed"),
                f"{b.location_name} (location {b.location_id}) has "
                f"{len(ent_b)} confirmed observation(s); entities: "
                + (", ".join(name_of.get(e, str(e)) for e in ent_b[:6])
                   or "unattributed"),
                f"Distance {dist:.2f} km (haversine) within the "
                f"documented {PROXIMITY_RADIUS_KM:.0f} km radius.",
                ("Recorded times span " + f"{dt:.0f} min."
                 if dt is not None else
                 "No comparable timestamps are recorded for both "
                 "locations.")],
            entity_ids=sorted(set(ent_a) | set(ent_b)),
            location_ids=[a.location_id, b.location_id],
            distance_km=round(dist, 3),
            time_difference_minutes=dt,
            threshold=f"<= {PROXIMITY_RADIUS_KM} km",
            details={"locations": [a.location_name, b.location_name]}))

    # ------------------------------------------ LOCATION_SEQUENCE
    by_entity: dict[int, list[GeoObservation]] = {}
    for o in obs:
        if o.entity_id is not None:
            by_entity.setdefault(o.entity_id, []).append(o)
    seqs = []
    for entity_id in sorted(by_entity):
        locs = {o.location_id for o in by_entity[entity_id]}
        if len(locs) >= 2:
            seqs.append((entity_id, by_entity[entity_id]))
    seqs.sort(key=lambda s: (-len({o.location_id for o in s[1]}), s[0]))
    for entity_id, group in seqs[:MAX_GEO_FINDINGS]:
        name = name_of.get(entity_id, str(entity_id))
        dated = [o for o in group if o.timestamp is not None]
        ordered = sorted(dated, key=lambda o: (o.timestamp, o.source_event_id)) \
            if dated else sorted(group, key=lambda o: o.location_id)
        loc_names = []
        for o in ordered:
            if o.location_name not in loc_names:
                loc_names.append(o.location_name)
        leg_dist = 0.0
        intervals = []
        if len(dated) >= 2:
            for a, b in zip(ordered, ordered[1:]):
                leg_dist = max(leg_dist, haversine_km(a.lat, a.lon, b.lat, b.lon))
                intervals.append(round((b.timestamp - a.timestamp).total_seconds() / 60.0, 1))
        out.append(GeoResult(
            geo_type="LOCATION_SEQUENCE",
            title=f"Recorded at multiple locations: {name}",
            summary=(f"{name} is confirmed at {len(loc_names)} distinct "
                     f"locations: {', '.join(loc_names[:4])}"
                     + (f" (+{len(loc_names) - 4} more)" if len(loc_names) > 4 else "")
                     + (". Chronological order and intervals are computed "
                        "from the recorded timestamps."
                        if len(dated) >= 2 else
                        ". No timestamps are recorded, so the order of "
                        "these observations is not determinable.")),
            explanation=[
                f"{len(group)} confirmed observation(s) link {name} to "
                f"{len(loc_names)} distinct confirmed locations.",
                ("Sequence (chronological): "
                 + " → ".join(
                     f"{o.location_name} "
                     f"({o.timestamp.strftime('%Y-%m-%d %H:%M')})"
                     for o in ordered[:6])
                 if len(dated) >= 2 else
                 "Observations (order not determinable — no timestamps "
                 "recorded): " + " · ".join(o.location_name for o in ordered[:6])),
                ("Longest implied leg "
                 f"{leg_dist:.1f} km; intervals "
                 + ", ".join(f"{x:.0f} min" for x in intervals[:5])
                 if len(dated) >= 2 else
                 "Movement is described as recorded, not inferred.")],
            entity_ids=[entity_id],
            event_ids=[o.source_event_id for o in group if o.source_event_id],
            relationship_ids=[o.source_relationship_id
                              for o in group if o.source_relationship_id],
            location_ids=sorted({o.location_id for o in group}),
            distance_km=round(leg_dist, 2) if len(dated) >= 2 else None,
            time_difference_minutes=(round(
                (ordered[-1].timestamp - ordered[0].timestamp).total_seconds() / 60.0, 1)
                if len(dated) >= 2 else None),
            threshold=">= 2 distinct locations",
            details={"locations": loc_names[:10],
                     "dated": len(dated),
                     "intervals_minutes": intervals[:10]}))

    order = {"CO_LOCATION": 0, "LOCATION_PROXIMITY": 1, "LOCATION_SEQUENCE": 2}
    out.sort(key=lambda r: (order[r.geo_type], r.title))
    return out, obs, meta
