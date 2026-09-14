# NEXUS — Stage 6 Report: The Case Workflow

**Scope:** make one case work end-to-end — upload → process → extract →
review → confirm → graph → intelligence → timeline/map/evidence →
re-upload → stale → re-analyze — as a single coherent case workspace,
built **in place** on Stages 1–5. No rewrites of existing engines, no
mock fallback, no fabricated data.

**Status: complete and verified** — 383 passed / 1 skipped (pytest),
stage-4/5/6 live smokes green, production build + 45-page frontend
sanity green.

---

## 1. What Stage 6 delivered

- A **17-tab case workspace** where every tab answers one question in
  the investigation sequence (Overview readiness → Documents → Review
  → Entities/Relationships → Evidence → Graph → Timeline/Map →
  Hypotheses/Contradictions/Gaps/Impact → Intelligence → Audit →
  Reports).
- **Real per-document processing** with job rows, stage state, errors
  and a status endpoint — no fake progress.
- A **review center** with five categories and full provenance;
  confirm/reject are explicit human decisions.
- A **case graph built only from confirmed case data** (versioned,
  with per-node evidence counts and per-edge provenance).
- **CaseAnalysisService** — orchestration of the existing
  stage-3/4 engines over confirmed data, with a freshness state
  machine (`not-analyzed / up-to-date / stale(reason) /
  insufficient`) and preserved stale findings.
- A **case access model** (owner / supervisor / admin) enforced on
  every case route, plus a read-only per-case audit trail.
- The **`CASE-DEMO-END2END-01`** demonstration case (FIR + CDR + reports),
  alongside the existing `CASE-DEMO-MULTILING-01`.

## 2. What was NOT changed (binding rule respected)

Stages 1–5 endpoints, services, engines, tests and pages remain as
delivered. Stage 6 added routes, services, models and pages; it did
not rewrite extraction, network analysis, anomaly detection,
contradiction rules, hypothesis scoring, timeline, geospatial or gap
engines — it **orchestrates** them. The pre-existing analysis pipeline
(`backend/pipeline`) is untouched.

## 3. Documents: upload, real processing, status

- `POST /cases/{id}/documents` (multipart, INVESTIGATOR+) → 201 row
  with `status: UPLOADED → PROCESSING → PROCESSED / FAILED`.
- Processing is a **real job** (`DocumentProcessingJob`): per-document
  stage text (ingest → text extraction → OCR → normalize → extract →
  resolve → file review candidates), started/finished timestamps,
  error. `GET /cases/{id}/documents/processing/status` returns the
  per-document state + case aggregate.
- **No fake percentages:** a PDF with no extractable text finishes
  `FAILED` with the real reason (`No text could be extracted…`); the
  UI shows exactly that, with Retry.
- Retry re-runs the job for a failed document; it does not recreate
  the row.

## 4. Idempotent re-upload (no duplicates)

Re-uploading identical bytes (sha256 match on the same case) returns
the existing row with `duplicate: true` — no duplicate document, no
double extraction, no double candidates. Verified by
`test_stage6_e2e.py::test_upload_is_idempotent` and the live smoke.

## 5. Extraction → candidates (never auto-confirmed)

Processing files results as review candidates:

| Candidate row | What it carries |
|---|---|
| `ExtractedEntity` | type, canonical name, aliases, source doc + snippet, confidence, extraction method |
| `ExtractedEntityMatch` | existing entity id, matched name, similarity, reason |
| `ExtractedRelationship` | source→target, relationship type, confidence, source doc + snippet, method |
| evidence claims | structured claims (contradiction inputs) — **display-only**, not decisions |

Nothing is merged or confirmed automatically; `total_pending` counts
only decidable items.

## 6. Review center (5 categories)

`GET /cases/{id}/review/queue` → entities / entity matches /
relationship candidates / evidence claims / contradictions, each item
with source document, snippet, page (where the document carries it),
confidence and method. The Review tab renders all five; evidence
claims are display-only with a link to the Evidence tab.

## 7. Confirm / reject semantics

`POST /cases/{id}/review/confirm|reject` with
`{category, item_ids}`:

- **Entity confirm** → creates the `Entity` row (canonical name,
  type, metadata incl. aliases + `confirmed: true`) and materialises
  every confirmed relationship touching it.
- **Match confirm** → alias on the existing entity (no second row).
- **Relationship confirm** → upserts `Relationship`
  (idempotent on source/target/type) with `metadata.confirmed: true`
  + provenance (source document name/snippet/evidence id, method).
- **Reject** → terminal for that candidate.

Errors: 404 unknown item, 409 already decided, 422 bad category.
Every decision audited with actor + item ids.

## 8. Relationships are CANDIDATE by default

Extraction never writes a confirmed relationship. A relationship
exists in the case graph **only after** an explicit confirm. The
Relationships tab shows confirmed relationships with their
provenance and deep links to the evidence and the graph.

## 9. Case graph — confirmed data only

`POST /cases/{id}/graph/build` → `{status, graph_version, nodes,
edges}` built strictly from confirmed entities/relationships. A new
case with no confirmations has no graph — the static demo graph is
never reused for a new case (verified: empty-case smoke asserts the
build returns zero nodes/edges and analysis is 409).
`GET /cases/{id}/graph` adds per-node `evidence_count` and per-edge
provenance.

## 10. Intelligence orchestration (existing engines)

`CaseAnalysisService.run` runs, in order: graph build (versioned) →
network analysis → anomaly detection → contradiction analysis →
hypothesis generation → timeline analysis → geospatial analysis → gap
detection → findings persistence (`GraphFinding` rows stamped with
`graph_version`). No engine was rewritten.
`POST /cases/{id}/analysis/run` → `{status, findings_count,
analysis_id, graph_version}`; 409 `INSUFFICIENT_CONFIRMED_DATA`
before any confirmations.

## 11. Idempotent re-run

Re-running analysis over unchanged confirmed data returns the stored
results with `status: "no_changes"` and `recomputed: false` — verified
by test and live smoke (twice in a row).

## 12. Freshness state machine + stale reason

`GET /cases/{id}/analysis/status` →
`not-analyzed / up-to-date / stale / insufficient`.

- Uploading + processing new documents does **not** mark the analysis
  stale (no confirmed data changed).
- Confirming **new** candidates marks it **stale** with
  `stale_reason` = "N new confirmed item(s) since last analysis" —
  the UI shows a stale banner with that exact reason and a Re-run
  action.
- Re-running returns to `up-to-date`.

## 13. Stale findings preserved, never deleted

Findings from the previous `graph_version` remain in
`stale_findings` (visible in the API and Reports tab); the current
set is `current_findings`. Nothing is garbage-collected.

## 14. Timeline, map, evidence integration

- Timeline tab: case events with `?entity=` filter; empty state is
  honest ("no events recorded yet" — no fabricated timeline).
- Map tab: **real** case locations only; coordinates left NULL where
  the documents don't state them (never fabricated); `?entity=` /
  `?location=` focus; markers show related events + evidence links.
- Evidence tab: paginated, filterable, `?evidence=` / `?reference=`
  deep link with row highlight; original document + snippet always
  visible.

## 15. Security: case access model + RBAC

- Case routes resolve ownership: owner / SUPERVISOR / ADMIN.
- A different INVESTIGATOR gets **404** (not 403) on read, upload,
  review, graph, analysis, copilot and audit — existence not leaked;
  counts/search cannot leak either case data.
- Role gates unchanged: writes INVESTIGATOR+, analysis ANALYST+,
  users ADMIN, cross-case audit SUPERVISOR+.
- Verified by `test_stage6_e2e.py::test_case_access_isolation`
  (two investigators, full negative matrix) and the live smoke.

## 16. Audit trail

Read-only `GET /cases/{id}/audit`: case creation, document upload,
processing completion/failure, every confirm/reject (with item ids),
graph build, analysis run / re-analysis. Actor + timestamp +
metadata; no passwords, tokens or keys in any row.

## 17. Frontend: the case workspace

- 17 tabs (Documents, Review, Entities, Relationships, Impact,
  Reports added; Overview, Timeline, Map, Evidence, Graph,
  Hypotheses, Contradictions, Gaps, Intelligence, Audit updated).
- **Overview readiness panel** — documents / extraction / review /
  graph / intelligence with the deterministic **next action**
  (upload → wait → review → run/re-run → explore).
- **No mock fallback:** `VITE_USE_MOCK_API=false`; failures render
  the real API error with retry — never fake data.
- Deep links: `?entity=` (Entities/Graph/Timeline/Map),
  `?evidence=` / `?reference=` (Evidence), `?location=` (Map),
  `?relationship=` (Graph).
- All new pages use the shared UI kit (Card/Badge/Button/EmptyState/
  PageLoader/ErrorState) and the case-file context — no parallel
  data paths.

## 18. Demo case — CASE-DEMO-END2END-01 (synthetic)

5 documents (FIR.pdf, Investigation_Report.pdf, CDR.csv,
Vehicle_Report.pdf, Location_Report.pdf) → processed → 17 entities,
10 confirmed relationships, 38 evidence items, 3 timeline events, 3
locations, **1** evidence contradiction ("Vikram Sethi — Bhiwandi
Godown vs Kurla, 15 minutes apart"), **2** hypotheses. A central
person with relationships, vehicle + location connections, and an
investigation gap. Labeled **SYNTHETIC DEMONSTRATION DATA** in the
UI; coordinates NULL where unstated. Reproducible seed
(`backend/scripts/seed_demo_e2e.py`), idempotent at startup.

## 19. Tests & verification evidence

| Check | Result |
|---|---|
| `python3 -m pytest backend/tests/ -q` | **383 passed, 1 skipped** (skip = live Neo4j round-trip) |
| `backend/tests/test_stage6_e2e.py` | 3/3 (full workflow, STALE lifecycle, access isolation) |
| `scripts/stage6-live-smoke.py` (live API) | **all ~60 checks passed** (11 sections) |
| `scripts/stage4/5-live-smoke.py` | green (no regressions) |
| `npm run build` | 10.8s, clean |
| `scripts/frontend-sanity.mjs` | 45/45 pages render |

## 20. Acceptance checklist (spec §final demo)

- [x] brand-new case → upload FIR + CDR → processing status is real
- [x] extraction produces review candidates (none auto-confirmed)
- [x] confirm entity + relationship → they appear in Entities /
      Relationships with provenance
- [x] graph build reflects confirmed data only; edge shows supporting
      evidence → original document
- [x] run intelligence → findings / hypotheses / gaps / timeline /
      locations
- [x] second upload + confirm → analysis marked STALE **with reason**
- [x] re-run → up-to-date; old findings preserved as stale history
- [x] copilot answers for the same case (stage-5 intents)
- [x] another investigator cannot read/upload/build/analyze (404)
- [x] audit shows the sequence
- [x] no manual DB edits needed at any step

## 21. Known limitations (stated, not hidden)

- Page-level snippet extraction: snippets come from the extracted
  text stream; the "page" field is present when the document parser
  provides page boundaries (PDFs do; CSVs don't).
- Processing jobs run synchronously inside the request worker for
  typical file sizes; very large corpora would need a queue (the
  job model is already in place to grow into one).
- OCR path exists (stage 2) but depends on an installed OCR engine;
  scanned-only PDFs without text fail honestly with the real reason.
- Map shows locations with real coordinates only; cases whose
  documents don't state coordinates render an honest empty map.
- Incremental (per-delta) analysis is structured (version hash over
  confirmed data) but the re-run is a full recomputation of
  intelligence over the confirmed set — incremental execution is
  stage 7's explicit target.

---

### Key files (stage 6)

- Backend: `backend/app/services/v1/case_analysis.py`,
  `case_workflow.py`, `document_service.py` (job model),
  `routers/v1/cases.py` (workflow routes), `schemas/v1.py`
  (queue/status/summary schemas), `backend/scripts/seed_demo_e2e.py`.
- Frontend: `src/pages/cases/*` (17 tabs),
  `src/services/v1/analysisService.js`, `src/lib/navigation.js`,
  `src/App.jsx` (case routes).
- Tests/scripts: `backend/tests/test_stage6_e2e.py`,
  `scripts/stage6-live-smoke.py`, `docs/CASE_WORKFLOW.md`.
