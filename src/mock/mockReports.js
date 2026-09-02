/**
 * Mock generated-report records. Document generation itself is a backend
 * concern; the frontend only tracks request status.
 */
export const mockReports = [
  {
    id: 'rep-101',
    investigationId: 'inv-001',
    type: 'case_summary',
    title: 'NEX-014 · Case summary — August 2026',
    format: 'PDF',
    status: 'ready',
    requestedBy: 'Priya Deshmukh',
    createdAt: '2026-08-20T10:30:00+05:30',
  },
  {
    id: 'rep-102',
    investigationId: 'inv-001',
    type: 'evidence_index',
    title: 'NEX-014 · Evidence index v3',
    format: 'PDF',
    status: 'ready',
    requestedBy: 'Sneha Joshi',
    createdAt: '2026-08-12T15:00:00+05:30',
  },
  {
    id: 'rep-103',
    investigationId: 'inv-003',
    type: 'network_analysis',
    title: 'NEX-009 · Cluster graph export',
    format: 'PDF',
    status: 'ready',
    requestedBy: 'Sneha Joshi',
    createdAt: '2026-08-29T11:45:00+05:30',
  },
  {
    id: 'rep-104',
    investigationId: 'inv-003',
    type: 'timeline_digest',
    title: 'NEX-009 · Timeline digest (weekly)',
    format: 'DOCX',
    status: 'queued',
    requestedBy: 'Priya Deshmukh',
    createdAt: '2026-08-30T08:15:00+05:30',
  },
  {
    id: 'rep-105',
    investigationId: 'inv-007',
    type: 'case_summary',
    title: 'NEX-016 · Case summary — draft',
    format: 'PDF',
    status: 'failed',
    requestedBy: 'Arjun Patil',
    createdAt: '2026-08-27T16:20:00+05:30',
  },
  {
    id: 'rep-106',
    investigationId: 'inv-002',
    type: 'evidence_index',
    title: 'NEX-011 · Evidence index v2',
    format: 'PDF',
    status: 'ready',
    requestedBy: 'Vikas Rane',
    createdAt: '2026-08-22T09:50:00+05:30',
  },
];

export default mockReports;
