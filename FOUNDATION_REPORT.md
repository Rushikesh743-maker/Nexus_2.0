# NEXUS — Stage 1 Foundation: Implementation Report

**Date:** 2026-09-07 · **Scope:** Stage-1 foundation, migrated in-place into `/home/user/NEXUS`.
**Result:** Backend and frontend running, all tests green, pre-existing pipeline preserved and verified.

---

## 1. What was implemented

### Backend — platform foundation (`/api/v1`)
- **FastAPI + Pydantic + SQLAlchemy 2.0**, layered architecture:
  `api/v1 (routers) → services → repositories → models`.
- **Authentication:** JWT (HS256, PyJWT) + bcrypt password hashing; four roles
  (INVESTIGATOR / ANALYST / SUPERVISOR / ADMIN) enforced server-side
  (`security/rbac.py`); structured `401/403/404/422` errors with a single
  `{ "error": { "code", "message" } }` shape.
- **13 platform tables** (user, case, document, entity, relationship,
  evidence, timeline_event, location, hypothesis, contradiction,
  investigation_gap, simulation, audit_log) with cascading relationships,
  auto-created at startup.
- **Case API:** list, create (auto `CASE-YYYY-NNN` numbering), detail with
  computed counts, key entities (aliases + link counts), cross-case entity
  links, latest events; 11 sub-resource endpoints (documents, entities,
  relationships, evidence, timeline, locations, hypotheses, contradictions,
  gaps, simulations, + simulation create).
- **Audit log:** login success/failure, case creation, simulation creation —
  69+ rows recorded during verification; no secrets in any log line.
- **Logging:** startup, DB connection, Neo4j status, auth events, per-request
  API log — none of them print passwords, tokens or API keys.
- **Atomic seed** (`app/seed.py`): single commit, full rollback on any
  failure, idempotent re-runs, sentinel-based skip (`CASE-2026-001`),
  defensive entity-consistency assertion. Seeds:
  - Spec dataset — 5 persons, 2 vehicles, 4 locations, cases CASE-2026-001…003;
  - **Operation Meridian corpus** (imported from the pipeline's synthetic
    generator) as CASE-2026-021 — 53 entities, 138 relationships, 40 source
    documents, 5 contradictions, 14 findings→hypotheses.
- **Copilot:** `GET /api/v1/copilot` foundation-stage status endpoint with
  provider/model config surface (`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`).
- **Pre-existing pipeline preserved:** the CNA analysis API (`/api/stats`,
  `/api/graph`, `/api/findings`, report PDF, legacy `/legacy` frontend
  server) still runs in the same app — verified live (53 nodes / 138 edges /
  23 findings).

### Backend — Neo4j layer (stage-1 scope only)
- Connection config (`NEO4J_URI/USERNAME/PASSWORD/DATABASE`), `GraphStore`
  service abstraction (`app/graph/neo4j.py`) with node/relationship
  vocabulary fixed (9 node labels, 10 relationship types), health check in
  `/api/v1/health`, honest graceful degradation (no server → `connected:
  false` + reason, warning at startup, no crashes), allowlist validation,
  write path that converts driver exceptions into `ConnectionError`.
- **No graph analytics at this stage** (explicitly deferred).

### Frontend (existing React/Vite stack, extended in place)
- **`src/services/v1/`** — centralized axios client (baseURL `/api/v1`, JWT
  bearer injection, normalized errors with offline vs 401 vs validation
  semantics), `authService`, `caseService`, `copilotService`, barrel.
- **Case area (live-backed, zero mock data):**
  - `/cases` — registry (live counts, new-case form, offline/empty/error states);
  - `/cases/:caseId` — case file shell + 9 tool tabs: Overview (counts, key
    entities, cross-case connections, recent activity, working state), Graph
    (React Flow + entity/relationship inspection), Evidence, Timeline, Map
    (Leaflet/OSM, offline-tile notice), Hypotheses, Contradictions, Gaps,
    Simulation (record scenarios; scoring engine labelled later stage);
  - `/copilot` — honest foundation-stage status page (no fake chat box).
- **Auth:** JWT-first login; when the backend is unreachable (network error
  or dev-proxy 500) an explicitly-labelled offline demo session opens with
  the *same* demo credentials; wrong passwords are never silently accepted.
- **Navigation:** sidebar gains Cases + Copilot; topbar breadcrumbs support
  both case registries; page contexts updated.
- **Vite proxy:** `/api` → backend :8000 (alongside the preserved
  `/cna-api` rewrite); SPA deep-route fallback verified.
- All pages render loading / empty / error / success states; no blank
  screens, no placeholder buttons.

### Docs & infra
- `docs/ARCHITECTURE.md` (system-level; pipeline doc preserved as
  `docs/PIPELINE_ARCHITECTURE.md`), `docs/API.md` (full v1 contract),
  `docs/DATABASE.md` (schema, Neo4j vocabulary, environment).
- `docker-compose.yml` — PostgreSQL 17 + Neo4j 5 with healthchecks and
  volumes, matching the dev `.env` defaults.
- `README.md` rewritten for the full system (quick start, credentials,
  tests, layout); `backend/.env.example` documents every variable.

## 2. Final project structure

```
/home/user/NEXUS
├── backend/
│   ├── app/
│   │   ├── api/v1/            auth, users, cases (+11 sub-resources), copilot
│   │   ├── core/              config, database, errors, logging
│   │   ├── models/models.py   13 platform ORM models (+ legacy pipeline models)
│   │   ├── repositories/      case_repository (queries, aggregates, cross-case)
│   │   ├── services/          case_service, auth_service (business rules)
│   │   ├── schemas/v1.py      pydantic v1 contract
│   │   ├── security/          jwt, rbac
│   │   ├── graph/neo4j.py     GraphStore (graceful degradation)
│   │   ├── seed.py            atomic idempotent seed (spec + Meridian)
│   │   ├── main.py            app wiring + legacy pipeline routes
│   │   └── run.py / run.py    dev entry point
│   ├── tests/                 test_v1_api, test_models, test_neo4j_layer + legacy suite
│   ├── requirements.txt       + .env / .env.example
├── src/                       React frontend
│   ├── services/v1/           client, authService, caseService, copilotService
│   ├── pages/cases/           CasesPage, CaseLayout, 8 case tabs, CopilotPage
│   ├── components/cases/      StatusBadge, EntityChip
│   ├── lib/caseTypes.js       v1 → visual-vocabulary mappings
│   ├── pages/, components/    (pre-existing: analysis, investigations, UI kit)
│   └── mock/                  offline demo directory (mirrors demo accounts)
├── scripts/
│   ├── frontend-sanity.mjs    SSR render check (14 pages)
│   └── frontend-auth-flow.mjs adaptive auth-flow test (up/down backend)
├── data/                      synthetic corpus + generator (reproducible)
├── docs/                      ARCHITECTURE · API · DATABASE · PIPELINE_* · DATA_MODEL · …
├── docker-compose.yml         postgres 17 + neo4j 5
├── vite.config.js             /api and /cna-api proxies
├── package.json / backend/requirements.txt
├── README.md · FOUNDATION_REPORT.md · AUDIT_REPORT.md
```

## 3. Technologies installed / in use

**Backend (Python 3.13):** FastAPI 0.141.1 · SQLAlchemy 2.0.52 · Pydantic
2.13.4 · psycopg 3.3.5 (PostgreSQL driver) · PyJWT 2.13.0 · bcrypt 5.0.0 ·
neo4j driver 6.3.0 · uvicorn 0.52.4 · networkx 3.6.1 (pipeline) ·
email-validator 2.3.0 · pytest 8.x.

**Frontend (Node 20):** React 18.3 · Vite 5.4 · React Router 6.26 ·
Tailwind 3.4 · axios 1.7 · React Flow 11.11 · d3-force · Leaflet 1.9 +
React-Leaflet 4.2 · Recharts 2.12 · Lucide · pdfjs (reports).

**Infrastructure:** PostgreSQL 17.11 (sandbox-local) · Docker Compose file
for PostgreSQL 17 + Neo4j 5 · Vite dev server with API proxying.

## 4. Database configuration

- **Engine:** PostgreSQL 17.11, driver `psycopg 3` via SQLAlchemy 2.0.
- **Dev database:** `nexus` @ `127.0.0.1:5432` — user `nexus`, password
  `nexus_dev_2026` (development default in `backend/.env.example`; change
  in any real deployment; `.env` is git-ignored, never committed).
- **URL:** `postgresql+psycopg://nexus:nexus_dev_2026@127.0.0.1:5432/nexus`
- **Tables:** created at startup; atomically seeded when empty.
- **Seeded state (verified):** 5 users · 4 cases · 79 entities (32 person,
  11 vehicle, 11 location, 9 organization, 11 case-reference, 5 account/phone
  within) · 198 typed relationships · 42 documents · evidence/timeline/
  locations per case · 1 contradiction per spec case + 5 Meridian ·
  hypotheses from findings · 69+ audit rows.
- **Composable:** `docker compose up -d postgres` provides the same
  database with the same credentials.

## 5. Neo4j configuration

- **Config:** `NEO4J_URI=bolt://127.0.0.1:7687`, `NEO4J_USERNAME=neo4j`,
  `NEO4J_PASSWORD=neo4j_dev_2026`, `NEO4J_DATABASE=neo4j` (env-driven).
- **Status in this sandbox:** no graph server present → the layer reports
  `neo4j.connected=false` with the connection reason in
  `GET /api/v1/health`, logs a WARNING at startup, and every call degrades
  to `ConnectionError`. Nothing in the platform path blocks or crashes.
- **Real instance:** `docker compose up -d neo4j` (Neo4j 5, bolt :7687,
  browser :7474, healthcheck, persistent volumes). The Neo4j-layer test
  suite (9 tests) includes a live round-trip test that activates
  automatically when a server is reachable (currently skipped).
- **Vocabulary (fixed, stage 1):** nodes `Person, Phone, Vehicle, Location,
  Account, Organization, Case, Document, Event`; relationships `CALLED, OWNS,
  USED, LOCATED_AT, ASSOCIATED_WITH, INVOLVED_IN, TRANSFERRED_TO,
  MENTIONED_IN, CONNECTED_TO, OCCURRED_AT`. Analytics deferred by design.

## 6. Demo credentials

Password for all five seeded backend accounts: **`nexus2026`**

| Email | Role |
| --- | --- |
| `demo-investigator@nexus.local` | INVESTIGATOR (primary) |
| `arjun.patil@nexus.gov.in` | INVESTIGATOR |
| `sneha.joshi@nexus.gov.in` | ANALYST |
| `priya.deshmukh@nexus.gov.in` | SUPERVISOR (user directory) |
| `admin@nexus.local` | ADMIN |

Same credentials also work for the **offline demo session** (backend down) —
the mock directory mirrors the seeded accounts. All data shown is labelled
*synthetic demonstration data*; no real people anywhere.

## 7. Commands to start

```bash
# Backend (from /home/user/NEXUS/backend)
pip install -r requirements.txt          # once
cp .env.example .env                     # once — dev defaults work as-is
python3 run.py                           # → http://127.0.0.1:8000
#   startup log: DB connected · Neo4j status · seed (only when empty)

# Frontend (from /home/user/NEXUS)
npm install                              # once
npm run dev                              # → http://localhost:5173
#   /api and /cna-api are proxied to the backend

# Optional: real Neo4j
docker compose up -d neo4j
# Optional: Postgres via compose instead of the sandbox instance
docker compose up -d postgres
```

Sign in at `http://localhost:5173/login` with a demo account above.

## 8. Tests executed

| Suite | Result |
| --- | --- |
| `python3 -m pytest backend/tests/ -q` | **90 passed, 1 skipped** (skip = live Neo4j round-trip; no graph server in sandbox) |
| — `test_v1_api.py` (new) | 23: health shape, login (JWT issued, wrong-pw 401, bad email 422, unauth 401), RBAC, cases list/detail/sub-resources, cross-case links, simulation create, structured 404 |
| — `test_models.py` (new) | 4: model creation, FK cascades, JSON metadata column, relationships |
| — `test_neo4j_layer.py` (new) | 8 + 1 skipped: vocabulary constants, unconfigured honesty, graceful degradation, allowlist rejections, write → ConnectionError, live round-trip (skipif) |
| — legacy pipeline suite (pre-existing) | 56: preserved, all passing |
| `npm run build` | **✓ built in ~10 s** (only pre-existing chunk-size warnings) |
| `npm run test:frontend-sanity` | **14/14 pages SSR-render** (all new case pages, login, sidebar, topbar) |
| `npm run test:frontend-auth` | **8/8 checks** (adaptive): JWT login → normalized session → `/auth/me` verify → live case data via JWT header → wrong-pw 401 (no mock fallback); offline variant separately verified: proxy-500 classified offline → demo fallback session → restore → rejection |
| Live API smoke (curl) | v1: health, login, me, cases (4), all 11 sub-resources, copilot, 401 unauth · legacy: `/legacy` 200, `/api/stats` 200, `/api/graph` 53 nodes/138 edges, `/api/findings` 23 |
| Live proxy smoke | `/api/v1/*` through Vite :5173 → backend :8000 ✓ · SPA + deep routes 200 ✓ |

Bugs found and fixed during verification (all fixed, re-tested): seed
atomicity + FK-retry trap (resurrected `user` reserved-word DROP), seed data
paths (`data/raw`, CDR `start_time`, feed documents without timestamps),
repository `options()` misuse + lazy `ScalarResult` return, missing
imports in users/cross-case, `access_token` → `token` session normalization
(would have broken every JWT request from the UI), offline classification of
dev-proxy 500, v1/legacy service-name collision in the barrel, contract
drift on 7 API fields.

## 9. Remaining issues / deferred work

**Remaining issues (none blocking):**
- **No headless browser in the sandbox** — UI verification is via SSR render
  checks, the adaptive auth-flow test, and live API/proxy smoke; a click
 -through in a real browser is the one verification step not executed here.
- **Neo4j not live in the sandbox** — layer is code-complete and
  degradation-tested; the 1 skipped round-trip test plus
  `docker compose up -d neo4j` closes the loop.
- **`JWT_SECRET` is a dev placeholder** in the shipped `.env.example`
  (`dev-only-change-me`) — must be changed for any real deployment.
- **Vite chunk-size warning** on the main bundle (pre-existing; cosmetic).
- The analysis section still has **mock-driven screens by design** (its
  original architecture); only the case area is live-backed.

**Deliberately NOT implemented (per stage plan):** LLM conversation,
advanced graph analytics, entity resolution, OCR, evidence-impact scoring,
multilingual AI, CCTV/facial recognition, real police-system integrations.
The UI labels these as later stages instead of faking them, and the
pre-existing pipeline code touching these topics is preserved unchanged.

**Suggested next stage** (not started, per stop directive): document upload
+ processing pipeline into `Document`, and the LLM copilot conversation on
the prepared `/api/v1/copilot` contract.

---
*Both servers were left running at hand-off: NEXUS API on :8000, Vite on
:5173 (live preview available).*
