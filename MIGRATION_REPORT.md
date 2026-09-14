# NEXUS — Supabase Migration & De-Docker/De-Neo4j Audit

**Mode: config-only.** No live Supabase credentials were available, so the
project is made **Supabase-ready by configuration** and **verified against a
local PostgreSQL 17** instance (the same psycopg 3 + SQLAlchemy + Alembic
stack Supabase PostgreSQL uses). Nothing here claims live-Supabase testing;
the exact hand-off commands are in the "Go live on Supabase" section.

**Outcome:** Docker is gone from every startup path, the Neo4j runtime
dependency is removed, Supabase PostgreSQL is the documented primary
database (via `DATABASE_URL`, credentials never hardcoded), Supabase
Storage is wired for evidence files, and the **full backend test suite is
green (427 passed, 0 failed)** plus live startup / auth / graph / export /
frontend checks.

---

## 1. Changed

| Area | What changed |
| --- | --- |
| `backend/app/core/config.py` | Removed `neo4j_*` settings + `neo4j_configured`. Added `supabase_url`, `supabase_anon_key`, `supabase_service_role_key`, `supabase_configured`, and two Supabase-aware resolvers: `effective_s3_endpoint_url` (derives `<SUPABASE_URL>/storage/v1/s3`) and `effective_s3_secret_access_key` (falls back to the service-role key). Reframed the `database_url` docstring as Supabase-first. |
| `backend/app/core/storage.py` | `get_storage()` now resolves the S3 endpoint + secret through the Supabase-aware settings, so Supabase Storage works from `SUPABASE_URL` + `S3_BUCKET` + credentials. |
| `backend/app/main.py` | Removed the startup Neo4j health check and the shutdown Neo4j close. Startup is now: connect → Alembic → seed → worker. |
| `backend/app/api/v1/health.py` | Removed `_neo4j_status` and the `neo4j` field from the health payload. `/readyz` docstring updated. |
| `backend/app/schemas/v1.py` | Removed `neo4j` from `HealthOut`. |
| `backend/app/graph/build.py`, `core/logging.py`, `services/case_service.py`, `app/static/index.html` | Docstrings / legacy console updated to drop Neo4j references (no behaviour change). |
| `backend/app/services/entity_profile.py` | **Bug fix (pre-existing, found by the suite):** `_require_entity` conflated the `Entity` and `EntityCandidate` id spaces, so a confirmed entity from another case could return `400 ENTITY_NOT_CONFIRMED` instead of `404`. Now resolves the confirmed entity first (case-scoped → `404` if it's another case's), then falls back to the candidate check. |
| `backend/requirements.txt` | Removed `neo4j>=5.15`. Added `httpx>=0.27` (Starlette `TestClient` dependency — required for the API test suite to be reproducible). |
| `backend/.env` | Stripped `NEO4J_*`. Kept the sandbox-local `DATABASE_URL` (the test DB) + JWT secret. |
| `backend/.env.example` | **Rewritten Supabase-first.** Added `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`; reframed `DATABASE_URL` as the Supabase Postgres connection string (session-mode pooler, `?sslmode=require`); removed the Neo4j block; documented Supabase Storage under the S3 section. Placeholders only. |
| `scripts/export_graph.py` | Dropped the `--neo4j` path; now exports Cypher/JSON only. |
| Frontend | `src/components/analysis/CapabilityStrip.jsx` (the "Graph storage" chip now reflects the active in-process engine + exports, not a Neo4j flag) and `src/pages/analysis/SystemPage.jsx` (removed the two dead "neo4j driver / Neo4j configured" badges and reworded the Graph card). **No redesign** — three small, targeted edits so the UI stops referencing a removed dependency. |
| Docs | `README.md`, `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/API.md`, `docs/PIPELINE_ARCHITECTURE.md`, `docs/DEMO_SCRIPT.md` — all rewritten to remove Docker/Neo4j as runtime dependencies and document Supabase + NetworkX. |

## 2. Removed

- `docker-compose.yml` (Postgres 17 + Neo4j 5, healthchecks, 3 volumes) — **deleted**. There is no `Dockerfile` and no other compose file; no startup path references Docker.
- `backend/app/graph/neo4j.py` (Neo4j driver module) — **deleted**.
- `Neo4jStore` class in `backend/app/graph/store.py` — **deleted** (the `GraphStore` contract + `CypherExportStore` + `JsonExportStore` remain).
- `backend/tests/test_neo4j_layer.py` — **deleted**.
- All `NEO4J_*` environment variables from `backend/.env`, `backend/.env.example`, and every doc.
- The `neo4j` field from the `/api/v1/health` payload and from `describe_backends()`.

## 3. Database (Supabase PostgreSQL)

- **Primary DB is Supabase PostgreSQL**, reached through `DATABASE_URL`
  (psycopg 3). **No credentials are hardcoded** — the one non-empty default
  in `config.py` is a clearly-labelled local-development fallback (an empty
  default would break the engine-at-import in `database.py`); every real
  deployment sets `DATABASE_URL`.
- **Alembic is the schema authority.** Migrations live in `backend/alembic/`
  (`0001_initial_schema`, `0002_phase2_intelligence`). `env.py` reads
  `DATABASE_URL` from settings, so it points at Supabase automatically.
  `init_database` runs `alembic upgrade head` in-process at startup
  (idempotent — safe on a **fresh** and an **existing** database).
- **Verified on a fresh database:** created an empty `nexus_fresh`, ran
  `alembic upgrade head` → both revisions applied, **25 tables** created
  (all 19 platform tables + CNA tables present), `alembic current` =
  `0002 (head)`, and a re-run was a no-op. This is the exact path a brand-new
  Supabase project takes.
- **Existing database:** the sandbox `nexus` DB is at head; startup reported
  `schema: at head` (no-op) and all tables/relationships (users, roles,
  cases, documents, entities, relationships, evidence, timeline, locations,
  hypotheses, contradictions, gaps, simulations, audit, graph_finding,
  investigation_hypothesis, document_extraction, entity_candidate,
  relationship_candidate, entity_match_suggestion) are preserved.

## 4. Storage (Supabase Storage)

- `STORAGE_BACKEND=local` (development filesystem) remains the default and is
  what the test suite uses.
- `STORAGE_BACKEND=s3` targets **Supabase Storage** (its S3-compatible API):
  the endpoint is derived as `<SUPABASE_URL>/storage/v1/s3` when
  `S3_ENDPOINT_URL` is empty, `S3_SECRET_ACCESS_KEY` falls back to
  `SUPABASE_SERVICE_ROLE_KEY`, and `S3_BUCKET` should be a **private** bucket.
  The service-role key is server-side only (never sent to the frontend).
- The evidence workflow is unchanged: `validate_upload` (extension/MIME
  allowlist, streaming size, SHA-256, magic bytes) runs before storage, and
  the app only ever sees object keys.

## 5. Graph (NetworkX, in-process — no graph database)

- **Neo4j runtime dependency removed** (driver, config, connection code,
  health checks, startup/shutdown hooks, env vars, compose service,
  dependency, tests).
- **Graph intelligence is fully preserved** and runs in-process with
  **NetworkX** over the confirmed relational rows. Postgres is the source of
  truth; the graph is a computed view, and expensive results persist in
  `graph_finding` / `investigation_hypothesis` with a `graph_version`
  snapshot hash for freshness.
- **Export seam kept:** `CypherExportStore` + `JsonExportStore` in
  `graph/store.py`; `GET /api/export/cypher` writes a `.cypher` file (no
  server needed). **Verified live:** HTTP 200, 53 nodes / 141 edges, valid
  Cypher.
- **Verified live:** `POST /cases/8/graph/analyze` returned a
  `graph_version` + findings; `GET /cases/8/graph` returned 17 confirmed
  nodes / 9 edges.

## 6. Authentication

- **Unchanged:** JWT (HS256) + bcrypt, four roles
  (INVESTIGATOR / ANALYST / SUPERVISOR / ADMIN) enforced server-side,
  protected routes, login rate limiting. No auth was weakened.
- The Supabase service-role/secret key is **server-side only** and is never
  exposed to the frontend or logged.
- **Verified live:** login returns a signed JWT, `/auth/me` reflects the
  role, an unauthenticated request → 401, and a wrong password → 401 with no
  mock fallback. The frontend auth flow (live JWT path) passed end-to-end.

## 7. Tests

- **Full backend suite: `427 passed, 0 failed`** (≈3.5 min) against local
  PostgreSQL 17. This includes API/auth/RBAC, document lifecycle + OCR,
  extraction, graph + investigation intelligence, multilingual, stage-6 E2E,
  storage backends (moto in-memory S3), and the production-foundation suite.
- Environment restored to match the prior green baseline: recreated the
  Python venv, installed `requirements.txt` (no `neo4j`), installed
  `httpx` (TestClient), installed `postgresql` + `tesseract-ocr` (base +
  Hindi) system packages, and created the `nexus` role/DB.
- Two tests were **updated to assert the removal** (not weakened):
  `/health` no longer contains a `neo4j` key, and `.env.example` is
  Supabase-first with no `NEO4J` string.
- **Frontend:** `npm run build` succeeds (10s); `test:frontend-sanity`
  renders **all 45 pages**; `test:frontend-auth` passes on both the offline
  path and the **live JWT path** (login → normalised session → 8 live cases →
  case detail; wrong password rejected).

## 8. Startup (no Docker, no local-Postgres requirement)

Verified by booting `uvicorn` (fresh DB) and `run.py` (existing DB):

```
Starting NEXUS 0.2.0 (env=development)
Platform database connected: PostgreSQL 17.11 … (schema: at head)
Platform database seeded with synthetic data.   # fresh DB only
Document worker active (in-process).
Uvicorn running on http://127.0.0.1:8000
```

No `docker compose`, no `docker` command, and no Neo4j step anywhere.
`start.sh` (unchanged) is already Docker-free (venv + python + npm).

## 9. Remaining issues / honest caveats

1. **Not live-Supabase-tested.** Everything was verified against a local
   PostgreSQL 17 using the identical driver/ORM/migration stack. The Supabase
   specifics that still need a real project: the exact `DATABASE_URL`
   (session-mode pooler port 5432 + `?sslmode=require`) and the Supabase
   Storage S3 credentials/bucket. See the hand-off below.
2. **Supabase Storage S3 access key id.** Supabase's managed Storage exposes
   an S3 protocol endpoint; the endpoint is derived automatically, the
   secret defaults to the service-role key, but `S3_ACCESS_KEY_ID` must be
   filled from your project (documented in `.env.example` — not guessed).
3. **`database_url` keeps a non-empty local-dev default** so the engine can
   be created at import and the test suite runs without a configured DB.
   This is a dev fallback, not a requirement — any deployment overrides it.
4. **Supabase key deprecation.** Supabase is deprecating the legacy
   `anon`/`service_role` JWT keys in favour of `publishable`/`secret` keys
   (noted in `.env.example`). The variable names in your brief
   (`SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`) are used, with the
   modern equivalents documented alongside.
5. **Historical reports left as-is.** `FOUNDATION_REPORT.md`,
   `STAGE*_REPORT.md`, `PHASE*_REPORT.md`, `AUDIT_REPORT.md` describe past
   states (when Neo4j/Docker existed) and were intentionally not rewritten —
   they are records, not active config. All **active** code, config, env
   files, scripts and docs are clean.
6. **Frontend build chunk-size warning** (some chunks > 500 kB) is
   pre-existing and unrelated to this migration.

---

## Go live on Supabase (hand-off)

PowerShell, repo root. Requires a Supabase project
([supabase.com → New project](https://supabase.com)).

```powershell
# 1. Create and fill the env file
Copy-Item backend\.env.example backend\.env
#    - SUPABASE_URL                 = Project Settings → API → Project URL
#    - SUPABASE_SERVICE_ROLE_KEY    = Project Settings → API → service_role key
#    - DATABASE_URL                 = Project Settings → Database → Connection string,
#                                     session-mode pooler (port 5432), append ?sslmode=require
#    - JWT_SECRET                   = python -c "import secrets; print(secrets.token_urlsafe(48))"
#    (optional, for evidence files)  STORAGE_BACKEND=s3, S3_BUCKET=<private bucket>, S3_ACCESS_KEY_ID=…

# 2. Backend
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head        # apply the schema to Supabase (idempotent)
python run.py               # → http://127.0.0.1:8000 (seeds only if empty)

# 3. Frontend (repo root)
npm install
npm run dev                 # → http://localhost:5173
```

For a **fresh** project the same `alembic upgrade head` creates every table;
for an **existing** project it applies only the missing revisions and never
drops or alters existing data.
