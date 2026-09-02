/**
 * Mock relationships between entities. `strength` is 0–100 analyst confidence
 * in the link. All data is fictional.
 */
export const mockRelationships = [
  /* ---- inv-001 ---- */
  { id: 'rel-101', investigationId: 'inv-001', sourceId: 'ent-101', targetId: 'ent-102', type: 'hierarchical', label: 'Runs collection crew', strength: 90, note: 'Multiple race-night sightings.' },
  { id: 'rel-102', investigationId: 'inv-001', sourceId: 'ent-102', targetId: 'ent-103', type: 'communication', label: 'Race-day calls', strength: 62 },
  { id: 'rel-103', investigationId: 'inv-001', sourceId: 'ent-103', targetId: 'ent-104', type: 'co_located', label: 'Regular presence', strength: 71 },
  { id: 'rel-104', investigationId: 'inv-001', sourceId: 'ent-101', targetId: 'ent-106', type: 'co_located', label: 'Late-night bookings', strength: 66 },
  { id: 'rel-105', investigationId: 'inv-001', sourceId: 'ent-102', targetId: 'ent-107', type: 'financial', label: 'Cash deposits', strength: 87 },
  { id: 'rel-106', investigationId: 'inv-001', sourceId: 'ent-103', targetId: 'ent-105', type: 'communication', label: 'Settlement calls', strength: 55 },
  { id: 'rel-107', investigationId: 'inv-001', sourceId: 'ent-101', targetId: 'ent-105', type: 'communication', label: 'Settlement calls', strength: 73 },

  /* ---- inv-002 ---- */
  { id: 'rel-201', investigationId: 'inv-002', sourceId: 'ent-201', targetId: 'ent-202', type: 'associate', label: 'Seen together at Warehouse 9', strength: 64 },

  /* ---- inv-003 ---- */
  { id: 'rel-301', investigationId: 'inv-003', sourceId: 'ent-301', targetId: 'ent-304', type: 'hierarchical', label: 'Proprietor', strength: 88 },
  { id: 'rel-302', investigationId: 'inv-003', sourceId: 'ent-301', targetId: 'ent-302', type: 'associate', label: 'Long-time associates', strength: 76 },
  { id: 'rel-303', investigationId: 'inv-003', sourceId: 'ent-302', targetId: 'ent-308', type: 'financial', label: 'Operates mule account', strength: 91 },
  { id: 'rel-304', investigationId: 'inv-003', sourceId: 'ent-308', targetId: 'ent-309', type: 'financial', label: 'Routed transfers', strength: 84 },
  { id: 'rel-305', investigationId: 'inv-003', sourceId: 'ent-301', targetId: 'ent-309', type: 'hierarchical', label: 'Beneficiary', strength: 80 },
  { id: 'rel-306', investigationId: 'inv-003', sourceId: 'ent-303', targetId: 'ent-304', type: 'associate', label: 'Store employee', strength: 70 },
  { id: 'rel-307', investigationId: 'inv-003', sourceId: 'ent-303', targetId: 'ent-306', type: 'communication', label: 'Registered in KYC bundle', strength: 58 },
  { id: 'rel-308', investigationId: 'inv-003', sourceId: 'ent-302', targetId: 'ent-305', type: 'communication', label: 'Co-activation window', strength: 64 },
  { id: 'rel-309', investigationId: 'inv-003', sourceId: 'ent-305', targetId: 'ent-307', type: 'communication', label: 'Bulk SMS bursts', strength: 52 },
  { id: 'rel-310', investigationId: 'inv-003', sourceId: 'ent-304', targetId: 'ent-310', type: 'co_located', label: 'Registered shop address', strength: 95 },

  /* ---- inv-004 ---- */
  { id: 'rel-401', investigationId: 'inv-004', sourceId: 'ent-401', targetId: 'ent-402', type: 'hierarchical', label: 'Operations head', strength: 72 },

  /* ---- inv-007 ---- */
  { id: 'rel-701', investigationId: 'inv-007', sourceId: 'ent-701', targetId: 'ent-702', type: 'hierarchical', label: 'Controls route', strength: 85 },
  { id: 'rel-702', investigationId: 'inv-007', sourceId: 'ent-702', targetId: 'ent-703', type: 'communication', label: 'Load-night calls', strength: 68 },
  { id: 'rel-703', investigationId: 'inv-007', sourceId: 'ent-702', targetId: 'ent-704', type: 'co_located', label: 'Uses tempo', strength: 77 },
  { id: 'rel-704', investigationId: 'inv-007', sourceId: 'ent-703', targetId: 'ent-705', type: 'co_located', label: 'Loads at godown', strength: 82 },
  { id: 'rel-705', investigationId: 'inv-007', sourceId: 'ent-701', targetId: 'ent-706', type: 'communication', label: 'Late-night calls', strength: 61 },
];

export default mockRelationships;
