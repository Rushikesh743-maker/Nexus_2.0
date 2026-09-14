# NEXUS — AI-Powered Criminal Network Analysis & Investigation Intelligence

A monorepo investigation platform: a **live case-management foundation**
(FastAPI + PostgreSQL + JWT, React frontend) built in Stage 1 around a
**pre-existing criminal-network-analysis pipeline** (Python + synthetic
corpus) that keeps running unchanged.

> **Synthetic data only.** Every person, case, number, document and
> transaction in this system is fictional and generated reproducibly by
> `data/generator.py`. The UI carries a standing disclosure to that effect.
> No real case material, people or police databases are used or connected.

---

## What is in Stage 1 (this build)

**Backend — platform foundation (`/api/v1`)**

- FastAPI + Pydantic + SQLAlchemy 2.0, layered
  (routers → services → repositories → models).
- JWT auth (HS256, bcrypt) with four roles —
  INVESTIGATOR / ANALYST / SUPERVISOR / ADMIN — and protected routes.
- 13 platform tables (cases, documents, entities, relationships, evidence,
  timeline, locations, hypotheses, contradictions, gaps, simulations,
  audit log) created and **atomically seeded** at startup.
- Seeded data: the spec dataset (5 persons, 2 vehicles, 4 locations,
  CASE-2026-001…003) plus the Operation Meridian corpus (53 entities,
  138 relationships, 40 source documents, contradictions, findings →
  hypotheses) as CASE-2026-021.
- Case API with sub-resources and cross-case entity links; structured error
  shape; startup/DB/auth logging (no secrets in logs).
- **Graph intelligence:** computed in-process with **NetworkX** over the
  relational data (confirmed records only) — there is no graph database to
  install or run; the Cypher/JSON export stays available for other tools.
- Copilot endpoint at foundation stage (status + provider config surface).

**Frontend (repo root, existing React/Vite stack extended)**

- `src/services/v1/*` — centralized axios client, JWT headers, normalized
  errors (offline vs. 401 vs. validation).
- **Case area (live-backed, no mock data):** `/cases` registry + case file
  with Overview, Graph (React Flow), Evidence, Timeline, Map (Leaflet),
  Hypotheses, Contradictions, Gaps, Simulation; `/copilot` status page.
- JWT-first login with an explicitly-labelled offline demo fallback.
- The analysis section (`/investigations/:id/analysis/…`) and all pre-existing
  screens keep working exactly as before.

**Not implemented yet (by design):** LLM conversation, advanced graph
analytics, OCR, evidence-impact scoring, multilingual AI,
CCTV/facial recognition, real integrations. Foundation-stage UI labels the
gap instead of faking it.

---

## What is in Stage 2 (this build)

**Document ingestion & entity extraction — in-place on the Stage 1
platform, same stack, no parallel implementations.**

**Backend**

- **Upload & storage:** `POST /cases/{id}/documents` accepts PDF / TXT /
  CSV, validates (extension, contradicting MIME, size, empty, `%PDF`
  header, encoding, CSV header), streams the SHA-256, and stores the file
  under `backend/storage/documents/{case_id}/{doc_id}_{safe_stem}.ext`
  (server-generated name; the path is metadata in PostgreSQL and **never**
  exposed by the API). Duplicate content per case → `409`.
- **Processing lifecycle:** background task with its own session;
  `UPLOADED → PROCESSING → PROCESSED | FAILED` is real and pollable (no
  invented percentages). A `FAILED` document carries a user-safe error and
  can be retried (`POST /documents/{id}/process`); reprocessing is
  idempotent. Corrupt PDFs, non-UTF-8 text, and malformed CSVs fail
  honestly with structured codes.
- **Extraction:** `document_processor` normalizes the stored file into a
  capped `DocumentContent`; `entity_extraction` runs behind one
  `EntityExtractionProvider` interface — a deterministic **rule-based**
  provider (default, no credentials) and an **LLM** provider
  (OpenAI-compatible via the existing `LLM_*` env, JSON-only contract,
  Pydantic-validated; the LLM never writes to the DB and any malformed
  output fails the document). Confidence is a documented table, never
  random.
- **Provenance (mandatory):** every candidate/relationship carries
  `document_id` + page (PDF) / line (TXT) / row+column (CSV) + snippet;
  an unavailable location is represented, never invented.
- **Entity resolution:** `entity_resolution` proposes match suggestions
  (exact 1.00 / initial+surname 0.82 / token-overlap ≥ 0.55) with the
  data-supported reasons. No silent merges.
- **Investigator review:** accept / reject / defer for entity candidates,
  relationships, and matches. Only **acceptance** writes to the confirmed
  case data — `Entity`, `Relationship`, `Evidence`, `TimelineEvent` — each
  carrying provenance. Rejected candidates are preserved for the audit
  trail; the uploaded file and extraction record are immutable.
- **Audit:** every step (upload, processing transitions, and every review
  decision) writes an `audit_log` row with actor, case, object id, time,
  and structured metadata (no secrets, no raw content).
- **Four new tables** (`document_extraction`, `entity_candidate`,
  `relationship_candidate`, `entity_match_suggestion`) plus six columns on
  `document`; pre-existing databases get the new columns via an idempotent
  startup migration.

**Frontend (existing case area extended, nothing restyled)**

- `src/services/v1/documentService.js` on the shared axios client.
- The **Evidence** tab now opens with a **Documents** panel: upload, real
  pollable status, extraction counts, retry-on-failure, and a review link.
- A new **review workspace** at `/cases/:caseId/documents/:documentId`
  presents suggested matches → entity candidates → relationship proposals,
  each with working accept / reject / (defer) actions and full provenance.

**Synthetic fixtures:** `data/documents/` holds a small, labelled set
(`synthetic_fir.txt/.pdf`, `synthetic_calls.csv`) generated reproducibly by
`data/documents/generate_fixtures.py` — fictional names/numbers, clearly
marked "SYNTHETIC DEMONSTRATION DATA".

---

## What is in Stage 3 (this build)

**Graph intelligence & hidden connection engine — in-place on Stages
1–2, same stack, no parallel implementations.**

**Backend**

- A new service layer `backend/app/services/graph_intelligence/` analyzes
  the **confirmed** case graph with **NetworkX** (confirmed entities +
  relationships only — extraction candidates and unresolved matches never
  enter the analysis). No LLM, no similarity guessing: every finding is a
  named algorithm's output, and every explanation is generated from the
  computed values.
- **Paths:** bounded BFS shortest paths (depth ≤ 4 hops, ≤ 5 results,
  cycle-free). No path → explicit `PATH_NOT_FOUND`; candidate ids →
  `ENTITY_NOT_CONFIRMED`.
- **Bridge entities:** articulation points + betweenness centrality +
  connectivity impact + cross-case reach, combined with a documented,
  deterministic score; a triangle yields zero bridges (an honest empty
  answer).
- **Cross-case:** only confirmed links — the same (entity type,
  normalized name) confirmed in two cases, with an example confirmed path
  through the shared entity where the data supports one.
- **Clusters:** connected components (deterministic); optional greedy
  modularity communities only when they split a large component
  meaningfully. Neutral labels — "connected group", never a label
  implying guilt.
- **Metrics:** degree, evidence-weighted degree, betweenness, component
  size, cross-case reach — always presented as analytical context, not
  proof.
- **Findings:** a new `graph_finding` table persists
  `HIDDEN_CONNECTION / BRIDGE_ENTITY / CROSS_CASE_CONNECTION /
  NETWORK_CLUSTER / HIGH_CONNECTIVITY` findings with their involved
  entities, supporting relationships, linked evidence ids, the analysis
  method and a `graph_version` (snapshot hash of the confirmed data).
  **Freshness:** re-analyzing unchanged data is idempotent; when the
  confirmed data changes, old findings are flagged *stale* and kept as
  history — never deleted, never silently reused.
- **Review workflow:** `POST …/findings/{id}/review | dismiss` mark
  findings `REVIEWED` / `DISMISSED` with reviewer + note; both are
  audit-logged (`GRAPH_ANALYSIS_STARTED/COMPLETED/FAILED`,
  `FINDING_REVIEWED`, `FINDING_DISMISSED`).
- **API:** `POST /cases/{id}/graph/analyze`,
  `GET /cases/{id}/graph/findings | metrics | bridges | clusters |
  cross-case | paths` — structured errors (`CASE_NOT_FOUND`,
  `ENTITY_NOT_FOUND`, `ENTITY_NOT_CONFIRMED`, `GRAPH_INSUFFICIENT_DATA`,
  `GRAPH_ANALYSIS_FAILED`, `PATH_NOT_FOUND`, `FINDING_NOT_FOUND`,
  `FINDING_REVIEW_NOT_ALLOWED`).
- The pre-existing CNA pipeline and its routes (`/api/stats`,
  `/api/graph`, `/api/findings`, `/legacy`) are untouched and keep
  working.

**Frontend (existing case network page extended, nothing restyled)**

- `src/services/v1/graphService.js` on the shared axios client.
- The **Case Network** page now carries: a **Network Intelligence**
  findings panel with the *Analyze Network* trigger (and "Not analyzed
  yet" / loading / error / empty states), a **path explorer** (pick two
  entities → confirmed paths with length, relationships and linked
  evidence; "No confirmed connection path found." when there is none),
  **bridge / cluster / cross-case** panels, per-entity metrics in the
  entity detail, and graph highlighting with a **Clear** button. The
  React Flow graph itself is visually unchanged.

---

## What is in Stage 4 (this build)

**Investigation reasoning & evidence intelligence — in-place on Stages
1–3, same stack, no parallel implementations, no graph redesign.**

Stage 4 answers *"why did NEXUS produce this finding?"* by reasoning over
**confirmed data only** (entities, relationships, evidence, timeline
events, locations). Extraction candidates, rejected/pending review items,
unresolved match suggestions and text-similarity guesses never enter the
analysis, and nothing is ever silently promoted to confirmed. Every
result is a named deterministic algorithm's output with a computed-value
explanation — no LLM inference, no fabricated records, and neutral
language throughout ("potential contradiction", "analytical support",
"requires review" — never "proves" or "guilty").

**Backend** — a new service layer `backend/app/services/investigation_intelligence/`
with pure, unit-tested engines:

- **Contradiction engine** — three documented rules over confirmed
  records: R1 timeline (two dated events for one confirmed entity at two
  different confirmed locations closer together than the conservative
  minimum travel time, haversine ÷ 100 km/h), R2 location (identical
  timestamps, different coordinates), R3 relationship (mutual OWNS — the
  only relationship state the domain documents as incompatible). Missing
  coordinates/timestamps are reported as *insufficient pairs*, never as
  contradictions. `EVIDENCE_CONTRADICTION` is intentionally not
  implemented (the evidence model has no structured claims to compare).
- **Competing hypothesis engine** — generates competing explanations per
  contradiction (assumption-based vs record-accuracy, split by the
  computed travel-time margin) and per indirect person-pair (direct
  links vs mediated, plus an explicit "insufficient to distinguish"
  hypothesis when the scores are close). Each hypothesis is persisted
  with a **transparent deterministic score** (documented weights:
  evidence 0.30, relationships 0.20, consistency 0.20, provenance 0.15,
  connectivity 0.15) whose every component and signal is visible in the
  API and UI. Score = analytical support, not probability of guilt.
- **Evidence impact** — per-evidence metrics (linked entities /
  relationships / events, cited findings / hypotheses) and a documented
  0–1 impact score, plus an **in-memory removal simulation**
  (sole-provenance edge rule; degrees, betweenness and components
  recomputed on a copy; before/after diff) — **zero database writes**.
- **Timeline intelligence** — `EVENT_OVERLAP`, `TEMPORAL_PROXIMITY`
  (≤ 30 min), `EVENT_SEQUENCE` (≥ 3 dated events for one entity),
  `TIMELINE_GAP` (> 12 h between consecutive confirmed events, reported
  only as a *potential investigation gap*).
- **Geospatial intelligence** — `CO_LOCATION` (< 0.05 km),
  `LOCATION_PROXIMITY` (≤ 2 km), `LOCATION_SEQUENCE`, all haversine,
  no GIS dependencies; confirmed location entities join to location
  rows by (case, normalized name); missing coordinates → explicit
  `LOCATION_DATA_INSUFFICIENT`.
- **Investigation-gap detection** — evidence gaps (degree ≥ 3, zero
  linked evidence), relationship gaps (indirect 2–3 hop path, no direct
  link), timeline gaps (reused), identity gaps (confirmed person, no
  aliases/identifying metadata, ≥ 2 relationships).

Findings reuse the stage-3 `graph_finding` table (four new types); the
only new table is `investigation_hypothesis`. Versioning extends the
stage-3 snapshot hash to evidence + timeline events + locations;
re-analysis is idempotent per snapshot; stale results are kept as
history. Lifecycle (review/dismiss/audit, never delete) and RBAC reuse
the stage-3 machinery.

**API** — 15 case-scoped routes under
`/api/v1/cases/{case_id}/investigation/…` (analyze, status, findings,
contradictions, gaps, hypotheses GET/POST, evidence-impact,
evidence/{id}/impact, simulate-impact, timeline, geospatial,
review/dismiss for findings and hypotheses). Analysis and review
actions require INVESTIGATOR+; reads work for ANALYST+; structured
errors include the explicit `INSUFFICIENT_CONFIRMED_DATA` (409) for
cases without confirmed graph data.

**Frontend** — a new **Investigation** tab per case (the stage-3 graph
is untouched) with seven panels: analysis status & run (with the
not-analyzed / analyzing / up-to-date / stale / insufficient / error
states), potential contradictions, competing hypotheses (score bars,
components, disclaimer), evidence impact (per-record scores +
simulation with its "simulation only" banner), timeline intelligence,
geospatial intelligence (reusing the existing Leaflet map), and
investigation gaps. **Show in graph** reuses the case graph's
`highlightIds` mechanism via a deep link.

**Smoke data** — `backend/scripts/seed_stage4_demo.py` (idempotent,
INSERT-only) adds two labeled **SYNTHETIC DEMONSTRATION** cases:
`CASE-DEMO-EMPTY-01` (empty → insufficient state) and
`CASE-DEMO-CONTRA-01` (deterministic R1/R2/R3 contradictions, fictional
names). `scripts/stage4-live-smoke.py` re-runs the full live
verification against the running stack.

## What is in Stage 5 (this build)

**Multilingual investigation support** — in-place on Stages 1–4:
language detection + normalization on uploaded documents (real
detection, declared support, honest `unsupported` for unproven
languages), multilingual extraction with per-language rule packs,
structured cross-language claims feeding the stage-4 contradiction
engine, and a copilot provider contract surface. No invented language
support, no fabricated data. `CASE-DEMO-MULTILING-01` demonstrates it.
Details: `docs/MULTILINGUAL.md`.

## What is in Stage 6 (this build)

**The case workflow — one case, start to finish** — in-place on Stages
1–5. The case area becomes a real investigation workspace:

- **Documents tab** — upload, real per-document processing jobs
  (stage/progress/error, polled), statuses
  UPLOADED / PROCESSING / PROCESSED / FAILED, per-document retry and
  review, sha256 idempotent re-upload (no duplicate rows).
- **Review tab** — five categories (new entities, entity matches,
  relationship candidates, evidence claims, contradictions) with full
  provenance (source doc, snippet, page, confidence, method);
  CONFIRM / REJECT are explicit human decisions — extraction never
  auto-confirms, relationships are CANDIDATE by default.
- **Case graph** — built **only from confirmed case data** (never the
  static demo graph): versioned build + payload with per-node evidence
  counts and per-edge provenance; the graph page shows it with
  findings / paths / bridges / clusters / cross-case panels.
- **Intelligence** — `CaseAnalysisService` orchestrates the existing
  stage-3/4 engines (no rewrites) on confirmed data: graph → network →
  anomalies → contradictions → hypotheses → timeline → geospatial →
  gaps → findings persistence. `analysis/status` reports
  not-analyzed / up-to-date / **stale (with reason)** / insufficient;
  stale findings are preserved, never deleted.
- **Case access model** — case ownership: another investigator gets
  404 on read/upload/review/build/analysis/copilot/audit; no
  cross-case leakage.
- **Audit trail** — creation, uploads, processing, confirm/reject,
  graph builds, analysis runs; read-only per case.
- **New case tabs** — Documents, Review, Entities, Relationships,
  Impact, Reports (17 tabs total); deep links `?entity=` /
  `?evidence=` / `?location=` / `?relationship=` land on the object.
- **Demo case** — `CASE-DEMO-END2END-01`: FIR.pdf, Investigation_Report.pdf,
  CDR.csv, Vehicle_Report.pdf, Location_Report.pdf → 17 entities,
  10 relationships, 38 evidence, 3 timeline events, 1 contradiction,
  2 hypotheses — all labeled SYNTHETIC DEMONSTRATION DATA; coordinates
  left NULL where the documents don't state them (never fabricated).

Details: `docs/CASE_WORKFLOW.md`.

---
## Quick start

> **NEXUS does not require Docker.** There is no `docker-compose.yml`, no
> Dockerfile and no container in any startup path. The backend is a plain
> Python (FastAPI) app; it connects to **Supabase PostgreSQL** (or any
> other PostgreSQL) over a standard connection string and computes graph
> intelligence in-process with **NetworkX** — there is no graph database to
> install.

Prerequisites: Python 3.10+, Node 20+, and a **Supabase project**
([supabase.com](https://supabase.com) → New project). A local PostgreSQL
server also works for development if you prefer — NEXUS only needs a
reachable Postgres endpoint in `DATABASE_URL`.

### 1. Configure the environment

```powershell
# Repo root. Create a backend env file from the template.
Copy-Item backend\.env.example backend\.env
```

Open `backend\.env` and set (values from the Supabase Dashboard):

| Variable | Where in the Supabase Dashboard |
| --- | --- |
| `SUPABASE_URL` | Project Settings → API → **Project URL** |
| `SUPABASE_SERVICE_ROLE_KEY` | Project Settings → API → **service_role** key (server-side only — never to the frontend) |
| `DATABASE_URL` | Project Settings → **Database → Connection string**. Use the **session-mode pooler** (port **5432**) so SQLAlchemy's connection pooling works. Append `?sslmode=require`. |
| `JWT_SECRET` | Generate one: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |

`DATABASE_URL` example (psycopg 3):

```
DATABASE_URL=postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
```

> For evidence files on **Supabase Storage**, also set
> `STORAGE_BACKEND=s3`, `S3_BUCKET=<a private bucket>` and the S3
> credentials (the endpoint is derived from `SUPABASE_URL`; the secret can
> be the service-role key). See `docs/DATABASE.md`.

### 2. Run the backend (PowerShell)

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1          # bash/zsh:  source .venv/bin/activate
pip install -r requirements.txt
python run.py                        # → http://127.0.0.1:8000
```

At startup NEXUS **connects to Supabase PostgreSQL, applies the Alembic
migrations (`alembic upgrade head`, in-process, idempotent — safe on both a
fresh and an existing database) and atomically seeds** the synthetic demo
data only when the database is empty. Migrations can also be run manually:

```powershell
cd backend
.venv\Scripts\Activate.ps1
alembic upgrade head                 # apply schema to the DATABASE_URL target
alembic revision --autogenerate -m "name"   # author a new migration (careful review)
```

### 3. Run the frontend (PowerShell, repo root)

```powershell
npm install
npm run dev                          # → http://localhost:5173 (Vite proxies /api to :8000)
```

Sign in with a demo account (all share the password **`nexus2026`**):

| Email | Role |
| --- | --- |
| `demo-investigator@nexus.local` | INVESTIGATOR |
| `arjun.patil@nexus.gov.in` | INVESTIGATOR |
| `sneha.joshi@nexus.gov.in` | ANALYST |
| `priya.deshmukh@nexus.gov.in` | SUPERVISOR |
| `admin@nexus.local` | ADMIN (backend only) |

If the backend is not running, the same credentials open an **offline demo
session** (analysis screens only — the live case area needs the backend and
shows its offline state instead of mock data).

## Tests

```bash
python3 -m pytest backend/tests/ -q          # full backend suite (needs PostgreSQL)
npm run build                                # production build
npm run test:frontend-sanity                 # SSR render check, 45 pages
npm run test:frontend-auth                   # auth flow (adapts to backend state)
python3 scripts/stage4-live-smoke.py         # stage-4 live smoke vs the running stack
python3 scripts/stage5-live-smoke.py         # stage-5 multilingual live smoke
python3 scripts/stage6-live-smoke.py         # stage-6 case-workflow live smoke
```

Stage 2 adds `backend/tests/test_extraction.py` (rule + LLM-contract
extraction and resolution, no DB) and `backend/tests/test_documents_api.py`
(full upload → process → review lifecycle against PostgreSQL). Stage 3
adds `backend/tests/test_graph_intelligence.py` — engine unit tests over
synthetic confirmed records (builder, paths, bridges, clusters,
cross-case, metrics) plus full API tests (analyze/persist/idempotency,
findings review/dismiss + audit, staleness, path error codes, RBAC,
legacy routes). Stage 4 adds `backend/tests/test_investigation_intelligence.py`
— engine unit tests over synthetic confirmed records (contradiction
rules, impact + simulation zero-write proof, timeline, geospatial,
gaps, hypothesis scoring, version hash, builder exclusion of
candidates) plus full API tests (analyze/persist/idempotency/staleness,
all seven GET views, hypothesis create/review/dismiss + 409 codes,
evidence-impact + simulate-impact, timeline/geospatial/gaps,
review/dismiss + audit, RBAC matrix, insufficient-data 409,
stage-3/stage-4 separation, legacy regression). Stage 5 adds
`backend/tests/test_multilingual.py`; stage 6 adds
`backend/tests/test_stage6_e2e.py` (full create → upload → process →
review → confirm → graph → intelligence workflow, the STALE lifecycle,
and case-access isolation — two investigators, no leakage).

## Configuration

`backend/.env.example` documents every variable. The Supabase-related ones:
`SUPABASE_URL`, `SUPABASE_ANON_KEY` (optional, client-side),
`SUPABASE_SERVICE_ROLE_KEY` (server-side only), `DATABASE_URL` (the Supabase
Postgres connection string), plus `JWT_SECRET/ALGORITHM/
ACCESS_TOKEN_EXPIRE_MINUTES`, `LLM_PROVIDER/LLM_API_KEY/LLM_MODEL/
LLM_BASE_URL`, `STORAGE_BACKEND` (`local` | `s3`), `S3_BUCKET/S3_ENDPOINT_URL/
S3_REGION/S3_ACCESS_KEY_ID/S3_SECRET_ACCESS_KEY` (for Supabase Storage),
`STORAGE_ROOT` (local dev), `MAX_UPLOAD_MB`, `EXTRACTION_MAX_CHARS/
EXTRACTION_MAX_ROWS`, `APP_ENV`. Never commit a real `.env`; change
`JWT_SECRET` outside development; never put the service-role key in the
frontend. Uploaded document files live under `backend/storage/` (gitignored)
when `STORAGE_BACKEND=local`, or in the configured private bucket when `s3`.

## Layout

```
backend/
  app/
    api/v1/        platform routers (auth, users, cases, documents, copilot)
    core/          config, database (+ column migration), errors, logging,
                   storage (validated file storage)
    models/        19 platform ORM models (+ legacy pipeline models)
    repositories/  case + document data access
    services/      auth, case, document lifecycle, extraction
                   (rule-based + LLM providers), entity resolution,
                   graph_intelligence/ (stage 3: builder, paths, bridges,
                   clusters, cross-case, metrics, finding service),
                   investigation_intelligence/ (stage 4: builder,
                   contradictions, impact, timeline, geospatial, gaps,
                   hypotheses, analysis service)
    graph/         NetworkX build + analytics + Cypher/JSON export
                   (GraphStore seam — no graph database required)
    security/      JWT + RBAC ladder
    seed.py        atomic idempotent seed (spec dataset + Meridian)
    main.py        app wiring, legacy pipeline mounted under /api
  scripts/seed_stage4_demo.py   idempotent synthetic demo cases (INSERT-only)
  alembic/         versioned migrations (schema authority for PostgreSQL)
  storage/         uploaded documents (gitignored; metadata in PostgreSQL)
  tests/           pytest: API, extraction, documents, models, legacy,
                   graph + investigation intelligence
  run.py           dev server entry point
src/
  services/v1/     live case + document + graph + investigation services (shared axios client)
  components/cases/DocumentsPanel.jsx   upload/status/retry in the Evidence tab
  pages/cases/DocumentReviewPage.jsx    review workspace
  components/cases/GraphFindingsPanel.jsx   findings panel + Analyze trigger
  components/cases/PathExplorer.jsx       confirmed path explorer
  components/cases/GraphIntelPanels.jsx   bridge / cluster / cross-case panels
  pages/cases/InvestigationIntelligencePage.jsx   stage-4 "Investigation" tab
  components/cases/InvestigationPanels.jsx        7 panels + shared state UI
  components/cases/GeoMap.jsx                 Leaflet map (reused for geospatial)
scripts/
  frontend-sanity.mjs                 SSR render check (45 pages)
  frontend-auth-test.mjs              auth flow test
  stage4-live-smoke.py                stage-4 live smoke vs the running stack
data/
  raw/             synthetic corpus (reproducible)
  documents/       stage-2 fixtures + generate_fixtures.py
docs/              ARCHITECTURE · API · DATABASE · pipeline docs
```

## Documentation

- `docs/ARCHITECTURE.md` — system architecture and design rules
- `docs/API.md` — the `/api/v1` contract
- `docs/DATABASE.md` — Supabase/PostgreSQL schema, Alembic migrations, storage, environment
- `docs/PIPELINE_ARCHITECTURE.md` — the analysis pipeline (pre-existing)
- `STAGE3_REPORT.md` — stage-3 completion report (graph intelligence)
- `STAGE4_REPORT.md` — stage-4 completion report (investigation intelligence)
