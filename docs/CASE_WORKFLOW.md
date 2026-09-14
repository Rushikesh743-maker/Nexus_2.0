# NEXUS — Case Workflow (Stage 6)

The single-case investigation workflow: one case, its documents, its
extraction, its review, its graph, its intelligence — all case-scoped,
all real, no mock fallback.

> All data in this system is **synthetic demonstration data** (see the
> standing UI disclosure). No real case material is used or connected.

## 1. The shape of the workflow

```
create case ──▶ upload documents ──▶ process (auto, per-document jobs)
      │                                   │
      │                          extracted candidates
      │                                   ▼
      │                          review queue (CONFIRM / REJECT —
      │                          human decision, never automatic)
      │                                   │ confirmed
      │                                   ▼
      │                          case graph (built only from
      │                          confirmed case data)
      │                                   │
      │                                   ▼
      │                          intelligence run (existing engines,
      │                          orchestrated by CaseAnalysisService)
      │                                   │
      │                                   ▼
      │                          findings · contradictions · hypotheses
      │                          gaps · anomalies · timeline · map
      │
      └──▶ upload more documents → new candidates → confirm →
           analysis marked STALE (with reason) → re-run →
           stale findings preserved as history, new ones current
```

The frontend is organised around this flow: every case tab exists to
answer one question in the sequence, and every artifact links to its
evidence and back to its source document.

## 2. Case area (frontend)

`/cases/:caseId` — `CaseLayout` provides the 17-tab navigation and the
case-file context (`useCaseFile`):

| Tab | Route | Answers |
|---|---|---|
| Overview | `/cases/{id}` | Where is this case in the workflow? (readiness panel + next action) |
| Documents | `/cases/{id}/documents` | What is in this case, and what happened to each upload? |
| Review | `/cases/{id}/review` | What needs my decision? (5 categories, with provenance) |
| Entities | `/cases/{id}/entities` | Who/what is in this case? |
| Relationships | `/cases/{id}/relationships` | How are they connected, and why do we believe it? |
| Evidence | `/cases/{id}/evidence` | What supports a claim? (deep-linkable, paginated) |
| Graph | `/cases/{id}/graph` | The confirmed network + stage-3 intelligence panels |
| Timeline | `/cases/{id}/timeline` | What happened when? (`?entity=` filter) |
| Map | `/cases/{id}/map` | Where did it happen? (`?entity=` / `?location=` focus; real coords only) |
| Hypotheses / Contradictions / Gaps / Impact | `/cases/{id}/…` | Working state and what-if evidence simulation |
| Intelligence | `/cases/{id}/investigation` | Findings + anomalies + patterns + impact |
| Audit | `/cases/{id}/audit` | Who did what, when (read-only) |
| Reports | `/cases/{id}/reports` | State, counts, findings and the audit trail in one place |

**No mock fallback.** With `VITE_USE_MOCK_API=false` (the default) every
page loads live API data; failures render the real error with retry —
the UI never substitutes fake data.

## 3. Documents & processing (backend)

- Upload `POST /cases/{id}/documents` (multipart) → 201 with the row
  (`status: UPLOADED` → `PROCESSING` → `PROCESSED` / `FAILED`).
- Processing is a **real per-document job** (`DocumentProcessingJob`
  rows, `GET /cases/{id}/documents/processing/status`): stage text,
  progress, started/finished timestamps, error. No fake percentages —
  the job reports actual stage transitions; a PDF with no extractable
  text is `FAILED` with the real reason, not 100% green.
- Idempotency: re-uploading the same bytes (sha256) returns the
  existing row with `duplicate: true` — no duplicate rows.
- OCR is the existing Stage-2 path; extracted text is never written
  back into the original file.

## 4. Extraction → candidates (never auto-confirmed)

Processing runs the existing extraction pipeline and files results as
**candidates** in the review queue — nothing is merged or confirmed
automatically:

- **New entity** → `ExtractedEntity` (type, canonical name, aliases,
  source doc + snippet, confidence, `extracted`).
- **Entity duplicate/match** → `ExtractedEntityMatch` (existing entity,
  matched name, similarity, reason).
- **Relationship** → `ExtractedRelationship` (source→target, type,
  confidence, source doc + snippet, method) — **CANDIDATE by
  default**; only the investigator confirms.
- Evidence claims (contradiction inputs) → structured claims, not
  decisions.

`GET /cases/{id}/review/queue` returns all five categories with the
provenance fields (source document, snippet, page, confidence,
method). Counts: `total_pending` excludes evidence claims (they are
display-only, not decisions).

## 5. Confirm / reject semantics

`POST /cases/{id}/review/confirm` / `/reject` take
`{category: entity|relationship, item_ids: [...]}`:

- **Entity confirm** → materialises the `Entity` row (canonical name,
  type, metadata incl. aliases + `confirmed` flag), then materialises
  every confirmed relationship *touching* that entity.
- **Entity match confirm** → adds the matched name as an alias on the
  existing entity (never creates a second row).
- **Relationship confirm** → upserts the `Relationship` row
  (idempotent on (source, target, type)), stamped
  `metadata.confirmed = true`, provenance kept in `metadata`
  (source_document_name / source_snippet / source_evidence_id /
  extraction_method).
- **Reject** → terminal for that candidate.

Every confirm/reject is **audited** (`entity_confirm`,
`entity_match_confirm`, `relationship_confirm`, plus rejects) with the
actor, item ids and timestamps. No passwords or tokens in audit rows.

## 6. Case graph

`POST /cases/{id}/graph/build` → `{status, graph_version, nodes,
edges}`. The graph is built **only from confirmed case data** — a new
case with nothing confirmed has no graph (the static demo graph is
never reused). `GET /cases/{id}/graph` returns the payload with
per-node `evidence_count` and per-edge provenance (document, snippet,
evidence id).

## 7. Intelligence — orchestration, not rewrite

`POST /cases/{id}/analysis/run` runs the **existing** engines in order
through `CaseAnalysisService`:

1. graph build (versioned)
2. network analysis
3. anomaly detection
4. contradiction analysis
5. hypothesis generation
6. timeline analysis
7. geospatial analysis
8. gap detection
9. findings persistence (`GraphFinding` rows with `graph_version`)

Response: `{status, findings_count, analysis_id, …}`. 409
`INSUFFICIENT_CONFIRMED_DATA` when the case has nothing confirmed.
Idempotent: an unchanged re-run returns the stored results with
`recomputed: false`.

`GET /cases/{id}/analysis/status` → the freshness state machine:

| state | meaning |
|---|---|
| `not-analyzed` | never run |
| `up-to-date` | last run covers the current confirmed data |
| `stale` | confirmed data changed after the last run — `stale_reason` names it (e.g. "N new confirmed item(s) since last analysis") |
| `insufficient` | too little confirmed data to analyze |

Stale findings are **kept**, not deleted: `stale_findings` remain in
the API with their old `graph_version`; new runs create the current
set. The stale reason is always shown in the UI (never silent).

## 8. Audit trail

Read-only per case: `GET /cases/{id}/audit` (SUPERVISOR+ for cross-case).
Actions logged: case creation, document upload, processing completion/
failure, every review confirm/reject, graph build, analysis run,
re-analysis. Each row: actor, action, timestamp, metadata (item ids,
counts) — no secrets.

## 9. Security model

- JWT + role gates: upload/confirm/reject/build/run → INVESTIGATOR+;
  analysis → ANALYST+ (inherited).
- **Case access**: every case endpoint validates that the caller can
  access that case (owner / supervisor / admin). A different
  INVESTIGATOR gets **404** (existence not leaked); no case-level read,
  graph, analysis, copilot or audit is possible for a case that is not
  yours.
- Cross-case data isolation: no case may read or write another case's
  rows; the platform corpus case (CASE-2026-021) stays read-only to
  investigators.

## 10. Demo case (synthetic)

`CASE-DEMO-END2END-01` — the end-to-end demonstration file:

- 5 documents: `FIR.pdf`, `Investigation_Report.pdf`, `CDR.csv`,
  `Vehicle_Report.pdf`, `Location_Report.pdf`
- 17 entities (a central person, associates, vehicles, phones,
  locations), 10 confirmed relationships
- 38 evidence items, 3 timeline events, 3 locations (coordinates left
  NULL where the documents did not state them — **never fabricated**)
- 1 evidence contradiction ("Vikram Sethi — Bhiwandi Godown vs Kurla,
  15 minutes apart"), 2 hypotheses
- Labeled **SYNTHETIC DEMONSTRATION DATA** in the UI.

`CASE-DEMO-MULTILING-01` — the multilingual demonstration case (Stage 5)
remains available alongside it.

## 11. Verification

- `backend/tests/test_stage6_e2e.py` — full workflow E2E (3 tests).
- `scripts/stage6-live-smoke.py` — ~60 live-API checks across 11
  sections (fresh case, extraction, review, graph, intelligence,
  timeline, map, copilot, idempotency, STALE lifecycle, audit,
  RBAC/isolation, demo case exact counts, multilingual, empty case).
- `npm run build` + `scripts/frontend-sanity.mjs` (45 pages) green.
- Full backend suite: 383 passed / 1 skipped (no regressions).
