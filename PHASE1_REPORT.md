# NEXUS — Phase 1 Report: Production Backend Foundation

Date: 2026-09-10. Scope: production-readiness work on the Stage 6/7 platform,
in-place, no rebuild. All data remains synthetic demonstration data.

## What changed (by area)

### 1. Document processing — real background job architecture
- New table `document_processing_job` (one row per document, unique
  `document_id`) + `app/services/processing_worker.py`:
  - `enqueue_document_job()` is **idempotent**: a document with a live
    (QUEUED/PROCESSING) job is never re-queued; a completed document is never
    reprocessed; a FAILED job is re-queued in-place (`attempts` counts claims).
  - `DocumentProcessingWorker` claims rows with `SELECT … FOR UPDATE SKIP
    LOCKED` (safe with multiple workers), runs the *existing* pipeline
    (`document_service.process_document`) — no algorithm was replaced.
  - Runs **in-process with the API in development** (`WORKER_ENABLED=true`),
    or as a standalone process in production
    (`python -m app.workers.document_worker`, `WORKER_ENABLED=false`).
  - If no worker is running, the upload falls back to a FastAPI background
    task executing the *same* job function — the job row is always finalized
    from the real document state.
- Upload (`POST /cases/{id}/documents`) and retry
  (`POST /documents/{id}/process`) now create/reuse a job and return
  immediately. Status `QUEUED → PROCESSING → COMPLETED/FAILED` is real DB
  state, exposed on every document (`processing_job`) — no fake progress.
- `case_processing.py` early-exit race fixed: the case job now exits only
  when no document is still UPLOADED/PROCESSING (previously an enqueued-but-
  unpicked document let the job complete early).
- Meaningful, user-safe error messages; a stuck job fails honestly after
  `WORKER_STUCK_TIMEOUT_MINUTES`.

### 2. OCR in the primary upload workflow
- `app/pipeline/ocr.py`: shared OCR core (tesseract, language detection
  eng/hin, 2× upscale for small scans, mean confidence) + `ocr_bytes()` for
  in-memory images.
- `document_processor.py` per-document, per-page handling:
  - **Text PDFs** → plain text extraction (OCR never invoked).
  - **Scanned PDF pages** (page text layer < 12 chars) → rendered at
    `OCR_DPI` (PyMuPDF) and OCR'd; OCR text wins when it is longer.
  - **Image uploads** (PNG/JPG/JPEG/TIFF) → OCR'd outright.
  - **Never silent**: OCR disabled → clear FAILED "OCR is disabled…";
    tesseract/PyMuPDF missing → clear FAILED with the missing dependency;
    blank/low-quality → clear FAILED "no readable text".
- Provenance preserved: `document_extraction.pages[]` carries per-page
  `ocr: {engine, languages, confidence}`; `document_extraction.stats`
  carries `ocr_pages`; `processing_method` gets a `+ocr` suffix only when
  OCR actually ran.
- Verified live: scanned PNG and image-only PDF (0-char text layer) both
  OCR'd and yielded real candidates (names, phones, locations).

### 3. Storage abstraction
- `app/core/storage.py` rewritten around an `ObjectStorage` interface
  (`save/open/delete/exists/size`) with two real backends:
  - `LocalObjectStorage` (development; root from `STORAGE_ROOT`)
  - `S3ObjectStorage` (production; boto3, any S3-compatible endpoint,
    optional key prefix) — verified against an in-memory S3 (moto).
- The application only ever sees **object keys** — no hard-coded paths;
  readers in `document_processor` are stream-based (work for both backends).
- Upload validation unchanged + extended: extension allow-list now includes
  the OCR image types, size cap (`MAX_UPLOAD_MB`), sha256, and **magic-byte
  checks** for PDF *and* PNG/JPEG/TIFF (a `.png` that isn't PNG is rejected).

### 4. Database — Alembic migrations
- `backend/alembic/` + `alembic.ini` + initial revision `0001` (idempotent
  bootstrap: creates missing tables, ensures legacy columns, never drops).
- `init_database()` now runs **`alembic upgrade head` in-process at
  startup** (no-op at head; the real path for deploys). Verified:
  - **fresh database**: `None → 0001`, full schema, columns *and*
    constraints identical to the live schema;
  - **existing database**: rows before == rows after (data preserved),
    idempotent re-runs;
  - CLI (`alembic upgrade head`, `--autogenerate`) works from `backend/`.
- The legacy `create_all` path remains only as an explicit fallback if the
  alembic package is missing.

### 5. Security
- **CORS**: `allow_origins=["*"]` replaced by `CORS_ORIGINS` (comma list).
  Empty in development = permissive (Vite); empty in production = no
  cross-origin access.
- **Security headers** middleware: `Content-Security-Policy` (configurable
  `SECURITY_CSP`), `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`; HSTS in
  production only.
- **Login rate limiting**: fixed-window per (client IP) and per
  (client IP, email) — `LOGIN_RATE_LIMIT_PER_MINUTE` (0 disables) → 429
  `RATE_LIMITED` with `Retry-After`.
- Upload size + file-type + magic-byte validation enforced (400s with stable
  error codes).
- **`.env.example` cleaned**: placeholders only — the shipped dev passwords
  (`nexus_dev_2026`, `neo4j_dev_2026`, `dev-only-change-me`) are gone; all
  Phase 1 settings documented (worker, storage/S3, OCR, security, logging).
  `backend/.env` (real dev values) is gitignored.
- Reviewed JWT handling (short-lived, signed, type-checked, role must match
  DB role, active-user check, no sensitive claims) and password hashing
  (bcrypt) — already sound, no changes. No secrets in logs (scan + audit
  review).

### 6. Observability
- **Request IDs**: `X-Request-ID` honored/generated per request, echoed in
  the response, attached to every structured log record (`[rid=…]`,
  `[rid=… job=N]` for worker logs).
- **`GET /api/v1/health`** extended: database (connected + reachable),
  **storage** (backend, ok), **worker** (active workers + live queue depth
  from the queue table), neo4j.
- **`GET /api/v1/readyz`** (no auth): 200 only when DB + storage are usable;
  503 otherwise. Worker is reported, not required (it may be another
  process).
- `LOG_FORMAT=json` produces one JSON object per line with
  `request_id`/`job_id` fields for shippers.

### 7. Performance / pagination
- Opt-in pagination on the list endpoints (`/cases`, case-scoped
  documents/entities/relationships/evidence/timeline/locations/hypotheses/
  contradictions/gaps/simulations, and the top-level resource routers):
  `?limit=&offset=` (limit ≤ 1000) + **`X-Total-Count` always** (plus
  `X-Offset`/`X-Limit` when paged). **Body shape unchanged** — existing
  clients and tests are unaffected.
- Document processing no longer blocks the request lifecycle (job queue);
  OCR renders one page at a time; extraction caps unchanged.

### 8. Testing
- New `tests/test_production_foundation.py` (26 tests): job lifecycle
  (upload→job→worker→result), retry reuses the same job row, duplicate
  upload 409, OCR image + scanned PDF + honest failures (disabled,
  dependency missing), text PDF skips OCR, storage local + S3 (moto)
  round-trips, magic-byte/extension rejections, Alembic on fresh + existing
  DB (data preserved, idempotent), rate limiting, security headers, request
  IDs, CORS config, health/readyz, pagination + validation bounds,
  `.env.example` credential scan.
- **Full suite: 411 passed, 2 skipped, 0 failed** (3:36). The 2 skips are
  environment-conditional (Neo4j not running; Playwright not installed) —
  same categories as the pre-Phase-1 baseline.

## Remaining limitations (honest)
- S3 backend is verified against moto (in-memory S3); a real AWS/MinIO
  round-trip was not exercised in this environment.
- Login rate limiting is per-process (no shared Redis) — multi-process
  deployments enforce per-node budgets (limits are set with headroom).
- `alembic 0001` is a bootstrap (create_all-based by design); schema
  evolution from here is standard autogenerated migrations.
- The legacy `/api` surface (pre-v1) is unchanged by design.
- OCR quality depends on scan quality; low-quality scans fail honestly
  rather than guessing.
