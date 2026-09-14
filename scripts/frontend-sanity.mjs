/**
 * Frontend sanity check — SSR-renders the key pages through Vite's SSR
 * module loader (same aliases/transforms as the build) and fails on any
 * render error. No headless browser is available in this environment, so
 * this is the closest executable substitute: it executes every module in
 * the page trees, resolves every import, and renders the component code.
 *
 * Data branches use a seeded case context (same shape as GET /api/v1/cases/{id});
 * pages that fetch in effects render their loading branch (effects do not
 * run under SSR — that is expected and asserted where it matters).
 *
 * Run: npm run test:frontend-sanity
 */
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const SAMPLE_CASE = {
  id: 1,
  case_number: 'CASE-2026-001',
  title: 'Unauthorised vehicle movement — Pune ring road',
  status: 'ACTIVE',
  priority: 'HIGH',
  description: 'Synthetic demonstration case.',
  is_synthetic: true,
  created_at: '2026-06-10T09:00:00Z',
  updated_at: '2026-06-12T09:00:00Z',
  created_by_name: 'Demo Investigator',
  counts: {
    documents: 2, entities: 7, relationships: 5, evidence: 3, timeline_events: 3,
    locations: 3, hypotheses: 1, contradictions: 1, gaps: 1, simulations: 3,
  },
  key_entities: [
    { id: 1, canonical_name: 'Aarav Mehta', type: 'person', aliases: ['A. Mehta'], connection_count: 4, metadata: null },
    { id: 2, canonical_name: 'MH12AB1234', type: 'vehicle', aliases: [], connection_count: 3, metadata: null },
  ],
  cross_case_links: [
    { case_id: 2, case_number: 'CASE-2026-002', title: 'Fraud network — Industrial Area', status: 'ACTIVE', shared_entities: ['Aarav Mehta'], shared_count: 1 },
  ],
  latest_events: [
    { id: 1, event_type: 'sighting', timestamp: '2026-06-11T14:30:00Z', description: 'Vehicle sighted near Pune Central.' },
  ],
};

const SERVER = await createServer({
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'error',
});

const load = (p) => SERVER.ssrLoadModule(p);
const { ThemeProvider } = await load('/src/context/ThemeContext.jsx');
const { ToastProvider } = await load('/src/context/ToastContext.jsx');

const { CasesPage } = await load('/src/pages/cases/CasesPage.jsx');
const { CaseLayout, CaseFileContext } = await load('/src/pages/cases/CaseLayout.jsx');
const { CaseOverviewPage } = await load('/src/pages/cases/CaseOverviewPage.jsx');
const { CaseGraphPage } = await load('/src/pages/cases/CaseGraphPage.jsx');
const { CaseEvidencePage } = await load('/src/pages/cases/CaseEvidencePage.jsx');
const { CaseTimelinePage } = await load('/src/pages/cases/CaseTimelinePage.jsx');
const { CaseHypothesesPage, CaseContradictionsPage, CaseGapsPage } = await load('/src/pages/cases/CaseRecordPages.jsx');
const { CaseSimulationPage } = await load('/src/pages/cases/CaseSimulationPage.jsx');
const { CopilotPage } = await load('/src/pages/cases/CopilotPage.jsx');
const { LoginPage } = await load('/src/pages/LoginPage.jsx');
const { InvestigationIntelligencePage } = await load('/src/pages/cases/InvestigationIntelligencePage.jsx');
const {
  InvestigationStatusPanel, StatusBody, PanelBody,
  InvestigationContradictionsPanel, ContradictionsBody,
  InvestigationHypothesesPanel, HypothesesBody, HypothesisItem,
  InvestigationEvidenceImpactPanel, EvidenceImpactBody,
  InvestigationTimelinePanel, TimelineBody,
  InvestigationGeospatialPanel, GeospatialBody,
  InvestigationGapsPanel, GapsBody,
} = await load('/src/components/cases/InvestigationPanels.jsx');
const { GraphFindingsPanel, FindingsBody } = await load('/src/components/cases/GraphFindingsPanel.jsx');
const { PathExplorer, PathResult } = await load('/src/components/cases/PathExplorer.jsx');
const { BridgePanel, BridgeList, ClusterPanel, ClusterList, CrossCasePanel, CrossCaseList } = await load('/src/components/cases/GraphIntelPanels.jsx');

// Synthetic stage-3 data for the presentational branches (mirrors the
// backend's response shapes; nothing fetched under SSR).
const SAMPLE_FINDING = {
  id: 101, case_id: 1, finding_type: 'CROSS_CASE_CONNECTION',
  title: 'Cross-case link: CASE-2026-001 ↔ CASE-2026-002 (7 shared confirmed entities)',
  summary: 'CASE-2026-001 and CASE-2026-002 share 7 confirmed entities.',
  explanation: [
    'CASE-2026-001 and CASE-2026-002 share 7 confirmed entities: Aarav Mehta (person), Kabir Shah (person), …',
    'A confirmed path connects them: Aarav Mehta → Rohan Deshmukh → Aarav Mehta [shared].',
  ],
  details: {}, involved_entity_ids: [1, 2], supporting_relationship_ids: [1],
  supporting_evidence_ids: [], related_case_ids: [2],
  analysis_method: 'shared-identity v1 (confirmed entities matched by entity type + normalized name across cases)',
  graph_version: 'abc123def4567890', stale: false, status: 'ACTIVE',
  reviewed_by_name: null, reviewed_at: null, review_note: null,
  created_at: '2026-09-07T00:00:00Z',
};
const SAMPLE_PATH = {
  path_length: 2,
  nodes: [
    { entity_id: 7, name: 'MH14CD5678', entity_type: 'vehicle' },
    { entity_id: 2, name: 'Rohan Deshmukh', entity_type: 'person' },
    { entity_id: 1, name: 'Aarav Mehta', entity_type: 'person' },
  ],
  relationship_types: ['USED', 'CALLED'], relationship_ids: [3, 2], evidence_count: 1,
  explanation: 'MH14CD5678 is indirectly connected to Aarav Mehta through Rohan Deshmukh (2 hops)',
};
const SAMPLE_BRIDGE = {
  entity_id: 1, name: 'Aarav Mehta', entity_type: 'person', degree: 2,
  is_articulation_point: true, betweenness: 1, connectivity_impact: 2,
  cross_case_reach: 3, bridge_score: 1,
  reasons: [
    'Removing this entity increases the graph\'s connected components from 2 to 4 (it is an articulation point).',
    'It has 2 direct confirmed connections.',
  ],
};
const SAMPLE_CLUSTER = {
  index: 1, node_ids: ['e1', 'e2'], members: ['Aarav Mehta', 'Rohan Deshmukh'],
  entity_ids: [1, 2], entity_count: 4, relationship_count: 3,
  type_breakdown: { person: 2, vehicle: 2 }, case_ids: [1], cross_case: false,
  key_bridge: { display_name: 'Aarav Mehta', bridge_score: 1 }, subgroups: null,
  description: '4 confirmed entities and 3 confirmed relationships form one connected group of the confirmed graph (within a single case).',
};
const SAMPLE_CONNECTION = {
  case_id: 2, case_number: 'CASE-2026-002', connection_kind: 'shared_path',
  shared_entities: [{ name: 'Aarav Mehta', entity_type: 'person', entity_ids: [1] }],
  example_path: [
    { name: 'Aarav Mehta', entity_type: 'person', case_id: 1, node_id: 'm1' },
    { name: 'Shared Person', entity_type: 'person', case_id: null, node_id: 'm2', shared: true },
    { name: 'Person Eight', entity_type: 'person', case_id: 2, node_id: 'm3' },
  ],
  example_path_relationships: ['CALLED', 'CALLED'], evidence_count: 2,
  explanation: 'CASE-2026-001 and CASE-2026-002 share 1 confirmed entity: Aarav Mehta.',
};
const noop = () => {};
const { AuthProvider } = await load('/src/context/AuthContext.jsx');
const { Sidebar } = await load('/src/components/layout/Sidebar.jsx');
const { Topbar } = await load('/src/components/layout/Topbar.jsx');
const { NetworkGraph } = await load('/src/components/graph/NetworkGraph.jsx');

// ------------------------------------------------------------------ stage 4
// Synthetic stage-4 data for the presentational branches (mirrors the
// backend response shapes; nothing fetched under SSR).
const SAMPLE_STATUS_CURRENT = {
  case_id: 1, state: 'up-to-date', graph_version: '2487256b49fac5df',
  analyzed: true, reason: '9 finding(s) for the current confirmed-data snapshot 2487256b49fac5df.',
  current_findings: 9, stale_findings: 0, hypotheses: 6, insufficient: false,
  timeline: { events_total: 25, events_with_timestamp: 25, events_without_timestamp: 0 },
  geospatial: { locations_total: 11, locations_with_coords: 11 },
};
const SAMPLE_CONTRADICTION = {
  id: 201, case_id: 1, finding_type: 'CONTRADICTION',
  title: 'Potential timeline contradiction: Aarav Mehta',
  summary: 'Confirmed records place Aarav Mehta at Pune Central and CSMT Mumbai 20 min apart — shorter than the 71 min minimum travel time at 100 km/h.',
  explanation: [
    'Event 33 records Aarav Mehta at Pune Central at 2026-06-10T09:00:00.',
    'Event 34 records Aarav Mehta at CSMT Mumbai at 2026-06-10T09:20:00.',
    'Distance Pune Central ↔ CSMT Mumbai: 118.6 km (haversine); minimum travel time at the documented 100 km/h assumption: 71 min.',
    'Potential timeline contradiction — the records are not asserted to be false.',
  ],
  details: { contradiction_type: 'TIMELINE_CONTRADICTION', severity: 'HIGH', distance_km: 118.6, time_difference_min: 20 },
  involved_entity_ids: [1], supporting_relationship_ids: [], supporting_evidence_ids: [12],
  related_case_ids: [], analysis_method: 'contradiction-engine v1',
  graph_version: '2487256b49fac5df', stale: false, status: 'ACTIVE',
  reviewed_by_name: null, reviewed_at: null, review_note: null,
  created_at: '2026-09-07T00:00:00Z',
};
const SAMPLE_GAP_FINDING = {
  id: 202, case_id: 1, finding_type: 'INVESTIGATION_GAP',
  title: 'Potential investigation gap: Aarav Mehta',
  summary: 'Aarav Mehta (person) is confirmed in 3 relationships with no recorded aliases or identifying attributes.',
  explanation: ['Participates in 3 confirmed relationships.', 'Recorded aliases: none.', 'The confirmed record identifies this person by name alone.'],
  details: { gap_type: 'IDENTITY_GAP', degree: 3 },
  involved_entity_ids: [1], supporting_relationship_ids: [1, 2, 3], supporting_evidence_ids: [],
  related_case_ids: [], analysis_method: 'investigation-gap v1',
  graph_version: '2487256b49fac5df', stale: true, status: 'ACTIVE',
  reviewed_by_name: null, reviewed_at: null, review_note: null,
  created_at: '2026-09-07T00:00:00Z',
};
const SAMPLE_HYPOTHESIS = {
  id: 301, case_id: 1,
  title: 'Explanations for the apparent conflict (record accuracy)',
  description: 'At least one of the involved confirmed records may be inaccurate or misattributed.',
  hypothesis_type: 'GENERATED_CONTRADICTION',
  involved_entity_ids: [1], supporting_relationship_ids: [],
  supporting_evidence_ids: [12, 13], contradicting_evidence_ids: [],
  supporting_finding_ids: [], contradiction_ids: [201],
  analytical_score: 0.38, confidence_band: 'MEDIUM',
  score_components: { supporting_evidence: 2, contradicting_evidence: 0, supporting_relationships: 0, contradicting_signals: 0, involved_entities: 1, factor_values: {} },
  explanation: [
    'Analytical score: 0.38 (band MEDIUM).',
    '+ 2 directly linked evidence record(s)',
    '~ assumption-consistency factor 0.75',
    'This score represents analytical support, not probability or proof.',
  ],
  analysis_method: 'hypothesis-score v1',
  graph_version: '2487256b49fac5df', stale: false, status: 'ACTIVE',
  reviewed_by_name: null, reviewed_at: null, review_note: null,
  created_at: '2026-09-07T00:00:00Z', updated_at: '2026-09-07T00:00:00Z',
};
const SAMPLE_IMPACT = {
  evidence_count: 3, distribution: { HIGH: 0, MEDIUM: 1, LOW: 2 }, top_evidence: null,
  evidence_impacts: [
    { evidence_id: 12, linked_entities: [{ id: 1, name: 'Aarav Mehta' }], linked_relationships: [1],
      linked_timeline_events: [33], referenced_by_findings: [201], referenced_by_hypotheses: [301],
      impact_score: 0.35, impact_band: 'MEDIUM', impact_role: 'structural support via 1 confirmed relationship(s)',
      score_components: {}, explanation: [] },
    { evidence_id: 15, linked_entities: [], linked_relationships: [], linked_timeline_events: [],
      referenced_by_findings: [], referenced_by_hypotheses: [],
      impact_score: 0.0, impact_band: 'LOW', impact_role: 'standalone record (no direct analytical linkage)',
      score_components: {}, explanation: [] },
  ],
  analysis_method: 'evidence-impact v1',
};
const SAMPLE_SIMULATION = {
  evidence_id: 12, simulation_only: true,
  message: 'Simulation only — the stored evidence record was not modified, deleted, or re-analyzed.',
  edges_removed: [{ edge: ['e1', 'e2'], relationships: [1], rule: 'sole-provenance: every relationship of this pair is proven only by the simulated-evidence record' }],
  newly_isolated_entities: [{ node: 'e2', name: 'Rohan Deshmukh' }],
  metrics_before: {}, metrics_after: {},
  diff: { components_before: 1, components_after: 2, largest_component_before: 4, largest_component_after: 3,
          degree_changes: [], betweenness_changes: [], newly_disconnected_pairs: [['e1', 'e2']] },
  affected_findings: [201], analysis_method: 'evidence-simulation v1',
};
const SAMPLE_TIMELINE = {
  case_id: 1,
  results: [
    { timeline_type: 'EVENT_OVERLAP', title: 'Concurrent records',
      summary: 'Two confirmed records share the same recorded timestamp; neither carries entity attribution.',
      explanation: ['Event 15 (fir) at 2026-05-03T08:00:00.', 'Event 26 (surveillance) at 2026-05-03T08:00:00.'],
      event_ids: [15, 26], entity_ids: [], interval_minutes: 0, details: {} },
    { timeline_type: 'TIMELINE_GAP', title: 'Potential investigation gap',
      summary: 'No confirmed activity recorded between 2026-04-01 09:00 (event 3) and 2026-04-03 09:30 (event 4) — a 1.0 day gap.',
      explanation: ['Gap of 48.5 h exceeds the documented 12 h threshold.', 'This is a potential investigation gap — it describes coverage of the confirmed record, not suspicious activity.'],
      event_ids: [3, 4], entity_ids: [1], interval_minutes: 2910, details: {} },
  ],
  events_total: 25, events_with_timestamp: 25, events_without_timestamp: 0,
  insufficient: false, analysis_method: 'timeline-analysis v1',
};
const SAMPLE_GEO = {
  case_id: 1,
  results: [
    { geo_type: 'CO_LOCATION', title: 'Potential co-location: Pune Central Station',
      summary: '3 confirmed entities are recorded at Pune Central Station.',
      explanation: ['No timestamps are recorded on these observations, so no temporal relationship can be assessed.', 'Potential co-location — co-presence in the confirmed record only; no meeting or contact is implied.'],
      entity_ids: [1, 2, 6], event_ids: [33], relationship_ids: [5], location_ids: [1],
      distance_km: 0, time_difference_minutes: null, threshold: '< 0.05 km (same location)', details: {} },
  ],
  observations: [
    { entity_id: 1, entity_name: 'Aarav Mehta', location_id: 1, location_name: 'Pune Central Station',
      latitude: 18.5286, longitude: 73.8744, timestamp: '2026-06-10T09:00:00',
      source_event_id: 33, source_relationship_id: null },
  ],
  observations_count: 1, location_data_insufficient: false,
  analysis_method: 'geospatial-analysis v1',
};
const SAMPLE_GEO_INSUFFICIENT = {
  ...SAMPLE_GEO, results: [], observations: [], observations_count: 0,
  location_data_insufficient: true,
};
const INVESTIGATION_PANEL_PROPS = { caseId: 1, reloadKey: 0, analyzed: false, insufficient: false, onHighlight: noop };

const h = React.createElement;
const wrap = (node) =>
  h(ThemeProvider, null,
    h(AuthProvider, null,
      h(ToastProvider, null,
        h(MemoryRouter, { initialEntries: ['/cases'] }, node))));

const cases = [
  ['LoginPage (public)', h(AuthProvider, null, h(wrap, h(LoginPage)))],
  ['Sidebar (nav shell)', h(wrap, h(Sidebar, { collapsed: false, onToggleCollapse: () => {}, mobileOpen: false, onCloseMobile: () => {} }))],
  ['Topbar (breadcrumb shell)', h(wrap, h(Topbar, { onMenu: () => {} }))],
  ['CasesPage (loading branch — no effects under SSR)', h(wrap, h(CasesPage))],
  ['CaseLayout (loading branch)', h(wrap, h(CaseLayout))],
  ['CaseOverviewPage (seeded data branch)', h(wrap, h(CaseFileContext.Provider, { value: { caseFile: SAMPLE_CASE, caseId: '1', reload: () => {} } }, h(CaseOverviewPage)))],
  ['CaseGraphPage (loading branch)', h(wrap, h(CaseFileContext.Provider, { value: { caseFile: SAMPLE_CASE, caseId: '1', reload: () => {} } }, h(CaseGraphPage)))],
  ['CaseEvidencePage (loading branch)', h(wrap, h(CaseFileContext.Provider, { value: { caseFile: SAMPLE_CASE, caseId: '1', reload: () => {} } }, h(CaseEvidencePage)))],
  ['CaseTimelinePage (loading branch)', h(wrap, h(CaseFileContext.Provider, { value: { caseFile: SAMPLE_CASE, caseId: '1', reload: () => {} } }, h(CaseTimelinePage)))],
  ['CaseHypothesesPage (loading branch)', h(wrap, h(CaseFileContext.Provider, { value: { caseFile: SAMPLE_CASE, caseId: '1', reload: () => {} } }, h(CaseHypothesesPage)))],
  ['CaseContradictionsPage (loading branch)', h(wrap, h(CaseFileContext.Provider, { value: { caseFile: SAMPLE_CASE, caseId: '1', reload: () => {} } }, h(CaseContradictionsPage)))],
  ['CaseGapsPage (loading branch)', h(wrap, h(CaseFileContext.Provider, { value: { caseFile: SAMPLE_CASE, caseId: '1', reload: () => {} } }, h(CaseGapsPage)))],
  ['CaseSimulationPage (loading branch)', h(wrap, h(CaseFileContext.Provider, { value: { caseFile: SAMPLE_CASE, caseId: '1', reload: () => {} } }, h(CaseSimulationPage)))],
  ['CopilotPage (loading branch)', h(wrap, h(CopilotPage))],
  // stage 3: graph intelligence
  ['GraphFindingsPanel (loading branch)', h(wrap, h(GraphFindingsPanel, { caseId: 1, onHighlight: noop }))],
  ['FindingsBody (not analyzed / insufficient data state)', h(FindingsBody, { loading: false, data: null, error: null, onRetry: noop, analyzed: false, onHighlight: noop, onToast: noop, onChanged: noop })],
  ['FindingsBody (findings render)', h(FindingsBody, { loading: false, data: { current_findings: [SAMPLE_FINDING], stale_findings: [] }, error: null, onRetry: noop, analyzed: true, onHighlight: noop, onToast: noop, onChanged: noop })],
  ['FindingsBody (error state)', h(FindingsBody, { loading: false, data: null, error: { message: 'The platform backend is not reachable.' }, onRetry: noop, analyzed: false, onHighlight: noop, onToast: noop, onChanged: noop })],
  ['PathExplorer (no-search branch)', h(wrap, h(PathExplorer, { caseId: 1, entities: [{ id: 1, name: 'Aarav Mehta' }, { id: 2, name: 'Rohan Deshmukh' }], onHighlight: noop }))],
  ['PathResult (path render)', h(wrap, h(PathResult, { path: SAMPLE_PATH, onHighlight: noop }))],
  ['BridgePanel (loading branch)', h(wrap, h(BridgePanel, { caseId: 1, onHighlight: noop }))],
  ['BridgeList (bridge details)', h(wrap, h(BridgeList, { bridges: [SAMPLE_BRIDGE], onHighlight: noop }))],
  ['BridgeList (empty state)', h(wrap, h(BridgeList, { bridges: [], onHighlight: noop }))],
  ['ClusterPanel (loading branch)', h(wrap, h(ClusterPanel, { caseId: 1, onHighlight: noop }))],
  ['ClusterList (cluster info)', h(wrap, h(ClusterList, { clusters: [SAMPLE_CLUSTER], onHighlight: noop }))],
  ['ClusterList (empty state)', h(wrap, h(ClusterList, { clusters: [], onHighlight: noop }))],
  ['CrossCasePanel (loading branch)', h(wrap, h(CrossCasePanel, { caseId: 1, onHighlight: noop, onOpenCase: noop }))],
  ['CrossCaseList (data)', h(wrap, h(CrossCaseList, { connections: [SAMPLE_CONNECTION], onHighlight: noop, onOpenCase: noop }))],
  ['CrossCaseList (empty state)', h(wrap, h(CrossCaseList, { connections: [], onHighlight: noop, onOpenCase: noop }))],
  // stage 4: investigation intelligence (16 rendered states)
  ['Inv panel (not-analyzed state)', h(StatusBody, { loading: false, error: null, data: null, analyzing: false, onRun: noop })],
  ['Inv panel (loading branch — full page, all panels)', h(ThemeProvider, null, h(AuthProvider, null, h(ToastProvider, null, h(MemoryRouter, { initialEntries: ['/cases/1/investigation'] }, h(Routes, null, h(Route, { path: '/cases/:caseId/investigation', element: h(InvestigationIntelligencePage) }))))))],
  ['Inv panel (error state)', h(PanelBody, { loading: false, data: null, error: { message: 'The platform backend is not reachable.' }, onRetry: noop, empty: null, children: null })],
  ['Inv panel (empty — not analyzed body)', h(wrap, h(ContradictionsBody, { loading: false, data: null, error: null, onRetry: noop, analyzed: false, insufficient: false, onHighlight: noop, onToast: noop, onChanged: noop }))],
  ['Inv panel (stale history)', h(wrap, h(ContradictionsBody, { loading: false, data: { current_findings: [], stale_findings: [SAMPLE_GAP_FINDING] }, error: null, onRetry: noop, analyzed: true, insufficient: false, onHighlight: noop, onToast: noop, onChanged: noop }))],
  ['Contradiction list (render)', h(wrap, h(ContradictionsBody, { loading: false, data: { current_findings: [SAMPLE_CONTRADICTION, SAMPLE_GAP_FINDING], stale_findings: [] }, error: null, onRetry: noop, analyzed: true, insufficient: false, onHighlight: noop, onToast: noop, onChanged: noop }))],
  ['Contradiction empty (analyzed, none detected)', h(wrap, h(ContradictionsBody, { loading: false, data: { current_findings: [], stale_findings: [] }, error: null, onRetry: noop, analyzed: true, insufficient: false, onHighlight: noop, onToast: noop, onChanged: noop }))],
  ['Hypothesis list (render)', h(wrap, h(HypothesesBody, { loading: false, data: { hypotheses: [SAMPLE_HYPOTHESIS] }, error: null, onRetry: noop, analyzed: true, insufficient: false, onAct: noop, showForm: false, formNode: null }))],
  ['Hypothesis details (score components & signals)', h(wrap, h(HypothesisItem, { h: SAMPLE_HYPOTHESIS, onAct: noop }))],
  ['Evidence impact (rows render)', h(wrap, h(EvidenceImpactBody, { loading: false, data: SAMPLE_IMPACT, error: null, onRetry: noop, analyzed: true, insufficient: false, simulation: null, onSimulate: noop, simBusy: null }))],
  ['Evidence simulation (what-if result)', h(wrap, h(EvidenceImpactBody, { loading: false, data: SAMPLE_IMPACT, error: null, onRetry: noop, analyzed: true, insufficient: false, simulation: SAMPLE_SIMULATION, onSimulate: noop, simBusy: null }))],
  ['Timeline intelligence (results render)', h(wrap, h(TimelineBody, { loading: false, data: SAMPLE_TIMELINE, error: null, onRetry: noop, analyzed: true, insufficient: false }))],
  ['Geospatial intelligence (results + observations)', h(wrap, h(GeospatialBody, { loading: false, data: SAMPLE_GEO, error: null, onRetry: noop, analyzed: true, insufficient: false }))],
  ['Geospatial (insufficient location data)', h(wrap, h(GeospatialBody, { loading: false, data: SAMPLE_GEO_INSUFFICIENT, error: null, onRetry: noop, analyzed: true, insufficient: false }))],
  ['Investigation gaps (render)', h(wrap, h(GapsBody, { loading: false, data: { current_findings: [SAMPLE_GAP_FINDING], stale_findings: [] }, error: null, onRetry: noop, analyzed: true, insufficient: false, onHighlight: noop, onToast: noop, onChanged: noop }))],
  ['Graph highlighting (highlightIds mechanism, reused)', h(wrap, h(NetworkGraph, { entities: [
    { id: 1, name: 'Aarav Mehta', type: 'person', resolution: 'unverified', connections: 2, apiType: 'person', aliases: [] },
    { id: 2, name: 'Rohan Deshmukh', type: 'person', resolution: 'unverified', connections: 1, apiType: 'person', aliases: [] },
    { id: 3, name: 'MH12AB1234', type: 'vehicle', resolution: 'unverified', connections: 1, apiType: 'vehicle', aliases: [] },
  ], relationships: [
    { id: 1, sourceId: 1, targetId: 2, type: 'associate', label: 'CALLED', confidence: 0.8, metadata: null },
    { id: 2, sourceId: 1, targetId: 3, type: 'associate', label: 'USED', confidence: 0.8, metadata: null },
  ], highlightIds: new Set([1]), selectedId: null, onSelect: noop, onEdgeSelect: noop }))],
];

let failed = 0;
for (const [name, node] of cases) {
  try {
    const html = renderToStaticMarkup(node);
    if (!html || html.length < 40) throw new Error('suspiciously small output');
    console.log(`  ok   ${name} (${html.length} chars)`);
  } catch (err) {
    failed += 1;
    console.error(`  FAIL ${name}\n       ${err.message}`);
  }
}

await SERVER.close();
if (failed) {
  console.error(`\n${failed} page render(s) failed.`);
  process.exit(1);
}
console.log(`\nAll ${cases.length} pages rendered.`);
