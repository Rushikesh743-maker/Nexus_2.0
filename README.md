# NEXUS — Frontend

**Investigation Intelligence Platform** · Builds 1–6 (foundation · dashboard · evidence · workspace · graph/map/timeline · intelligence center, copilot & demo mode)

A production-quality **frontend-only** application for criminal network analysis and investigation
intelligence: case management, evidence with chain of custody, link/network analysis, geospatial
review, timelines, an analyst insight feed and report tracking.

> **Scope.** All data is **fictional and served from mocks** — there is no backend, no database and
> no real analysis/AI integration in this build, and the UI never claims otherwise.

---

## Tech stack

| Concern            | Choice                                              |
| ------------------ | --------------------------------------------------- |
| Framework          | React 18 + Vite 5 (JavaScript, no TypeScript)        |
| Styling            | Tailwind CSS 3 (custom `navy` palette, teal accent)  |
| Routing            | React Router 6 with frontend route guards            |
| Graph              | React Flow 11 + `d3-force` (static layout)           |
| Maps               | Leaflet 1.9 + React-Leaflet 4 (OpenStreetMap tiles)  |
| Charts             | Recharts 2                                           |
| Icons              | Lucide React                                         |
| HTTP               | Axios (service layer; unused while mocks are on)     |
| Font               | Inter Variable, bundled via Fontsource (no CDN)      |

## Getting started

```bash
npm install
npm run dev        # http://localhost:5173
```

Other scripts:

```bash
npm run build      # production build to dist/
npm run preview    # serve the production build locally
```

**Demo sign-in** (mock authentication, no network involved):

| Email                              | Password     | Notes                                      |
| ---------------------------------- | ------------ | ------------------------------------------ |
| `demo-investigator@nexus.local`    | `nexus2026`  | **Development account** for the frontend demo |
| `priya.deshmukh@nexus.gov.in`      | `nexus2026`  | Fictional personnel (case lead)            |
| `arjun.patil@nexus.gov.in`         | `nexus2026`  | Fictional personnel                        |
| `sneha.joshi@nexus.gov.in`         | `nexus2026`  | Fictional personnel                        |
| `vikas.rane@nexus.gov.in`          | `nexus2026`  | Fictional personnel                        |

The login screen has a one-click **Fill demo credentials** button. Mock accounts are clearly
isolated in `src/mock/mockUsers.js` and only active while `VITE_USE_MOCK_API=true` — production
authentication is a backend identity-service concern (see `services/authService.js` API branch).

## Environment

```bash
cp .env.example .env
```

| Variable             | Default | Purpose                                          |
| -------------------- | ------- | ------------------------------------------------ |
| `VITE_USE_MOCK_API`  | `true`  | `false` → services call the Axios client instead |
| `VITE_API_BASE_URL`  | `/api`  | Base URL of the future backend REST API          |

## Architecture

```text
UI (pages, components)
   │  imports only
   ▼
services/  ──►  mock/  (current, default)
   │              · simulated latency, in-memory mutations
   └─(VITE_USE_MOCK_API=false)──►  Axios api.js  ──►  REST backend (future)
```

* **UI never touches mock data directly.** Pages import `investigationService`, `evidenceService`,
  `intelligenceService` (and `authService`) from `src/services`.
* Every service function already has its real API path written behind the mock switch, so
  replacing mocks with the backend requires **no UI changes**.
* Mock mutations (create investigation, log evidence, mark insight reviewed, request report)
  persist for the session in memory.

### Intelligence Center, copilot & demo mode (build 6)

* **NEXUS Intelligence** (`/investigations/:id/intelligence`) — Intelligence Center header
  (Evidence Confidence · Conflicting Evidence · Open Gaps · Active Hypotheses, all from
  `analysisService`) over five tabs: **Signals** (insight feed + dynamic re-evaluation
  “What changed?” panel), **Contradictions** (supporting vs contradicting comparison, confidence
  revision, “Why is this contradictory?” details, provenance chain), **Hypotheses**
  (H1/H2/H3 competing explanations with Explore details and distinguishing criteria), **Gaps**
  (impact-ranked, lawful next steps) and an **Evidence Impact Simulator** (clearly labelled
  SIMULATION — no case data is ever modified).
* **Investigation Copilot** — right-side drawer available on every case screen (header button or
  `?copilot=1`); suggested questions, source-linked answers, and a single-function service hook
  (`askCopilot`) ready to be replaced by a streaming backend API.
* **Global “Why?” system** — reusable `WhyDrawer` (finding → relationship → evidence → source
  file → original record) wired into contradictions and the network edge panel.
* **Report preview** — print-style document view (summary, findings, evidence chain, gaps) with a
  mock Export PDF action.
* **Global search** now spans investigations, entities, evidence, events, locations and
  relationships, grouped with deep links. **Notification bell** shows the mock feed with unread
  counts and mark-all-read. **Settings**: Profile · Security · Notifications · Interface ·
  Data Preferences. **Demo Mode**: topbar button starts an 11-step guided walkthrough through the
  whole product using the same components and routes.
* **Responsible-AI notice** in the app footer, Intelligence Center, copilot and report preview:
  “NEXUS provides analytical assistance and investigation leads. It does not determine guilt or
  replace investigator judgment.”

### Graph, map & timeline (build 5)

* **Network graph** (React Flow — never Leaflet for relationships): per-type node styling
  (Person / Phone / Vehicle / Location / Organization / Account + optional dashed **Evidence**
  nodes with “Mentioned In” links), spec edge vocabulary (Communicated With · Associated With ·
  Used · Visited · Transferred · Mentioned In · Connected To), and full controls — entity search,
  entity-type chips, relationship filter, activity-date filter, evidence toggle, **Expand/Hide
  connections** (controlled expansion keeps big graphs small), Reset view and Fit graph.
* **Graph analytics (neutral):** highlight chips for High-connectivity entities, Potential bridge
  entities, Cross-case connections and Potential clusters (connected components) — transparent
  structural heuristics computed in the service layer, explicitly not risk scores.
* **Node panel:** Connections / Evidence / Events / Locations tiles with View Details and View
  Evidence actions; clicking any **edge** opens “Why this connection?” with supporting vs
  contradicting evidence references (mock, deterministic) and the interactive evidence chain.
* **Leaflet map:** search, entity filter, event-type filter, activity-date filter, Show movement
  toggle (numbered dashed polylines derived from event chronology — coordinates come only from
  the mock location store) and Reset. Popups show Events / Entities / Evidence counts and
  Last recorded date.
* **Timeline:** date-range, entity, event-type and evidence-source filters; every row opens an
  Event Details modal (type, date, time, entities, location, linked evidence, View Evidence).
* **Split-screen Workspace** (`/investigations/:id/workspace`) — graph and map side by side over a
  shared timeline; node/edge/event clicks open the same shared detail surfaces. The SIH demo screen.

### Investigation workspace & entity intelligence (build 4)

* **Case header** — dynamic investigation name, `Case type • Status` line, Created date, and header
  actions: **Upload Evidence** (deep-links to the evidence logger) and **Generate Report** (opens the
  report request modal via `reports?request=1`).
* **Summary strip** — Entities · Relationships · Evidence · Events · Locations, all served by
  `investigationService` (computed from the mock stores, never hardcoded).
* **Entity Explorer** (Network tab) — search + type chips (Person / Vehicle / Phone / Location /
  Organization / Account) and cards with connections, evidence and event counts, identity
  resolution (Verified / Possible match / Unverified) and match confidence.
* **Entity details drawer** — profile with aliases, associated phones/vehicles/locations, case and
  evidence counts, plus Overview / Relationships / Evidence / Events tabs. Reachable from the
  explorer, the graph side panel, or deep links (`network?entity=<id>`,
  `evidence?evidence=<id>` auto-opens the record).
* **"Why this connection?"** — relationship panel with both endpoints, analyst confidence,
  supporting vs contradicting evidence counts and an interactive evidence chain
  (Finding → Relationship → Evidence → Source File → Original Record). **Presentation only** —
  counts are mock values from the service layer; contradiction checking and scoring are explicitly
  left to future backend services. No risk scores, predictions or guilt determination anywhere.
* **Overview dashboard** — Case summary, Recent Evidence, Recent Entities, Recent Events,
  Investigation Activity (case-scoped feed) and Important Relationships (with Why? triggers).
* Neutral entity language throughout — roles are "Subject", "Associate", "Identity holder" etc.;
  the UI presents identity *matches*, never labels people.

### Investigation creation & evidence management (build 3)

* **Create New Investigation** — Investigation Name · Case Type (Missing Person, Kidnapping, Fraud,
  Financial Crime, Cyber Crime, Theft, Other) · Description · Priority (Low→Critical), with
  optional lead/jurisdiction/tags/team in a collapsible section. Creation lands on the case page
  with the real name and Active status — nothing is hardcoded.
* **Evidence page** — status summary chips (Total Files / Processed / Processing / Needs Review /
  Failed, clickable to filter), a record table (File · Type · Size · Uploaded · Language · Status ·
  Actions) and filters for search, file type, language, status and upload date.
* **Upload flow** — drag-and-drop dropzone (PDF, DOCX, TXT, CSV, XLSX, JSON, JPG, PNG), staged
  file list, per-file progress (Uploading % → Processing "Waiting…" → Processed / Needs review /
  Failed) rendered from frontend state. Uploads go through `evidenceService.uploadFiles()` —
  the mock service simulates progress and lifecycle outcomes; set `VITE_USE_MOCK_API=false` and the
  same function posts multipart/form-data to the backend. Security note shown; no local file paths
  are ever stored or displayed.
* **Evidence details drawer** — type, language, status, size, upload date, automated-extraction
  counts (entities / events / relationships, `—` until processed) and full chain of custody, with
  View Source / Download / Delete actions (document-service actions explained honestly in the
  frontend-only build).
* **Delete** — confirmation dialog → `evidenceService.remove()` → table, chips and case stats refresh.

### Dashboard (build 2)

* Time-based greeting + one-click **New Investigation**.
* **Overview stats** — Active Investigations, Evidence Items, Entities, Pending Reviews — all
  computed by `investigationService.getDashboardStats()` from the mock stores (never hardcoded JSX).
* **Recent Investigations table** — Investigation · Case Type · Status · Last Updated ·
  Investigator · Action (Open), with a spec'd empty state.
* **Investigation cards** — name, case type, status, evidence/entity counts, last update, Open.
* **Quick actions** — Create Investigation · Upload Evidence · View Network · View Timeline
  (case-scoped ones open a case-picker modal; Upload Evidence deep-links into the evidence
  logger via `/evidence?log=1`).
* **Activity panel** — mock UI events (evidence added, entity match to review, new relationship,
  timeline updated, report generated) served by `getRecentActivity()`.
* **Global search** (top bar; overlay on mobile) — frontend filtering across investigations,
  entities and evidence via `investigationService.globalSearch()`, with grouped results,
  deep links (`/network?entity=<id>` preselects a node) and a "see all matching investigations"
  fallback.

```text
src/
├── components/
│   ├── cards/        StatCard · InvestigationCard · EntityCard
│   ├── charts/       ChartCard · StatusDonut (Recharts)
│   ├── dashboard/    QuickActions · ActivityFeed
│   ├── evidence/     Dropzone · UploadEvidenceModal · EvidenceDetailsDrawer
│   ├── evidence/     EvidenceDetailModal (chain of custody)
│   ├── graph/        NetworkGraph · EntityNode · layout (d3-force)
│   ├── intelligence/ ConfidenceMeter · InsightCard · EntityExplorer · EntityDetailsDrawer ·
│   │                 RelationshipWhyModal · EvidenceChain · WhyDrawer · ContradictionPanel ·
│   │                 HypothesisPanel · GapPanel · ImpactSimulator · ReevaluationCard · CopilotDrawer
│   ├── reports/      ReportPreviewModal
│   ├── demo/         DemoModeTour (guided 11-step walkthrough)
│   ├── layout/       AppLayout · Sidebar · Topbar · UserMenu · GlobalSearch
│   ├── map/          InvestigationMap (Leaflet + custom pins)
│   ├── modals/       Modal · ConfirmDialog · CasePickerModal · Drawer
│   ├── tables/       DataTable · Pagination
│   ├── timeline/     EventTimeline
│   └── ui/           Button · IconButton · Input · Textarea · Select · Badge · Card ·
│                     Table · Tabs · Dropdown · Toast · Tooltip · EmptyState ·
│                     LoadingState (Spinner/PageLoader/Skeleton) · ErrorState ·
│                     Breadcrumb · PageHeader · Avatar · Logo
├── context/          AuthContext · ToastContext
├── hooks/            useDocumentTitle
├── lib/              utils (cn, date formats) · constants (status/type metadata) · navigation
├── mock/             mockUsers (incl. isolated demo dev account) · mockInvestigations ·
│                     mockActivity · mockEntities · mockRelationships · mockEvidence ·
│                     mockEvents · mockLocations · mockIntelligence · mockReports ·
│                     mockUploads · mockEventLinks · mockAnalysis (intelligence templates)
├── pages/            Login · Dashboard · NotFound · settings/
│   └── investigations/  List · New · Layout (case header + tabs) · Overview · Evidence ·
│                         Network · Map · Timeline · Intelligence · Reports
├── router/           guards (ProtectedRoute · PublicOnlyRoute)
└── services/         api (Axios) · authService · investigationService ·
                      evidenceService · intelligenceService
```

## Routes

| Path                                | Guard      | Screen                                  |
| ----------------------------------- | ---------- | --------------------------------------- |
| `/login`                            | public only| Sign-in (mock auth)                     |
| `/dashboard`                        | protected  | Overview stats, recent cases, status    |
| `/investigations`                   | protected  | Caseload list (table/grid), filters     |
| `/investigations/new`               | protected  | Create investigation                    |
| `/investigations/:id`               | protected  | Case overview                           |
| `/investigations/:id/evidence`      | protected  | Evidence log + chain of custody         |
| `/investigations/:id/network`       | protected  | Entity/relationship graph               |
| `/investigations/:id/map`           | protected  | Location map                            |
| `/investigations/:id/timeline`      | protected  | Event timeline                          |
| `/investigations/:id/intelligence`  | protected  | Analyst insight feed (mock)             |
| `/investigations/:id/reports`       | protected  | Report requests                         |
| `/settings`                         | protected  | Profile · Security · Preferences · Data |
| `*`                                 | —          | 404                                     |

Unauthenticated users are redirected to `/login` (and returned to their destination after
signing in). The sidebar's **Case workspace** section (evidence/network/map/timeline/…) appears
contextually while an investigation is open, matching the investigation-scoped routes.

## Design system

* Light theme: `slate-50` canvas, white cards, **dark navy** text (`navy` scale), **teal** accent.
* Semantic states only: success / warning / danger / info / neutral (+ teal emphasis).
* Subtle borders, small shadows, rounded-professional cards, dense but uncluttered tables.
* Status/type metadata (labels, colors, icons) lives in `src/lib/constants.js` and is reused by
  badges, graph edges, map pins and timeline markers.
* The collapsible sidebar state and preferences persist to `localStorage`.

## Swapping mocks for a real backend

1. Implement the REST endpoints that mirror the service functions
   (`/auth/*`, `/investigations`, `/investigations/:id`, `/investigations/:id/evidence`,
   `/entities`, `/relationships`, `/events`, `/locations`, `/insights`, `/reports`).
2. Set `VITE_USE_MOCK_API=false` and `VITE_API_BASE_URL`.
3. Errors arrive in UI code normalised as `{ message, status, isAuthError }` — hook a global
   401 handler in `services/api.js` when the identity service exists.

## Known limitations (foundation scope)

* Dashboard analytics widgets are intentionally deferred — the dashboard shows stats and recent
  cases only.
* Evidence file upload/preview, report downloads and live insight generation are backend concerns;
  the UI is honest about this (toasts/labels) rather than faking results.
* Map street tiles need internet access; offline (e.g. sandboxed previews) show an inline notice
  while markers still render.
* No automated tests or ESLint yet — recommended next milestone alongside dashboard features.
* Demo users/password are hardcoded mocks by design; replace via the identity service.
