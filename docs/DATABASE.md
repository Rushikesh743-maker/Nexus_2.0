# NEXUS — Database Configuration

## PostgreSQL (primary: Supabase)

- **Engine:** PostgreSQL (Supabase PostgreSQL is the primary target; any
  compatible PostgreSQL works), driver `psycopg 3` via SQLAlchemy 2.0.
- **URL:** `DATABASE_URL` — the Supabase Postgres connection string, e.g.
  `postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require`.
  Take it from the Supabase Dashboard → Project Settings → Database →
  Connection string and use the **session-mode pooler** (port **5432**) so
  SQLAlchemy's connection pooling works normally (the transaction-mode
  pooler on 6543 multiplexes sessions onto one connection and is not
  compatible with default pooling).
- **Schema authority — Alembic.** Migrations live in `backend/alembic/`
  (`versions/0001_initial_schema.py`, `0002_phase2_intelligence.py`). At
  startup `init_database` runs `alembic upgrade head` in-process —
  idempotent and safe on both a **fresh** and an **existing** database
  (it applies only missing revisions and never drops or alters existing
  data). You can also run them manually: `alembic upgrade head` (from
  `backend/`). A legacy `create_all` fallback only runs if the alembic
  package is missing.
- **Seed:** after the schema is at head, the seed fills the tables when
  empty (atomic; skipped when data already exists).
- **Development without Supabase:** any reachable PostgreSQL works — set
  `DATABASE_URL` to it (e.g. a local `postgres` server). There is no
  Docker requirement; for a throwaway local DB you can simply
  `CREATE ROLE nexus LOGIN PASSWORD '<your-password>'; CREATE DATABASE nexus OWNER nexus;`
  and point `DATABASE_URL` at it.

### Platform tables (19)

| Table | Purpose | Key columns / relationships |
| --- | --- | --- |
| `user` | Investigators & staff | `officer_id`, `email` (unique), `password_hash` (bcrypt), `role` ∈ INVESTIGATOR/ANALYST/SUPERVISOR/ADMIN, `is_active` |
| `case` | Case files | `case_number` (unique, `CASE-YYYY-NNN`), `title`, `status` (OPEN/ACTIVE/ON_HOLD/CLOSED/ARCHIVED), `priority` (LOW/MEDIUM/HIGH/CRITICAL), `is_synthetic`, `created_by → user` |
| `document` | Source documents | `filename`, `file_type`, `language`, `file_size`, `uploaded_at`, `processing_status` (UPLOADED/PROCESSING/PROCESSED/FAILED), stage 2: `mime_type`, `storage_path` (relative, never exposed via API), `sha256` (indexed, duplicate detection), `uploaded_by → user`, `processed_at`, `processing_error`; `case_id → case` |
| `entity` | Persons, vehicles, places, orgs, phones, accounts | `entity_type`, `canonical_name`, `metadata` (JSON), `case_id → case` |
| `relationship` | Typed links between entities | `source_entity_id → entity`, `target_entity_id → entity`, `relationship_type`, `confidence`, `metadata` (JSON), `case_id → case` |
| `evidence` | Evidence items tied to documents | `document_id → document`, `evidence_type`, `description`, `source_reference`, `confidence`, `case_id → case` |
| `timeline_event` | Dated occurrences | `event_type`, `timestamp`, `description`, `entity_id?`, `location_id?`, `evidence_id?`, `case_id → case` |
| `location` | Places | `name`, `latitude?`, `longitude?`, `metadata` (JSON), `case_id → case` |
| `hypothesis` | Working theories | `title`, `description`, `score?`, `status` (PROPOSED/TESTED/SUPPORTED/REFUTED), `case_id → case` |
| `contradiction` | Conflicting records | `title`, `description`, `severity` (low/medium/high), `status`, `case_id → case` |
| `investigation_gap` | Open questions | `title`, `description`, `priority`, `status` (OPEN/RESOLVED), `case_id → case` |
| `simulation` | Counterfactual scenarios | `name`, `description`, `created_by → user`, `case_id → case` |
| `audit_log` | Auth & mutating actions | `action`, `user_id?`, `case_id?`, `metadata` (JSON) |
| `document_extraction` | Normalized extraction record (stage 2) | `document_id → document` (unique), `source_type` (pdf/txt/csv), `raw_text` (capped), `pages` (JSON, PDF per-page heads), `rows` (JSON, CSV head), `stats` (JSON: provider, counts, warnings) |
| `entity_candidate` | Extracted, not yet reviewed (stage 2) | `case_id`, `document_id → document`, `entity_type`, `candidate_name`, `aliases` (JSON), `confidence`, `source_location` (JSON: page/row/column/line/value), `source_snippet`, `extraction_method`, `status` (PENDING/ACCEPTED/REJECTED/DEFERRED), `accepted_entity_id → entity?`, `decision_by → user?`, `decided_at`, `decision_note` |
| `relationship_candidate` | Extracted link proposals (stage 2) | `case_id`, `document_id`, `source_candidate_id → entity_candidate`, `target_candidate_id → entity_candidate`, `relationship_type` (10-type vocabulary), `confidence`, `source_location` (JSON), `source_snippet`, `extraction_method`, `status`, decision columns as above |
| `entity_match_suggestion` | Candidate ↔ existing entity proposals (stage 2) | `case_id`, `candidate_id → entity_candidate`, `existing_entity_id → entity`, `similarity`, `reasons` (JSON), `status` (PENDING/ACCEPTED/REJECTED), decision columns |
| `graph_finding` | Computed findings (stage 3 + stage 4) | `case_id → case`, `finding_type` — stage 3: HIDDEN_CONNECTION/BRIDGE_ENTITY/CROSS_CASE_CONNECTION/NETWORK_CLUSTER/HIGH_CONNECTIVITY; **stage 4: CONTRADICTION/TIMELINE_INSIGHT/GEO_INSIGHT/INVESTIGATION_GAP**, `title`, `summary`, `explanation` (JSON list of computed reason bullets), `details` (JSON: paths/metrics/members, or the rule-specific stage-4 fields), `involved_entity_ids` (JSON), `supporting_relationship_ids` (JSON), `supporting_evidence_ids` (JSON), `related_case_ids` (JSON, cross-case), `analysis_method` (algorithm + parameters), `graph_version` (snapshot hash of the confirmed data run — stage 4 uses its extended hash, see below), `status` (ACTIVE/REVIEWED/DISMISSED), `reviewed_by → user?`, `reviewed_at`, `review_note`, timestamps |
| `investigation_hypothesis` | Competing hypotheses with transparent scores (stage 4 — the only new stage-4 table) | `case_id → case`, `title`, `description`, `hypothesis_type` (GENERATED_CONTRADICTION/GENERATED_STRUCTURE/INVESTIGATOR), `involved_entity_ids` (JSON), `supporting_relationship_ids` (JSON), `supporting_evidence_ids` (JSON), `contradicting_evidence_ids` (JSON), `supporting_finding_ids` (JSON), `contradiction_ids` (JSON → graph_finding rows), `analytical_score` (0..1, deterministic formula), `confidence_band` (LOW/MEDIUM/HIGH), `score_components` (JSON: every visible factor value), `explanation` (JSON: supporting/contradicting signal lines), `analysis_method`, `graph_version?`, `status` (ACTIVE/REVIEWED/DISMISSED), `reviewed_by → user?`, `reviewed_at`, `review_note`, timestamps |

Notes:

- JSON columns are mapped as the ORM attribute `meta` and exposed as
  `metadata` in the API (SQLAlchemy reserves the attribute name
  `metadata`).
- All `case_id` foreign keys cascade-delete with the case; the stage-2
  tables cascade with their document/case, so a case delete removes its
  candidates and suggestions but **never** the stored file (handled at the
  storage layer) — and a rejected candidate is never deleted (audit trail).
- The six new `document` columns are applied to pre-existing databases by
  an idempotent startup migration (`database.py::_ensure_columns`,
  `ALTER TABLE … ADD COLUMN` guarded by an `information_schema` check);
  fresh installs get everything from `Base.metadata.create_all`.
- `audit_log` entries are written by `auth_service` (login success/failure,
  case creation, simulation creation) and by the document lifecycle
  (upload, processing transitions, every review decision); never contains
  passwords, tokens or raw document content. Stage 3 adds
  `GRAPH_ANALYSIS_STARTED/COMPLETED/FAILED` and `FINDING_REVIEWED` /
  `FINDING_DISMISSED`. Stage 4 adds
  `INVESTIGATION_ANALYSIS_STARTED/COMPLETED/FAILED`, `CONTRADICTION_DETECTED`
  (per finding), `INVESTIGATION_GAP_DETECTED` (per finding),
  `TIMELINE_ANALYSIS_COMPLETED`, `GEO_ANALYSIS_COMPLETED`,
  `EVIDENCE_IMPACT_ANALYZED`, `HYPOTHESIS_GENERATED` (per generated
  hypothesis), `HYPOTHESIS_CREATED`, `HYPOTHESIS_REVIEWED`,
  `HYPOTHESIS_DISMISSED` — stage-4 finding reviews reuse the stage-3
  `FINDING_REVIEWED`/`FINDING_DISMISSED` actions.
- `graph_finding` (stage 3) is a whole new table, so it is created by
  `Base.metadata.create_all` on fresh installs and automatically on the
  next startup of an existing database (no column migration needed — no
  pre-existing table is altered). Findings are append-only: re-analyses
  add rows for the new `graph_version`, and review/dismiss update status
  in place; nothing is ever deleted. Stage 4 reuses this table for its
  four finding types (no schema change; the varchar `finding_type` holds
  all nine types). Stage-3 listing endpoints filter to stage-3 types and
  stage-4 endpoints to stage-4 types, so each view sees only its own
  findings; each analysis stores its own version hash (stage 4's hash
  additionally covers evidence, timeline events and locations), so the
  two lineages flag staleness independently.
- `investigation_hypothesis` (stage 4) is the only new stage-4 table.
  Like findings it is append-only and never deleted; reviewer actions
  update status in place and are audit-logged. Generated hypotheses are
  created once per case (deduplicated by title + type across versions);
  investigator-created rows persist across re-analyses.

### The analysis pipeline's own tables

The pre-existing CNA pipeline keeps its own tables (created alongside the
platform tables by the same engine); they are owned by
`backend/app/models/` legacy models and documented in
`docs/PIPELINE_ARCHITECTURE.md` / `docs/DATA_MODEL.md`.

## Graph intelligence (NetworkX, in-process — no graph database)

NEXUS has **no graph database dependency** (Neo4j was removed). The
knowledge graph is built in-process with **NetworkX** from the confirmed
relational rows in PostgreSQL (`entity` + `relationship`, confirmed data
only). PostgreSQL is the source of truth; the graph is a computed view, and
expensive analysis results are persisted in the relational tables
(`graph_finding`, `investigation_hypothesis`, …) with a `graph_version`
snapshot hash for freshness.

- **Export seam.** `backend/app/graph/store.py` defines `GraphStore` with
  two adapters: `CypherExportStore` (writes a `.cypher` script loadable into
  any Cypher-compatible tool such as Neo4j Desktop/Aura — optional, not
  required) and `JsonExportStore`. `GET /api/v1/export/cypher` writes the
  Cypher to a file; nothing connects to a live graph server.
- **Vocabulary (kept stable for exports).** Node labels: `Person, Phone,
  Vehicle, Location, Account, Organization, Case, Document, Event`.
  Relationship types: `CALLED, OWNS, USED, LOCATED_AT, ASSOCIATED_WITH,
  INVOLVED_IN, TRANSFERRED_TO, MENTIONED_IN, CONNECTED_TO, OCCURRED_AT`.
  These match the seeded PostgreSQL vocabulary, so a Cypher export maps
  rows 1:1.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `SUPABASE_URL` | *(empty)* | Supabase project URL (`https://<ref>.supabase.co`). Used to derive the Supabase Storage S3 endpoint when `S3_ENDPOINT_URL` is empty. |
| `SUPABASE_ANON_KEY` | *(empty)* | Low-privilege key, safe for client-side use. The backend does **not** use it. (Modern equivalent: the `publishable` key.) |
| `SUPABASE_SERVICE_ROLE_KEY` | *(empty)* | Elevated, **server-side only** key (bypasses RLS). Authorises private Supabase Storage access. Never to the frontend. (Modern equivalent: the `secret` key.) |
| `DATABASE_URL` | local dev fallback | Supabase Postgres connection string (psycopg 3). See the PostgreSQL section for the session-mode pooler details. |
| `JWT_SECRET` | *(empty)* | Token signing key — **set in every environment, change outside development** |
| `JWT_ALGORITHM` | `HS256` | Token algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | Token lifetime |
| `LLM_PROVIDER` | *(empty)* | Extraction provider: empty = deterministic rules; set an OpenAI-compatible name to use the LLM provider |
| `LLM_API_KEY` | *(empty)* | LLM key — environment only, never in the frontend |
| `LLM_MODEL` | *(empty)* | Model name (provider default when empty) |
| `LLM_BASE_URL` | *(empty)* | OpenAI-compatible API root (default `https://api.openai.com/v1`) |
| `STORAGE_BACKEND` | `local` | `local` (development filesystem) or `s3` (Supabase Storage / any S3-compatible store) |
| `STORAGE_ROOT` | `backend/storage` | Local-backend root (gitignored). Only used when `STORAGE_BACKEND=local`. |
| `S3_BUCKET` | *(empty)* | Private bucket for evidence files (Supabase Storage). Required when `STORAGE_BACKEND=s3`. |
| `S3_ENDPOINT_URL` | *(empty)* | Explicit S3 endpoint. Empty ⇒ derived as `<SUPABASE_URL>/storage/v1/s3` for Supabase Storage. |
| `S3_REGION` | *(empty)* | S3 region (empty ⇒ provider default) |
| `S3_ACCESS_KEY_ID` | *(empty)* | Supabase Storage S3 access key id |
| `S3_SECRET_ACCESS_KEY` | *(empty)* | S3 secret; empty ⇒ falls back to `SUPABASE_SERVICE_ROLE_KEY` |
| `MAX_UPLOAD_MB` | `10` | Upload size limit |
| `EXTRACTION_MAX_CHARS` | `200000` | Cap for stored extracted text |
| `EXTRACTION_MAX_ROWS` | `2000` | Cap for processed CSV rows |
| `APP_ENV` | `development` | Environment label in logs/health |

## Seed

`backend/app/seed.py::seed_if_empty(db)`:

1. Skips when `CASE-2026-001` exists (interrupted seeds self-heal on next
   start; per-row idempotency guards the rest).
2. Stages users (5 demo accounts), the spec dataset (3 cases), and the
   Operation Meridian corpus (1 case) **without committing**, then makes one
   atomic `commit()`; any failure rolls everything back.
3. Log lines record what was staged; a defensive entity check raises with
   the exact missing names if a flush loses rows.
