# NEXUS — System Architecture

NEXUS is a monorepo with two cooperating systems and one shared frontend:

```
┌────────────────────────────────────────────────────────────────────────────┐
│  FRONTEND (repo root)                                                      │
│  React 18 + Vite + Tailwind + React Router 6                               │
│                                                                            │
│  ┌──────────────────────────┐   ┌────────────────────────────────────────┐ │
│  │ Case area (live)         │   │ Analysis section (pipeline)            │ │
│  │ /cases · /copilot        │   │ /investigations/:id/analysis           │ │
│  │ services/v1/*            │   │ services/cnaService → /cna-api         │ │
│  │ JWT auth, no mock data   │   │ mock-first dashboard & demo screens    │ │
│  └────────────┬─────────────┘   └───────────────────┬────────────────────┘ │
└───────────────┼─────────────────────────────────────┼──────────────────────┘
                │ /api/v1 (vite proxy)                │ /cna-api → /api (vite proxy)
┌───────────────┴─────────────────────────────────────┴──────────────────────┐
│  BACKEND (backend/) — one FastAPI application, two API surfaces           │
│                                                                            │
│  /api/v1/*        PLATFORM (Stage 1 foundation)                           │
│   ├ auth (JWT login/me, RBAC)  ├ users  ├ cases + 11 sub-resources        │
│   ├ documents · entities · relationships · evidence · timeline ·          │
│   │ locations · hypotheses · contradictions · gaps · simulations          │
│   └ copilot (status, foundation stage)                                    │
│   layers: api/v1 → services → repositories → models (SQLAlchemy 2.0)      │
│   graph/: NetworkX build + analytics + GraphStore export seam (Cypher/    │
│           JSON) — computed in-process, no graph database required         │
│   seed.py: atomic, idempotent seed — spec dataset + Operation Meridian    │
│                                                                            │
│  /api/*           ANALYSIS PIPELINE (pre-existing, preserved)              │
│   CNA endpoints over the synthetic corpus: network, findings, NLQ,        │
│   report export (PDF) — see docs/PIPELINE_ARCHITECTURE.md                 │
└───────────────┬──────────────────────────────────────────┬─────────────────┘
                │                                          │
        ┌───────────────────────────────┐   ┌─────────────────────────────┐
        │  Supabase PostgreSQL          │   │  Supabase Storage (optional)│
        │  (primary; session-mode :5432)│   │  private bucket, evidence   │
        │  platform + CNA tables;       │   │  files via S3 API (server-  │
        │  source of truth for the      │   │  side, service-role key)    │
        │  graph                        │   └─────────────────────────────┘
        └───────────────────────────────┘
        Graph intelligence: built in-process with NetworkX over the
        relational rows — no graph database to install or run.
```

## Design rules (binding)

1. **Two data worlds, one truth per world.** The case area is live-backed by
   PostgreSQL — it renders explicit loading/empty/error/offline states and
   never falls back to mock data. The analysis section is the pre-existing
   demonstration pipeline (synthetic corpus, real code); its mock-driven
   screens keep working exactly as before.
2. **No fake capabilities.** Every UI control performs the call it implies.
   Foundation-stage surfaces (copilot chat, impact scoring, advanced graph
   analytics) are labelled as later stages rather than simulated.
3. **Synthetic data only.** All people, cases, numbers and documents are
   fictional, generated reproducibly by `data/generator.py`, and labelled
   "synthetic demonstration data" in the UI and API health flag.
4. **Layering.** Routers (HTTP only) → services (business rules) →
   repositories (queries) → models. The frontend mirrors this with a
   service layer per concern; pages never import data modules directly.
5. **Secrets.** Configuration via environment/`.env` (see
   `backend/.env.example`). No secrets in source, no API keys in React code.
6. **No graph database.** Graph intelligence runs in-process with NetworkX
   over the relational rows; there is no external graph dependency. The
   optional capability dependencies (OCR, LLM, reportlab, S3 storage)
   degrade honestly — each is reported in the System view and its absence
   fails the affected document with a clear error, never a crash.

## Stage 1 — platform foundation (this build)

- **Auth:** JWT (HS256), bcrypt password hashing, four roles
  (INVESTIGATOR / ANALYST / SUPERVISOR / ADMIN) enforced server-side;
  protected routes and a simple demo login from seeded credentials.
- **Data model:** 13 platform tables (user, case, document, entity,
  relationship, evidence, timeline_event, location, hypothesis,
  contradiction, investigation_gap, simulation, audit_log) — see
  `docs/DATABASE.md`.
- **API:** `/api/v1/*` — auth, users, cases with sub-resources, copilot
  status — see `docs/API.md`.
- **Seed:** `backend/app/seed.py` runs atomically on startup when the DB is
  empty (single commit, full rollback on any failure, idempotent re-runs).
  It loads the spec dataset (5 persons, 2 vehicles, 4 locations, cases
  CASE-2026-001…003) and the Operation Meridian corpus (53 entities,
  138 relationships, 40 source documents, contradictions, findings →
  hypotheses) as CASE-2026-021.
- **Graph:** the knowledge graph is built in-process with **NetworkX** from
  the confirmed relational rows (no graph database). `graph/store.py`
  provides the export seam (`CypherExportStore`, `JsonExportStore`).
  Node/relationship vocabulary is fixed (9 node types, 10 relationship
  types) so a Cypher export maps rows 1:1. (Graph analytics arrive in
  Stage 3, still in-process.)
- **Frontend:** `src/services/v1/*` centralized HTTP client with JWT
  headers; case registry (`/cases`), case file with nine tool tabs
  (`/cases/:caseId/…`), and the copilot status page (`/copilot`).
  JWT-first login with an explicitly-labelled offline demo fallback.

## Stage 2 — document ingestion & entity extraction (this build)

- **Ingestion:** `POST /cases/{id}/documents` validates (extension,
  contradicting MIME, size, empty, PDF header, encoding, CSV header),
  streams the SHA-256, stores the file under
  `backend/storage/documents/{case_id}/{doc_id}_{safe_stem}.ext` with a
  server-generated name, and commits row + file atomically. Duplicate
  content per case is rejected by hash (409).
- **Processing:** background task (`document_service.process_document`)
  with its own session: `UPLOADED → PROCESSING → PROCESSED|FAILED`.
  `document_processor` normalizes the stored file into a capped
  `DocumentContent` (PDF pages / TXT lines / CSV rows). Any read or parse
  failure marks the document `FAILED` with a user-safe message; retries
  are idempotent.
- **Extraction:** `services/entity_extraction.py` defines the contract
  (pydantic `ExtractionResult`, `SourceRef`) and two providers behind one
  interface: a **rule-based** provider (deterministic, no credentials —
  the default) and an **LLM** provider (OpenAI-compatible, JSON-only
  contract, Pydantic-validated; the LLM never touches the database and any
  deviation fails the document). The case's confirmed entities and the
  synthetic corpus act as gazetteers. Confidence values are a documented,
  deterministic table per rule — never random, never a substitute for the
  investigator's decision.
- **Provenance (mandatory):** every candidate and relationship carries
  `document_id` + page (PDF) / line (TXT) / row+column (CSV) + snippet.
  Unavailable locations are represented as missing, never invented.
- **Resolution:** `services/entity_resolution.py` proposes
  `EntityMatchSuggestion` rows (exact 1.00, initial+surname 0.82,
  token-overlap ≥ 0.55) with the data-supported reasons. No silent
  merges: acceptance is an explicit investigator action.
- **Review:** candidates/relationships/matches accept/reject/defer
  endpoints; only acceptance writes to the confirmed case data (Entity,
  Relationship, Evidence, TimelineEvent) — all with provenance metadata.
  The uploaded file and the extraction record are immutable after
  processing; rejections remain in the tables for the audit trail.
- **Storage:** files live on the filesystem (gitignored); PostgreSQL holds
  metadata only (`storage_path`, `mime_type`, `file_size`, `sha256`,
  `uploaded_by`, `processed_at`, `processing_error`) and the path is never
  exposed through the API.
- **Frontend:** `documentService.js` on the shared v1 client; the Evidence
  tab now opens with a Documents panel (upload, real pollable status,
  counts, retry, review link); a review workspace at
  `/cases/:caseId/documents/:documentId` presents matches → candidates →
  relationships with working accept/reject/defer actions.
- **Audit:** DOCUMENT_UPLOADED / PROCESSING_STARTED|COMPLETED|FAILED /
  PROCESS_REQUESTED / ENTITY_ACCEPTED|REJECTED|DEFERRED /
  RELATIONSHIP_ACCEPTED|REJECTED / ENTITY_MATCH_ACCEPTED|REJECTED.


## Stage 3 — graph intelligence & hidden connection engine (this build)

Analyzes the **confirmed** case graph (confirmed `Entity` + `Relationship`
rows only — extraction candidates, pending/rejected review items and
unresolved matches never enter the analysis) with **NetworkX** and produces
explainable, traceable findings that an investigator can review. There is no
LLM and no similarity guessing anywhere in this stage; every finding is the
output of a named algorithm over confirmed data, and every explanation is
generated from the computed values.

- **Service layer:** `backend/app/services/graph_intelligence/`
  (`graph_builder`, `path_analysis`, `bridge_analysis`, `cluster_analysis`,
  `cross_case_analysis`, `metrics`, `finding_service`, `endpoints`).
  Flow: API router → service → engine (NetworkX) → PostgreSQL. No
  algorithm lives in a router. The pre-existing `app/graph/` CNA pipeline
  is untouched and keeps feeding `/api/stats`, `/api/graph`,
  `/api/findings`, `/legacy`.
- **Confirmed graph builder:** builds a NetworkX graph per case
  (node id `e{entity_id}`) and a **merged cross-case graph** in which
  confirmed entities sharing the same (entity type, normalized name)
  across cases collapse to one node. Node metadata carries entity ids,
  type, display name, case ids and directly-linked evidence ids; edge
  metadata carries the relationship id/type, case id and its directly
  linked evidence ids (Stage 2 acceptance writes evidence rows whose
  `source_reference` is `candidate:{id}`, which is read back as the
  entity/relationship → evidence link). Dangling rows are skipped; a
  candidate-shaped id can never enter the graph.
- **Paths:** `nx.all_shortest_paths` after a bounded BFS
  (`single_source_shortest_path_length`, `cutoff` = depth limit). Depth
  ≤ 4 hops, ≤ 5 paths, cycle-free by construction (simple paths). No
  path → explicit `PATH_NOT_FOUND` ("No confirmed connection path
  found."). Candidate ids are rejected with `ENTITY_NOT_CONFIRMED`.
- **Bridge entities:** articulation points
  (`nx.articulation_points`) + normalized betweenness
  (`nx.betweenness_centrality`) + connectivity impact (extra components
  created by node removal) + cross-case reach (distinct confirmed cases
  the identity appears in, from the merged graph). Documented,
  deterministic score:
  `0.45·betweenness + 0.35·connectivity-impact + 0.20·cross-case-reach`
  (each term normalized in-graph). Only degree ≥ 2 nodes with score ≥
  0.25 are reported; a triangle yields zero bridges.
- **Cross-case:** a connection exists only when confirmed data links the
  cases — the same (type, normalized name) confirmed in both cases
  (shared entity) and, when relationships touch it on both sides, a
  confirmed example path `entity(case A) → shared entity → entity(case
  B)`. Same name with a different type is **not** a shared entity; text
  similarity and timestamps are never used.
- **Clusters:** connected components (deterministic; largest first).
  Greedy modularity communities are attempted only on components with
  ≥ 8 members and reported only when they form a real partition
  (≥ 2 communities, each ≥ 3); otherwise they are omitted and the
  component remains the cluster. Neutral labels only:
  "connected group" / "network cluster".
- **Metrics:** degree, evidence-weighted degree (each relationship
  counts 1 + its directly-linked evidence records — documented),
  betweenness, connected-component size, cross-case reach. Wording is
  neutral ("highly connected entity"), and evidence counts are always
  presented as analytical context, never as proof.
- **Findings:** persisted `graph_finding` rows (see Database doc) with
  type (`HIDDEN_CONNECTION`, `BRIDGE_ENTITY`, `CROSS_CASE_CONNECTION`,
  `NETWORK_CLUSTER`, `HIGH_CONNECTIVITY`), title, summary, computed
  explanation bullets, structured details, `involved_entity_ids`,
  `supporting_relationship_ids`, `supporting_evidence_ids`,
  `related_case_ids`, `analysis_method`, `graph_version` and status
  (`ACTIVE` → `REVIEWED` | `DISMISSED`). Review/dismiss are audit-logged
  and never delete a finding.
- **Freshness (documented, versioned):** every analysis stores a
  `graph_version` — a deterministic hash of the confirmed entities +
  relationships it ran on. Re-analyzing unchanged data is idempotent
  (`recomputed: false`); when the hash changes, old findings are flagged
  `stale` in the API/UI and kept as history; the new run produces the
  current findings. No fake real-time invalidation, no silent staleness.
- **API:** `POST /cases/{case_id}/graph/analyze`,
  `GET /cases/{case_id}/graph/findings | metrics | bridges | clusters |
  cross-case`, `GET /cases/{case_id}/graph/paths?source_entity_id=&
  target_entity_id=&max_depth=&max_paths=`,
  `POST /cases/{case_id}/graph/findings/{id}/review | dismiss`.
  Role floor ANALYST (every authenticated role can view, run and review;
  matrix enforced server-side via the existing ladder).
- **Frontend:** the existing React Flow graph is visually unchanged;
  around it the Case Network page gains a Network Intelligence findings
  panel ("Analyze Network" trigger, "Not analyzed yet" state, loading /
  error / empty states, stale-history drawer), a path explorer, bridge /
  cluster / cross-case panels, per-entity metrics in the entity detail,
  and graph highlighting (dim-everything-else) with a Clear button —
  all built from the existing Card/Badge/Button/EmptyState primitives.
- **Audit:** GRAPH_ANALYSIS_STARTED | COMPLETED | FAILED,
  FINDING_REVIEWED, FINDING_DISMISSED (actor, case, finding, note, ts;
  no secrets).

## Stage 4 — investigation reasoning & evidence intelligence (this build)

**Scope:** explain and interrogate the *why* behind the stage-3 output.
Layered `API router → service → pure engines → confirmed-data builder /
repository`, exactly like stage 3. New package
`backend/app/services/investigation_intelligence/`; the case network
graph, the stage-3 engine and the legacy pipeline are untouched.

**Confirmed-data-only boundary (binding).** The builder
(`confirmed_data.py`) loads only confirmed records — `entity`,
`relationship`, `evidence`, `timeline_event`, `location` — for the case.
Extraction candidates, rejected/pending review items, unresolved match
suggestions and text-similarity guesses never enter the analysis; there
is no promotion path from a candidate to a confirmed record anywhere in
stage 4. Every engine is a pure function of that snapshot (unit-tested
without a database), so the same confirmed records always produce the
same findings, hypotheses and scores.

**Engines (pure, documented, neutral language).**

- `contradictions.py` — three implemented rule types, each documented
  with its exact rule and parameters:
  R1 `TIMELINE_CONTRADICTION` — one confirmed entity, two confirmed
  dated events at two different confirmed coordinates, separation ÷
  100 km/h (conservative minimum travel time) > available time;
  R2 `LOCATION_CONTRADICTION` — identical timestamps (Δt < 1 min),
  different coordinates, distance / 100 km/h reported;
  R3 `RELATIONSHIP_CONTRADICTION` — mutual OWNS between two confirmed
  entities (the only relationship state the domain documents as
  incompatible). `EVIDENCE_CONTRADICTION` is deliberately not
  implemented: the evidence model has no structured claims to compare,
  and the rule would be guesswork. Missing coordinates/timestamps are
  surfaced as *insufficient pairs* (with counts), never as contradictions.
  Severity: HIGH when the computed margin > 50%, otherwise MEDIUM.
- `hypotheses.py` — competing explanations per contradiction
  (assumption-based vs record-accuracy; split by the travel-time margin)
  and per indirect person-pair (direct link vs mediated, plus an
  explicit "insufficient to distinguish" hypothesis when the two scores
  are within 0.05). The score is deterministic and its components are
  stored verbatim: `analytical_score = 0.30·min(1, evidence/4) +
  0.20·min(1, relationships/3) + 0.20·consistency + 0.15·provenance +
  0.15·min(1, entities/5)`; bands LOW < 0.34 ≤ MEDIUM < 0.67 ≤ HIGH.
  The margin override (a margin > 50% caps consistency at 0.5, a margin
  < 5% caps it at 0.75) keeps scores honest against the rule evidence.
  Statuses ACTIVE / REVIEWED / DISMISSED; generated hypotheses are
  deduplicated by (title, type) across versions; investigator-created
  hypotheses persist across re-analyses.
- `impact.py` — per-evidence metrics (linked entities / relationships /
  events, cited findings / hypotheses) and `impact_score =
  0.5·graph_share + 0.25·finding_share + 0.25·hypothesis_share`
  (HIGH ≥ 0.67, MEDIUM ≥ 0.34). `simulate_removal` recomputes degrees,
  betweenness and weak components on an **in-memory copy** (sole
  provenance edge rule: an evidence-less relationship survives only when
  it has a second supporting evidence) and returns before/after +
  diff. It performs **zero database writes** (proven in tests).
- `timeline.py` — `EVENT_OVERLAP` (overlapping ranges, or point events
  within 5 min of the same entity), `TEMPORAL_PROXIMITY` (Δt ≤ 30 min),
  `EVENT_SEQUENCE` (≥ 3 dated events for one confirmed entity, ordered,
  with durations), `TIMELINE_GAP` (> 12 h between consecutive events —
  reported only as a *potential investigation gap*).
- `geospatial.py` — `CO_LOCATION` (< 0.05 km), `LOCATION_PROXIMITY`
  (≤ 2 km), `LOCATION_SEQUENCE` (ordered distinct locations for one
  entity). Haversine only — no GIS dependencies. Confirmed LOCATION
  entities join to `location` rows by (case, normalized name); records
  without usable coordinates produce `LOCATION_DATA_INSUFFICIENT`, not
  insights.
- `gaps.py` — four confirmed-data gap types: EVIDENCE (degree ≥ 3, zero
  linked evidence), RELATIONSHIP (indirect 2–3 hop path, no direct
  link), TIMELINE (reused from `timeline.py`), IDENTITY (confirmed
  PERSON, no aliases/identifying metadata, ≥ 2 relationships).

**Findings & versioning.** Findings persist in the stage-3
`graph_finding` table under four new types (CONTRADICTION,
TIMELINE_INSIGHT, GEO_INSIGHT, INVESTIGATION_GAP); stage-3 listing
endpoints filter to stage-3 types, stage-4 endpoints to stage-4 types.
The snapshot hash extends the stage-3 format to evidence, timeline
events and locations, so a change in any of them flags the analysis
`stale`; re-analysis is idempotent per snapshot; stale runs are kept as
history, never deleted. The only new table is `investigation_hypothesis`.

**Lifecycle & RBAC.** Reuses stage 3: review/dismiss on findings and
hypotheses (409 `FINDING_REVIEW_NOT_ALLOWED` when already reviewed/
dismissed), append-only audit, nothing ever deleted. Role floor:
reads for ANALYST+, analysis/review actions for INVESTIGATOR+
(matrix enforced server-side). Structured errors include
409 `INSUFFICIENT_CONFIRMED_DATA` for cases without confirmed graph
data.

**Frontend.** New "Investigation" tab per case (stage-3 graph
untouched) with seven panels — analysis status & run, potential
contradictions, competing hypotheses (score bars + components +
disclaimer "analytical support only — not proof or a probability of
guilt"), evidence impact (per-record scores + simulation with its
"simulation only" banner), timeline intelligence, geospatial
intelligence (reusing the existing Leaflet map), and investigation
gaps. Every panel renders all six states (not-analyzed / analyzing /
up-to-date / stale / insufficient / error); **Show in graph** reuses
the case graph's `highlightIds` mechanism via a deep link.

**Audit:** INVESTIGATION_ANALYSIS_STARTED | COMPLETED | FAILED,
CONTRADICTION_DETECTED, INVESTIGATION_GAP_DETECTED,
TIMELINE_ANALYSIS_COMPLETED, GEO_ANALYSIS_COMPLETED,
EVIDENCE_IMPACT_ANALYZED, HYPOTHESIS_GENERATED | CREATED |
REVIEWED | DISMISSED (actor, case, target, note, ts; no secrets).
Finding reviews reuse the stage-3 `FINDING_REVIEWED` /
`FINDING_DISMISSED` actions.

## Stage 5 — multilingual investigation support (this build)

Language detection + normalization in the document pipeline (real
detection with declared per-language rule packs; unproven languages
report `unsupported` honestly), multilingual extraction, and structured
cross-language claims feeding the stage-4 contradiction engine.
Existing single-language paths are unchanged; details in
`docs/MULTILINGUAL.md`.

## Stage 6 — the case workflow (this build)

One case from upload to intelligence, all case-scoped, no mock
fallback. New in-place components:

```
routers/v1/cases.py ──▶ CaseService ───────────────▶ Case (access model:
   │                                                           owner/supervisor/admin)
   ├── upload → DocumentProcessingJob (real per-doc job rows;
   │            stages: ingest → text → OCR → normalize →
   │            extract → resolve → review candidates)
   ├── review/queue|confirm|reject → ExtractedEntity /
   │   ExtractedEntityMatch / ExtractedRelationship (candidates;
   │   human confirm only; relationships CANDIDATE by default)
   ├── graph/build|get → confirmed-case graph only (versioned;
   │   per-node evidence counts, per-edge provenance)
   └── analysis/run|status → CaseAnalysisService ──▶ orchestrates the
        EXISTING engines in order: graph build → network → anomalies →
        contradictions → hypotheses → timeline → geospatial → gaps →
        findings persistence.  Freshness state machine:
        not-analyzed / up-to-date / stale(reason) / insufficient.
        Stale findings preserved (old graph_version), never deleted.
```

- **Access model:** every case endpoint resolves the case with an
  ownership check — other investigators get 404 (no existence
  leakage) on read, upload, review, graph, analysis, copilot, audit.
- **Audit:** case creation, uploads, processing completion/failure,
  every confirm/reject, graph build, analysis run; read-only
  `GET /cases/{id}/audit`. No secrets in rows.
- **Frontend:** 17-tab case workspace (Documents, Review, Entities,
  Relationships, Impact, Reports added); deep links `?entity=` /
  `?evidence=` / `?location=` / `?relationship=`; readiness panel with
  next action; stale banner with reason. No mock fallback — live
  errors render instead of fake data.
- **Demo:** `CASE-DEMO-END2END-01` (FIR + CDR + 3 reports → full
  workflow, labeled SYNTHETIC DEMONSTRATION DATA; coordinates NULL
  where unstated — never fabricated).

Details: `docs/CASE_WORKFLOW.md`, `STAGE6_REPORT.md`.

## Explicitly NOT implemented (later stages)

CCTV and facial recognition, and real police-system integrations.
OCR of scanned pages is wired (stage 2) but only activates when an OCR
engine is installed. The LLM extraction provider is configured via
`LLM_*` env but is off by default; the copilot provider contract
surfaced in stage 5 takes the LLM conversation stage forward.
(Rule-based extraction and entity resolution shipped in stage 2; the
contradiction / hypothesis / evidence-impact engines shipped in stage
4 — deterministic, over confirmed data only; the multilingual rule
packs shipped in stage 5.) The pre-existing pipeline code that touches
some of these topics is preserved unchanged; it is not extended.

## Detailed documentation

| Document | Contents |
| --- | --- |
| `docs/API.md` | The `/api/v1/*` contract, auth, error shape |
| `docs/DATABASE.md` | Supabase/PostgreSQL schema, Alembic migrations, storage, environment |
| `docs/PIPELINE_ARCHITECTURE.md` | The analysis pipeline (pre-existing) |
| `docs/DATA_MODEL.md`, `docs/CONTRADICTION_ENGINE.md`, `docs/IMPACT_SIMULATOR.md` | Pipeline modules |
| `docs/CASE_WORKFLOW.md` | Stage-6 case workflow: documents → review → graph → intelligence, states, access model, audit |
| `docs/MULTILINGUAL.md`, `docs/COPILOT.md` | Stage-5 language support and the copilot contract |
