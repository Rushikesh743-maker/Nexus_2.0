# NEXUS — Codebase Audit Report (2026-09-07)

Scope: full-repository audit + repair to a runnable state. No features removed,
no working logic replaced by placeholders.

## 1. Project architecture

```
Browser (React SPA)
 │  React 18 + Vite 5 + React Router 6 + Tailwind 3
 │  React Flow (graphs) · D3-force (layout) · Leaflet (maps) · Recharts (charts)
 │
 ├─ UI pages/components (src/pages, src/components)
 │     imports only from src/services
 ▼
Service layer (src/services)
 │  authService · investigationService · evidenceService
 │  intelligenceService · analysisService          ← mock branch (default)
 │     ⇢ src/mock/* (in-memory, simulated latency)
 │     ⇢ Axios api.js → REST /api/*                ← API branch (future NEXUS backend,
 │                                                    VITE_USE_MOCK_API=false)
 │  cnaService                                     ← real backend client, no mock:
 │     ⇢ /cna-api → (Vite dev proxy) → FastAPI :8000 /api/*
 │  extraction/ (extractor, gazetteer, ingest)    ← browser-side PDF/CSV/RTF/text
 │                                                    entity/event/location pipeline
 ▼
FastAPI backend (backend/app)
 │  auth.py     — RBAC (investigator/admin), hash-chained audit log,
 │                optional AES-256-GCM at rest (CNAS_AUDIT_KEY)
 │  main.py     — 36 routes; every case-data route: check permission → audit → answer
 ▼
Analysis pipeline (backend/app/pipeline)
 │  ingest → extract (rule+gazetteer NER) → translit (Devanagari) →
 │  resolve (cross-source identity) → graph (NetworkX)
 ▼
Analytics & intelligence
 │  graph/analytics (PageRank, betweenness, communities, Shapley attribution)
 │  graph/anomaly (8 detectors) · intelligence/ (contradiction engine,
 │  impact simulator, observations, scoring) · nlq (intent parser)
 ▼
Integrations & output
 │  integrations/ (CCTNS + ICJS adapters, authorisation-gated)
 │  report + pdf_report (markdown + reportlab PDFs) · graph/store (Cypher/JSON export)
 ▼
Storage (all local files)
 │  data/raw/*.csv|json — five synthetic source systems + scanned FIR images
 │  backend/audit_log.jsonl — hash-chained audit trail
 └  docs/demo + public/demo — NEX-2026-120 demo case bundle (PDF + tower CSV)
```

Dependency map: Frontend → Services → (mock store | /api REST | /cna-api) →
FastAPI modules → pipeline → data/raw + audit_log.jsonl.

## 2. Existing working features (verified live)

Backend (all endpoints probed, all pass; 56/56 pytest; scripts/verify.py 100%):
- Multi-source ingestion (FIR, CDR, transactions, criminal records, surveillance,
  social, scanned FIRs via OCR when tesseract present), rule+gazetteer extraction
  with Devanagari transliteration, cross-source entity resolution (alias merges,
  burner attribution, anti-fusion negative test)
- Network graph + analytics: influence ranking with per-component Shapley
  attribution, community detection, multi-hop path tracing, corroboration levels
- Anomaly detection: 8 detector types (burner, circular funds, structuring,
  insulated actor, clean-skin bridge, comm burst, co-location, custody conflict)
- Contradiction engine + evidence impact simulator (counterfactual re-run, diffed)
- Natural-language query parser (7 intents, restated interpretation)
- Case intake (schema-driven quick-add + file upload, pipeline re-run),
  report builder (markdown + reportlab PDFs), Cypher/JSON export
- CCTNS/ICJS adapters (authorisation-gated preview), legacy console at /legacy
- Security: RBAC (403 for admin-only routes, 401 for bad tokens), phone/account
  redaction for roles without entity:read, tamper-evident audit chain
  (tamper test passes), optional AES-256-GCM at rest

Frontend (builds; dev server verified; API proxied; demo bundle ingested):
- Auth (mock), dashboard, investigations CRUD, evidence upload + browser-side
  extraction (PDF via pdf.js, CSV, RTF, text) for the NEX-2026-120 demo case,
  network graph, map, timeline, intelligence center (gaps, hypotheses,
  re-evaluation), entity explorer, reports
- Analysis section (live backend, no mocks): graph, map, key people, patterns,
  conflicts, link analysis, pipeline transparency, OCR status, ask/copilot,
  system view — all wired to /cna-api and verified 200 through the proxy

## 3. Existing partially implemented features

- NEXUS platform REST backend (auth/investigations/evidence/insights endpoints):
  every service function has its API-mode branch written, but no backend serves
  them yet → app runs in mock mode by design (VITE_USE_MOCK_API=true default)
- OCR of scanned FIRs: full code path + scanner (data/make_scans.py) present;
  inactive here because the tesseract binary is not installed (degrades
  honestly, verified)
- LLM summariser: interface + guard rails (hallucinated-name check) implemented;
  falls back to template summariser when no LLM key is configured
- Neo4j: Cypher export verified; live-cluster write not exercised
- spaCy NER: optional; rule extractor is the active path
- Dashboard analytics widgets: intentionally deferred (documented in README)

## 4. Missing features (never implemented)

- The NEXUS REST backend itself (the /api/* the mock switch targets)
- Frontend automated tests / ESLint (README lists this as next milestone)
- Real identity provider (demo static tokens by design)

## 5. Errors found

1. `data/raw/` corpus missing — the entire backend pipeline had no input
   (generated artifact, gitignored by design).
2. `docs/demo/case_bundle.txt` missing — the text source for the committed
   demo PDF. Broke `npm run demo:case` (ENOENT) and `scripts/dev/testIngest.mjs`
   (which also reads it).
3. `scripts/generateDemoCase.mjs` footer loop buggy: with default pdfkit
   settings only the last buffered page is addressable, the footer y was below
   the bottom margin (forcing a page break), and the total count came from the
   buffer range. Result baked into the committed PDF: no footer on pages 1–2,
   a stray near-empty page 3 carrying "page 2 of 1".
4. `data/raw/scans/` missing (optional scanned-FIR images).
5. `dist/` missing (production build).
6. `docs/demo/Untitled.rtf` — stray macOS text-editor note, referenced nowhere.
7. Dead UI components: `src/components/charts/ChartCard.jsx`,
   `src/components/charts/StatusDonut.jsx` — exported but imported nowhere.
8. `package-lock.json` out of sync with `package.json` (pdfkit listed under
   runtime deps in the lockfile, devDependency in package.json).
9. Deprecation warnings (not errors): FastAPI `on_event` in backend/app/main.py.

## 6. Errors fixed

1. Regenerated the corpus with the project's own seeded generator
   (`python3 data/generator.py`, SEED=26189). Verified reproducible: two runs
   produce byte-identical files (md5). No data fabricated by hand.
2. Reconstructed `docs/demo/case_bundle.txt` from the committed PDF's text layer
   (the PDF is a plain text-layer document generated from this file). Verified
   by regeneration: 106/106 content lines identical, cover block and skip
   semantics of the renderer match exactly.
3. Fixed the footer pass: `bufferPages: true` (keeps every page addressable
   until `doc.end()`) + footer y moved just above the bottom margin (no more
   forced page break). Regenerated PDF: 2 pages, "page 1 of 2" / "page 2 of 2"
   on both pages, zero content drift. Copied to `public/demo/` (kept in sync via
   the `demo:case` script).
4. Rendered the optional scans with `python3 data/make_scans.py` (Pillow present;
   tesseract absent → pipeline still reports OCR as gracefully unavailable,
   verified: verify.py "OCR degrades gracefully" passes).
5. `npm run build` → fresh `dist/`, verified served by FastAPI in prod mode.
6. `npm install` re-synced the lockfile (pdfkit → devDependencies, matching
   package.json).

Not "fixed" (left as-is, reported): #6 stray RTF, #7 dead components (removing
them would delete existing code; they compile and are harmless), #9 warnings.

## 7. Files changed

| File | Change |
|---|---|
| `docs/demo/case_bundle.txt` | NEW — reconstructed generator source (verified against the committed PDF) |
| `scripts/generateDemoCase.mjs` | footer pass: `bufferPages: true` + safe footer y (bug fix) |
| `docs/demo/NEXUS_demo_case_missing_person.pdf` | regenerated (content-identical, correct footers, 2 pages) |
| `public/demo/NEXUS_demo_case_missing_person.pdf` | regenerated copy (in sync with docs/) |
| `package-lock.json` | lockfile synced with package.json by npm install |

Generated (gitignored, not source): `data/raw/*` (incl. `scans/`), `dist/`,
`node_modules/`, `backend/audit_log.jsonl` (runtime audit trail).

## 8. Commands used to verify

```bash
# Frontend
npm install
npm run build                                   # ✓ 12s, only chunk-size warning
npm run dev                                     # :5173, /cna-api proxy verified 200
npm run demo:case                               # ✓ regenerate + copy demo PDF

# Backend
python -m pip install -r backend/requirements.txt
python backend/run.py                           # :8000, 36 routes probed 200/403/401
python -m pytest backend/tests/                 # ✓ 56 passed
python scripts/verify.py                        # ✓ All checks passed (incl. reproducibility
                                                #   across 3 separate processes)

# Frontend pipeline dev scripts (Node ESM loader)
node --import ./scripts/dev/register.mjs scripts/dev/testPdfRoundtrip.mjs \
    docs/demo/NEXUS_demo_case_missing_person.pdf   # ✓ 15 events, 5 places, 7 persons
node --import ./scripts/dev/register.mjs scripts/dev/testExtract.mjs \
    docs/demo/case_bundle.txt                     # ✓ 23 entities
node --import ./scripts/dev/register.mjs scripts/dev/testIngest.mjs  # ✓ full pipeline

# Data
python3 data/generator.py && python3 data/generator.py   # md5-identical (reproducible)
python3 data/make_scans.py                              # ✓ 2 scanned FIR images

# Cross-checks
curl probes: /api/* (me, stats, graph, entities, influencers, communities,
findings, corroboration, contradictions, contradiction detail, impact
(source_id + record_id), query, pipeline, ocr, report/overview, security,
integrations, integrations preview, case/schema, audit, path, path.pdf,
report/overview.pdf, export/cypher, /legacy, /, SPA deep route)
```

## 9. Remaining limitations

- **tesseract not installed** → OCR of the two paper-only FIRs inactive on this
  machine (the System view and API report this honestly; install:
  `apt-get install tesseract-ocr tesseract-ocr-hin` per backend docs).
- **Demo security model by design**: static demo tokens (`demo-investigator`,
  `demo-admin`), missing token defaults to the low-privilege investigator,
  CORS `allow_origins=["*"]`, audit log plaintext unless `CNAS_AUDIT_KEY` is
  set. Fine for a local demo; must be replaced (agency IdP, strict CORS, WORM
  storage) before any real deployment.
- **NEXUS platform services are mock-backed** (default `VITE_USE_MOCK_API=true`);
  the REST backend they would call does not exist yet. The analysis section is
  the only live-backed part.
- Map street tiles need internet access (markers still render offline).
- Rule-based extractor is tuned to the synthetic corpus (documented; spaCy
  interface in place for a trained NER).
- FastAPI `on_event` deprecation warning (works; lifespan handlers are the
  modern API).
- Two unused chart components (ChartCard, StatusDonut) and one stray file
  (docs/demo/Untitled.rtf) remain in the tree.
- `run.py` binds 127.0.0.1 — correct for local dev; a reverse proxy fronts it
  in the sandbox preview (Vite dev on :5173 proxies `/cna-api`).
