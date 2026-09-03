"""
The contradiction engine.

NEXUS is otherwise built to *find* connections. This module exists to argue
with them: it searches the same evidence for records that cannot comfortably
all be true, and revises the affected confidence downward with the working
shown.

Five checks run over the claim set (see `observations.py`):

    timeline_conflict             movement between two sightings is not
                                  physically reasonable
    location_inconsistency        two source systems place one subject in two
                                  places at overlapping times
    vehicle_association_conflict  one vehicle, two subjects, overlapping window,
                                  no transfer or custody record
    device_conflict               one handset attributed to two resolved subjects
    identity_conflict             records merged into one identity disagree on
                                  a core attribute

Three rules constrain every detector:

1. **Nothing is asserted that a record does not say.** Each contradiction
   carries the source ids behind both sides, and the API can hand back the
   original document for any of them.
2. **Insufficient evidence is not a contradiction.** Where timing is only
   known to the day, or a coordinate is missing, the pair is reported as
   `insufficient_evidence` and excluded from the findings — see
   `EngineResult.skipped`.
3. **The engine never resolves the conflict.** It does not decide which record
   is wrong, and it never mutates the graph. Possible explanations are listed
   for the investigator to choose between.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from . import config
from .observations import (ClaimSet, Sighting, extract_claims, haversine_km)
from .scoring import assess


def _minutes(a: str, b: str) -> float:
    return abs((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()) / 60.0


def _same_record(a, b) -> bool:
    """
    True when two claims came out of the same source record.

    One narrative naming three places is a narrative, not a journey: the
    engine must never read a single document as evidence against itself.
    CDR rows separate on `record_id` (the call id); a document has no
    record id, so equal source ids alone identify it.
    """
    if a.source_id != b.source_id:
        return False
    ra, rb = getattr(a, "record_id", None), getattr(b, "record_id", None)
    return ra == rb


def _ev(source_id, source_type, confidence, detail, timestamp=None, record_id=None,
        entity_ids=None):
    """One provenance row. Shape is shared by both sides of every contradiction."""
    return {
        "source_id": source_id,
        "record_id": record_id,
        "source_type": source_type,
        "confidence": round(float(confidence), 3),
        "timestamp": timestamp,
        "entity_ids": entity_ids or [],
        "detail": detail,
    }


class ContradictionEngine:
    """
    Stateless with respect to the case: give it a built CaseGraph, get findings.
    Never writes to the graph.
    """

    def __init__(self, case_graph, claims: ClaimSet | None = None):
        self.cg = case_graph
        self.raw = case_graph.raw
        self.claims = claims if claims is not None else extract_claims(case_graph)
        self.skipped: list[dict] = []

    # ------------------------------------------------------------ helpers
    def label(self, node_id: str) -> str:
        try:
            return self.cg.G.nodes[node_id].get("label") or node_id
        except KeyError:
            return node_id

    def _edge(self, a: str, b: str):
        return self.cg.G[a][b] if self.cg.G.has_edge(a, b) else None

    def _edge_support(self, a: str, b: str) -> tuple[float, list[dict]]:
        """
        The records already supporting the A–B link, as evidence rows. This is
        what the contradiction is weighed against, and it comes straight from
        the graph's own provenance.
        """
        e = self._edge(a, b)
        if not e:
            return 0.6, []
        rows = [
            _ev(s.get("source_id"), s.get("source_type"), s.get("confidence", 0.8),
                s.get("evidence") or "", s.get("timestamp"),
                entity_ids=[a, b])
            for s in e.get("sources", [])
        ]
        return float(e.get("confidence", 0.6)), rows

    def _entity_support(self, entity_id: str) -> tuple[float, list[dict]]:
        """Records attesting an entity itself, used when a contradiction is about a subject rather than a link."""
        rows = []
        node = self.cg.G.nodes.get(entity_id, {})
        for src in node.get("sources", []) or []:
            stype, _, sid = str(src).partition(":")
            rows.append(_ev(sid or src, stype or "inferred", 0.85,
                            f"{self.label(entity_id)} recorded in {sid or src}",
                            entity_ids=[entity_id]))
        return 0.85, rows

    def _skip(self, kind: str, reason: str, **detail):
        self.skipped.append({"check": kind, "reason": reason, **detail})

    # ------------------------------------------------------------------ 1
    def timeline_conflicts(self) -> list[dict]:
        """
        Consecutive sightings whose implied point-to-point speed exceeds what
        ground travel explains.

        The check is deliberately narrow. It requires both sightings to fix a
        time (a record stamped only with its filing date cannot support a
        conflict measured in minutes), a real separation in space, and an
        interval long enough that clock skew between two systems is not the
        simpler explanation.
        """
        out = []
        for eid, rows in self.claims.sightings_by_entity().items():
            for i in range(len(rows) - 1):
                a, b = rows[i], rows[i + 1]
                verdict = self._movement_verdict(a, b)
                if verdict is None:
                    continue
                if verdict["status"] != "conflict":
                    continue
                # Cross-source disagreements are reported by the location check,
                # which frames them as two systems disagreeing rather than as
                # impossible travel.
                if a.source_type != b.source_type:
                    continue
                out.append(self._movement_finding(
                    "timeline_conflict", eid, a, b, verdict,
                    title=(f"Timeline conflict for {self.label(eid)} between "
                           f"{a.place} and {b.place}"),
                    explanations=[
                        "A timestamp on one of the two records is wrong.",
                        "The two records describe different people and an "
                        "identity was merged in error.",
                        "A handset was carried or used by someone else.",
                        "A cell site or coordinate is mis-recorded.",
                    ],
                    verification=[
                        f"Pull the raw {a.source_type.upper()} rows for "
                        f"{a.timestamp[:10]} and confirm both timestamps.",
                        "Confirm handset attribution for the subject on that date.",
                        "Check for tower-location errors at "
                        f"{a.place} and {b.place}.",
                    ],
                ))
        return out

    def _movement_verdict(self, a: Sighting, b: Sighting) -> dict | None:
        """
        Classify a pair of consecutive sightings, or return None when the pair
        is not evaluable at all. Records the reason for every skip.
        """
        if _same_record(a, b):
            return None
        if not (a.time_precise and b.time_precise):
            self._skip("timeline_conflict", "insufficient_evidence",
                       detail=("At least one record fixes only a calendar date, "
                               "so no timing conclusion is available."),
                       entity_id=a.entity_id,
                       sources=[a.source_id, b.source_id],
                       precision=[a.time_precision, b.time_precision])
            return None
        km = haversine_km(a.lat, a.lon, b.lat, b.lon)
        if km is None:
            self._skip("timeline_conflict", "insufficient_evidence",
                       detail="A coordinate is missing for one of the two places.",
                       entity_id=a.entity_id, places=[a.place, b.place])
            return None
        if km < config.MIN_SEPARATION_KM:
            return {"status": "consistent", "km": km, "reason": "same locality"}
        mins = _minutes(a.timestamp, b.timestamp)
        # A time read out of prose carries the officer's rounding; widen the
        # interval in the subject's favour before judging it.
        if config.PRECISION_STATED in (a.time_precision, b.time_precision):
            mins += config.STATED_TIME_TOLERANCE_MINUTES
        # Clock skew is a disagreement *between* systems. Two rows from one
        # machine-generated source share a clock, so the tolerance does not
        # apply to them — and applying it there would discard the strongest
        # evidence the corpus has, a subject on two towers 36 seconds apart.
        if a.source_type != b.source_type and mins < config.MIN_INTERVAL_MINUTES:
            self._skip("timeline_conflict", "insufficient_evidence",
                       detail=(f"The two records are {mins:.1f} minutes apart, which is "
                               "within the clock-skew tolerance between "
                               f"{a.source_type} and {b.source_type}."),
                       entity_id=a.entity_id, sources=[a.source_id, b.source_id])
            return None
        if mins <= 0:
            self._skip("timeline_conflict", "insufficient_evidence",
                       detail="The two records carry the same timestamp.",
                       entity_id=a.entity_id, sources=[a.source_id, b.source_id])
            return None
        speed = km / (mins / 60.0)
        status = ("conflict" if speed > config.MAX_REASONABLE_SPEED_KMPH
                  else "unusual" if speed > config.UNUSUAL_SPEED_KMPH
                  else "consistent")
        return {"status": status, "km": km, "minutes": mins, "speed": speed}

    def _movement_finding(self, ctype, eid, a: Sighting, b: Sighting, v: dict,
                          title: str, explanations: list[str],
                          verification: list[str]) -> dict:
        base, support = self._entity_support(eid)
        contradicting = [
            _ev(a.source_id, a.source_type, a.confidence, a.evidence, a.timestamp,
                a.record_id, [eid]),
            _ev(b.source_id, b.source_type, b.confidence, b.evidence, b.timestamp,
                b.record_id, [eid]),
        ]
        scored = assess(base, support, contradicting)
        required_min = (v["km"] / config.MAX_REASONABLE_SPEED_KMPH) * 60.0
        return {
            "type": ctype,
            "severity": "high" if v["speed"] > 2 * config.MAX_REASONABLE_SPEED_KMPH
                        else scored["severity"],
            "title": title,
            "description": (
                f"{self.label(eid)} is placed at {a.place} at "
                f"{a.timestamp[11:16]} and at {b.place} at {b.timestamp[11:16]} on "
                f"{b.timestamp[:10]}. The two points are {v['km']:.1f} km apart with "
                f"{v['minutes']:.0f} minute(s) between them, an implied "
                f"{v['speed']:.0f} km/h. Ordinary ground travel would need about "
                f"{required_min:.0f} minutes."
            ),
            "entity_ids": [eid],
            "entity_labels": [self.label(eid)],
            "affected_relationships": [],
            "events": [
                {"place": a.place, "timestamp": a.timestamp, "lat": a.lat, "lon": a.lon,
                 "source_id": a.source_id, "source_type": a.source_type,
                 "time_precision": a.time_precision, "record_id": a.record_id},
                {"place": b.place, "timestamp": b.timestamp, "lat": b.lat, "lon": b.lon,
                 "source_id": b.source_id, "source_type": b.source_type,
                 "time_precision": b.time_precision, "record_id": b.record_id},
            ],
            "basis": {
                "rule": (f"implied speed > {config.MAX_REASONABLE_SPEED_KMPH:g} km/h "
                         f"between consecutive time-precise sightings"),
                "distance_km": round(v["km"], 2),
                "interval_minutes": round(v["minutes"], 1),
                "implied_speed_kmph": round(v["speed"], 1),
                "reasonable_travel_minutes": round(required_min, 1),
                "threshold_kmph": config.MAX_REASONABLE_SPEED_KMPH,
            },
            "supporting_evidence": support,
            "contradicting_evidence": contradicting,
            "assessment": scored,
            "possible_explanations": explanations,
            "recommended_verification": verification,
        }

    # ------------------------------------------------------------------ 2
    def location_inconsistencies(self) -> list[dict]:
        """
        Two *different* source systems placing one subject in two places at
        overlapping times.

        Framed separately from the timeline check on purpose: when one system
        disagrees with another the useful statement is that the sources
        disagree, not that the subject travelled impossibly. Neither record is
        preferred — the engine reports the disagreement and its own reliability
        weights, and leaves the judgement to the investigator.
        """
        out = []
        for eid, rows in self.claims.sightings_by_entity().items():
            for i in range(len(rows) - 1):
                a, b = rows[i], rows[i + 1]
                if a.source_type == b.source_type:
                    continue
                v = self._movement_verdict(a, b)
                if v is None or v["status"] not in ("conflict", "unusual"):
                    continue
                base, support = self._entity_support(eid)
                contradicting = [
                    _ev(a.source_id, a.source_type, a.confidence, a.evidence,
                        a.timestamp, a.record_id, [eid]),
                    _ev(b.source_id, b.source_type, b.confidence, b.evidence,
                        b.timestamp, b.record_id, [eid]),
                ]
                scored = assess(base, support, contradicting)
                more, less = sorted(
                    (a, b), key=lambda s: config.reliability(s.source_type), reverse=True)
                out.append({
                    "type": "location_inconsistency",
                    "severity": scored["severity"] if v["status"] == "conflict" else "low",
                    "title": (f"Potential location inconsistency for {self.label(eid)} "
                              f"between {a.source_type} and {b.source_type} records"),
                    "description": (
                        f"{a.source_id} places {self.label(eid)} at {a.place} "
                        f"({a.timestamp[11:16]}) while {b.source_id} places the same "
                        f"subject at {b.place} ({b.timestamp[11:16]}) on "
                        f"{b.timestamp[:10]}. The points are {v['km']:.1f} km apart with "
                        f"{v['minutes']:.0f} minute(s) between them. The two sources do "
                        "not agree; neither is assumed correct."
                    ),
                    "entity_ids": [eid],
                    "entity_labels": [self.label(eid)],
                    "affected_relationships": [],
                    "events": [
                        {"place": a.place, "timestamp": a.timestamp, "lat": a.lat,
                         "lon": a.lon, "source_id": a.source_id,
                         "source_type": a.source_type,
                         "time_precision": a.time_precision, "record_id": a.record_id},
                        {"place": b.place, "timestamp": b.timestamp, "lat": b.lat,
                         "lon": b.lon, "source_id": b.source_id,
                         "source_type": b.source_type,
                         "time_precision": b.time_precision, "record_id": b.record_id},
                    ],
                    "basis": {
                        "rule": ("two source systems place one subject at points "
                                 f">{config.MIN_SEPARATION_KM:g} km apart within an "
                                 "interval ordinary travel does not cover"),
                        "distance_km": round(v["km"], 2),
                        "interval_minutes": round(v["minutes"], 1),
                        "implied_speed_kmph": round(v["speed"], 1),
                        "higher_weighted_source": more.source_type,
                        "lower_weighted_source": less.source_type,
                    },
                    "supporting_evidence": support,
                    "contradicting_evidence": contradicting,
                    "assessment": scored,
                    "possible_explanations": [
                        f"The {less.source_type} record's time is approximate or was "
                        "entered after the fact.",
                        "The subject's identity was mis-resolved in one of the records.",
                        "A handset was with another person at the time.",
                        "One of the two locations is recorded at the wrong granularity.",
                    ],
                    "recommended_verification": [
                        f"Retrieve {a.source_id} and {b.source_id} and compare the "
                        "recorded times against the originating logs.",
                        "Confirm which observation was made directly and which was "
                        "reconstructed.",
                    ],
                })
        return out

    # ------------------------------------------------------------------ 3
    def vehicle_association_conflicts(self) -> list[dict]:
        """
        One vehicle recorded with two subjects inside a short window, with
        nothing in the graph explaining a handover.

        Vehicles change hands and carry passengers, so a bare "two people, one
        vehicle" is not a conflict and is not reported. The window and the
        transfer-relationship exemption are what keep this check quiet.
        """
        by_vehicle: dict[str, list] = defaultdict(list)
        for c in self.claims.vehicles:
            by_vehicle[c.vehicle].append(c)
        out = []
        for vehicle, claims in by_vehicle.items():
            claims = [c for c in claims if c.timestamp]
            for i in range(len(claims)):
                for j in range(i + 1, len(claims)):
                    a, b = claims[i], claims[j]
                    if a.entity_id == b.entity_id:
                        continue
                    gap = _minutes(a.timestamp, b.timestamp) / 60.0
                    if gap > config.VEHICLE_WINDOW_HOURS:
                        continue
                    if self._explained_by_transfer(a.entity_id, b.entity_id):
                        self._skip("vehicle_association_conflict", "explained",
                                   detail=("A recorded relationship between the two "
                                           "subjects explains the handover."),
                                   vehicle=vehicle,
                                   entities=[a.entity_id, b.entity_id])
                        continue
                    out.append(self._association_finding(
                        "vehicle_association_conflict", vehicle, "vehicle", a, b, gap,
                        title=f"Potential conflicting association for vehicle {vehicle}",
                        rule=(f"one vehicle recorded with two subjects within "
                              f"{config.VEHICLE_WINDOW_HOURS:g}h and no transfer or "
                              "custody record"),
                        explanations=[
                            "The vehicle changed hands and the transfer was not recorded.",
                            "One subject was a passenger rather than the user.",
                            "A registration number was mis-read in one record.",
                            "The two records describe different vehicles.",
                        ],
                        verification=[
                            f"Check registration and ownership history for {vehicle}.",
                            "Establish which subject was driving at each recorded time.",
                        ]))
        return out

    # ------------------------------------------------------------------ 4
    def device_conflicts(self) -> list[dict]:
        """
        A handset attributed to two subjects whose names do not otherwise agree.

        Identity resolution merges on a shared identifier unconditionally, so
        by the time the graph exists two people who were recorded with the same
        number are already one node — the conflict has been absorbed rather
        than resolved. The detectable signal is therefore the *merge itself*:
        a subject assembled only because two records quote the same handset,
        where the two name forms are too dissimilar for the resolver's own name
        matcher to have joined them on their own.

        That distinction is what keeps this check quiet on the corpus's real
        cross-script pairs. "Sanjay Bhosle" and "संजय भोसले" quote one number
        and are the same person; the resolver's phonetic matcher agrees, so
        nothing is raised. Only a genuine disagreement survives.
        """
        from ..pipeline.resolve import name_similarity
        from ..pipeline.resolve import EntityResolver

        threshold = EntityResolver.NAME_MATCH_THRESHOLD
        by_device: dict[str, list] = defaultdict(list)
        for c in self.claims.devices:
            by_device[c.device].append(c)
        # Ownership claims name a person; group the raw spellings per handset.
        raw_owners: dict[str, dict[str, dict]] = defaultdict(dict)
        for oe in self.raw.get("ownership_evidence", []):
            raw_owners[oe["phone"]].setdefault(oe["owner"].strip(), oe)

        out = []
        for device, owners in raw_owners.items():
            names = sorted(owners)
            if len(names) < 2:
                continue
            # Collapse spellings of one name first. Without this the corpus's
            # cross-script pairs turn every conflict into several: a handset
            # disputed between one new name and a subject written in both Latin
            # and Devanagari would otherwise be reported twice.
            clusters = self._cluster_names(names, name_similarity, threshold, device)
            if len(clusters) < 2:
                continue
            reps = [self._representative(c) for c in clusters]
            for i in range(len(reps)):
                for j in range(i + 1, len(reps)):
                    na, nb = reps[i], reps[j]
                    sim = name_similarity(na, nb)
                    ea = self.cg.resolve_name(na)
                    eb = self.cg.resolve_name(nb)
                    if ea and eb and ea != eb and self._explained_by_transfer(ea, eb):
                        self._skip("device_conflict", "explained",
                                   detail=("A recorded relationship between the two "
                                           "subjects explains shared handset use."),
                                   device=device, entities=[ea, eb])
                        continue
                    out.append(self._device_finding(device, na, nb, sim, ea, eb,
                                                    owners[na], owners[nb], threshold))
        return out

    def _cluster_names(self, names, similarity, threshold, device) -> list[list[str]]:
        """Group name forms that the resolver's own matcher treats as one name."""
        clusters: list[list[str]] = []
        for name in names:
            for c in clusters:
                if any(similarity(name, other) >= threshold for other in c):
                    self._skip("device_conflict", "explained",
                               detail=(f"'{name}' and '{c[0]}' match as spellings of one "
                                       "name; the shared handset is consistent with a "
                                       "single subject."),
                               device=device, names=[c[0], name])
                    c.append(name)
                    break
            else:
                clusters.append([name])
        return clusters

    @staticmethod
    def _representative(cluster: list[str]) -> str:
        """The spelling that names a cluster: the longest Latin form, else the longest."""
        latin = [n for n in cluster if n.isascii()]
        return max(latin or cluster, key=len)

    def _device_finding(self, device, na, nb, sim, ea, eb, oa, ob, threshold) -> dict:
        merged = bool(ea and eb and ea == eb)
        entity_ids = sorted({x for x in (ea, eb) if x})
        if merged:
            base, support = self._entity_support(ea)
        elif ea and eb:
            base, support = self._edge_support(ea, eb)
            if not support:
                base, support = self._entity_support(ea)
        else:
            base, support = 0.85, []
        contradicting = [
            _ev(oa["source_id"], oa["source_type"], oa.get("confidence", 0.9),
                f"{oa['source_id']} attributes {device} to {na}: "
                f"{(oa.get('evidence') or '').strip()[:160]}",
                entity_ids=entity_ids),
            _ev(ob["source_id"], ob["source_type"], ob.get("confidence", 0.9),
                f"{ob['source_id']} attributes {device} to {nb}: "
                f"{(ob.get('evidence') or '').strip()[:160]}",
                entity_ids=entity_ids),
        ]
        scored = assess(base, support, contradicting)
        node = self.cg.G.nodes.get(ea or "", {}) if merged else {}
        merge_note = ""
        if merged:
            merge_note = (
                f" Identity resolution merged both records into "
                f"{self.label(ea)}, and the only stated grounds for that merge is the "
                f"shared handset — the two name forms score {sim:.2f} against each "
                f"other, below the {threshold:.2f} the name matcher requires. The "
                "subject is left merged for review; this engine does not split it."
            )
        return {
            "type": "device_conflict",
            "severity": scored["severity"],
            "title": f"Conflicting attribution for handset {device}",
            "description": (
                f"Handset {device} is attributed to '{na}' in {oa['source_id']} and to "
                f"'{nb}' in {ob['source_id']}. The two names do not match as spellings "
                f"of one person.{merge_note} The engine does not determine which "
                "attribution is correct."
            ),
            "entity_ids": entity_ids,
            "entity_labels": [self.label(x) for x in entity_ids],
            "affected_relationships": [],
            "events": [
                {"asset": device, "claimed_owner": na, "entity_id": ea,
                 "source_id": oa["source_id"], "source_type": oa["source_type"]},
                {"asset": device, "claimed_owner": nb, "entity_id": eb,
                 "source_id": ob["source_id"], "source_type": ob["source_type"]},
            ],
            "basis": {
                "rule": ("one handset attributed to two name forms whose similarity is "
                         f"below the resolver's {threshold:.2f} name-match threshold"),
                "asset": device,
                "name_similarity": round(sim, 3),
                "name_match_threshold": threshold,
                "identities_merged": merged,
                "merge_evidence": node.get("merge_evidence", []),
                "transfer_record_found": False,
            },
            "supporting_evidence": support,
            "contradicting_evidence": contradicting,
            "assessment": scored,
            "possible_explanations": [
                "The handset is shared between two people.",
                "The number was reassigned between the two recorded dates.",
                "A SIM was replaced and the number moved with the handset.",
                "One attribution was read out of the text incorrectly.",
                "Identity resolution merged two different people on this number.",
            ],
            "recommended_verification": [
                f"Request subscriber and IMEI history for {device} covering both records.",
                f"Re-examine the merge that produced {self.label(ea) if merged else 'these subjects'}.",
                "Confirm each attribution against the originating document.",
            ],
        }

    def _explained_by_transfer(self, a: str, b: str) -> bool:
        e = self._edge(a, b)
        return bool(e and set(e.get("types", [])) & config.TRANSFER_RELATIONSHIPS)

    def _association_finding(self, ctype, asset, asset_word, a, b, gap_hours,
                             title, rule, explanations, verification) -> dict:
        la, lb = self.label(a.entity_id), self.label(b.entity_id)
        base, support = self._edge_support(a.entity_id, b.entity_id)
        if not support:
            base, support = self._entity_support(a.entity_id)
        contradicting = [
            _ev(a.source_id, a.source_type, a.confidence, a.evidence,
                getattr(a, "timestamp", None), None, [a.entity_id]),
            _ev(b.source_id, b.source_type, b.confidence, b.evidence,
                getattr(b, "timestamp", None), None, [b.entity_id]),
        ]
        scored = assess(base, support, contradicting)
        when = ""
        if gap_hours is not None:
            when = (f" The two records are {gap_hours:.1f} hour(s) apart, inside the "
                    f"{config.VEHICLE_WINDOW_HOURS:g}-hour window the engine treats as "
                    "overlapping.")
        rels = []
        if self._edge(a.entity_id, b.entity_id):
            rels.append({"source": a.entity_id, "target": b.entity_id,
                         "source_label": la, "target_label": lb,
                         "types": self._edge(a.entity_id, b.entity_id).get("types", [])})
        return {
            "type": ctype,
            "severity": scored["severity"],
            "title": title,
            "description": (
                f"{asset_word.capitalize()} {asset} is associated with {la} in "
                f"{a.source_id} and with {lb} in {b.source_id}, with no transfer or "
                f"custody record linking the two.{when} The engine does not determine "
                "which attribution is correct."
            ),
            "entity_ids": [a.entity_id, b.entity_id],
            "entity_labels": [la, lb],
            "affected_relationships": rels,
            "events": [
                {"asset": asset, "entity_id": a.entity_id, "entity_label": la,
                 "timestamp": getattr(a, "timestamp", None), "source_id": a.source_id,
                 "source_type": a.source_type},
                {"asset": asset, "entity_id": b.entity_id, "entity_label": lb,
                 "timestamp": getattr(b, "timestamp", None), "source_id": b.source_id,
                 "source_type": b.source_type},
            ],
            "basis": {"rule": rule, "asset": asset,
                      "window_hours": (round(gap_hours, 2) if gap_hours is not None else None),
                      "transfer_record_found": False},
            "supporting_evidence": support,
            "contradicting_evidence": contradicting,
            "assessment": scored,
            "possible_explanations": explanations,
            "recommended_verification": verification,
        }

    # ------------------------------------------------------------------ 5
    def identity_conflicts(self) -> list[dict]:
        """
        Records merged into one identity that disagree on a core attribute.

        This never splits the entity. Resolution merged those records for a
        reason — usually a shared identifier — and a differing district or date
        of birth is a reason to look again, not grounds for the engine to undo
        the merge on its own.
        """
        by_entity: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        for c in self.claims.attributes:
            by_entity[c.entity_id][c.attribute].append(c)
        out = []
        for eid, attrs in by_entity.items():
            for attr, claims in attrs.items():
                values = {c.value for c in claims}
                if len(values) < 2:
                    continue
                if config.IDENTITY_ATTRIBUTES.get(attr) == "overlap" and \
                        self._ranges_overlap(values):
                    self._skip("identity_conflict", "explained",
                               detail=f"The recorded {attr} ranges overlap.",
                               entity_id=eid, values=sorted(values))
                    continue
                first = {}
                for c in claims:
                    first.setdefault(c.value, c)
                rows = list(first.values())
                base, support = self._entity_support(eid)
                contradicting = [
                    _ev(c.source_id, c.source_type, 0.9,
                        f"{c.source_id} records {attr.replace('_', ' ')} as {c.value}",
                        entity_ids=[eid])
                    for c in rows
                ]
                scored = assess(base, support, contradicting)
                node = self.cg.G.nodes.get(eid, {})
                out.append({
                    "type": "identity_conflict",
                    "severity": scored["severity"],
                    "title": f"Identity consistency warning for {self.label(eid)}",
                    "description": (
                        f"Records resolved into {self.label(eid)} disagree on "
                        f"{attr.replace('_', ' ')}: "
                        + "; ".join(f"{c.source_id} gives {c.value}" for c in rows)
                        + ". The merge was made on "
                        + (", ".join(node.get("merge_evidence", [])[:2]) or "name similarity")
                        + ". The identity is left intact for review."
                    ),
                    "entity_ids": [eid],
                    "entity_labels": [self.label(eid)],
                    "affected_relationships": [],
                    "events": [{"attribute": attr, "value": c.value,
                                "source_id": c.source_id, "source_type": c.source_type}
                               for c in rows],
                    "basis": {
                        "rule": f"records merged into one identity disagree on {attr}",
                        "attribute": attr,
                        "values": sorted(values),
                        "merge_evidence": node.get("merge_evidence", []),
                        "aliases": node.get("aliases", []),
                    },
                    "supporting_evidence": support,
                    "contradicting_evidence": contradicting,
                    "assessment": scored,
                    "possible_explanations": [
                        "Two different people share a name and an identifier was "
                        "wrongly treated as shared.",
                        f"The subject's {attr.replace('_', ' ')} changed between the "
                        "two records.",
                        "One record contains a data-entry error.",
                        "The merge was correct and the attribute was never updated.",
                    ],
                    "recommended_verification": [
                        "Re-check the identifier that drove the merge.",
                        f"Confirm {attr.replace('_', ' ')} against the originating "
                        "record for each source.",
                    ],
                })
        return out

    @staticmethod
    def _ranges_overlap(values: set[str]) -> bool:
        """True when every 'YYYY-YYYY' range in `values` shares at least one year."""
        spans = []
        for v in values:
            parts = [p for p in str(v).replace("–", "-").split("-") if p.strip().isdigit()]
            if not parts:
                return False
            years = [int(p) for p in parts]
            spans.append((min(years), max(years)))
        lo = max(s[0] for s in spans)
        hi = min(s[1] for s in spans)
        return lo <= hi

    # ------------------------------------------------------------- driver
    def run_all(self) -> list[dict]:
        self.skipped = []
        findings = (self.timeline_conflicts()
                    + self.location_inconsistencies()
                    + self.vehicle_association_conflicts()
                    + self.device_conflicts()
                    + self.identity_conflicts())
        order = {"high": 0, "medium": 1, "low": 2}
        # Deterministic: severity, then type, then the title. Two runs over the
        # same corpus must produce the same ids, or nothing downstream can cite
        # a contradiction by number.
        findings.sort(key=lambda f: (order.get(f["severity"], 3), f["type"], f["title"]))
        for i, f in enumerate(findings, 1):
            f["id"] = f"C{i:03d}"
        return findings


def detect_contradictions(case_graph) -> tuple[list[dict], list[dict]]:
    """Findings plus the pairs that were examined and deliberately not flagged."""
    engine = ContradictionEngine(case_graph)
    return engine.run_all(), engine.skipped
