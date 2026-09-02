/**
 * Mock dashboard activity feed. UI mock events only — these represent the
 * notifications a backend event bus would emit; nothing here is live.
 */
export const mockActivity = [
  {
    id: 'act-001',
    type: 'evidence_added',
    message: 'New evidence uploaded',
    detail: 'GPS trace export — tempo MH-12 DE 4421',
    investigationId: 'inv-007',
    at: '2026-08-30T16:40:00+05:30',
  },
  {
    id: 'act-002',
    type: 'entity_match',
    message: 'Entity match requires review',
    detail: 'Second handset active on the F. Shaikh identity',
    investigationId: 'inv-003',
    at: '2026-08-30T11:05:00+05:30',
  },
  {
    id: 'act-003',
    type: 'relationship_detected',
    message: 'New relationship detected',
    detail: 'Shared device fingerprint links two crew handsets',
    investigationId: 'inv-001',
    at: '2026-08-29T18:20:00+05:30',
  },
  {
    id: 'act-004',
    type: 'report_generated',
    message: 'Report generated',
    detail: 'NEX-009 · Cluster graph export',
    investigationId: 'inv-003',
    at: '2026-08-29T12:00:00+05:30',
  },
  {
    id: 'act-005',
    type: 'timeline_updated',
    message: 'Timeline updated',
    detail: 'Fifth corridor run added to the case timeline',
    investigationId: 'inv-007',
    at: '2026-08-28T20:10:00+05:30',
  },
  {
    id: 'act-006',
    type: 'evidence_added',
    message: 'New evidence uploaded',
    detail: 'CCTV stills — Galaxy Racing Lounge entrance',
    investigationId: 'inv-001',
    at: '2026-08-28T09:45:00+05:30',
  },
  {
    id: 'act-007',
    type: 'entity_match',
    message: 'Entity match requires review',
    detail: 'Manifest signatures match two consignors',
    investigationId: 'inv-002',
    at: '2026-08-27T15:30:00+05:30',
  },
  {
    id: 'act-008',
    type: 'relationship_detected',
    message: 'New relationship detected',
    detail: 'Rendezvous cluster near the Chakan weighbridge',
    investigationId: 'inv-007',
    at: '2026-08-27T09:15:00+05:30',
  },
];

export default mockActivity;
