# The Contradiction Engine

## 1. Purpose

Everything else in NEXUS is built to *find* connections. This engine is built to
argue with them.

A system that only accumulates supporting evidence will always grow more
confident, because nothing in it is looking for the record that does not fit.
That is how an investigation acquires a comfortable theory and stops testing it.
The contradiction engine searches the same corpus for records that cannot
comfortably all be true, and revises the affected confidence downward with the
working shown.

It answers a different question from the rest of the platform:

> Not *"what supports this?"* but *"what argues against it, and how much does
> that cost the conclusion?"*

Three constraints hold everywhere in this module:

1. **Nothing is asserted that a record does not say.** Every contradiction
   carries the source ids on both sides, and the API returns the original
   document for any of them.
2. **Insufficient evidence is not a contradiction.** Where the timing is known
   only to the day, or a coordinate is missing, the engine reports that it
   declined to draw a conclusion. Those pairs appear in `skipped`, never in
   `items`.
3. **The engine never resolves the conflict and never mutates the graph.** It
   does not decide which record is wrong. It lists the possible explanations and
   leaves the judgement to the investigator.

> The engine produces **investigative leads**. It does not determine guilt, it
> does not decide that a person is lying, and it does not declare any record
> false.

## 2. Contradiction types

| Type | The question it asks | Fires on |
|---|---|---|
| `timeline_conflict` | Do two records place a subject further apart than the time between them allows? | Consecutive time-precise sightings whose implied speed exceeds the threshold |
| `location_inconsistency` | Do two source systems place one subject in two places at overlapping times? | The same geometry, but where the two sightings come from *different* systems |
| `vehicle_association_conflict` | Is one vehicle recorded with two subjects inside a window, with no transfer record? | Two subjects, one vehicle, within `VEHICLE_WINDOW_HOURS`, no transfer relationship |
| `device_conflict` | Is one handset attributed to two subjects whose names do not otherwise agree? | A handset claimed by two name forms the resolver's own matcher would not join |
| `identity_conflict` | Do records merged into one identity disagree on a core attribute? | Two merged records giving different `police_district`, `date_of_birth`, `address` |

Timeline and location conflicts share their geometry but are reported
separately on purpose. When two records from one machine-generated source
disagree, the useful statement is that the movement is impossible. When two
different systems disagree, the useful statement is that *the sources disagree*
— and neither is assumed correct.

### Why `device_conflict` is framed as a merge problem

Identity resolution merges on a shared identifier unconditionally
(`pipeline/resolve.py`, step 1). By the time the graph exists, two people
recorded with the same number are already one node — the conflict has been
absorbed rather than resolved.

So the detectable signal is *the merge itself*: a subject assembled only because
two records quote the same handset, where the two name forms score below the
resolver's own `NAME_MATCH_THRESHOLD`. This is what keeps the check quiet on the
corpus's real cross-script pairs — "Sanjay Bhosle" and "संजय भोसले" share a
number and are the same person, the phonetic matcher agrees, and nothing is
raised.

The engine reports the questionable merge. It never splits the entity.

## 3. Data inputs

`observations.py` turns the ingested corpus into four families of *claim*, each
still carrying the record it came from:

| Claim | Meaning | Derived from |
|---|---|---|
| `Sighting` | this entity was at this place at this time | CDR rows; location relations from FIR / surveillance / social text |
| `DeviceClaim` | this handset belongs to this entity | the explicit ownership cues ingestion already extracts |
| `VehicleClaim` | this entity was recorded with this vehicle | vehicle relations from narrative sources |
| `AttributeClaim` | this record gives this entity this attribute value | per-observation attrs kept by the resolver |

### Time precision — the load-bearing idea

Most FIR and surveillance records in the corpus are stamped with the moment the
document was *filed*, not the moment the event happened. Every FIR in Operation
Meridian carries `08:00:00`.

Reading those as observation times manufactures contradictions out of nothing: a
single FIR naming three locations becomes three "impossible journeys" between
them. Every sighting therefore carries an explicit precision:

| Precision | Meaning | May support a timing conflict |
|---|---|---|
| `exact` | a timestamped machine record (a CDR call start) | yes |
| `stated` | a clock time written in the narrative — "at 2340 hrs" | yes, widened by ±15 min |
| `document` | only the document's own date is known | **no** |

A stated time is only accepted when the narrative actually names the place it is
being attached to. Without that rule a report's single clock reading would be
stamped onto every location it mentions — and the engine would flag its own
parsing artefact as a conflict.

## 4. Scoring logic

The output is never a bare percentage. What is scored is **not guilt and not the
truth of any statement**, but *how well the surviving evidence supports the
recorded link*. The engine calls this an **evidence-supported relationship
confidence**; it carries no evidentiary or legal meaning.

Each record contributes:

```
weight = reliability(source_type) × record_confidence × diminishing(k)
```

`diminishing(k)` is `1/√k` for the k-th record from the same source system.
Twenty calls on one CDR are strongly correlated and are not twenty independent
confirmations, so the twentieth counts for about a fifth of the first.

```
support_score       = Σ weight over supporting records
contradiction_score = Σ weight over contradicting records
contradiction_ratio = contradiction_score / (support_score + contradiction_score)

adjusted_confidence = base_confidence × (1 − CONFIDENCE_IMPACT_CAP × ratio)
```

`CONFIDENCE_IMPACT_CAP` is 0.45. **The cap is deliberate**: conflicting evidence
weakens a conclusion, it does not delete the evidence supporting it, so this
engine can never drive a confidence to zero. At most it removes 45% of it.

Severity follows the ratio — `high` ≥ 0.50, `medium` ≥ 0.25, `low` below — except
that a timeline conflict at more than twice the speed threshold is always `high`.

Every finding returns the full per-record breakdown under `assessment.terms`, so
the arithmetic can be checked rather than trusted.

## 5. Source reliability

Prototype weights, configurable in `intelligence/config.py`. **These are not a
legal or real-world reliability ranking** and carry no evidentiary standing. A
deployment replaces them with values its own jurisdiction and data quality
justify.

```python
SOURCE_RELIABILITY = {
    "cdr": 1.00, "transaction": 1.00,   # machine-generated
    "surveillance": 0.90,                # an officer's own observation
    "criminal_record": 0.90,
    "fir": 0.80,                         # a filed record parsed as text
    "fir_scan": 0.70,                    # recovered by OCR
    "social_media": 0.55,                # open source, unverified
    "inferred": 0.50,                    # produced by the system, not observed
}
```

The ordering is what does the work: a conflict raised by call records moves
confidence further than the same conflict raised by a social-media post.

## 6. False-positive handling

A false positive costs an investigator hours; in this domain it can cost a
person their liberty. Every control below exists because a naive version of this
engine produced a wrong answer during development.

| Control | What it prevents |
|---|---|
| Document-level timestamps cannot raise timing conflicts | An FIR naming three places becoming three impossible journeys |
| A stated time needs its place named nearby | One clock reading stamped onto every location in a report |
| Two claims from the same record are never compared | A single narrative read as evidence against itself |
| `MIN_SEPARATION_KM` (1.5 km) | A handset switching between adjacent towers read as travel |
| Clock-skew tolerance applies only *between* systems | Discarding a real conflict inside one machine-generated source |
| ±15 min slack on stated times | An officer's rounding read as a conflict |
| `VEHICLE_WINDOW_HOURS` (12 h) | Ordinary changes of driver flagged as disputes |
| Transfer-relationship exemption | A recorded handover flagged as a conflict |
| Name clustering before device comparison | Cross-script spellings of one person read as two claimants |
| Active-period overlap check | A widened date range read as a disagreement |

Where information is insufficient the engine says so. `skipped` is returned by
the API and rendered in the UI, because an investigator should be able to see
where the engine declined to draw a conclusion, not only where it did.

On the Operation Meridian corpus the engine currently examines ~82 candidate
pairs and reports 5.

## 7. API

```
GET /api/contradictions?severity=&type=
GET /api/contradictions/{contradiction_id}
```

Both follow the existing conventions in `main.py`: permission check, audit
entry, then answer. The listing requires `graph:read`; the detail view requires
`evidence:read` because it returns source documents.

The listing returns `items`, `counts_by_type`, `counts_by_severity`, the
`skipped` pairs, the active `config` thresholds, and a `disclaimer`. Thresholds
travel with the findings deliberately — a rule the caller cannot see is not
reviewable.

Each item carries:

```
id, type, severity, title, description
entity_ids, entity_labels, affected_relationships
events[]                     the records in conflict
basis                        the rule that fired, with its numbers
supporting_evidence[]        source_id, record_id, source_type, confidence, detail
contradicting_evidence[]     same shape
assessment                   scores, before/after confidence, per-record terms, formula
possible_explanations[]      listed, never ranked
recommended_verification[]
```

The detail endpoint adds `documents`, keyed by source id, so the evidence drawer
can show the original record without a round trip per item.

## 8. Example output

```json
{
  "id": "C001",
  "type": "timeline_conflict",
  "severity": "high",
  "title": "Timeline conflict for Rajesh Kumar Singh between Kurla and Ghatkopar",
  "description": "Rajesh Kumar Singh is placed at Kurla at 22:12 and at Ghatkopar at 22:13 on 2026-05-23. The two points are 3.7 km apart with 1 minute(s) between them, an implied 367 km/h. Ordinary ground travel would need about 2 minutes.",
  "basis": {
    "rule": "implied speed > 120 km/h between consecutive time-precise sightings",
    "distance_km": 3.67, "interval_minutes": 0.6,
    "implied_speed_kmph": 366.8, "reasonable_travel_minutes": 1.8
  },
  "contradicting_evidence": [
    {"source_id": "CDR", "record_id": "C000054", "source_type": "cdr", "confidence": 0.95,
     "detail": "Handset 9000000002 active on the Kurla cell site at 22:12 on 2026-05-23 (call C000054)"},
    {"source_id": "CDR", "record_id": "C000017", "source_type": "cdr", "confidence": 0.95,
     "detail": "Handset 9000000002 active on the Ghatkopar cell site at 22:13 on 2026-05-23 (call C000017)"}
  ],
  "assessment": {
    "support_score": 6.6449, "contradiction_score": 1.6218,
    "contradiction_ratio": 0.1962,
    "confidence_before": 0.85, "confidence_after": 0.775
  },
  "possible_explanations": [
    "A timestamp on one of the two records is wrong.",
    "The two records describe different people and an identity was merged in error.",
    "A handset was carried or used by someone else.",
    "A cell site or coordinate is mis-recorded."
  ]
}
```

## 9. Architecture

```
Evidence  (FIR · CDR · surveillance · transactions · social · criminal records)
   |
   v
Ingestion + extraction + identity resolution        [existing NEXUS pipeline]
   |
   +--> Graph  (entities, relationships, provenance) [existing]
   |
   v
Claim extraction            observations.py
   Sighting · DeviceClaim · VehicleClaim · AttributeClaim
   each carrying source_id, source_type, time_precision
   |
   v
Consistency checks          contradiction_engine.py
   |-- Timeline      implied speed vs configured threshold
   |-- Location      two systems, overlapping times
   |-- Vehicle       one asset, two subjects, no transfer
   |-- Device        one handset, two dissimilar names
   +-- Identity      merged records disagreeing on an attribute
   |
   v
Contradiction scoring       scoring.py
   support vs contradiction, weighted by source reliability
   -> adjusted confidence, capped
   |
   v
Evidence provenance         both sides, every source id resolvable to a document
   |
   v
API  /api/contradictions    -> Investigator UI  (analysis > Conflicts)
```

The engine is a service, not route logic: `ContradictionEngine(case_graph)` is
constructible anywhere. The API layer only filters and serialises.

## 10. Limitations

Stated honestly, because a tool that hides its blind spots is worse than one
that has none.

- **It cannot read most narrative times.** Only clock times in `HHMM hrs` form,
  next to a named place, are recognised. Everything else stays document-level
  and can never raise a timing conflict — the engine is far more likely to miss
  a real contradiction than to invent one, which is the correct direction to
  fail in, but it *is* a miss.
- **Distances are straight-line.** There is no road network and no traffic
  model, so the speed threshold is generous to compensate. A conflict that
  depends on the actual road distance will not be found.
- **Locations are points standing in for areas.** A cell site covers a sector,
  not a coordinate; "Dongri" is a neighbourhood, not a spot.
- **It cannot detect a contradiction between two claims it never extracted.**
  Anything the NER and cue patterns miss is invisible to it.
- **`identity_conflict` only compares four attributes,** and only where the
  resolver recorded them per observation.
- **Source reliability weights are prototype values,** not a real-world ranking.
- **It cannot tell which record is wrong.** By design — but it means a
  contradiction never resolves itself, and every finding needs a human.
- **Semantic contradictions are out of scope.** Two statements that disagree in
  meaning ("he was alone" / "three men were present") are not detected; the
  engine reasons over structured claims, not prose.

## 11. Test data

`data/contradiction_scenarios.json` holds a small set of clearly labelled
synthetic records. The Operation Meridian corpus contains exactly one naturally
occurring contradiction — the 367 km/h CDR pair — so the other four types would
have nothing to fire on without them.

They are **ordinary evidence records, not pre-baked contradictions**. Each goes
through the same ingestion, extraction and resolution as every real source, and
the engine has to find the conflict for itself. Deleting the file removes those
findings and changes no engine behaviour. Synthetic ids carry a `/T` prefix or a
`CR9xxx` number so they are identifiable at a glance in the UI and the audit log.

## 12. Future improvements

- ~~Evidence Impact Simulator~~ — **built**, see `docs/IMPACT_SIMULATOR.md`. It
  consumes this engine's provenance directly: the evidence drawer seeds a
  simulation with exactly the records a contradiction cites.
- Road-network travel times in place of straight-line distance.
- Location uncertainty radii per source type, so a cell sector is not treated as
  a point.
- A wider time-expression grammar ("late evening", "shortly after midnight").
- Contradiction *resolution* tracking: let an investigator record which
  explanation was confirmed, and feed that back into the confidence.
- Semantic contradiction detection over narrative text.
