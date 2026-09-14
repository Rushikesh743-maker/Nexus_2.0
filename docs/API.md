# NEXUS — Platform API (`/api/v1`)

Base URL: `/api/v1` (served by `backend/`; in development the Vite server
proxies `/api` → `http://127.0.0.1:8000`).

All timestamps are UTC ISO-8601. All JSON bodies are UTF-8.

## Authentication

JWT bearer tokens, HS256, signed with `JWT_SECRET`.

| Endpoint | Method | Body | Result |
| --- | --- | --- | --- |
| `/auth/login` | POST | `{"email": "name@domain", "password": "…"}` | `200 {"access_token", "token_type": "bearer", "user"}` |
| `/auth/me` | GET | — (bearer) | `200 UserOut` |

Login rules:

- Unknown email and wrong password both return `401 INVALID_CREDENTIALS`
  (indistinguishable by design).
- Malformed email shape → `422 VALIDATION_ERROR`.
- Token header: `Authorization: Bearer <token>`.
- Missing/invalid/expired token → `401 UNAUTHENTICATED` with a structured
  body (below).

Roles: `INVESTIGATOR` (cases read, simulation create), `ANALYST` (same),
`SUPERVISOR` (adds `/users` read), `ADMIN` (all).

## Error shape

Every non-2xx response is:

```json
{ "error": { "code": "CASE_NOT_FOUND", "message": "No case with this id." } }
```

Common codes: `UNAUTHENTICATED`, `FORBIDDEN`, `INVALID_CREDENTIALS`,
`VALIDATION_ERROR`, `CASE_NOT_FOUND`,
`DOCUMENT_INVALID`, `DOCUMENT_UNSUPPORTED_TYPE`, `DOCUMENT_TOO_LARGE`,
`DOCUMENT_DUPLICATE`, `DOCUMENT_NOT_FOUND`, `DOCUMENT_PROCESSING`,
`DOCUMENT_ALREADY_PROCESSED`, `ENTITY_NOT_FOUND`, `MATCH_NOT_FOUND`,
`RELATIONSHIP_NOT_FOUND`, `CANDIDATE_NOT_CONFIRMED`, `MATCH_REVIEW_REQUIRED`.

## Health

`GET /health` (no auth) →

```json
{
  "status": "ok",
  "version": "0.2.0",
  "environment": "development",
  "database": { "connected": true, "driver": "psycopg", "sqlalchemy": "2.0.52" },
  "storage": { "backend": "local", "ok": true },
  "worker": { "enabled": true, "queue": { "pending": 0 } },
  "synthetic_data_only": true
}
```

There is no graph database to health-check: graph intelligence is computed
in-process with NetworkX over the relational rows.

## Users (SUPERVISOR+)

- `GET /users` → `list[UserOut]`
- `GET /users/{id}` → `UserOut`

`UserOut`: `id, officer_id, name, email, role, created_at`.

## Cases

### `GET /cases` → `list[CaseListItem]`

`CaseListItem` = case columns + `created_by_name` + `counts`
(documents, entities, relationships, evidence, timeline_events, locations,
hypotheses, contradictions, gaps, simulations) + `latest_event_at`.

### `POST /cases` (INVESTIGATOR+)

Body: `{"title": "…", "status": "OPEN|ACTIVE|ON_HOLD|CLOSED|ARCHIVED",
"priority": "LOW|MEDIUM|HIGH|CRITICAL", "description": "…?"}` —
`case_number` is generated (`CASE-YYYY-NNN`, next free).

### `GET /cases/{case_id}` → `CaseDetail`

`CaseListItem` fields plus:

- `key_entities`: up to 25 — `{id, type, canonical_name, aliases,
  connection_count, metadata}`
- `cross_case_links`: `{case_id, case_number, title, status,
  shared_entities[], shared_count}` — cases sharing at least one
  canonical entity name (case-insensitive)
- `latest_events`: up to 8 most recent timeline events as
  `{id, event_type, timestamp, description}`

### Sub-resources (all `GET /cases/{case_id}/…`, bearer)

| Path | Returns | Notes |
| --- | --- | --- |
| `/documents` | `list[DocumentOut]` | `id, filename, file_type, file_size, mime_type, file_hash, uploaded_by_name, uploaded_at, processing_status, processed_at, processing_error, extracted_entities, extracted_relationships, pending_review` |
| `/entities` | `list[EntityOut]` | `id, entity_type, canonical_name, metadata (JSON), created_at` |
| `/relationships` | `list[RelationshipOut]` | `id, source_entity_id, target_entity_id, relationship_type, confidence, metadata, source_label, target_label` |
| `/evidence` | `list[EvidenceOut]` | `id, document_id, document_filename, evidence_type, description, source_reference, confidence` |
| `/timeline` | `list[TimelineEventOut]` | chronological, `timestamp` nullable |
| `/locations` | `list[LocationOut]` | `id, name, latitude?, longitude?, metadata (JSON)` |
| `/hypotheses` | `list[HypothesisOut]` | `title, description, score?, status` |
| `/contradictions` | `list[ContradictionOut]` | `title, description, severity, status` |
| `/gaps` | `list[GapOut]` | `title, description, priority, status` |
| `/simulations` | `list[SimulationOut]` | `name, description, created_at` |

### `POST /cases/{case_id}/simulations` (INVESTIGATOR+)

Body: `{"name": "…", "description": "…?"}` → `201 SimulationOut`.
The counterfactual scoring engine is a later stage; the record is real.

## Documents (stage 2 — ingestion, extraction, review)

All endpoints are bearer-authenticated. Every role can upload and review
(INVESTIGATOR/ANALYST explicitly, SUPERVISOR/ADMIN by the role ladder).
The filesystem path of a stored file is **never** returned; only metadata.

### Upload

`POST /cases/{case_id}/documents` — multipart form, field `file`.

- Accepted: `.pdf`, `.txt`, `.csv` (≤ `MAX_UPLOAD_MB`, default 10 MB).
- Validation: extension, contradicting MIME, empty file, missing `%PDF`
  header for `.pdf`, non-UTF-8/containing NUL bytes for `.txt`, missing
  header commas for `.csv`. Each failure is a structured `400`.
- SHA-256 of the exact bytes is computed while streaming (never the whole
  file in memory); a duplicate content for the same case →
  `409 DOCUMENT_DUPLICATE` with `existing_document_id`.
- The file is written to `storage/documents/{case_id}/{doc_id}_{safe_stem}.ext`
  (server-generated name; the client filename is display metadata only) and
  the row is committed atomically with it.
- Processing starts automatically in a background task; the response is
  `201 DocumentOut` with `processing_status: "UPLOADED"`.

Codes: `DOCUMENT_UNSUPPORTED_TYPE`, `DOCUMENT_INVALID`,
`DOCUMENT_DUPLICATE`, `CASE_NOT_FOUND`, `UNAUTHENTICATED`.

### Status & processing

| Endpoint | Method | Result |
| --- | --- | --- |
| `/documents/{id}` | GET | `200 {document, summary}` — detail + extraction summary |
| `/documents/{id}/status` | GET | `200 {id, case_id, filename, processing_status, processed_at, processing_error, summary}` |
| `/documents/{id}/process` | POST | `202` — start or **retry** processing (own session, background task) |

Lifecycle (real, pollable — no invented progress):
`UPLOADED → PROCESSING → PROCESSED | FAILED`. `FAILED` carries a user-safe
`processing_error` (no tracebacks, no filesystem paths) and can be retried
with `POST /process`; reprocessing is idempotent (a candidate with the same
type, name and source location is never duplicated).
`PROCESSED` + `POST /process` → `409 DOCUMENT_ALREADY_PROCESSED`;
`PROCESSING` + `POST /process` → `409 DOCUMENT_PROCESSING`.

Codes: `DOCUMENT_NOT_FOUND`, `DOCUMENT_ALREADY_PROCESSED`,
`DOCUMENT_PROCESSING`.

### Extraction results

`GET /documents/{id}/extraction` →

```
{
  "summary":   { source_type, stats, entities, relationships, matches,
                 pending, accepted, rejected, evidence_generated },
  "entities":  [ { id, entity_type, candidate_name, aliases, confidence,
                   source_location {page|row|column|line}, source_snippet,
                   extraction_method, status, accepted_entity_id,
                   match {id, existing_entity_id, existing_entity_name,
                          similarity, reasons[], status} | null } ],
  "relationships": [ { id, source_candidate_id, target_candidate_id,
                       source_name, target_name, relationship_type,
                       confidence, source_location, source_snippet,
                       extraction_method, status, endpoints_confirmed } ],
  "matches":   [ { id, candidate_id, existing_entity_id,
                   existing_entity_name, similarity, reasons[], status } ]
}
```

Provenance rule: every candidate carries the document page (PDF),
line (TXT) or row+column (CSV) it came from plus a snippet. A location the
extractor could not determine is represented as missing — never invented.

### Review workflow

| Endpoint | Method | Effect |
| --- | --- | --- |
| `…/extraction/candidates/{id}/accept` | POST | Candidate → `ACCEPTED`; links or creates the confirmed `Entity`; adds an `Evidence` row (`source_reference = "candidate:{id}"`); event candidates also create a `TimelineEvent` |
| `…/extraction/candidates/{id}/reject` | POST | Candidate → `REJECTED` (kept for audit); pending relationships on that endpoint are auto-rejected |
| `…/extraction/candidates/{id}/defer` | POST | Candidate → `DEFERRED` (review later) |
| `…/extraction/relationships/{id}/accept` | POST | Both endpoints must be `ACCEPTED` first, else `409 CANDIDATE_NOT_CONFIRMED`; creates the confirmed `Relationship` (deduped per case+endpoints+type) + `Evidence` |
| `…/extraction/relationships/{id}/reject` | POST | Candidate → `REJECTED` |
| `…/extraction/matches/{id}/accept` | POST | Folds the candidate into the existing entity (alias), confirms the candidate, adds `Evidence` |
| `…/extraction/matches/{id}/reject` | POST | Candidate stays independent (still reviewable) |

Guards: accepting a candidate with a pending match →
`409 MATCH_REVIEW_REQUIRED`; re-reviewing a decided candidate/match →
`409 CANDIDATE_ALREADY_REVIEWED` / `409 MATCH_ALREADY_REVIEWED`.
Reject bodies accept an optional `{"note": "…", "max_length 255"}`.

Codes: `ENTITY_NOT_FOUND`, `RELATIONSHIP_NOT_FOUND`, `MATCH_NOT_FOUND`,
`MATCH_REVIEW_REQUIRED`, `MATCH_NOT_ALLOWED`, `CANDIDATE_NOT_CONFIRMED`,
`CANDIDATE_ALREADY_REVIEWED`, `MATCH_ALREADY_REVIEWED`.

### Audit

Every step writes an `audit_log` row (actor, case, object id, UTC time,
structured metadata — no secrets, no raw document content):
`DOCUMENT_UPLOADED`, `DOCUMENT_PROCESSING_STARTED/COMPLETED/FAILED`,
`PROCESS_REQUESTED`, `ENTITY_ACCEPTED/REJECTED/DEFERRED`,
`RELATIONSHIP_ACCEPTED/REJECTED`, `ENTITY_MATCH_ACCEPTED/REJECTED`.


## Graph intelligence (stage 3 — analysis, findings, paths)

All routes are case-scoped, bearer-authenticated, and run over **confirmed
data only** (extraction candidates never influence results). Every response
carries a `graph_version` — a deterministic hash of the confirmed entities +
relationships the analysis ran on; findings from an older version are
returned flagged `stale` (kept, never deleted).

### `POST /cases/{case_id}/graph/analyze` (ANALYST+)

Runs the engine, persists findings (versioned, idempotent while the data is
unchanged → `recomputed: false`).

```json
{ "recomputed": true, "graph_version": "754981fcf3712440",
  "graph": { "nodes": 10, "edges": 4 },
  "findings": [ /* GraphFindingOut, below */ ] }
```

Errors: `CASE_NOT_FOUND` 404 · `GRAPH_INSUFFICIENT_DATA` 409 (no confirmed
graph data, or < 3 entities / < 2 relationships) · `GRAPH_ANALYSIS_FAILED`
500 (audited as `GRAPH_ANALYSIS_FAILED`).

### `GET /cases/{case_id}/graph/findings`

→ `{ graph_version, analyzed, current_findings: [GraphFindingOut],
stale_findings: [GraphFindingOut] }` (add `?include_stale=false` to omit
history).

`GraphFindingOut`:

```json
{ "id": 12, "case_id": 1,
  "finding_type": "BRIDGE_ENTITY",
  "title": "Potential bridge entity: Aarav Mehta",
  "summary": "…",
  "explanation": ["…computed reason bullets…"],
  "details": { "…structured payload (paths, metrics, members)…": {} },
  "involved_entity_ids": [1],
  "supporting_relationship_ids": [1, 2],
  "supporting_evidence_ids": [101],
  "related_case_ids": [],
  "analysis_method": "articulation+betweenness v1 (…documented formula…)",
  "graph_version": "754981fcf3712440",
  "stale": false,
  "status": "ACTIVE",
  "reviewed_by_name": null, "reviewed_at": null, "review_note": null,
  "created_at": "2026-09-07T09:00:00Z" }
```

`finding_type` ∈ `HIDDEN_CONNECTION`, `BRIDGE_ENTITY`,
`CROSS_CASE_CONNECTION`, `NETWORK_CLUSTER`, `HIGH_CONNECTIVITY`.
`status` ∈ `ACTIVE`, `REVIEWED`, `DISMISSED`.

### `POST /cases/{case_id}/graph/findings/{finding_id}/review` (ANALYST+)
### `POST /cases/{case_id}/graph/findings/{finding_id}/dismiss` (ANALYST+)

Optional body `{ "note": "…" }` (≤ 255 chars). Sets `REVIEWED` /
`DISMISSED`, records reviewer + note, and audits `FINDING_REVIEWED` /
`FINDING_DISMISSED`. Re-reviewing a settled finding → 409
`FINDING_REVIEW_NOT_ALLOWED`. Findings are never deleted; dismissed rows
stay queryable. Errors: `FINDING_NOT_FOUND` 404 (also when the finding
belongs to a different case).

### `GET /cases/{case_id}/graph/metrics`

→ `{ graph_version, nodes, edges, metrics: [{ entity_id, name, entity_type,
degree, weighted_degree, betweenness, component_size, cross_case_reach,
is_articulation_point, neighbor_types }] }`. `weighted_degree` counts each
adjacent relationship as 1 + its directly-linked evidence records
(documented; analytical context, not proof).

### `GET /cases/{case_id}/graph/bridges`

→ `{ graph_version, nodes, edges, insufficient, bridges: [{ entity_id,
name, entity_type, degree, is_articulation_point, betweenness,
connectivity_impact, cross_case_reach, bridge_score, reasons }] }`.
Score = `0.45·betweenness + 0.35·connectivity-impact + 0.20·cross-case-
reach` (normalized in-graph); reported only for degree ≥ 2 and score ≥
0.25. An empty list is a real answer ("no significant bridge entities"),
not a failure.

### `GET /cases/{case_id}/graph/clusters`

→ `{ graph_version, clusters: [{ index, node_ids, members, entity_ids,
entity_count, relationship_count, type_breakdown, case_ids, cross_case,
key_bridge, subgroups, description }] }` (connected components, largest
first; neutral labels only).

### `GET /cases/{case_id}/graph/cross-case`

→ `{ graph_version, connections: [{ case_id, case_number,
connection_kind: "shared_entity" | "shared_path", shared_entities: [{name,
entity_type, entity_ids}], example_path: [{name, entity_type, case_id,
shared}], example_path_relationships, evidence_count, explanation }] }`.
Only confirmed same-(type, normalized-name) links; same name with a
different type is not shared.

### `GET /cases/{case_id}/graph/paths?source_entity_id=&target_entity_id=&max_depth=4&max_paths=5`

→ `{ graph_version, source, target, max_depth, paths: [{ path_length,
nodes: [{entity_id, name, entity_type}], relationship_types,
relationship_ids, evidence_count, explanation }] }`. Bounded BFS shortest
paths, cycle-free. Errors: `ENTITY_NOT_FOUND` 404 · `ENTITY_NOT_CONFIRMED`
400 (the id is an extraction candidate) · `INVALID_PATH_REQUEST` 400
(same entity) · `PATH_NOT_FOUND` 404 ("No confirmed connection path
found.").

### Audit

`GRAPH_ANALYSIS_STARTED`, `GRAPH_ANALYSIS_COMPLETED` (with finding counts
per type and `recomputed`), `GRAPH_ANALYSIS_FAILED` (with safe error
reason), `FINDING_REVIEWED`, `FINDING_DISMISSED` — actor, case, finding
id, note, UTC time; no secrets.

## Investigation intelligence (stage 4 — reasoning & evidence intelligence)

All routes are case-scoped under `/cases/{case_id}/investigation/…` and
reason over **confirmed data only** (entities, relationships, evidence,
timeline events, locations). Extraction candidates, rejected/pending
review items and unresolved match suggestions never enter the analysis
and are never promoted. Every result is a named deterministic
algorithm's output with a computed-value explanation; language is
neutral ("potential contradiction", "analytical support", "requires
review" — never "proves"/"guilty").

Role floor: reads for **ANALYST+**; `analyze`, hypothesis create and
all review/dismiss actions for **INVESTIGATOR+**.

### `POST /cases/{case_id}/investigation/analyze` (INVESTIGATOR+)

Runs the full analysis (contradictions, hypotheses, gaps; timeline,
geospatial and evidence-impact are computed on read). Idempotent per
confirmed-data snapshot: same data → no recompute
(`recomputed: false`, findings unchanged). Returns:

```json
{
  "case_id": 6,
  "graph_version": "sha256:<64 hex>",
  "recomputed": true,
  "findings": [ /* InvestigationFinding objects, see below */ ],
  "findings_by_type": {"CONTRADICTION": 3, "TIMELINE_INSIGHT": 2,
                       "GEO_INSIGHT": 3, "INVESTIGATION_GAP": 1},
  "hypotheses": 8,
  "duration_ms": 412,
  "status": "up-to-date"
}
```

`graph_version` is the extended stage-4 snapshot hash (entities +
relationships + evidence + timeline events + locations), so a change in
any confirmed record flags the analysis `stale`.

### `GET /cases/{case_id}/investigation/status`

```json
{
  "case_id": 6,
  "state": "not-analyzed | up-to-date | stale | insufficient",
  "graph_version": "sha256:<hex>",
  "analyzed": true,
  "reason": "…human-readable explanation…",
  "current_findings": 9,
  "stale_findings": 0,
  "hypotheses": 8,
  "insufficient": false,
  "timeline": {"events_total": 6, "events_with_timestamp": 6,
               "events_without_timestamp": 0},
  "geospatial": {"locations_total": 4, "locations_with_coords": 4}
}
```

`state` is `insufficient` when the case has no confirmed entities or
relationships (the frontend maps this to its insufficient state).

### `GET /cases/{case_id}/investigation/findings?include_stale=true`
### `GET /cases/{case_id}/investigation/contradictions?include_stale=true`
### `GET /cases/{case_id}/investigation/gaps?include_stale=true`

Same envelope for all three (the last two filter to the `CONTRADICTION`
and `INVESTIGATION_GAP` types):

```json
{
  "case_id": 6,
  "findings": [
    {
      "id": 31,
      "finding_type": "CONTRADICTION",
      "title": "Potential timeline contradiction: A. K. …",
      "summary": "…neutral-language description…",
      "explanation": ["R1 … computed value …", "…"],
      "details": {"rule": "R1", "contradiction_type": "TIMELINE_CONTRADICTION",
                  "severity": "HIGH", "entities": [33, 34],
                  "events": [51, 52], "distance_km": 118.581,
                  "available_minutes": 20, "required_minutes": 71.1},
      "involved_entity_ids": [33, 34],
      "supporting_relationship_ids": [],
      "supporting_evidence_ids": [],
      "related_case_ids": [],
      "analysis_method": "contradiction-engine/R1",
      "graph_version": "sha256:<hex>",
      "is_stale": false,
      "status": "ACTIVE",
      "reviewed_by": null, "reviewed_at": null, "review_note": null
    }
  ],
  "total": 3,
  "current": 3,
  "stale": 0
}
```

Finding types: `CONTRADICTION` (rule in `details.rule` = R1/R2/R3,
`contradiction_type` = TIMELINE/LOCATION/RELATIONSHIP, severity
HIGH/MEDIUM), `TIMELINE_INSIGHT` (insight_type = EVENT_OVERLAP /
TEMPORAL_PROXIMITY / EVENT_SEQUENCE / TIMELINE_GAP), `GEO_INSIGHT`
(insight_type = CO_LOCATION / LOCATION_PROXIMITY / LOCATION_SEQUENCE),
`INVESTIGATION_GAP` (gap_type = EVIDENCE / RELATIONSHIP / TIMELINE /
IDENTITY).

### `GET /cases/{case_id}/investigation/hypotheses?include_stale=true`

```json
{
  "case_id": 6,
  "hypotheses": [
    {
      "id": 12,
      "title": "…competing explanation…",
      "description": "…",
      "hypothesis_type": "GENERATED_CONTRADICTION | GENERATED_STRUCTURE | INVESTIGATOR",
      "analytical_score": 0.71,
      "confidence_band": "HIGH",
      "score_components": {"evidence": 1.0, "relationships": 1.0,
                           "consistency": 1.0, "provenance": 0.5,
                           "connectivity": 0.6, "weights":
                           {"evidence": 0.30, "relationships": 0.20,
                            "consistency": 0.20, "provenance": 0.15,
                            "connectivity": 0.15}},
      "explanation": {"supporting": ["…"], "contradicting": ["…"]},
      "involved_entity_ids": [33, 34],
      "supporting_relationship_ids": [],
      "supporting_evidence_ids": [91, 92],
      "contradicting_evidence_ids": [],
      "supporting_finding_ids": [31],
      "status": "ACTIVE",
      "is_stale": false,
      "graph_version": "sha256:<hex>",
      "reviewed_by": null, "reviewed_at": null, "review_note": null
    }
  ],
  "total": 8,
  "disclaimer": "Scores express analytical support for the hypothesis based on the confirmed data in this case — not proof or a probability of guilt."
}
```

### `POST /cases/{case_id}/investigation/hypotheses` (INVESTIGATOR+)

Body: `{"title": "…", "description": "…", "involved_entity_ids": [..],
"supporting_evidence_ids": [..]}` → the new hypothesis, deterministically
scored against the confirmed snapshot (unknown entity/evidence ids →
`400 INVALID_FINDING_TYPE`). Investigator hypotheses persist across
re-analyses and are never deleted; statuses ACTIVE / REVIEWED /
DISMISSED.

### `GET /cases/{case_id}/investigation/evidence-impact`

Per-evidence summary for the case:

```json
{
  "case_id": 6,
  "evidence": [
    {"evidence_id": 91, "evidence_type": "SURVEILLANCE",
     "linked_entity_ids": [33], "linked_relationship_ids": [21],
     "linked_event_ids": [51], "cited_by_findings": 1,
     "cited_by_hypotheses": 2, "impact_score": 0.68,
     "impact_band": "HIGH",
     "sole_provenance_relationships": [21]}
  ],
  "total": 6,
  "analysis_method": "evidence-impact/0.5·graph+0.25·finding+0.25·hypothesis"
}
```

### `GET /cases/{case_id}/investigation/evidence/{evidence_id}/impact`

Single-record detail: the metrics above plus `impact_breakdown`
(graph/finding/hypothesis shares) and the computed `impact_score`.
Unknown id → `400 EVIDENCE_NOT_FOUND`.

### `POST /cases/{case_id}/investigation/evidence/{evidence_id}/simulate-impact` (INVESTIGATOR+)

In-memory removal simulation — **never deletes or modifies stored
data** (zero database writes; asserted in tests):

```json
{
  "case_id": 6, "evidence_id": 91,
  "simulation_only": true,
  "removed": {"evidence_id": 91,
              "relationships": [21],
              "events_without_provenance": []},
  "before": {"entities": 5, "relationships": 3, "max_degree": 3,
             "components": 1, "avg_betweenness": 0.33},
  "after":  {"entities": 5, "relationships": 2, "max_degree": 2,
             "components": 2, "avg_betweenness": 0.25},
  "changes": {"relationships_removed": 1,
              "components_increase": 1,
              "degree_decreased": [{"entity_id": 33, "before": 3, "after": 2}],
              "sole_provenance_relationships": [21]},
  "analysis_method": "evidence-simulation/in-memory-networkx"
}
```

Removal rule: a relationship loses its evidence support only when the
simulated evidence was its *sole* provenance (relationships with other
supporting evidence survive).

### `GET /cases/{case_id}/investigation/timeline`

```json
{
  "case_id": 6,
  "results": [
    {"insight_type": "EVENT_SEQUENCE", "entity_id": 33, "entity_name": "…",
     "event_ids": [51, 52, 53], "explanation": ["…computed…"],
     "details": {"sequence": [{"event_id": 51, "timestamp": "…",
                                "duration_minutes": 20}, …]}},
    {"insight_type": "TIMELINE_GAP", "entity_id": 33, "event_ids": [52, 53],
     "details": {"gap_hours": 15.2, "threshold_hours": 12}}
  ],
  "events_total": 6, "events_with_timestamp": 6,
  "events_without_timestamp": 0,
  "insufficient": false,
  "analysis_method": "timeline-engine/overlap+proximity+sequence+gap"
}
```

Insight types: EVENT_OVERLAP, TEMPORAL_PROXIMITY (≤ 30 min),
EVENT_SEQUENCE (≥ 3 dated events), TIMELINE_GAP (> 12 h — reported only
as a *potential investigation gap*). `insufficient: true` when fewer
than two dated events exist.

### `GET /cases/{case_id}/investigation/geospatial`

```json
{
  "case_id": 6,
  "results": [
    {"insight_type": "CO_LOCATION", "entity_ids": [33, 34],
     "location_ids": [71, 72], "distance_km": 0.03,
     "explanation": ["…haversine…"]}
  ],
  "observations": [
    {"entity_id": 33, "entity_name": "…", "location_id": 71,
     "location_name": "…", "latitude": 19.076, "longitude": 72.877,
     "timestamp": "2026-01-04T09:00:00Z", "source_event_id": 51,
     "source_relationship_id": null}
  ],
  "observations_count": 6,
  "location_data_insufficient": false,
  "analysis_method": "geospatial-engine/haversine"
}
```

Insight types: CO_LOCATION (< 0.05 km), LOCATION_PROXIMITY (≤ 2 km),
LOCATION_SEQUENCE (ordered distinct locations for one entity).
`location_data_insufficient: true` when fewer than two observations
have usable coordinates (the panel renders its explicit
LOCATION_DATA_INSUFFICIENT state). `observations` feed the frontend
Leaflet map.

### Review / dismiss (INVESTIGATOR+)

```
POST /cases/{case_id}/investigation/findings/{finding_id}/review
POST /cases/{case_id}/investigation/findings/{finding_id}/dismiss
POST /cases/{case_id}/investigation/hypotheses/{hypothesis_id}/review
POST /cases/{case_id}/investigation/hypotheses/{hypothesis_id}/dismiss
```

Body (optional): `{"note": "…"}`. Returns the updated object
(`status: REVIEWED` / `DISMISSED`, `reviewed_by`, `reviewed_at`,
`review_note`). Already-reviewed/dismissed rows → `409
FINDING_REVIEW_NOT_ALLOWED`. Wrong case scope → `404`. Nothing is ever
deleted.

### Structured errors (stage 4)

| HTTP | `error_code` | Raised when |
| --- | --- | --- |
| 404 | `CASE_NOT_FOUND` / `ENTITY_NOT_FOUND` / `HYPOTHESIS_NOT_FOUND` | id not in this case |
| 400 | `EVIDENCE_NOT_FOUND` | impact/simulate on an unknown evidence id |
| 400 | `INVALID_FINDING_TYPE` | investigator hypothesis referencing unknown entity/evidence |
| 409 | `INSUFFICIENT_CONFIRMED_DATA` | `analyze` on a case without confirmed graph data |
| 409 | `FINDING_REVIEW_NOT_ALLOWED` | re-review / re-dismiss |

### Audit

`INVESTIGATION_ANALYSIS_STARTED | COMPLETED | FAILED`,
`CONTRADICTION_DETECTED` (per finding), `INVESTIGATION_GAP_DETECTED`
(per finding), `TIMELINE_ANALYSIS_COMPLETED`, `GEO_ANALYSIS_COMPLETED`,
`EVIDENCE_IMPACT_ANALYZED`, `HYPOTHESIS_GENERATED` (per generated
hypothesis), `HYPOTHESIS_CREATED`, `HYPOTHESIS_REVIEWED`,
`HYPOTHESIS_DISMISSED` — actor, case, target id, note, UTC time; no
secrets. Finding reviews reuse the stage-3 `FINDING_REVIEWED` /
`FINDING_DISMISSED` actions.

## Case workflow (stage 6)

All case-scoped and case-access-checked: a caller without access to
the case gets **404** (existence is not leaked). Write actions are
INVESTIGATOR+, analysis is ANALYST+ (inherited).

### `GET /cases/{id}/summary`
Case header + real counts: documents / entities / relationships /
evidence / timeline events / locations / contradictions / hypotheses /
gaps / pending review.

### `GET /cases/{id}/review/queue`
Five categories, each item with provenance (source document, snippet,
page, confidence, extraction method): `entity_candidates` (new
entities), `entity_matches` (duplicate/match candidates),
`relationship_candidates` (**CANDIDATE by default** — never
auto-confirmed), `evidence_claims` (display-only, not decisions),
`contradictions`. `counts.total_pending` excludes evidence claims.

### `POST /cases/{id}/review/confirm` / `POST /cases/{id}/review/reject`
Body: `{category: "entity" | "relationship" | "entity_match",
item_ids: [..]}`. Entity confirm materialises the `Entity` row (plus
every confirmed relationship touching it); match confirm adds an
alias; relationship confirm upserts the `Relationship` row with
`metadata.confirmed = true` and provenance. Reject is terminal.
404 unknown item, 409 already decided, 422 bad category. Every
decision is audited.

### `POST /cases/{id}/graph/build` (ANALYST+) → `GET /cases/{id}/graph`
Builds the graph **only from confirmed case data** →
`{status, graph_version, nodes, edges}`. The GET payload carries
per-node `evidence_count` and per-edge provenance
(`source_document_name`, `source_snippet`, `source_evidence_id`,
`extraction_method`). A case with no confirmed data has no graph.

### `POST /cases/{id}/analysis/run` (ANALYST+)
Runs the existing engines (graph build → network → anomalies →
contradictions → hypotheses → timeline → geospatial → gaps → findings
persistence) over confirmed data.
`{status: "completed" | "no_changes", findings_count, analysis_id,
graph_version}`. 409 `INSUFFICIENT_CONFIRMED_DATA` when nothing is
confirmed. Idempotent: unchanged re-run → `no_changes`
(`recomputed: false`).

### `GET /cases/{id}/analysis/status`
`{state, graph_version, stale_reason, documents: {total,
by_status, all_processed}, pending_review: {…}, findings: {current,
stale}}`. `state` ∈ not-analyzed / up-to-date / **stale** (with
reason) / insufficient. Stale findings remain available (old
`graph_version`) — they are history, not garbage.

### `GET /cases/{id}/documents/processing/status`
Real per-document job state: per-document stage, progress,
started/finished, error (failed documents carry the real reason —
e.g. PDF with no extractable text), plus the case-level aggregate.
No fake percentages.

### `GET /cases/{id}/audit`
Read-only case audit trail (actor, action, target, metadata,
timestamp): creation, uploads, processing completion/failure,
confirm/reject, graph build, analysis run. No secrets in rows.

### Case access model (all of the above, and stage-1–5 case routes)
Case rows carry ownership; access is granted to the owner, SUPERVISOR
and ADMIN. A different INVESTIGATOR receives 404 on every case route
(read, upload, review, graph, analysis, copilot, audit) — no leakage
via counts, search or audit.

## Copilot

`GET /copilot` (bearer) → foundation-stage status:

```json
{
  "stage": "foundation",
  "provider": "not-configured",
  "model": null,
  "message": "The conversational copilot lands in a later stage with a configurable LLM provider…"
}
```

When `LLM_PROVIDER`/`LLM_API_KEY` are configured the stage advances; the
contract (authenticated, case-scoped later) does not change.

## Relationship vocabulary (seeded data)

`ASSOCIATED_WITH, CONNECTED_TO, OWNS, USED, CALLED, LOCATED_AT,
TRANSFERRED_TO, MENTIONED_IN` — the same ten types used across the graph,
so a Cypher export maps rows 1:1.

## Conventions

- Pagination is not yet needed at these data volumes; lists are complete.
- The API is versioned at the path (`/api/v1`); breaking changes bump the
  path, not the behaviour.
- The graph is built in-process with NetworkX (no graph database); the
  export seam (Cypher/JSON) lives in `backend/app/graph/store.py`.
