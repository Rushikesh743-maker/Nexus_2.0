"""
Claim extraction for the contradiction engine.

The graph answers "are A and B connected?". Contradiction detection needs a
different shape of the same evidence: individual *claims* that a source record
makes about the world, each still carrying the record it came from.

Four claim families are derived from the existing ingested corpus. Nothing is
invented here — every claim points back at a source id already in
`raw["documents"]`, and the engine never asserts anything a claim does not say.

    Sighting        this entity was at this place at this time
    DeviceClaim     this handset belongs to this entity
    VehicleClaim    this entity was recorded with this vehicle
    AttributeClaim  this record gives this entity this attribute value

The hard part is time. Most FIR and surveillance records in the corpus are
stamped with the moment the document was filed, not the moment the event
happened, so a claim carries an explicit `time_precision` and the engine
refuses to raise timing conflicts from records that only fix a calendar day.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import config


# ------------------------------------------------------------------ types

@dataclass(frozen=True)
class Sighting:
    entity_id: str
    place: str
    lat: float | None
    lon: float | None
    timestamp: str
    time_precision: str
    source_id: str
    source_type: str
    evidence: str
    confidence: float = 0.9
    record_id: str | None = None

    @property
    def when(self) -> datetime:
        return datetime.fromisoformat(self.timestamp)

    @property
    def time_precise(self) -> bool:
        return self.time_precision in config.TIME_PRECISE


@dataclass(frozen=True)
class DeviceClaim:
    device: str
    entity_id: str
    source_id: str
    source_type: str
    evidence: str
    confidence: float
    timestamp: str | None = None


@dataclass(frozen=True)
class VehicleClaim:
    vehicle: str
    entity_id: str
    timestamp: str | None
    time_precision: str
    source_id: str
    source_type: str
    evidence: str
    confidence: float = 0.7


@dataclass(frozen=True)
class AttributeClaim:
    entity_id: str
    attribute: str
    value: str
    source_id: str
    source_type: str


@dataclass
class ClaimSet:
    sightings: list[Sighting] = field(default_factory=list)
    devices: list[DeviceClaim] = field(default_factory=list)
    vehicles: list[VehicleClaim] = field(default_factory=list)
    attributes: list[AttributeClaim] = field(default_factory=list)

    def sightings_by_entity(self) -> dict[str, list[Sighting]]:
        out: dict[str, list[Sighting]] = {}
        for s in self.sightings:
            out.setdefault(s.entity_id, []).append(s)
        for rows in out.values():
            rows.sort(key=lambda s: s.timestamp)
        return out


# ------------------------------------------------------------- geo helper

def haversine_km(lat1, lon1, lat2, lon2) -> float | None:
    """Great-circle distance in km, or None when either point is unknown."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    r = 6371.0
    rad = math.radians
    dlat, dlon = rad(lat2 - lat1), rad(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(dlon / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


# --------------------------------------------------- narrative clock times
#
# Surveillance and FIR narratives state the time of the event in words even
# though the record's own timestamp is the filing time: "at 2340 hrs",
# "from 2100 to 0230 hrs", "at 1215 hrs". Reading those upgrades a
# document-level claim to a usable one — but only for the location the
# sentence is actually about, so the match must sit near the place name.

_TIME_PATTERNS = [
    re.compile(r"\bat\s+(?:approximately\s+)?(\d{4})\s*hrs\b", re.I),
    re.compile(r"\bfrom\s+(\d{4})\s+to\s+\d{4}\s*hrs\b", re.I),
    re.compile(r"\b(\d{4})\s*hrs\b", re.I),
]


def _clock_times(text: str) -> list[tuple[int, int, int]]:
    """(position, hour, minute) for every HHMM-hrs time written in `text`."""
    out: list[tuple[int, int, int]] = []
    seen: set[int] = set()
    for pat in _TIME_PATTERNS:
        for m in pat.finditer(text or ""):
            if m.start() in seen:
                continue
            seen.add(m.start())
            raw = m.group(1)
            hh, mm = int(raw[:2]), int(raw[2:])
            if 0 <= hh <= 23 and 0 <= mm <= 59:
                out.append((m.start(), hh, mm))
    out.sort()
    return out


def stated_time_for(text: str, anchor: str, day: str) -> str | None:
    """
    The clock time the narrative gives for `anchor` (a place or name), as a
    full ISO timestamp on `day`.

    The nearest stated time to the anchor's first mention wins. When the text
    states no time, or never mentions the anchor, the caller keeps the
    document-level timestamp and the claim stays imprecise — which is the
    safe direction to fail in.
    """
    if not text or not day:
        return None
    times = _clock_times(text)
    if not times:
        return None
    at = text.find(anchor) if anchor else -1
    if at < 0:
        # The anchor is not named in the narrative, so no stated time can be
        # tied to it. Returning the document's single time here would stamp
        # every place a report mentions with the same clock reading and
        # manufacture an instant "impossible journey" between them — the
        # engine would then flag its own parsing artefact as a contradiction.
        return None
    pos, hh, mm = min(times, key=lambda t: abs(t[0] - at))
    return f"{day[:10]}T{hh:02d}:{mm:02d}:00"


# ------------------------------------------------------------- extraction

class ClaimExtractor:
    """Derives the claim set from an already-built CaseGraph."""

    def __init__(self, case_graph):
        self.cg = case_graph
        self.raw = case_graph.raw

    # ---------------------------------------------------------- sightings
    def _cdr_sightings(self) -> list[Sighting]:
        """
        One sighting per call leg. A CDR row is a machine record: the start
        time is exact and the cell site is a real coordinate, so these are the
        only claims strong enough to carry a timing conflict on their own.
        """
        out = []
        for r in self.raw.get("cdr_rows", []):
            try:
                lat, lon = float(r["lat"]), float(r["lon"])
            except (TypeError, ValueError, KeyError):
                continue
            for phone in (r.get("caller"), r.get("callee")):
                eid = self.cg.phone_index.get(phone)
                if not eid:
                    continue
                out.append(Sighting(
                    entity_id=eid, place=r["cell_tower"], lat=lat, lon=lon,
                    timestamp=r["start_time"],
                    time_precision=config.PRECISION_EXACT,
                    source_id="CDR", source_type="cdr",
                    record_id=r.get("call_id"),
                    evidence=(f"Handset {phone} active on the {r['cell_tower']} cell site "
                              f"at {r['start_time'][11:16]} on {r['start_time'][:10]} "
                              f"(call {r.get('call_id')})"),
                    confidence=0.95,
                ))
        return out

    def _text_sightings(self) -> list[Sighting]:
        """
        Sightings from narrative sources. The location relations were already
        extracted during ingestion; this adds the timing judgement the graph
        does not need but the contradiction engine does.
        """
        out = []
        docs = self.raw.get("documents", {})
        for rel in self.raw.get("raw_relations", []):
            if rel.get("b_kind") != "LOCATION":
                continue
            eid = self.cg.resolve_name(rel["a"])
            if not eid:
                continue
            place = rel["b"]
            doc = docs.get(rel["source_id"], {})
            record = doc.get("record") or {}
            narrative = next((record.get(k) for k in
                              ("observation", "narrative", "text", "brief_facts")
                              if record.get(k)), "")
            day = rel.get("timestamp") or ""
            stated = stated_time_for(narrative, place, day) if day else None
            lat = record.get("lat")
            lon = record.get("lon")
            if lat is None or lon is None:
                from ..graph.build import LOCATION_COORDS
                lat, lon = LOCATION_COORDS.get(place, (None, None))
            out.append(Sighting(
                entity_id=eid, place=place, lat=lat, lon=lon,
                timestamp=stated or day,
                time_precision=(config.PRECISION_STATED if stated
                                else config.PRECISION_DOCUMENT),
                source_id=rel["source_id"], source_type=rel["source_type"],
                evidence=rel.get("evidence") or f"Recorded at {place} in {rel['source_id']}",
                confidence=float(rel.get("confidence") or 0.7),
            ))
        return out

    # ------------------------------------------------------------ devices
    def _device_claims(self) -> list[DeviceClaim]:
        """
        Handset attribution, from the explicit ownership cues ingestion found.
        Names are resolved to entities here, so two spellings of one person
        collapse to a single claim rather than looking like a conflict.
        """
        out = []
        for oe in self.raw.get("ownership_evidence", []):
            eid = self.cg.resolve_name(oe.get("owner") or "")
            if not eid:
                continue
            out.append(DeviceClaim(
                device=oe["phone"], entity_id=eid,
                source_id=oe["source_id"], source_type=oe["source_type"],
                evidence=oe.get("evidence") or "",
                confidence=float(oe.get("confidence") or 0.8),
            ))
        return out

    # ----------------------------------------------------------- vehicles
    def _vehicle_claims(self) -> list[VehicleClaim]:
        out = []
        docs = self.raw.get("documents", {})
        for rel in self.raw.get("raw_relations", []):
            if rel.get("b_kind") != "VEHICLE":
                continue
            eid = self.cg.resolve_name(rel["a"])
            if not eid:
                continue
            record = (docs.get(rel["source_id"], {}) or {}).get("record") or {}
            narrative = next((record.get(k) for k in
                              ("observation", "narrative", "text", "brief_facts")
                              if record.get(k)), "")
            day = rel.get("timestamp") or ""
            stated = stated_time_for(narrative, rel["b"], day) if day else None
            out.append(VehicleClaim(
                vehicle=rel["b"], entity_id=eid,
                timestamp=stated or day,
                time_precision=(config.PRECISION_STATED if stated
                                else config.PRECISION_DOCUMENT),
                source_id=rel["source_id"], source_type=rel["source_type"],
                evidence=rel.get("evidence") or f"Recorded with {rel['b']}",
                confidence=float(rel.get("confidence") or 0.7),
            ))
        return out

    # --------------------------------------------------------- attributes
    def _attribute_claims(self) -> list[AttributeClaim]:
        """
        Per-record attribute values for entities that resolution merged. The
        merged entity carries one flattened `attrs` dict, so divergence is only
        visible in the observations that fed it.
        """
        out = []
        for ent in self.raw.get("entities", []):
            for obs in getattr(ent, "observations", None) or []:
                attrs = obs.get("attrs") or {}
                for key in config.IDENTITY_ATTRIBUTES:
                    val = attrs.get(key)
                    if val in (None, "", "-"):
                        continue
                    out.append(AttributeClaim(
                        entity_id=ent.id, attribute=key, value=str(val),
                        source_id=obs.get("source_id") or "unknown",
                        source_type=obs.get("source_type") or "inferred",
                    ))
        return out

    # ------------------------------------------------------------- driver
    def run(self) -> ClaimSet:
        return ClaimSet(
            sightings=self._cdr_sightings() + self._text_sightings(),
            devices=self._device_claims(),
            vehicles=self._vehicle_claims(),
            attributes=self._attribute_claims(),
        )


def extract_claims(case_graph) -> ClaimSet:
    return ClaimExtractor(case_graph).run()
