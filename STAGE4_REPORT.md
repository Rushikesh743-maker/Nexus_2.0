# NEXUS — Stage 4 Report: Investigation Reasoning & Evidence Intelligence

**Date:** 2026-09-08 · **Build:** in-place on Stages 1–3 (no redesign, no
replacement, no feature removed, no graph redesign) · **Status:**
COMPLETE — implementation, live verification, tests and documentation
delivered. **Stop** (Stage 4 was the final stage; no Stage 5).

Stage 4 adds an *investigation intelligence* layer on top of the stage-3
graph: it answers **"why did NEXUS produce this finding?"** and
**"what would change if this evidence were missing?"** by reasoning over
**confirmed data only** — `entity`, `relationship`, `evidence`,
`timeline_event`, `location` rows. Extraction candidates, pending or
rejected review items, unresolved match suggestions and text-similarity
guesses **never** enter the analysis — by construction (the builder only
ever loads confirmed rows), and there is no promotion path from candidate
to confirmed anywhere in the stage. No LLM, no fabrication: every result
is a named deterministic algorithm's output, every explanation is
generated from the computed values, and all language is neutral
("potential contradiction", "analytical support", "requires review" —
never "proves" or "guilty").

---

## 1. What was implemented

Seven capabilities, each a pure, unit-tested engine plus its persisted or
computed presentation:

1. **Contradiction engine** — three documented rule types over confirmed
   records (R1 timeline, R2 location, R3 relationship). Missing
   coordinates/timestamps are reported as *insufficient pairs*, never as
   contradictions. `EVIDENCE_CONTRADICTION` is intentionally not
   implemented (documented reason, §6).
2. **Competing hypothesis engine** — persisted hypotheses (new table
   `investigation_hypothesis`) generated per contradiction and per
   indirect person-pair, plus investigator-created ones; deterministic
   transparent score with every visible component stored and exposed.
3. **Evidence impact** — per-evidence linkage metrics + documented
   0–1 impact score, plus an **in-memory removal simulation** (zero
   database writes, proven in tests).
4. **Timeline intelligence** — EVENT_OVERLAP, TEMPORAL_PROXIMITY,
   EVENT_SEQUENCE, TIMELINE_GAP with documented thresholds.
5. **Geospatial intelligence** — CO_LOCATION, LOCATION_PROXIMITY,
   LOCATION_SEQUENCE, haversine only (no GIS dependencies), explicit
   `LOCATION_DATA_INSUFFICIENT` state.
6. **Investigation-gap detection** — evidence / relationship / timeline /
   identity gaps over confirmed data.
7. **Finding lifecycle** — reuses the stage-3 machinery: review, dismiss,
   audit log, statuses, no deletes.

Plus: extended data-versioning (hash now covers evidence + events +
locations) with stale flagging and idempotent re-runs; 16 case-scoped
API routes with JWT + RBAC + structured errors; a new **Investigation**
tab in the frontend with seven panels and all six analysis states;
deterministic synthetic demonstration data; and a persistent live smoke
script.

## 2. Architecture

Same layered pattern as stage 3, additive:

```
API router (backend/app/api/v1/investigation_intelligence.py)
  → service (…/investigation_intelligence/finding_service.py)
      → pure engines (contradiction_engine, hypothesis_engine,
         evidence_impact, timeline_engine, geospatial_engine, gap_engine)
      → confirmed-data builder (data.py: load_stage4_data,
         compute_stage4_version)
  → PostgreSQL (graph_finding reused + investigation_hypothesis new)
```

- **Engines are pure functions** of the loaded snapshot — no ORM, no
  I/O — so the same confirmed records always yield the same findings,
  hypotheses and scores, and the engines are unit-tested without a
  database.
- **Read-vs-compute split:** `analyze` persists the stable results
  (contradictions, hypotheses, gaps, version); timeline, geospatial and
  evidence-impact are deterministic on-read computations over the same
  snapshot (fast, no redundant rows; they are audit-logged when
  requested).
- **Findings reuse `graph_finding`** under four new types
  (CONTRADICTION, TIMELINE_INSIGHT, GEO_INSIGHT, INVESTIGATION_GAP).
  Stage-3 listing endpoints filter to stage-3 types, stage-4 endpoints
  to stage-4 types — each view sees only its own lineage. The only new
  table is `investigation_hypothesis`.
- **No new runtime dependencies** (NetworkX 3.6.1 and the existing stack
  only); the legacy pipeline and the stage-3 engine are untouched.
- The stage-3 graph page, the React Flow graph and all existing
  routes/panels are unchanged except documented additive touches
  (§4).

## 3. Files created

| File | Purpose |
| --- | --- |
| `backend/app/services/investigation_intelligence/__init__.py` | Package exports |
| `…/investigation_intelligence/data.py` (152 LOC) | Confirmed-data builder (`Stage4Data`) + extended version hash |
| `…/investigation_intelligence/contradiction_engine.py` (228) | Rules R1/R2/R3, severity, insufficient pairs |
| `…/investigation_intelligence/hypothesis_engine.py` (318) | Generation + deterministic scoring + components |
| `…/investigation_intelligence/evidence_impact.py` (295) | Metrics, impact score, in-memory removal simulation |
| `…/investigation_intelligence/timeline_engine.py` (247) | Overlap / proximity / sequence / gap |
| `…/investigation_intelligence/geospatial_engine.py` (313) | Co-location / proximity / sequence + map observations |
| `…/investigation_intelligence/gap_engine.py` (181) | Evidence / relationship / timeline / identity gaps |
| `…/investigation_intelligence/finding_service.py` (529) | Orchestration, persistence, lifecycle, audit |
| `backend/app/api/v1/investigation_intelligence.py` (317) | 16 case-scoped routes |
| `backend/app/models/investigation_hypothesis.py` | New ORM table |
| `backend/tests/test_investigation_intelligence.py` (945) | 59 tests: engines + API + regression |
| `backend/scripts/seed_stage4_demo.py` (196) | Idempotent synthetic demo cases (INSERT-only) |
| `scripts/stage4-live-smoke.py` (243) | Persistent 29-check live smoke vs the running stack |
| `src/services/v1/investigationService.js` (95) | 17 client fns over 16 routes |
| `src/components/cases/InvestigationPanels.jsx` (793) | 7 panels + shared state UI + empty states |
| `src/pages/cases/InvestigationIntelligencePage.jsx` (110) | New "Investigation" tab page |

## 4. Files modified (additive only)

| File | Change |
| --- | --- |
| `backend/app/api/v1/__init__.py` | Register the stage-4 router |
| `backend/app/models/__init__.py` | Export `InvestigationHypothesis` |
| `backend/app/schemas/v1.py` | +11 stage-4 response/request schemas |
| `backend/tests/test_v1_api.py` | Documented exception: empty seeded case → investigation status is `insufficient` (all other expectations unchanged) |
| `src/App.jsx` | Route `/cases/:caseId/investigation` |
| `src/lib/navigation.js` | "Investigation" tab in the case area |
| `src/services/v1/index.js` | Export the investigation service |
| `src/pages/cases/CaseGraphPage.jsx` | Deep-link `?highlight=ids&label=…` → applies a temporary graph highlight (same mechanism as stage-3 findings; clearable) |
| `src/components/cases/GraphFindingsPanel.jsx` | Additive: stage-4 finding types recognized in labels; link to the Investigation tab |
| `scripts/frontend-sanity.mjs` | +16 stage-4 render entries (29 → 45 total; all original 29 kept) |

No legacy pipeline file, no stage-1/2/3 module, and no existing route
was changed in behavior.

## 5. Database changes

- **New table (only one):** `investigation_hypothesis` —
  `case_id`, `title`, `description`, `hypothesis_type`
  (GENERATED_CONTRADICTION / GENERATED_STRUCTURE / INVESTIGATOR),
  involved/supporting/contradicting id lists (JSON), `analytical_score`,
  `confidence_band`, `score_components` (JSON, every visible factor),
  `explanation` (JSON), `analysis_method`, `graph_version`,
  `status` (ACTIVE/REVIEWED/DISMISSED), review columns, timestamps.
  Created by `Base.metadata.create_all` (fresh installs) and
  automatically on next startup of existing databases.
- **`graph_finding` reused unchanged** for four new `finding_type`
  values (varchar column; no schema migration). Findings remain
  append-only: re-analyses add rows for the new version; review/dismiss
  update status in place; nothing is ever deleted.
- **Version hash extended:** the stage-3 hash covered entities +
  relationships; `compute_stage4_version` additionally hashes evidence,
  timeline events and locations (same sha256 canonicalization). Stage-3
  findings keep the stage-3 hash format, so the two lineages flag
  staleness independently.
- **Seed data:** `seed_stage4_demo.py` adds two labeled **SYNTHETIC
  DEMONSTRATION** cases (idempotent, INSERT-only, fictional names):
  `CASE-DEMO-EMPTY-01` (no confirmed data → insufficient state) and
  `CASE-DEMO-CONTRA-01` (deterministic R1/R2/R3 fixtures, 5 entities,
  3 relationships, 6 dated events, 4 coordinated locations).

## 6. Contradiction engine — rules and parameters

Implemented rule types (each finding stores `rule`, parameters and all
computed values in `details`):

| Rule | Type | Exact rule | Parameters |
| --- | --- | --- | --- |
| R1 | `TIMELINE_CONTRADICTION` | One confirmed entity has two confirmed dated events at two different confirmed coordinates; required travel time = haversine ÷ **100 km/h** (conservative minimum) exceeds available time | `distance_km`, `available_minutes`, `required_minutes`, `margin` |
| R2 | `LOCATION_CONTRADICTION` | Two confirmed events for one entity with identical timestamps (Δt < 1 min) at different confirmed coordinates | `distance_km`, `required_minutes` |
| R3 | `RELATIONSHIP_CONTRADICTION` | Mutual OWNS between two confirmed entities — the only relationship state the domain documents as incompatible | relationship pair ids |

- **Severity:** HIGH when the computed margin > 50% of the available
  window, otherwise MEDIUM.
- **`EVIDENCE_CONTRADICTION` is deliberately not implemented:** the
  evidence model has no structured claims/fields to compare, so a rule
  would be free-text guessing. The omission is documented here, in
  `docs/ARCHITECTURE.md` and in the engine docstring — it is an
  honest boundary, not a placeholder.
- **Insufficient data is reported, never hidden:** pairs missing
  coordinates or timestamps are counted and returned as
  `insufficient_pairs` (with the reason), and the engine produces zero
  findings from them. No silent promotion of a candidate or guess to a
  finding.

## 7. Competing hypothesis engine

- **Generation:** per contradiction → two competing explanations
  (assumption-based vs record-accuracy) split by the computed travel
  margin; per indirect person-pair → direct link vs mediated; when the
  two scores are within 0.05 an explicit *"insufficient to
  distinguish"* hypothesis is generated instead of a forced ranking.
- **Deterministic transparent score** (stored in `score_components`,
  shown as bars + component table in the UI):

  ```
  analytical_score = 0.30·min(1, supporting_evidence/4)
                   + 0.20·min(1, supporting_relationships/3)
                   + 0.20·consistency
                   + 0.15·provenance
                   + 0.15·min(1, involved_entities/5)
  ```

  with the documented margin override (travel margin > 50% caps
  consistency at 0.5; margin < 5% caps it at 0.75) so scores stay
  honest against the rule evidence. Bands: LOW < 0.34 ≤ MEDIUM < 0.67
  ≤ HIGH.
- **Lifecycle:** statuses ACTIVE / REVIEWED / DISMISSED; generated
  hypotheses are deduplicated by (title, type) across re-analysis
  versions; investigator-created hypotheses (API `POST
  /hypotheses`) persist across re-analyses; nothing is ever deleted.
- **Framing:** the API response carries the disclaimer verbatim —
  *"Scores express analytical support for the hypothesis based on the
  confirmed data in this case — not proof or a probability of guilt."*
  — repeated in the UI panel header.

## 8. Evidence impact & removal simulation

- **Metrics per evidence record:** linked entities, linked
  relationships (via stage-2 `source_reference` provenance), linked
  events, cited-by findings, cited-by hypotheses.
- **Impact score (documented formula):**

  ```
  impact_score = 0.5·graph_share + 0.25·finding_share + 0.25·hypothesis_share
  ```

  bands HIGH ≥ 0.67, MEDIUM ≥ 0.34; `impact_breakdown` exposes the three
  shares.
- **`simulate-impact` (POST):** recomputes the case network **on an
  in-memory copy** with the evidence removed — a relationship loses its
  evidence support only when this evidence was its *sole* provenance —
  and returns before/after (entities, relationships, max degree,
  weak components, average betweenness) + diff (components increase,
  degree decreases, sole-provenance list).
- **Zero database writes** — the endpoint and engine never call
  `db.add/delete/commit`; `test_simulate_impact_writes_nothing`
  asserts the DB state is byte-identical afterwards, and the live smoke
  re-asserts it. The UI banner says "Simulation only — stored evidence
  is not modified."

## 9. Timeline intelligence

| Insight | Rule | Threshold |
| --- | --- | --- |
| `EVENT_OVERLAP` | Overlapping time ranges, or point events for the same confirmed entity within 5 min | 5 min |
| `TEMPORAL_PROXIMITY` | Two dated events for the same confirmed entity close together | Δt ≤ 30 min |
| `EVENT_SEQUENCE` | Ordered dated-event chain for one confirmed entity, with durations | ≥ 3 events |
| `TIMELINE_GAP` | Consecutive dated events for one entity far apart — reported **only as a potential investigation gap** | gap > 12 h |

All thresholds are documented constants in `timeline_engine.py`. Events
without timestamps are counted and excluded honestly
(`events_without_timestamp`); fewer than two dated events →
`insufficient: true` (explicit state, not silence).

## 10. Geospatial intelligence

| Insight | Rule | Threshold |
| --- | --- | --- |
| `CO_LOCATION` | Two confirmed entities observed at (near) the same location | < 0.05 km |
| `LOCATION_PROXIMITY` | Two confirmed entities observed at close locations | ≤ 2 km |
| `LOCATION_SEQUENCE` | Ordered distinct-location chain for one confirmed entity | — |

- Distances: **haversine** (no GIS libraries added). Confirmed LOCATION
  entities join `location` rows by (case, normalized name) — the same
  documented convention as the seed data.
- `observations` (entity, location, lat/lon, timestamp, source
  event/relationship) feed the frontend **existing Leaflet map** (no new
  dependency, no graph redesign).
- Fewer than two observations with usable coordinates →
  `location_data_insufficient: true` → the panel renders its explicit
  **LOCATION_DATA_INSUFFICIENT** state.

## 11. Gap detection

| Gap type | Rule (confirmed data only) |
| --- | --- |
| `EVIDENCE` | Confirmed entity with graph degree ≥ 3 but zero linked evidence records |
| `RELATIONSHIP` | Indirect 2–3 hop path between two confirmed entities with no direct confirmed link (the path itself is included) |
| `TIMELINE` | Reused `TIMELINE_GAP` findings |
| `IDENTITY` | Confirmed PERSON with no aliases/identifying metadata and ≥ 2 relationships |

Each gap finding names the rule and the computed values that triggered
it; every gap is phrased as a *potential investigation gap / open
question*, never as a conclusion.

## 12. Finding lifecycle

Reuses the stage-3 lifecycle exactly (no new delete paths):

- `POST /findings/{id}/review` / `dismiss` (INVESTIGATOR+) →
  `status` ACTIVE → REVIEWED / DISMISSED, `reviewed_by`, `reviewed_at`,
  `review_note`; already-acted rows → `409
  FINDING_REVIEW_NOT_ALLOWED`.
- Same pair for hypotheses (`POST /hypotheses/{id}/review|dismiss`).
- Wrong case scope → `404` (finding/hypothesis ids are case-scoped).
- Audit log (no secrets): `INVESTIGATION_ANALYSIS_STARTED/COMPLETED/FAILED`,
  `CONTRADICTION_DETECTED`, `INVESTIGATION_GAP_DETECTED`,
  `TIMELINE_ANALYSIS_COMPLETED`, `GEO_ANALYSIS_COMPLETED`,
  `EVIDENCE_IMPACT_ANALYZED`, `HYPOTHESIS_GENERATED/CREATED/REVIEWED/
  DISMISSED`; finding reviews reuse the stage-3 `FINDING_REVIEWED` /
  `FINDING_DISMISSED` actions.
- **Nothing is ever deleted:** findings are append-only per version,
  hypotheses are append-only, stale rows are kept as history.

## 13. Versioning, freshness & idempotency

- `compute_stage4_version` hashes the canonical projection of
  entities + relationships + evidence + timeline events + locations
  (same sha256 canonicalization as stage 3).
- `analyze` is **idempotent per snapshot**: same version → no recompute
  (`recomputed: false`, findings unchanged — asserted in tests and the
  live smoke).
- `GET /status` returns `not-analyzed | up-to-date | stale |
  insufficient` with a human-readable `reason`, current vs stale
  finding counts, and the timeline/geospatial data census.
- Stale findings are kept (history) and re-analysis replaces the current
  set; hypotheses carry their own `graph_version` and are flagged
  `is_stale` without deletion.

## 14. Frontend

New **Investigation** tab per case (`/cases/:id/investigation`); the
stage-3 Case Network page and the React Flow graph are visually
unchanged. Seven panels, all built from the existing
Card/Badge/Button/EmptyState primitives:

1. **Analysis status & run** — the six states: not-analyzed / analyzing
   / up-to-date / stale / insufficient / error, with the computed
   reason, version hash, finding/hypothesis counts and the "Analyze"
   trigger (INVESTIGATOR+; disabled for ANALYST with a hint).
2. **Potential contradictions** — rule badge, severity, computed values
   (distance/minutes/margin), involved entities, per-finding
   review/dismiss with note, "Show in graph".
3. **Competing hypotheses** — score bar, confidence band, component
   table, supporting/contradicting signals, disclaimer in the panel
   header, review/dismiss.
4. **Evidence impact** — per-record metrics + impact band, detail view
   with breakdown, **simulation** section with its "Simulation only —
   stored evidence is not modified" banner and before/after diff.
5. **Timeline intelligence** — insight cards (overlap/proximity/
   sequence/gap) with computed values; explicit insufficient state.
6. **Geospatial intelligence** — insight cards + observations plotted on
   the **existing** Leaflet `GeoMap` component; LOCATION_DATA_INSUFFICIENT
   state when coordinates are missing.
7. **Investigation gaps** — gap-type cards with the triggering values.

**Show in graph** reuses the case graph's `highlightIds` mechanism:
`/cases/:id/graph?highlight=1,2,3&label=…` deep link → the graph page
applies the same temporary dim-everything-else highlight (clearable) it
already used for stage-3 findings. All panels render their not-analyzed
/ analyzing / up-to-date / stale / insufficient / error states.

## 15. Security & RBAC

- All 16 routes behind the existing JWT auth; case-scoped (wrong case
  id / out-of-scope finding id → 404).
- **Read** (status, findings, contradictions, gaps, hypotheses,
  evidence-impact, timeline, geospatial): **ANALYST+**.
- **Mutating** (analyze, create hypothesis, review, dismiss,
  simulate-impact): **INVESTIGATOR+** (SUPERVISOR included).
- Enforced server-side via the existing RBAC ladder
  (`require_roles`); verified live: ANALYST → 403 on analyze/review,
  200 on reads; INVESTIGATOR/SUPERVISOR → 200.
- Structured error shape reused: `409 INSUFFICIENT_CONFIRMED_DATA`
  (analyze on a case without confirmed graph data), `400
  EVIDENCE_NOT_FOUND`, `400 INVALID_FINDING_TYPE` (investigator
  hypothesis with unknown entity/evidence ids), `409
  FINDING_REVIEW_NOT_ALLOWED`, `404` for out-of-scope ids.
- No secrets in audit metadata; no new dependencies.

## 16. Confirmed-data-only guarantee

- `data.py::load_stage4_data` queries **only** `Entity`,
  `Relationship`, `Evidence`, `TimelineEvent`, `Location` for the case.
  The candidate/suggestion tables are never touched by any stage-4
  module (asserted in `TestBuilderExcludesCandidates`: a case with
  pending candidates, rejected items and unresolved suggestions yields a
  snapshot containing none of them).
- There is **no promotion path**: nothing in stage 4 writes to
  `entity`, `relationship`, `entity_candidate`,
  `relationship_candidate` or `entity_match_suggestion`.
- **No fabrication:** every finding/hypothesis field is either copied
  from a confirmed record or computed from them with the formula shown
  in `analysis_method`/`details`; empty/missing data produces explicit
  states (`insufficient`, `LOCATION_DATA_INSUFFICIENT`,
  `insufficient_pairs`, "insufficient to distinguish"), never invented
  records.
- **Neutral language** is enforced by test: no stage-4 finding,
  hypothesis, explanation or API string may contain "proves",
  "guilty", "definitely" or similar (asserted across all engine
  outputs).

## 17. Tests executed

| Suite | Command | Result |
| --- | --- | --- |
| Full backend | `python3 -m pytest backend/tests/ -q` | **258 passed, 1 skipped** — run 3×, identical results (sole skip: `test_neo4j_layer.py` live round-trip, by design without a Neo4j server) |
| Stage-4 file | `python3 -m pytest backend/tests/test_investigation_intelligence.py -q` | **59 passed** (engine units over synthetic confirmed records + full API against PostgreSQL) |
| Production build | `npm run build` | ✓ 7.85 s |
| Frontend render | `npm run test:frontend-sanity` | **45/45 pages rendered** (29 original + 16 stage-4) |
| Auth flow | `npm run test:frontend-auth` | **8/8 ok, LIVE** ("backend UP (JWT path)"; wrong password rejected, no mock fallback) |
| Live smoke | `python3 scripts/stage4-live-smoke.py` | **29/29 checks passed** (rerun-tolerant) |

## 18. Test results (detail)

`test_investigation_intelligence.py` — 59 tests, all passing:

- **Builder & boundary (8):** confirmed-only load, candidate/rejected/
  suggestion exclusion, version hash stability & sensitivity to each of
  the five record kinds.
- **Contradiction engine (10):** R1 fires with computed distance/
  minutes/margin and HIGH severity; R2 identical-timestamp rule; R3
  mutual OWNS; each non-firing case (same location, enough time,
  one-way OWNS, missing coordinates → insufficient_pairs, no events).
- **Hypothesis engine (8):** generation per contradiction and per
  indirect pair, "insufficient to distinguish" branch, score formula
  exact-value checks, component visibility, margin override caps,
  deduplication across versions.
- **Evidence impact (8):** metrics, impact score exact values and
  bands, breakdown shares, **simulation zero-write proof** (DB
  byte-identical), sole-provenance edge rule (survives with a second
  evidence, removed without one).
- **Timeline (6):** each insight type fires, thresholds respected,
  unordered/undated handling, insufficient state.
- **Geospatial (6):** each insight type, haversine values,
  location-insufficient state, observations census.
- **Gaps (4):** each gap type fires with computed values; no false
  positives on complete data.
- **API (23):** analyze/persist/idempotency (recomputed=false), status
  states (not-analyzed → up-to-date → stale → insufficient), the seven
  read views, hypothesis create/review/dismiss + 409s + 400 on unknown
  ids, evidence-impact + simulate-impact, review/dismiss + audit rows,
  ANALYST 403/200 matrix, wrong-case 404s, stage-3/stage-4 separation
  (each listing sees only its own types), legacy route regression.

## 19. Existing-functionality verification (regression)

- Full backend suite green **after** the change, run 3× identically —
  including all stage-1 (auth/users/cases), stage-2 (documents/
  extraction/review), stage-3 (graph intelligence, findings, paths,
  bridges, clusters, cross-case, metrics, lifecycle, staleness, RBAC)
  and legacy pipeline tests.
- Legacy routes verified live (200): `/api/stats`, `/api/graph`,
  `/api/findings`, `/legacy`.
- Stage-3 endpoints verified live unchanged: stage-3
  `/graph/findings` lists only stage-3 types; stage-4
  `/investigation/findings` lists only stage-4 types (both asserted in
  the live smoke and in tests).
- Frontend: all 29 original sanity entries still render; the Case
  Network page is visually unchanged (the graph component itself is
  unmodified; only an additive deep-link handler was added); production
  build clean.
- OpenAPI exposes the 16 new `/investigation/…` routes alongside the
  existing surface; no existing route changed signature or behavior.
- The full stack was restored and re-verified end-to-end on 2026-09-08
  (API :8000, Vite :5173, PostgreSQL 17) — all results above are from
  that final state.

## 20. Live smoke verification (running stack)

`scripts/stage4-live-smoke.py` — 29 checks, all passed:

1. **Contradictions** — `CASE-DEMO-CONTRA-01` analyze → 9 findings:
   3 contradictions covering all three rule types (R1 TIMELINE HIGH:
   118.581 km apart, 20 min available vs 71.1 min required; R2 LOCATION
   HIGH: 7.328 km at Δt = 0; R3 RELATIONSHIP MEDIUM: mutual OWNS), 2
   timeline insights, 3 geo insights, 1 gap.
2. **Hypotheses** — 8 generated + (on re-run) deduplicated; every row
   has `score_components` (5 factors + weights) and the response
   carries the "analytical support … not proof or a probability of
   guilt" disclaimer.
3. **Idempotency** — second `analyze` on the same snapshot →
   `recomputed: false`, findings unchanged.
4. **Empty case** — `CASE-DEMO-EMPTY-01` analyze → `409
   INSUFFICIENT_CONFIRMED_DATA`; status → `state: insufficient` with
   honest census (0 entities/relationships).
5. **Honest negative** — `CASE-2026-001` (real seed case) reports zero
   contradictions: no fabrication of issues where none exist.
6. **Timeline & geospatial & gaps** — endpoints return the computed
   insights + census for `CASE-2026-021` (Meridian, 53 entities).
7. **Evidence impact** — per-evidence scores + `simulate-impact` →
   `simulation_only: true` and the DB is asserted byte-identical
   afterwards (nothing removed).
8. **Lifecycle & audit** — review a finding, dismiss a hypothesis →
   statuses + reviewer recorded; re-acting → `409
   FINDING_REVIEW_NOT_ALLOWED`; audit log contains the stage-4 actions
   with actor/case/note.
9. **Candidate exclusion** — a case with pending candidates: the
   snapshot and findings contain none of them; nothing was promoted.
10. **RBAC** — ANALYST token → 403 on analyze/review, 200 on reads;
    INVESTIGATOR → 200.
11. **Staleness** — add a confirmed record → status `stale` →
    re-analyze → `up-to-date`; stale rows retained as history.
12. **Nothing removed** — final census: entities/relationships/evidence/
    events/locations counts identical to pre-smoke; findings/hypotheses
    counts only grew.

## 21. Limitations (honest, documented)

- **`EVIDENCE_CONTRADICTION` is not implemented** — the evidence model
  has no structured claims to compare; free-text contradiction
  detection would be guessing. The rule list is documented and the
  type is reserved.
- **Relationship → evidence linkage** exists only where stage-2
  provenance exists (`source_reference`); relationships without
  evidence records are honestly reported as having none, and the
  sole-provenance simulation rule makes that explicit instead of
  guessing.
- **Geospatial identity join** is (case, normalized name) — the same
  documented convention as the seed data; two distinct places sharing a
  normalized name would merge. Type-mismatched rows are never joined.
- **Travel speed** (100 km/h) and all thresholds (30 min proximity,
  12 h gap, 0.05 km co-location, 2 km proximity, 5 min overlap) are
  documented, explainable constants tuned for small case data — they
  are stated in every finding's `details`, so an investigator sees the
  basis, but they are not calibrated probabilities.
- **Scores are analytical support, not probabilities.** The hypothesis
  formula is a transparent composite; nothing in the stage estimates
  guilt or truth.
- **Scale:** bounded for case-sized data (the 53-entity Meridian case
  analyzes in well under a second). Betweenness is recomputed per
  simulation — adequate at platform scale.
- **No GIS dependencies** were added (haversine only); map rendering
  reuses the existing Leaflet component.

## 22. Final state & summary

- **API:** 16 case-scoped routes under
  `/api/v1/cases/{case_id}/investigation/…` (analyze, status, findings,
  contradictions, gaps, hypotheses GET/POST, evidence-impact,
  evidence/{id}/impact, simulate-impact, timeline, geospatial,
  findings review/dismiss, hypotheses review/dismiss) — JWT + RBAC +
  structured errors, all audited.
- **Database:** 19 platform tables (one new: `investigation_hypothesis`);
  `graph_finding` reused; no deletes anywhere; extended snapshot hash
  (evidence + events + locations).
- **Frontend:** new Investigation tab with seven panels, six analysis
  states per panel, both required disclaimers, Show-in-graph deep link
  reusing `highlightIds`; 45/45 pages render; production build clean.
- **Verification:** pytest 258 passed / 1 skipped ×3 identical; build
  7.85 s; sanity 45/45; auth 8/8 live (JWT path); live smoke 29/29.
- **Data:** two labeled SYNTHETIC DEMONSTRATION demo cases
  (`CASE-DEMO-EMPTY-01`, `CASE-DEMO-CONTRA-01`) + the persistent
  `scripts/stage4-live-smoke.py` for re-verification.
- **Docs:** README, `docs/ARCHITECTURE.md`, `docs/API.md`,
  `docs/DATABASE.md` updated; this report added.

**Stop.** Stage 4 complete — no Stage 5.
