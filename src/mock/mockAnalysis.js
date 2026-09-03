/**
 * Mock intelligence-analysis templates.
 *
 * These are STATIC, CLEARLY-LABELLED presentation datasets. No contradiction
 * detection, hypothesis scoring, gap detection or simulation logic runs in
 * the client — every value here is a placeholder that a backend analysis
 * service will replace. Entity names are injected by the service layer from
 * the case's own data so the screens always show this investigation's data.
 */

export const HYPOTHESIS_TEMPLATES = [
  {
    id: 'H1',
    title: 'Intentional Coordination',
    supportingPoints: ['Shared communication', 'Repeated location overlap', 'Vehicle association'],
    contradictingPoints: ['Timeline inconsistency'],
    distinguishing: ['Independent location evidence', 'Additional communication record', 'Verified transaction information'],
  },
  {
    id: 'H2',
    title: 'Indirect Association',
    supportingPoints: ['One shared contact point', 'Single location overlap'],
    contradictingPoints: ['No direct communication recorded'],
    distinguishing: ['Intermediary identification', 'Full call-record review'],
  },
  {
    id: 'H3',
    title: 'Coincidental Interaction',
    supportingPoints: ['Isolated single contact'],
    contradictingPoints: ['Multiple independent links recorded'],
    distinguishing: ['Wider timeframe comparison', 'Random-baseline check (backend service)'],
  },
];

export const GAP_TEMPLATES = [
  { title: 'Independent location verification', impact: 'High', description: 'Recorded movements rely on a single source. Independent verification (e.g. CCTV or toll records obtained through lawful requisition) would strengthen or weaken the movement assessment.' },
  { title: 'Vehicle ownership verification', impact: 'Medium', description: 'The registered keeper of the observed vehicle has not been confirmed with the registration authority.' },
  { title: 'Additional communication records', impact: 'Medium', description: 'Call-detail coverage ends before the review window. Requesting the remaining period would close the timeline.' },
  { title: 'Second-source statement', impact: 'Medium', description: 'One witness account currently supports a key relationship; a second independent statement is needed for corroboration.' },
  { title: 'Financial trail completion', impact: 'Low', description: 'Transfers beyond the first hop are not yet traced. Bank requisitions for the linked accounts would complete the picture.' },
  { title: 'Device–user attribution', impact: 'Low', description: 'Handsets are linked to identities through purchase records only; usage attribution is unverified.' },
];

/**
 * Removed: the contradiction engine is no longer mocked. Contradictions are
 * computed by `backend/app/intelligence/contradiction_engine.py` from real
 * evidence and served by `GET /cna-api/contradictions`. The hypothesis, gap,
 * impact-simulator and copilot mocks above remain until those engines land.
 */

/** Static global notification feed (mock). */
export const MOCK_NOTIFICATIONS = [
  { id: 'ntf-1', icon: 'Upload', title: 'New evidence processed', detail: 'CDR export added to the active case', minutesAgo: 2, to: '/investigations' },
  { id: 'ntf-2', icon: 'AlertTriangle', title: 'Contradicting evidence detected', detail: 'Timeline conflict flagged for review', minutesAgo: 10, to: '/investigations' },
  { id: 'ntf-3', icon: 'UserSearch', title: 'Entity match requires review', detail: 'Possible match on a tracked person', minutesAgo: 24, to: '/investigations' },
  { id: 'ntf-4', icon: 'Share2', title: 'New relationship detected', detail: 'Link analysis proposed a new connection', minutesAgo: 51, to: '/investigations' },
  { id: 'ntf-5', icon: 'FileText', title: 'Report generated', detail: 'Evidence index export is ready', minutesAgo: 130, to: '/investigations' },
];

export default { HYPOTHESIS_TEMPLATES, GAP_TEMPLATES, MOCK_NOTIFICATIONS };
