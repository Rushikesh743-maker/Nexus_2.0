/**
 * Mock intelligence insights.
 *
 * These represent items a backend analysis engine would emit. Sources are
 * explicitly labelled "(mock)" so the UI never implies live AI output.
 */
export const mockInsights = [
  /* ---- inv-003 ---- */
  {
    id: 'int-301',
    investigationId: 'inv-003',
    category: 'pattern',
    title: 'Sub-₹10,000 structuring across mule account',
    summary:
      'Fourteen cash deposits below the reporting threshold landed in A/C ••3391 within three days, followed by a single outbound transfer. Consistent with layered placement of pooled proceeds.',
    confidence: 82,
    status: 'reviewed',
    linkedEntityIds: ['ent-302', 'ent-308', 'ent-309'],
    source: 'Pattern detection service (mock)',
    createdAt: '2026-08-16T09:00:00+05:30',
  },
  {
    id: 'int-302',
    investigationId: 'inv-003',
    category: 'link',
    title: 'Six mule SIMs activated at one counter in nine days',
    summary:
      'Purchase register entries and activation logs tie all six kits to the QuickTech counter; three share one identity bundle anchored to a store employee.',
    confidence: 76,
    status: 'new',
    linkedEntityIds: ['ent-303', 'ent-304', 'ent-305', 'ent-306', 'ent-307'],
    source: 'Link analysis engine (mock)',
    createdAt: '2026-08-21T14:30:00+05:30',
  },
  {
    id: 'int-303',
    investigationId: 'inv-003',
    category: 'anomaly',
    title: 'Second handset active on F. Shaikh identity',
    summary:
      'Tower data shows a second IMEI active on the same subscriber identity during after-hours store visits. Verify against the seized handset before any action.',
    confidence: 61,
    status: 'new',
    linkedEntityIds: ['ent-303'],
    source: 'Anomaly detector (mock)',
    createdAt: '2026-08-27T18:00:00+05:30',
  },

  /* ---- inv-001 ---- */
  {
    id: 'int-101',
    investigationId: 'inv-001',
    category: 'temporal',
    title: 'Settlement spikes follow Pune race meets',
    summary:
      'Deposits into A/C ••4213 rise 48–72 hours after each race day, with a stable 3–4 day settlement lag across the review period.',
    confidence: 79,
    status: 'reviewed',
    linkedEntityIds: ['ent-102', 'ent-107'],
    source: 'Temporal analysis service (mock)',
    createdAt: '2026-08-10T11:00:00+05:30',
  },
  {
    id: 'int-102',
    investigationId: 'inv-001',
    category: 'link',
    title: 'Shared device fingerprint links two crew handsets',
    summary:
      'Forensic images show a common messaging app account restored on both recovered handsets, implying shared operational control rather than parallel use.',
    confidence: 71,
    status: 'new',
    linkedEntityIds: ['ent-101', 'ent-103'],
    source: 'Link analysis engine (mock)',
    createdAt: '2026-08-19T16:45:00+05:30',
  },

  /* ---- inv-002 ---- */
  {
    id: 'int-201',
    investigationId: 'inv-002',
    category: 'pattern',
    title: 'Break-ins avoid CCTV maintenance weeks',
    summary:
      'Site logs show camera service outages before two of four incidents, suggesting awareness of maintenance schedules.',
    confidence: 57,
    status: 'new',
    linkedEntityIds: [],
    source: 'Pattern detection service (mock)',
    createdAt: '2026-08-08T10:20:00+05:30',
  },
  {
    id: 'int-202',
    investigationId: 'inv-002',
    category: 'link',
    title: 'Manifest signatures match two consignors',
    summary:
      'Preliminary handwriting review flags recurring initials across four falsified dispatch records, narrowing the insider pool.',
    confidence: 52,
    status: 'new',
    linkedEntityIds: [],
    source: 'Document analysis service (mock)',
    createdAt: '2026-08-14T15:10:00+05:30',
  },

  /* ---- inv-007 ---- */
  {
    id: 'int-701',
    investigationId: 'inv-007',
    category: 'geo',
    title: 'Rendezvous cluster near Chakan weighbridge',
    summary:
      'Courier stops concentrate within roughly 800 m of the NH-48 weighbridge on run nights, consistent with a hand-off staging area.',
    confidence: 74,
    status: 'new',
    linkedEntityIds: ['ent-702', 'ent-704', 'ent-705'],
    source: 'Geospatial analysis service (mock)',
    createdAt: '2026-08-22T12:00:00+05:30',
  },
  {
    id: 'int-702',
    investigationId: 'inv-007',
    category: 'temporal',
    title: 'Corridor runs launch before dawn on Tuesdays',
    summary:
      'All five recorded tempo crossings fall between 02:00 and 05:00, four of them on Tuesdays — a stable operating window.',
    confidence: 68,
    status: 'reviewed',
    linkedEntityIds: ['ent-704'],
    source: 'Temporal analysis service (mock)',
    createdAt: '2026-08-18T09:30:00+05:30',
  },
];

export default mockInsights;
