# NEXUS — Stage 3 Report: Graph Intelligence & Hidden Connection Engine

**Date:** 2026-09-07 · **Build:** in-place on Stages 1–2 (no redesign, no
replacement, no feature removed) · **Status:** COMPLETE — implementation,
live verification, tests and documentation delivered.

The engine analyzes the **confirmed** case graph (confirmed `Entity` +
`Relationship` rows only) with **NetworkX 3.6.1** and produces explainable,
traceable findings that an investigator can review. Extraction candidates,
pending/rejected review items and unresolved match suggestions **never**
enter the analysis — by construction (the builder only ever sees confirmed
rows), not by filtering. There is no LLM and no similarity guessing in this
stage: every finding is the output of a named algorithm over confirmed
data, and every explanation string is generated from the computed values.

---

## 1. What was implemented

1. **Confirmed-graph builder** — NetworkX graphs from confirmed rows only,
   with full node/edge metadata for traceability (a case graph and a
   merged cross-case graph).
2. **Path analysis** — bounded BFS shortest paths between two confirmed
   entities (depth ≤ 4 hops, ≤ 5 paths, cycle-free), with deterministic
   explanations; explicit `PATH_NOT_FOUND` when no path exists.
3. **Bridge-entity detection** — articulation points + betweenness
   centrality + connectivity impact + cross-case reach, combined with a
   documented, deterministic score; honest empty result when no node
   qualifies.
4. **Cross-case connection analysis** — only confirmed same
   (entity-type, normalized-name) links across cases, with an example
   confirmed path through the shared entity where the data supports one;
   no false positives by design.
5. **Network-cluster analysis** — connected components (deterministic),
   with optional greedy-modularity subgroups only when meaningful;
   neutral labels only ("connected group").
6. **Per-entity metrics** — degree, evidence-weighted degree, betweenness,
   component size, cross-case reach; neutral wording, evidence framed as
   analytical context (never proof).
7. **Finding lifecycle** — a new `graph_finding` table persisting
   `HIDDEN_CONNECTION / BRIDGE_ENTITY / CROSS_CASE_CONNECTION /
   NETWORK_CLUSTER / HIGH_CONNECTIVITY` findings with involved entities,
   supporting relationships, linked evidence ids, analysis method,
   graph version and `ACTIVE / REVIEWED / DISMISSED` status; review and
   dismiss endpoints that keep dismissed findings auditable (never
   deleted).
8. **Freshness** — versioned analyses (deterministic snapshot hash);
   idempotent re-runs; stale findings flagged and kept as history.
9. **API** — 9 new case-scoped endpoints (analyze, findings,
   review/dismiss, metrics, bridges, clusters, cross-case, paths) with the
   project's structured error shape and the specified error codes.
10. **Frontend** — the existing React Flow graph is visually unchanged;
    around it: a Network Intelligence findings panel (Analyze trigger,
    "Not analyzed yet", loading/error/empty/stale states, review/dismiss),
    a path explorer, bridge/cluster/cross-case panels, per-entity metrics
    in the entity detail, and graph highlighting with a Clear button —
    built entirely from the existing Card/Badge/Button/EmptyState
    primitives.
11. **Audit** — `GRAPH_ANALYSIS_STARTED / COMPLETED / FAILED`,
    `FINDING_REVIEWED`, `FINDING_DISMISSED`.
12. **Tests + docs** — 56 new tests (engine unit tests + full API tests),
    extended frontend sanity (14 → 29 rendered states), updated
    `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/DATABASE.md`, `README.md`.

## 2. Architecture

```
API router (app/api/v1/graph_intelligence.py)
  └─ service layer (app/services/graph_intelligence/)
       ├─ finding_service  — orchestration, persistence, review, audit
       ├─ endpoints        — thin DB→graph→dict serializers
       ├─ graph_builder    — ConfirmedGraph (case + merged), version hash
       ├─ path_analysis    — bounded shortest paths, indirect connections
       ├─ bridge_analysis  — articulation + betweenness + documented score
       ├─ cluster_analysis — connected components (+ modularity, optional)
       ├─ cross_case_analysis — shared confirmed identities + example paths
       └─ metrics          — per-entity metrics, high-connectivity ranking
            └─ engine: NetworkX 3.6.1 (pure functions over plain records)
                 └─ repository/DB: PostgreSQL (entity, relationship,
                    evidence, entity_candidate, graph_finding, audit_log)
```

Rules honoured: API → Service → Engine → DB (no algorithm in a router);
the engine is a pure function over plain `EntityRecord` /
`RelationshipRecord` dataclasses, so it is unit-testable without a
database; the pre-existing `app/graph/` CNA pipeline and `app/intelligence/`
foundation are untouched.

## 3. Files created

Backend — new package `backend/app/services/graph_intelligence/`:

| File | Lines | Purpose |
| --- | --- | --- |
| `__init__.py` | 20 | package exports |
| `graph_builder.py` | 283 | records, `ConfirmedGraph`, case + merged builders, evidence linkage, `compute_graph_version`, `merged_reach`, documented limits |
| `path_analysis.py` | 171 | `find_paths`, `find_indirect_connections`, deterministic path explanations |
| `bridge_analysis.py` | 130 | `analyze_bridges` (articulation + betweenness + impact + reach, documented score), `connectivity_impact` |
| `cluster_analysis.py` | 103 | `analyze_clusters` (components + optional modularity subgroups) |
| `cross_case_analysis.py` | 139 | `analyze_cross_case` (shared identities, example paths) |
| `metrics.py` | 93 | `compute_metrics`, `high_connectivity` |
| `finding_service.py` | 490 | data loading, finding generation, `run_analysis`, `list_findings`, `apply_review`, audit |
| `endpoints.py` | 159 | DB-backed serializers for the 5 GET analyses + paths |

Other created files:

| File | Lines | Purpose |
| --- | --- | --- |
| `backend/app/api/v1/graph_intelligence.py` | 131 | the 9 routes |
| `backend/tests/test_graph_intelligence.py` | 821 | 56 tests (engine units + API) |
| `src/services/v1/graphService.js` | 56 | frontend service (shared axios client) |
| `src/components/cases/GraphFindingsPanel.jsx` | 305 | findings panel + Analyze trigger (panel + exported `FindingsBody`/`FindingRow`) |
| `src/components/cases/PathExplorer.jsx` | 161 | path explorer (+ exported `PathResult`) |
| `src/components/cases/GraphIntelPanels.jsx` | 244 | bridge/cluster/cross-case panels (+ exported lists) |
| `STAGE3_REPORT.md` | — | this report |

## 4. Files modified

| File | Change |
| --- | --- |
| `backend/app/models/models.py` | new `GraphFinding` model (18th table); `Case.graph_findings` relation |
| `backend/app/models/__init__.py` | export `GraphFinding` |
| `backend/app/schemas/v1.py` | +13 stage-3 response schemas (`GraphFindingOut`, `GraphAnalysisOut`, `GraphFindingsOut`, `EntityMetricsOut`, `GraphMetricsOut`, `BridgeOut`, `GraphBridgesOut`, `ClusterOut`, `GraphClustersOut`, `CrossCaseConnectionOut`, `GraphCrossCaseOut`, `PathOut`, `GraphPathsOut`) |
| `backend/app/api/v1/__init__.py` | register `graph_intelligence.router` |
| `src/pages/cases/CaseGraphPage.jsx` | additive: highlight state, metrics resource, highlight banner + Clear button, entity-detail metrics, findings/path/bridge/cluster/cross-case sections (existing layout and graph preserved) |
| `src/services/v1/index.js` | export `graphService` |
| `scripts/frontend-sanity.mjs` | +15 rendered states (14 → 29) |
| `docs/ARCHITECTURE.md` | Stage 3 section (engine, methodology, limits, lifecycle, freshness); "not implemented" list updated |
| `docs/API.md` | Stage 3 endpoint documentation + audit actions |
| `docs/DATABASE.md` | `graph_finding` table row (17 → 18 tables) + migration note |
| `README.md` | Stage 3 section; tests counts; layout |

No file in `backend/app/graph/` (legacy CNA pipeline), no legacy route,
and no Stage 1–2 feature was changed.

## 5. Database changes

- **One new table** `graph_finding` (created by `Base.metadata.create_all`
  on fresh installs and on the next startup of the existing database — no
  pre-existing table is altered, so no `_ensure_columns` migration is
  needed):

| Column | Type | Notes |
| --- | --- | --- |
| `id` | serial PK | |
| `case_id` | int FK → case (CASCADE, indexed) | |
| `finding_type` | varchar(32), indexed | 5 allowed values |
| `title` / `summary` | varchar(255) / text | |
| `explanation` | json | computed reason bullets (list) |
| `details` | json | paths / metrics / members payload |
| `involved_entity_ids` | json | confirmed entity ids |
| `supporting_relationship_ids` | json | confirmed relationship ids |
| `supporting_evidence_ids` | json | directly-linked evidence ids |
| `related_case_ids` | json | cross-case findings |
| `analysis_method` | varchar(255) | algorithm + parameters |
| `graph_version` | varchar(32), indexed | snapshot hash of the confirmed data |
| `status` | varchar(16), indexed | ACTIVE / REVIEWED / DISMISSED |
| `reviewed_by` / `reviewed_at` / `review_note` | — | review workflow |
| `created_at` / `updated_at` | timestamptz | |

- Findings are **append-only across versions** and update-only on review;
  nothing is ever deleted (audit trail).
- Verified live: `\d graph_finding` on the development database shows the
  table with all columns.

## 6. NetworkX methodology

- **Graph model:** undirected `nx.Graph`; node id `e{entity_id}` (case
  graph), `m{type}:{normalized_name}` (merged graph). Self-loops and
  dangling rows are skipped — the builder never fabricates structure.
- **Algorithms used (all real, all bounded):**
  `nx.single_source_shortest_path_length(cutoff=…)`,
  `nx.all_shortest_paths`, `nx.shortest_path`, `nx.articulation_points`,
  `nx.betweenness_centrality`, `nx.connected_components`,
  `nx.number_connected_components`, `nx.community.greedy_modularity_communities`.
- **Limits (documented in `graph_builder.py` and the API docs):**
  `MAX_PATH_DEPTH = 4` hops, `MAX_PATHS = 5` paths,
  `MAX_INDIRECT_PAIRS = 10`, `MAX_BRIDGES = 10`, `MAX_CLUSTERS = 15`,
  `MAX_TOP_ENTITIES = 5`, analysis minimum = 3 entities & 2 relationships.
  Searches are BFS-based with explicit cutoffs and result caps — no
  exponential enumeration (`all_shortest_paths` is consumed lazily and
  stopped after the cap; simple paths are cycle-free by definition).
- **Evidence traceability:** Stage 2 acceptance writes evidence rows whose
  `source_reference` is `candidate:{id}`; the builder reads that link back
  (via accepted `entity_candidate.accepted_entity_id` and
  `relationship.meta.candidate_id`) so every node/edge can report the
  evidence records that directly support it. Seeded rows (no candidate
  provenance) honestly report 0 linked records.
- **No fake intelligence:** empty results return explicit, documented
  empty states (`PATH_NOT_FOUND`, "No significant bridge entities", "No
  significant connection found.", "Insufficient confirmed graph data.") —
  never invented results.

## 7. Path analysis

- `GET /cases/{id}/graph/paths?source_entity_id=&target_entity_id=&max_depth=4&max_paths=5`.
- Validates both ids belong to the case (`ENTITY_NOT_FOUND` 404), rejects
  candidate ids with `ENTITY_NOT_CONFIRMED` 400 (with a clear
  "confirmed data only" message), rejects same-entity with
  `INVALID_PATH_REQUEST` 400.
- Step 1: bounded BFS (`single_source_shortest_path_length`, `cutoff`);
  step 2: shortest paths only (all have exactly that length), capped.
- Each path returns hop count, node list (id/name/type), relationship
  types + ids, linked-evidence count and a deterministic explanation built
  from the actual hops, e.g.
  `MH14CD5678 is indirectly connected to Aarav Mehta through Rohan
  Deshmukh (2 hops): MH14CD5678 → USED → Rohan Deshmukh / Rohan Deshmukh
  → CALLED → Aarav Mehta`.
- Verified live: direct path 1 hop (OWNS); indirect 2-hop path;
  disconnected pair → 404 `PATH_NOT_FOUND` "No confirmed connection path
  found."; `max_depth=1` blocks a 2-hop path.

## 8. Bridge entities

- `GET /cases/{id}/graph/bridges`. Three real properties per node:
  1. **Articulation** (`nx.articulation_points`) with **connectivity
     impact** = extra components created by removal;
  2. **Betweenness** (`nx.betweenness_centrality`, normalized);
  3. **Cross-case reach** = distinct confirmed cases the identity appears
     in (merged graph).
- **Documented, deterministic score:**
  `bridge_score = 0.45·betweenness + 0.35·connectivity-impact +
  0.20·cross-case-reach` — each term normalized within the graph.
  Reported only for degree ≥ 2 and score ≥ 0.25 (cap 10). Every reported
  reason bullet is derived from the computed values.
- Verified: case 1 → Aarav Mehta & Rohan Deshmukh at 1.00 (articulation +
  max betweenness + 3-case reach); Meridian case → 5 bridges
  (0.80 / 0.567 / 0.414 …); a synthetic triangle → **zero** bridges
  (asserted in tests).

## 9. Cross-case analysis

- `GET /cases/{id}/graph/cross-case`. A connection exists **only** when
  confirmed data links the cases: the same (entity type, normalized name)
  confirmed in both cases — in the merged graph, a node with ≥ 2 case ids.
- Where relationships touch the shared entity on both sides, one example
  confirmed path is included (`entity(case A) → shared entity →
  entity(case B)`), deterministically chosen.
- **Anti-false-positive rules asserted in tests:** no shared identity → no
  connection; same name with a **different type** is not a shared entity;
  text similarity and timestamps are never used.
- Verified live: CASE-2026-001 ↔ CASE-2026-002 and ↔ CASE-2026-003, each
  with 7 shared confirmed entities and example paths; Meridian
  (CASE-2026-021) reports no connections to the seed cases (correct — it
  shares no confirmed identity).

## 10. Clusters

- `GET /cases/{id}/graph/clusters` — connected components (deterministic
  order: size desc, then smallest node id), each with member list,
  entity/relationship counts, type breakdown, case span, key bridge
  (highest bridge score inside the component) and a neutral description.
- Greedy-modularity subgroups are attempted only on components with
  ≥ 8 members and reported only when they form a real partition
  (≥ 2 communities, each ≥ 3); otherwise they are omitted (documented).
- Isolated singletons are not clusters. Labels are neutral
  ("Connected group N") — never "criminal gang".
- Verified: case 1 → one 4-entity/3-link component + one 2-entity/1-link
  component (isolated seed entities correctly excluded); Meridian → one
  large connected group.

## 11. Metrics

- `GET /cases/{id}/graph/metrics` — per entity: `degree`,
  `weighted_degree` (each adjacent relationship counts 1 + its
  directly-linked evidence records — documented), `betweenness`,
  `component_size`, `cross_case_reach`, `is_articulation_point`,
  `neighbor_types`.
- Wording is neutral ("highly connected entity"), and evidence counts are
  presented in the UI as "analytical context, not proof".
- `HIGH_CONNECTIVITY` findings rank the top 5 entities with degree ≥ 3
  (degree, then betweenness, then id — deterministic).

## 12. Finding lifecycle

- **Generate:** `POST /cases/{id}/graph/analyze` runs all engines and
  persists one row per finding (with type, title, computed explanation
  bullets, structured details, involved entity ids, supporting
  relationship ids, linked evidence ids, related case ids, analysis
  method, graph version, `status = ACTIVE`).
- **List:** `GET …/findings` → `{graph_version, analyzed,
  current_findings, stale_findings}` (stale = different graph version).
- **Review:** `POST …/findings/{id}/review` → `REVIEWED` + reviewer +
  note + `FINDING_REVIEWED` audit.
- **Dismiss:** `POST …/findings/{id}/dismiss` → `DISMISSED` + note +
  `FINDING_DISMISSED` audit. Dismissed findings stay queryable — nothing
  is deleted.
- **Re-review:** a settled finding returns 409 `FINDING_REVIEW_NOT_ALLOWED`.
- **Missing / wrong-case finding:** 404 `FINDING_NOT_FOUND`.
- Verified end-to-end live and in tests, including audit rows
  (`FINDING_REVIEWED`/`FINDING_DISMISSED` with finding id, case, note).

## 13. Freshness

Documented, versioned (the spec's Option C, the simplest reliable
variant):

- Every analysis stores a `graph_version` — a deterministic SHA-256
  (16-char) hash over the sorted confirmed entities (id, type, normalized
  name) and relationships (id, type, source, target) of the case.
- Re-analyzing **unchanged** data is **idempotent**: the existing run is
  returned with `recomputed: false`, no duplicate findings.
- When the confirmed data **changes**, the new hash flags every earlier
  finding `stale` (API + UI banner "Stale — data changed"); a new run
  produces the current findings and the old ones remain as history
  (never deleted).
- No fake real-time invalidation, no silent staleness. Verified by
  `TestStaleness`: add a confirmed relationship → findings go stale →
  re-analyze → current set updates, history kept → restore → original
  findings current again.

## 14. Frontend

- **`src/services/v1/graphService.js`** on the shared axios client
  (analyze, findings, review/dismiss, metrics, bridges, clusters,
  cross-case, paths) — normalized errors, live-backed, no mock fallback.
- **Case Network page (additive; the React Flow graph is visually
  unchanged):**
  - **Network Intelligence panel** — "Analyze Network" trigger with
    loading state; "Not analyzed yet" state; "up to date / N stale"
    badge; findings list with type badges, expandable computed
    explanations, supporting-id counts, **Show in graph**, **Review** and
    **Dismiss**; stale-history drawer; "No significant connection found."
    empty state; `GRAPH_INSUFFICIENT_DATA` → warning toast; error state
    with retry.
  - **Path explorer** — two entity selects, bounded search, path results
    with hops/relationship types/hop count/linked-evidence count,
    per-node highlight, explicit "No confirmed connection path found."
  - **Bridge / Cluster / Cross-case panels** — computed data with reasons,
    type breakdowns, neutral labels, example cross-case paths, case link
    reusing existing case navigation (`/cases/:id/graph`).
  - **Entity detail** — per-entity metrics (degree, weighted degree,
    betweenness, group size, cases seen in, articulation badge) with the
    "analytical context, not proof" disclaimer.
  - **Graph highlighting** — dim-everything-else via the existing
    `NetworkGraph` `highlightIds` prop (no component rewrite), with a
    "Highlighting … — Clear" banner.
- **States covered:** loading, error (retry), empty, insufficient data,
  not-analyzed, stale — asserted by the extended sanity harness.

## 15. Security

- All 9 routes are JWT-authenticated (`get_current_user`); unauthenticated
  → 401 (verified).
- Role floor via the existing ladder (`require_roles("ANALYST")` on
  analyze/review/dismiss = every authenticated role, matching the Stage 3
  access matrix: ANALYST run/inspect/review; INVESTIGATOR
  view/run/review/dismiss; SUPERVISOR inspect+review; ADMIN all). Reads
  require any authenticated role. Enforced server-side.
- The analysis graph is fed **only** by confirmed rows; candidate ids are
  explicitly rejected (`ENTITY_NOT_CONFIRMED`).
- Audit rows (actor, case, finding, note, UTC time) contain no secrets,
  tokens or raw content; `GRAPH_ANALYSIS_FAILED` stores a truncated,
  user-safe reason.
- Error responses use the project's `{error:{code,message,details}}`
  shape; 500s are audited and re-raised as structured
  `GRAPH_ANALYSIS_FAILED`.

## 16. Tests executed

`backend/tests/test_graph_intelligence.py` — **56 tests**:

- **Engine units (no DB, synthetic confirmed records):** builder
  (nodes/edges/metadata, evidence linkage, dangling-row skip,
  candidate-exclusion), graph versioning (deterministic + sensitive),
  paths (direct / indirect / none / depth limit / cycle-free / cap),
  indirect connections (exclude direct pairs, prefer person pairs,
  bounded), bridges (articulation detected, degree-1 excluded, triangle →
  none, data-derived reasons), clusters (single/two components,
  singleton exclusion, key-bridge annotation), cross-case (shared entity
  + path, no false positives, type-mismatch not shared), metrics (values,
  ranking).
- **API (live PostgreSQL):** analyze on the 53-node Meridian case
  (findings > 0, allowed types, non-empty explanations, traceable ids),
  idempotent re-run, unknown case, empty case → 409
  `GRAPH_INSUFFICIENT_DATA`, audit rows written, analyst can analyze,
  401 unauthenticated; findings listing shape; review/dismiss workflow
  (self-created rows; re-review 409; nothing deleted); wrong-case finding
  404; paths (direct, indirect + explanation, `PATH_NOT_FOUND`, depth
  limit, unknown entity, other-case entity, candidate id →
  `ENTITY_NOT_CONFIRMED`, same entity → 400); metrics/bridges/clusters/
  cross-case values (incl. cross-case reach = 3 for Aarav Mehta and
  Meridian no-false-positives); legacy `/api/stats /api/graph
  /api/findings /legacy` + existing case sub-resources; staleness
  (data change → stale → re-analyze → restore).

## 17. Test results

| Suite | Command | Result |
| --- | --- | --- |
| Full backend | `cd backend && python3 -m pytest tests/ -q` | **199 passed, 1 skipped** (skip = live Neo4j round-trip; pre-existing), in ~10 s — **run twice, identical** (idempotent) |
| Stage 3 only | `cd backend && python3 -m pytest tests/test_graph_intelligence.py -q` | **56 passed** |
| Pre-existing suites | same run | v1 API 47, documents 25, extraction 28, pipeline/legacy/Neo4j/model tests all green |
| Frontend build | `npm run build` | ✓ built in ~10 s |
| Frontend sanity | `npm run test:frontend-sanity` | **All 29 pages rendered** (14 pre-existing + 15 new Stage-3 states: findings panel loading/not-analyzed/render/error, path explorer + path render, bridge list details + empty, cluster list info + empty, cross-case list data + empty, panel loading branches) |
| Frontend auth flow | `npm run test:frontend-auth` | **passed** (8/8 checks) |

## 18. Existing-functionality verification

- Legacy routes verified live (200): `/api/stats`, `/api/graph`,
  `/api/findings`, `/legacy` — and asserted in tests
  (`TestLegacyNotBroken`).
- All existing v1 routes verified live (200): `/api/v1/cases`, case
  detail, entities, relationships, evidence, documents, timeline,
  simulations, `/api/v1/health`.
- OpenAPI exposes exactly the 9 new `/graph/…` endpoints alongside the
  existing surface.
- Stage 1–2 features (documents upload/processing/review, case area,
  copilot status, auth) untouched; full suite green after the change.
- Live server restarted on the final code (process
  `nexus-api-fastapi-postgresql-91380d5e`, :8000); Vite dev server on
  :5173.

## 19. Limitations (honest, documented)

- **Relationship → evidence linkage** exists only where Stage 2
  provenance exists (`source_reference = candidate:{id}`); seeded
  relationships honestly report 0 linked evidence records. There is no
  free-text evidence→relationship matching (that would be guessing).
- **Cross-case identity** is (entity type, normalized name). Two distinct
  real people who happen to share a confirmed name are treated as the
  same identity — the same, documented, explainable convention the seed
  data itself uses. Type-mismatches are never merged.
- **Scale:** the engine is bounded for case-sized graphs (dozens to low
  hundreds of nodes; the 53-node/138-edge Meridian case analyzes in
  < 0.2 s). Betweenness is recomputed on demand per request — adequate
  at platform scale, to be cached if graphs grow by orders of magnitude.
- **Bridge score** is a documented deterministic composite, not a
  statistically calibrated probability; thresholds (0.25 / degree 2) are
  documented constants, tuned for small case graphs.
- **Modularity subgroups** are intentionally conservative (omitted unless
  a real partition exists) — most small components report no subgroups.
- The legacy `/api/findings` (CNA pipeline) and the new
  `/graph/findings` are different things by design; both work.

## 20. Stage-4 recommendation

Suggested next stage (per the original roadmap, nothing built here):

1. **Contradiction & hypothesis engines** on the confirmed graph — the
   Stage 1 `app/intelligence/` foundation (contradiction engine, impact
   simulator) can be wired to the same confirmed-data service pattern
   used in Stage 3 (engine = pure functions + persisted, versioned,
   reviewable findings + audit + RBAC), reusing `graph_finding`-style
   lifecycle.
2. **Evidence-impact scoring** — extend the evidence linkage
   (source_reference) into a per-entity "evidence weight" used by
   bridge/connectivity scores, with the same "context, not proof"
   framing.
3. **Timeline & geospatial intelligence** — the confirmed
   `timeline_event`/`location` data is already present; build
   event-overlap and co-location analyses with the same bounded,
   explainable pattern.
4. **Multilingual extraction** — the LLM provider contract from Stage 2
   (config via `LLM_*`) is ready; extend the rule provider's gazetteers.
5. **Scale hardening** — cache per-`graph_version` metrics/betweenness,
   index-friendly cross-case identity lookups, and pagination for
   findings lists.

**Stop.** Stage 3 complete.
