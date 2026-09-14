# NEXUS — Phase 2 Plan: Investigation Intelligence Upgrade

Status: in progress. Baseline: Stage 6/7 + Phase 1 (411 passed / 2 skipped).
Rule: in-place upgrades on the existing platform; no engine rewrites;
confirmed-data principle and candidate-by-default preserved.

## What already exists (inspected, not rebuilt)
- Versioned analysis runs (`CaseAnalysisRun`) + freshness state machine
  (not-analyzed / up-to-date / stale+reason / insufficient) + preserved
  stale findings + recalculate endpoint. (case_analysis.py)
- Findings carry `involved_entity_ids`, `supporting_relationship_ids`,
  `supporting_evidence_ids` (+ graph_version, review state).
- Graph intelligence: findings / metrics / bridges / clusters / cross-case /
  paths — all on confirmed data.
- Case workspace with 17 tabs; `?entity=` / `?evidence=` / `?location=` /
  `?relationship=` deep links across Graph/Timeline/Map/Evidence.
- Entity resolution: deterministic, explainable name scoring (exact,
  cross-script transliteration, initials, near-phonetic, token overlap) —
  one best suggestion per candidate, no contextual signals.
- Copilot: case-scoped, confirmed-only context, deterministic core +
  validated optional Gemini prose, citations, audit, honest "not found".
- Audit trail: uploads, processing, confirm/reject (item ids), graph
  build, analysis runs, case close.

## Work items
- **P2-A** Alembic migration `0002` (multi match-suggestions + rank;
  `case_snapshot` table) + **ranked multi-suggestion entity resolution**
  with contextual signals (shared phone / vehicle / account / location),
  reason strings per the spec example. Suggestions only — never auto-merge.
- **P2-B** **Evidence-first findings**: `GET /cases/{id}/findings/{fid}`
  resolves the full chain finding → entities → relationships → evidence
  (with source document + page/row) → claims. Findings list carries a
  compact evidence summary; findings with no resolvable evidence say so.
  Frontend: findings drawer shows the chain with deep links.
- **P2-C** **Entity profile / graph focus**:
  `GET /cases/{id}/entities/{eid}` → entity + connections (with per-edge
  evidence) + timeline events + locations + involved findings + metrics
  (degree/betweenness/bridge) + time span from claims. Feeds graph focus,
  Entities tab, and cross-mode links.
- **P2-D** **Case snapshots/versions**: immutable snapshots of confirmed
  data (entities/relationships/evidence/findings/hypotheses/gaps/locations)
  + graph_version; create on demand (audited) + list + compare
  (new / removed / changed entities & relationships, new evidence,
  changed findings/hypotheses/gaps). No mutation or deletion endpoints.
- **P2-E** **State on every intelligence surface**: graph, metrics,
  bridges, clusters, paths, findings, hypotheses, gaps, timeline,
  geospatial, copilot context all report `analysis_state` +
  `graph_version` (UP-TO-DATE / STALE / NOT-ANALYZED / INSUFFICIENT) so
  stale analysis is never displayed as current.
- **P2-F** **Copilot hardening**: new evidence-grounded intent
  ("what is the evidence for X?" → cited evidence rows only); explicit
  "no information in the confirmed case data" answers; candidate data
  discussed only when the question explicitly asks for it.
- **P2-G** **Frontend: connected investigation modes** — case-level focus
  context (selected entity survives mode switches), entity focus panel
  with "View in Timeline / Map / Evidence / Graph", findings evidence
  chain, ranked match suggestions in Review, stale badges on all
  intelligence tabs, snapshots view (list + compare).
- **P2-H** **Audit trail completion**: verify + add events for analysis
  executed (per surface), hypothesis changed, report generated, snapshot
  created — actor/timestamp/case/action/object on every row.
- **P2-I** **Hybrid extraction documentation/verification**: rule +
  regex + multilingual + optional validated LLM, all candidate-only;
  `processing_method` reports the real combination. (Verification +
  tests; no fake NLP.)
- **P2-J** **Tests + close**: new `test_phase2_intelligence.py` (provenance
  chain, ranked resolution + reasons, confirmation workflow → staleness,
  recalculation, snapshots + compare + immutability, entity profile,
  copilot grounding + missing-info honesty, audit events, the full
  acceptance workflow) + complete suite + `npm run build` + report.
