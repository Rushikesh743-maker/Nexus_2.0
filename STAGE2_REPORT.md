# NEXUS — Stage 2 Report: Document Ingestion & AI Entity Extraction

Date: 2026-09-07 · Built in-place on the Stage 1 platform (no redesign, no
parallel implementations). All data is synthetic and labelled
"SYNTHETIC DEMONSTRATION DATA".

**Verification summary:** pytest `143 passed, 1 skipped` · `npm run build`
✓ 9.9 s · `npm run test:frontend-sanity` 14/14 pages ·
`npm run test:frontend-auth` 8/8 · live smoke test (upload → process →
review → graph/timeline/evidence updates, plus the full legacy API surface)
all green.

---

## 1. What was implemented

The complete Stage 2 pipeline, real backend only (no fake AI, no hardcoded
extraction in React, no random confidence):

1. **Document upload** — PDF / TXT / CSV with real validation
   (extension, contradicting MIME, size, empty, PDF magic header, encoding,
   CSV header), streaming SHA-256, safe server-generated storage, and
   per-case duplicate detection by hash.
2. **Processing lifecycle** — `UPLOADED → PROCESSING → PROCESSED | FAILED`
   as a real, pollable state driven by a background task; honest `FAILED`
   with user-safe messages; idempotent retry.
3. **Normalization** — stored file → capped `DocumentContent`
   (PDF per-page text, TXT lines, CSV rows + column names; unknown CSV
   columns tolerated).
4. **Entity & relationship extraction** — behind one
   `EntityExtractionProvider` interface: a deterministic rule-based
   provider (default, works with no credentials) and an LLM provider
   (OpenAI-compatible via the existing `LLM_*` env; JSON-only contract,
   Pydantic-validated; the LLM never writes to the database; any failure
   fails the document).
5. **Mandatory provenance** — every candidate/relationship carries
   document + page (PDF) / line (TXT) / row+column (CSV) + snippet;
   unavailable locations are represented, never invented.
6. **Entity resolution** — conservative, explainable match suggestions
   against the case's confirmed entities (exact 1.00, initial+surname 0.82,
   token-overlap ≥ 0.55, best-one, data-supported reasons).
7. **Investigator verification** — accept / reject / defer for entity
   candidates, relationships and matches; only acceptance writes to the
   confirmed case data (`Entity`, `Relationship`, `Evidence`,
   `TimelineEvent`), each with provenance; the case graph, evidence
   register and timeline therefore grow only through verified facts.
8. **Audit** — every step audited (upload, processing transitions, every
   review decision) with actor, case, object id, time, structured metadata.
9. **Frontend** — document service on the shared axios client, a Documents
   panel in the Evidence tab (upload / live status / counts / retry /
   review link), and a review workspace with working actions.

## 2. Files created

| File | Purpose |
| --- | --- |
| `backend/app/core/storage.py` | Upload validation (`validate_upload`, `DocumentInvalidError`), safe storage (`store_file`, `.part` + atomic rename, realpath containment), `delete_file`, `storage_root` |
| `backend/app/services/entity_extraction.py` | Extraction contract (`SourceRef`, `ExtractedEntity`, `ExtractedRelationship`, `ExtractionResult`), `RuleBasedExtractionProvider` (documented confidence/rule tables), `LLMExtractionProvider`, `get_extraction_provider` factory, corpus gazetteer |
| `backend/app/services/document_processor.py` | `extract_content(document) → DocumentContent` for PDF (pypdf, per-page) / TXT / CSV; `ProcessingError` |
| `backend/app/services/document_service.py` | Upload, background-safe `process_document`, atomic `_persist_extraction` (idempotent), the full review workflow (accept/reject/defer for candidates, relationships, matches), audit events |
| `backend/app/services/entity_resolution.py` | Deterministic scoring: exact / initial+surname / token-overlap with data-supported reasons |
| `backend/app/repositories/document_repository.py` | Document lists with extraction counts, candidate/relationship/match loading (bounded queries), summary builder |
| `backend/app/api/v1/documents.py` | The 13 document lifecycle endpoints |
| `backend/tests/test_extraction.py` | 28 unit tests: rule extraction, provenance, dedupe, CSV roles, gazetteers, resolution scoring, LLM contract (stubbed HTTP) |
| `backend/tests/test_documents_api.py` | 25 end-to-end API tests: validation, lifecycle, review workflow, corrupted PDF, CSV, audit trail |
| `data/documents/generate_fixtures.py` | Reproducible generator for the three fixtures |
| `data/documents/synthetic_fir.txt` / `.pdf` / `synthetic_calls.csv` | Small labelled synthetic fixtures (echo seeded case entities to exercise matching) |
| `src/services/v1/documentService.js` | All document API calls on the shared v1 client |
| `src/components/cases/DocumentsPanel.jsx` | Upload, real pollable status, counts, retry, review link |
| `src/pages/cases/DocumentReviewPage.jsx` | Review workspace: matches → candidates → relationships |

## 3. Files modified

| File | Change |
| --- | --- |
| `backend/app/models/models.py` | `Document` +6 columns (`mime_type`, `storage_path`, `sha256` indexed, `uploaded_by` FK, `processed_at`, `processing_error`); 4 new tables: `document_extraction`, `entity_candidate`, `relationship_candidate`, `entity_match_suggestion` |
| `backend/app/models/__init__.py` | Export the 4 new models |
| `backend/app/core/config.py` | `llm_base_url`, `storage_root`, `max_upload_mb`, `extraction_max_chars`, `extraction_max_rows` |
| `backend/app/core/database.py` | Idempotent startup migration (`_ensure_columns`: `ALTER TABLE … ADD COLUMN` guarded by `information_schema`) so pre-existing DBs pick up the 6 new columns |
| `backend/app/services/auth_service.py` | **Bug fix:** `record_audit` passed `metadata=` where the model attribute is `meta` — all Stage 1 audit rows had NULL metadata; now `meta=metadata` |
| `backend/app/api/v1/__init__.py` | Register the documents router |
| `backend/app/api/v1/cases.py` | `GET /cases/{id}/documents` now returns the extended `DocumentOut` (hash, uploader, processing state, extraction counts) |
| `backend/app/schemas/v1.py` | Extended `DocumentOut`; new schemas (`EntityCandidateOut`, `RelationshipCandidateOut`, `MatchSuggestionOut`, `ExtractionSummaryOut`, `DocumentStatusOut`, `DocumentDetailOut`, `ExtractionOut`, `ReviewDecision`) |
| `backend/requirements.txt` | `pypdf>=4.0` (PDF text extraction) |
| `backend/.env.example` | `LLM_BASE_URL`, `STORAGE_ROOT`, `MAX_UPLOAD_MB`, `EXTRACTION_MAX_CHARS`, `EXTRACTION_MAX_ROWS`; LLM section now describes extraction usage |
| `.gitignore` | `backend/storage/` |
| `src/App.jsx` | Route `cases/:caseId/documents/:documentId` → `DocumentReviewPage` |
| `src/services/v1/index.js` | Export `documentService` |
| `src/pages/cases/CaseEvidencePage.jsx` | Renders `DocumentsPanel` above the existing evidence register (register unchanged) |
| `README.md`, `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/DATABASE.md` | Stage 2 documentation (endpoints, architecture, schema, env) |

## 4. Database changes

PostgreSQL (nexus). No blobs — files live on disk; only metadata in DB.

**`document` — 6 new columns** (applied to existing DBs by an idempotent
startup migration; new installs get them from the models):

| Column | Type | Notes |
| --- | --- | --- |
| `mime_type` | VARCHAR(128) | validated content type |
| `storage_path` | VARCHAR(512) | relative path, **never exposed via the API** |
| `sha256` | VARCHAR(64), indexed | per-case duplicate detection |
| `uploaded_by` | INTEGER → `user.id` (SET NULL) | actor |
| `processed_at` | TIMESTAMPTZ | when extraction succeeded |
| `processing_error` | TEXT | user-safe failure message |

**4 new tables** (all cascade with their case/document):

- `document_extraction` — one per document: `source_type` (pdf/txt/csv),
  capped `raw_text`, `pages` JSON (per-page heads for PDF), `rows` JSON
  (CSV head), `stats` JSON (provider, counts, warnings).
- `entity_candidate` — extracted, unreviewed entities: type, name,
  aliases, confidence, `source_location` JSON (page/row/column/line/value),
  `source_snippet`, `extraction_method`, status
  (PENDING/ACCEPTED/REJECTED/DEFERRED), `accepted_entity_id`, decision
  columns (by/at/note).
- `relationship_candidate` — extracted link proposals referencing two
  `entity_candidate` rows, 10-type vocabulary, confidence, provenance,
  status, decision columns.
- `entity_match_suggestion` — candidate ↔ existing entity: similarity,
  `reasons` JSON, status, decision columns.

Total platform tables: 13 → **17**.

## 5. New endpoints

All under `/api/v1`, JWT-authenticated (all four roles may upload and
review, per the role ladder); errors use the platform shape
`{error:{code,message}}`.

| Method & path | Result |
| --- | --- |
| `POST /cases/{case_id}/documents` (multipart `file`) | `201 DocumentOut` — validates, stores, commits atomically, starts background processing. `400 DOCUMENT_UNSUPPORTED_TYPE / DOCUMENT_INVALID / DOCUMENT_TOO_LARGE`, `409 DOCUMENT_DUPLICATE` |
| `GET /documents/{document_id}` | `200 {document, summary}` |
| `GET /documents/{document_id}/status` | `200` real status + summary (poll endpoint) |
| `POST /documents/{document_id}/process` | `202` start/retry processing. `409 DOCUMENT_ALREADY_PROCESSED / DOCUMENT_PROCESSING` |
| `GET /documents/{document_id}/extraction` | `200` candidates + relationships + matches + summary |
| `POST /documents/{id}/extraction/candidates/{cid}/accept` | `200` — links/creates confirmed `Entity` + `Evidence`; events also create `TimelineEvent`. `409 MATCH_REVIEW_REQUIRED / CANDIDATE_ALREADY_REVIEWED` |
| `POST …/candidates/{cid}/reject` | `200` — rejected (kept for audit); pending relationships on that endpoint auto-rejected. `409 CANDIDATE_ALREADY_REVIEWED` |
| `POST …/candidates/{cid}/defer` | `200` — `DEFERRED` |
| `POST /documents/{id}/extraction/relationships/{rid}/accept` | `200` — creates confirmed `Relationship` (deduped per case+endpoints+type) + `Evidence`. `409 CANDIDATE_NOT_CONFIRMED / CANDIDATE_ALREADY_REVIEWED` |
| `POST …/relationships/{rid}/reject` | `200` — rejected. `409 CANDIDATE_ALREADY_REVIEWED` |
| `POST /documents/{id}/extraction/matches/{mid}/accept` | `200` — folds candidate into the existing entity (alias) + confirms it + `Evidence` |
| `POST …/matches/{mid}/reject` | `200` — candidate stays independent |

`404` codes: `DOCUMENT_NOT_FOUND`, `ENTITY_NOT_FOUND`,
`RELATIONSHIP_NOT_FOUND`, `MATCH_NOT_FOUND`.
(Pre-existing `GET /cases/{case_id}/documents` was extended in place with
hash, uploader, processing state and extraction counts.)

## 6. Document-processing architecture

```
POST /cases/{id}/documents (multipart)
  └─ api/v1/documents.upload_document
       └─ document_service.upload_document
            ├─ core/storage.validate_upload   ext · MIME · size · empty · %PDF · UTF-8/NUL · CSV header
            ├─ SHA-256 streamed (10 MB cap) · per-case duplicate check → 409
            └─ Document row (UPLOADED) + storage.store_file (atomic .part→rename,
               server-generated name) committed together
       └─ BackgroundTasks.add_task(document_service.process_document, doc.id)

process_document (own SessionLocal — background-safe)
  ├─ status PROCESSING + audit DOCUMENT_PROCESSING_STARTED
  ├─ document_processor.extract_content → DocumentContent {pages|lines|csv_rows, raw_text (capped)}
  │     PDF: pypdf per-page text   TXT: strict UTF-8 lines   CSV: DictReader, known column roles,
  │     unknown columns ignored, rows capped (EXTRACTION_MAX_ROWS)
  ├─ entity_extraction.get_extraction_provider().extract(content, case_entities)
  │     → ExtractionResult (pydantic-validated; LLM any-failure ⇒ ExtractionError)
  ├─ _persist_extraction (ONE atomic commit):
  │     DocumentExtraction row · EntityCandidate rows (deduped on type+name+source location)
  │     · RelationshipCandidate rows (endpoints must be detected candidates)
  │     · EntityMatchSuggestion rows (one best per candidate, reasons recorded)
  ├─ status PROCESSED + processed_at + audit DOCUMENT_PROCESSING_COMPLETED
  └─ any ProcessingError/ExtractionError ⇒ rollback, status FAILED +
     processing_error (user-safe) + audit DOCUMENT_PROCESSING_FAILED
```

Properties: the upload response is immediate; status is real and pollable
(no invented progress); a corrupted/unsupported file ends `FAILED` with an
honest message (no tracebacks, no FS paths); reprocessing is idempotent;
processing is atomic — there is no half-extracted state.

## 7. Extraction architecture

- **Contract** (`entity_extraction.py`): `SourceRef` (document_id,
  page/row/column/line, value, snippet, available) + `ExtractedEntity`
  (8-type vocabulary, confidence 0–1, method) + `ExtractedRelationship`
  (fixed 10-type vocabulary) → `ExtractionResult`. Validated with Pydantic;
  an invalid type or out-of-range confidence is a hard error.
- **Rule-based provider (default):** deterministic, no credentials.
  Patterns: case reference 0.98, phone 0.95, vehicle 0.95, account 0.80,
  person via title 0.60 / explicit "named" 0.70 / subject 0.75 / initial
  0.60, org suffix 0.65, event (ISO/DMY timestamp + line content) 0.80;
  gazetteers: the case's confirmed entities (0.90, first-class) and the
  synthetic corpus (0.80). Relationships are proposed **only** where a
  sentence states the link (e.g. "X called Y", "vehicle REG owned by Z",
  "X arrived in vehicle REG", "transfer … from A to B", person near a
  known location) or where a CSV row structurally pairs columns
  (caller↔callee → CALLED, from_account→to_account → TRANSFERRED_TO,
  person + phone/vehicle/location/account columns → OWNS/LOCATED_AT/
  INVOLVED_IN). Co-occurrence alone never yields a relationship.
- **LLM provider (opt-in via `LLM_PROVIDER`):** OpenAI-compatible
  `chat/completions` (env: key, model, base URL), temperature 0, JSON-only
  system contract mirroring the Pydantic schema. Output → `json.loads` →
  `ExtractionResult.model_validate` → the provider stamps the real
  document id and dedupes. **Any** failure (HTTP, JSON, schema, timeout)
  raises `ExtractionError` → document `FAILED`. The provider holds no DB
  session and has no write path. A misconfigured LLM setting at startup
  logs a warning and falls back to rules; a runtime LLM failure does not
  silently fall back (that would mask a broken configuration).
- **Factory:** `get_extraction_provider()` — rules by default; LLM only
  when configured.
- **Confidence is documented and deterministic** (tables in the module
  docstring); it ranks candidates, it is never a substitute for the
  investigator's accept/reject decision.
- **In-document dedupe:** one candidate per (type, normalized name,
  source location); when multiple rules hit the same spot, the higher
  confidence survives (gazetteer before pattern).

## 8. Resolution architecture

`entity_resolution.py` compares each new candidate only against
**same-type** confirmed entities of the same case:

| Rule | Score | Emitted reason |
| --- | --- | --- |
| normalized names identical | 1.00 | "normalized names are identical" |
| surname(s) identical + first-name initial matches ("V. Rao" ~ "Vikram Rao") | 0.82 | "surname(s) are identical" + initial match |
| token overlap (Jaccard ≥ 0.5) | 0.55 + 0.35·J | shared tokens + counts |

Best-one suggestion per candidate at threshold 0.55, with the exact checks
that fired (`reasons`). Nothing is suggested without a data-supported
reason; nothing is ever merged silently — acceptance is an explicit
endpoint call that folds the candidate's name into the entity's aliases
and records the decision (who, when, similarity) plus an `Evidence` row.
Rejecting a suggestion keeps the candidate independent and reviewable.

## 9. Provenance model

Every persisted fact knows where it came from, and the UI shows it:

- **PDF:** `source_location.page` (1-based) + snippet of the page text.
- **TXT:** `source_location.line` (1-based) + line snippet.
- **CSV:** `source_location.row` (1-based, header = row 0) +
  `source_location.column` + row snippet.
- **Events:** the matched timestamp additionally in
  `source_location.value`.
- Confirmed rows keep the chain: `Entity.meta.extracted` +
  `Evidence(source_reference="candidate:{id}")` +
  `Relationship.meta.source_location/source_snippet/extraction_method` +
  `TimelineEvent.evidence_id`.
- If the extractor could not determine a location it says so
  (`available` flag / missing fields) — locations are never invented.
- The uploaded file itself is immutable after upload; the extraction
  record is immutable after processing; rejections are preserved (audit
  trail), never deleted.

## 10. Verification workflow

```
process → candidates (PENDING) + match suggestions (PENDING)
reviewer (review workspace, /cases/:id/documents/:docId)
  ├─ match pending?  accept → fold into existing entity (alias + evidence)
  │                  reject → candidate stays independent
  ├─ entity candidate: accept → confirmed Entity (+Evidence; event → TimelineEvent)
  │                     reject → REJECTED (kept); its pending relationships auto-rejected
  │                     defer  → DEFERRED (review later)
  └─ relationship:     accept → allowed only when BOTH endpoints are ACCEPTED
                          (else 409 CANDIDATE_NOT_CONFIRMED)
                        → confirmed Relationship (deduped) + Evidence
                          reject → REJECTED
```

Guards: a candidate with a pending match cannot be accepted directly
(`409 MATCH_REVIEW_REQUIRED`); a decided candidate/match cannot be
re-decided (`409 CANDIDATE_ALREADY_REVIEWED` / `MATCH_ALREADY_REVIEWED`).
Rejected items are **not** facts: they appear nowhere in the graph,
timeline or evidence register. The case's confirmed graph, evidence and
timeline grow exclusively through acceptance — and every decision is
audited.

## 11. Frontend additions

Existing React/Vite stack, existing design system, no restyling, no
parallel data layer:

- `src/services/v1/documentService.js` — all 13 calls on the shared axios
  client (JWT, normalized `V1Error` with offline/401/structured codes).
- `DocumentsPanel` (top of the Evidence tab) — upload control, per-document
  rows with real status badges (queued / processing / processed / failed +
  error message), extraction counts and pending-review count, Retry on
  failure, and a Review link. Polls the real backend every 4 s **only
  while** a document is in flight; shows loading / empty / error / offline
  states; duplicate and validation errors surface as toasts with the
  backend's message.
- `DocumentReviewPage` (`/cases/:caseId/documents/:documentId`) — three
  sections: **Suggested matches** (similarity + reasons, accept / not-a-
  match), **Entity candidates** (type, confidence, method, provenance
  line/row/column + snippet, accept / reject / later; reviewed rows show
  the decision and the linked entity), **Relationship proposals**
  (source —TYPE— target, confidence, supporting snippet, accept disabled
  until both endpoints are confirmed, reject). Processing and failed
  states are explicit pages; every action is a real call with per-row
  loading and error toasts.
- Route registered in `App.jsx` inside the existing `CaseLayout` tree
  (case file loads once via context, as with every other tab).

## 12. Security

- **RBAC enforced in the backend** (role ladder ANALYST < INVESTIGATOR <
  SUPERVISOR < ADMIN): upload/processing/review endpoints require the
  floor role; reads require authentication. No frontend-only checks.
- **Upload validation is adversarial**: extension allowlist, MIME
  contradiction rejection, 10 MB streaming limit (no full-file buffering),
  empty-file and corrupt-PDF rejection, UTF-8/NUL checks, CSV header
  check.
- **Safe storage**: server-generated filenames (`{doc_id}_{safe_stem}`),
  `..`/path-separator sanitization, containment check against the storage
  root via `realpath`; uploads land in `.part` files and are atomically
  renamed. The storage path is metadata only — no API returns it.
- **Duplicates** detected by streamed SHA-256 per case (409).
- **Errors never leak**: structured `{error:{code,message}}`, user-safe
  messages (no tracebacks, no paths); failures are logged server-side
  with context.
- **LLM keys** live only in environment config; the LLM provider has no
  database access and its output is fully validated before persistence.
- **Audit**: actor + case + object + time + structured metadata for every
  document and review action; no secrets, tokens or raw document content
  in logs or audit rows.
- **JWT** unchanged (HS256, role-verified against the DB user on every
  request).

## 13. Tests executed

Exact commands (repo root / `backend/` as noted):

```bash
cd backend && python3 -m pytest -q
python3 -m pytest backend/tests/test_extraction.py -q
python3 -m pytest backend/tests/test_documents_api.py -q
npm run build
npm run test:frontend-sanity
npm run test:frontend-auth
```

plus a live smoke test against the running backend (real login, real
uploads of the synthetic fixtures, real review decisions, legacy surface
checks).

## 14. Test results

| Check | Result |
| --- | --- |
| `python3 -m pytest backend/tests/ -q` | **143 passed, 1 skipped** (skip = live Neo4j round-trip, needs a graph server) |
| — of which `test_extraction.py` | 28 passed (rule extraction, provenance, dedupe, CSV roles, gazetteers, resolution scoring, LLM contract incl. malformed-JSON and invalid-type rejection) |
| — of which `test_documents_api.py` | 25 passed (validation codes, lifecycle, corrupted-PDF FAILED + retry, match-first workflow, endpoint confirmation guards, reject cascades, duplicate 409, re-run idempotency, CSV row provenance, audit actions present) |
| `npm run build` | ✓ built in 9.9 s (no errors) |
| `npm run test:frontend-sanity` | 14/14 pages rendered (SSR harness) |
| `npm run test:frontend-auth` | 8/8 (JWT login, session normalization, live list, wrong-password rejection) |
| **Live smoke** (backend on :8000, case 1) | login ✓ · TXT upload → 201, `UPLOADED` → poll → `PROCESSED` (15 candidates, 4 relationships, 9 matches) ✓ · match accept (sim 1.00, "normalized names are identical") ✓ · initial+surname match surfaced (sim 0.82, "first name initial matches") ✓ · OWNS relationship confirmed after both endpoints ✓ · event accept → new `TimelineEvent` ✓ · reject/defer ✓ · re-reject 409 `CANDIDATE_ALREADY_REVIEWED` ✓ · duplicate upload 409 `DOCUMENT_DUPLICATE` ✓ · bad extension 400 `DOCUMENT_UNSUPPORTED_TYPE` ✓ · missing doc 404 `DOCUMENT_NOT_FOUND` ✓ · no auth 401 ✓ · CSV upload → `PROCESSED` (21 candidates, 13 relationships, row+column provenance) ✓ · case counts updated (entities 9→10, relationships +1, timeline 3→4, evidence rows from extractions) ✓ |
| **Legacy surface** | `/api/stats` 200 · `/api/graph` 200 (53 nodes / 138 edges) · `/api/findings` 200 (23) · `/legacy` 200 |
| Audit trail (DB) | `DOCUMENT_UPLOADED / PROCESSING_STARTED / PROCESSING_COMPLETED / PROCESSING_FAILED / PROCESS_REQUESTED / ENTITY_ACCEPTED / ENTITY_REJECTED / ENTITY_DEFERRED / RELATIONSHIP_ACCEPTED / RELATIONSHIP_REJECTED / ENTITY_MATCH_ACCEPTED / ENTITY_MATCH_REJECTED` all present with structured metadata (the Stage 1 `record_audit` metadata bug is fixed and verified) |

## 15. Existing-functionality verification

- All 90 Stage 1 tests still pass unchanged (no test was weakened or
  removed; the suite grew 90 → 143).
- The legacy analysis API (`/api/stats`, `/api/graph`, `/api/findings`,
  `/legacy`, dashboard, investigations/analysis screens) verified live —
  responses unchanged in shape and content (53 nodes / 138 edges /
  23 findings, as before).
- Seeded case data intact: 4 cases; case 1's original 7 entities and 5
  relationships retained (stage 2 additions are additive).
- Seeded documents 1–2 still list correctly; the extended `DocumentOut`
  defaults keep the old consumers working (the top-level `/api/v1/documents`
  list endpoint included).
- Case creation, simulations, users, copilot status, login/JWT flows
  covered by the passing Stage 1 tests plus the frontend auth script.
- The two frontend QA scripts (sanity 14/14, auth 8/8) pass, confirming
  no regressions in the existing UI.

## 16. Remaining limitations

1. **Line-based text rules:** the rule extractor evaluates TXT/PDF text
   per line; a connective phrase wrapped across lines (e.g. "vehicle …
   owned by" split by a line break) is not detected. Fixtures and
   documentation keep such phrases on one line; the LLM provider is the
   remedy for arbitrary layouts.
2. **Person detection is cue-based** (title, explicit "named/subject",
   initial, case/corpus gazetteer) — a bare full name in free text is not
   extracted by rules. Deliberate: precision over recall in v1.
3. **CSV:** one named party per row participates in relationship pairing
   (first name column in column order); richer multi-party rows need the
   LLM provider.
4. **PDF:** text layer only — scanned pages yield no text (OCR is a later
   stage); per-page text is capped.
5. **LLM provider** is contract-tested with a stubbed endpoint; it is not
   exercised against a live model in CI (no credentials in the sandbox),
   and rules remain the default.
6. **One best match** per candidate (no ranked alternatives list).
7. **Event timestamps** parse a fixed format set (ISO, DMY, H:M).
8. **No document delete endpoint** (documents are immutable by design);
   retention is operational, not API-driven.
9. No in-browser document viewer (page/line display) — review shows
   provenance snippets; the full file stays on server storage.
10. Graph sync to Neo4j of newly confirmed entities is not performed
    automatically (optional mirror, later stage).

## 17. Stage 3 recommendations

Prioritized against the "do not yet" list:

1. **Copilot conversation** on the now-proven LLM provider infrastructure
   (same env, same validation discipline; case-scoped, read-only first).
2. **Advanced graph analytics** (community detection, centrality, shortest
   paths) over the *confirmed* case graph — the stage 2 workflow makes
   that graph trustworthy enough to analyze.
3. **Neo4j sync of confirmed case data** (the `GraphStore` write path
   exists; add a sync job + drift check).
4. **OCR for scanned documents** (`pytesseract` is already an optional
   dependency) feeding the same `DocumentContent` contract.
5. **Document viewer** (render stored PDF/TXT/CSV in the review UI with
   the provenance line highlighted) — directly improves review accuracy.
6. **Evidence-impact scoring** for hypotheses against the confirmed
   evidence graph (the Stage 1 simulation records are the placeholder).
7. **Bulk review** (accept all high-confidence candidates of a type) with
   per-action audit, and export of the review decision log.
8. **Alembic migrations** once the schema has stopped evolving (the
   idempotent startup migration is a deliberate stopgap).
9. **Multilingual extraction** (Hindi-first) via the LLM provider +
   translated rule tables.
10. Retention/cleanup job for `backend/storage` (configurable, audited).

**Stop.** Stage 2 is complete and verified; nothing from the "do not yet"
list has been started.
