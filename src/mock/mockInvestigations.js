/**
 * Mock investigations. All names, cases and identifiers are fictional.
 * NOTE: `stats` are computed by the service layer from the other mock
 * modules, so case statistics always match the underlying mock data.
 */
export const mockInvestigations = [
  {
    id: 'inv-001',
    code: 'NEX-2026-014',
    caseType: 'betting',
    title: 'Raceview Betting Syndicate',
    summary:
      'Organised off-track betting network running layered cash settlement around Pune race events.',
    description:
      'A structured betting syndicate collects wagers through lounge and club fronts around the Pune racecourse, then layers proceeds through cash deposits into linked accounts. Surveillance and financial records indicate a core crew of three operating under a single coordinator. Priority is tracing settlement flows before the next race meet.',
    status: 'active',
    priority: 'critical',
    leadId: 'usr-001',
    teamIds: ['usr-002', 'usr-003'],
    tags: ['betting', 'organised-crime', 'financial'],
    jurisdiction: 'Pune City',
    openedAt: '2026-03-12T09:30:00+05:30',
    updatedAt: '2026-08-29T17:10:00+05:30',
  },
  {
    id: 'inv-002',
    code: 'NEX-2026-011',
    caseType: 'theft',
    title: 'Bhiwandi Warehouse Theft Series',
    summary:
      'Repeated break-ins at logistics warehouses with matching entry methods and a recurring tempo.',
    description:
      'Four warehouse intrusions in the Bhiwandi belt since May 2026 share tool marks and approach patterns. Toll and patrol footage repeatedly shows the same white tempo idling near target sites before each incident. Focus is on linking the vehicle to a handler and recovering consigned goods.',
    status: 'active',
    priority: 'high',
    leadId: 'usr-002',
    teamIds: ['usr-004'],
    tags: ['theft', 'logistics'],
    jurisdiction: 'Bhiwandi, Thane',
    openedAt: '2026-04-02T11:00:00+05:30',
    updatedAt: '2026-08-24T14:45:00+05:30',
  },
  {
    id: 'inv-003',
    code: 'NEX-2026-009',
    caseType: 'financial',
    title: 'Phantom SIM Fraud Cluster',
    summary:
      'Mule SIM kits and shell accounts used to absorb fraud proceeds through a mobile retail front.',
    description:
      'A cluster of subscriber-identity kits purchased from a single retailer routes scam proceeds through low-value deposits into cooperative-bank mule accounts, ultimately reaching a shell LLP. Call records tie the mule handsets together and back to two coordinators. Priority is freezing linked accounts and mapping the full beneficiary chain.',
    status: 'active',
    priority: 'critical',
    leadId: 'usr-003',
    teamIds: ['usr-001', 'usr-004'],
    tags: ['cyber-fraud', 'identity-theft', 'financial'],
    jurisdiction: 'Mumbai City',
    openedAt: '2026-02-18T10:15:00+05:30',
    updatedAt: '2026-08-30T09:20:00+05:30',
  },
  {
    id: 'inv-004',
    code: 'NEX-2026-007',
    caseType: 'counterfeiting',
    title: 'Counterfeit Auto-Parts Ring',
    summary:
      'Counterfeit components distributed through the Chakan industrial belt under a registered brand.',
    description:
      'Seized consignments of counterfeit brake and filter components trace to a unit operating under a legitimate-sounding trade name in the Chakan–Rajgurunagar belt. Trademark holders have filed complaints in two states. Case is pending supervisory review before expansion.',
    status: 'pending_review',
    priority: 'medium',
    leadId: 'usr-004',
    teamIds: ['usr-002'],
    tags: ['counterfeiting', 'ip-crime'],
    jurisdiction: 'Chakan–Rajgurunagar belt, Pune',
    openedAt: '2026-01-27T14:00:00+05:30',
    updatedAt: '2026-07-15T12:30:00+05:30',
  },
  {
    id: 'inv-005',
    code: 'NEX-2026-004',
    caseType: 'smuggling',
    title: 'Old Mumbai–Pune Gold Corridor',
    summary:
      'Suspected gold movement along the old highway using passenger taxis and paying-guest lodges.',
    description:
      'Pattern analysis of seizures along the old Mumbai–Pune corridor suggested a low-volume courier route exploiting passenger transport. Two intercepts confirmed the method. Case closed after successful interdiction; retained for reference on corridor tactics.',
    status: 'closed',
    priority: 'medium',
    leadId: 'usr-001',
    teamIds: ['usr-003'],
    tags: ['smuggling', 'customs'],
    jurisdiction: 'Pune–Mumbai corridor',
    openedAt: '2026-01-05T08:45:00+05:30',
    updatedAt: '2026-06-10T16:00:00+05:30',
  },
  {
    id: 'inv-006',
    code: 'NEX-2025-118',
    caseType: 'extortion',
    title: 'Call-Centre Extortion Racket',
    summary:
      'Archived extortion case involving spoofed caller-ID harassment of business owners.',
    description:
      'A seven-seat call operation placed spoofed-ID extortion calls to traders. Premises raided in December 2025; equipment seized and eleven chargesheeted. Archived after conviction of the primary operators.',
    status: 'archived',
    priority: 'low',
    leadId: 'usr-004',
    teamIds: ['usr-001'],
    tags: ['extortion', 'cyber'],
    jurisdiction: 'Navi Mumbai',
    openedAt: '2025-11-19T09:00:00+05:30',
    updatedAt: '2026-04-21T11:20:00+05:30',
  },
  {
    id: 'inv-007',
    code: 'NEX-2026-016',
    caseType: 'narcotics',
    title: 'Chakan Narcotics Courier Line',
    summary:
      'Courier line moving contraband between a Chakan godown and city markets in pre-dawn runs.',
    description:
      'A small courier line transports contraband panels from a rented godown in the Chakan MIDC belt to distributors at the market yard. Toll records show repeated pre-dawn tempo runs on the NH-48 corridor. One recovery is confirmed by FSL; focus is on the route controller and hand-off points.',
    status: 'active',
    priority: 'high',
    leadId: 'usr-001',
    teamIds: ['usr-002', 'usr-003'],
    tags: ['narcotics', 'distribution'],
    jurisdiction: 'Chakan Industrial Belt, Pune',
    openedAt: '2026-05-06T07:50:00+05:30',
    updatedAt: '2026-08-28T19:35:00+05:30',
  },
  {
    /**
     * Multi-source analysis case.
     *
     * Unlike every other record here, this case's entities, relationships,
     * evidence and findings are NOT held in the mock store — they are produced
     * live by the criminal-network-analysis pipeline in `backend/`. The
     * `analysisBackend` flag routes the case file to the analysis surfaces
     * instead of the mock tabs, so nothing is rendered as empty that is
     * actually populated.
     *
     * The corpus itself is synthetic, generated by `data/generator.py`.
     */
    id: 'inv-cna-001',
    code: 'NEX-2026-021',
    caseType: 'organised_network',
    title: 'Operation Meridian — Multi-Source Network Analysis',
    summary:
      'Fragmented FIR, call, financial, surveillance and social-media records resolved into a single relationship graph.',
    description:
      'Eight fragmented sources — FIR narratives in English and Devanagari, scanned paper FIRs, call detail records, financial transactions, criminal history, surveillance reports, social-media intelligence, and read-only CCTNS and ICJS feeds — are ingested, resolved into single identities across scripts, and built into a provenance-carrying graph. Influence is ranked with exact Shapley attribution, and nine suspicious-pattern detectors each state the rule that fired and the numbers behind it. Every claim traces back to the source record that produced it.',
    status: 'active',
    priority: 'critical',
    leadId: 'usr-001',
    teamIds: ['usr-002', 'usr-003', 'usr-004'],
    tags: ['multi-source', 'network-analysis', 'devanagari', 'synthetic-corpus'],
    jurisdiction: 'Greater Mumbai',
    openedAt: '2026-05-01T09:00:00+05:30',
    updatedAt: '2026-06-10T22:35:00+05:30',
    analysisBackend: 'cna',
  },
];

export default mockInvestigations;
