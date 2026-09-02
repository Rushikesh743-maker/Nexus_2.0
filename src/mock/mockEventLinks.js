/**
 * Links between timeline events and mapped locations / evidence records.
 * Kept separate so mockEvents.js stays a pure event list. Events without an
 * entry here simply have no location/evidence link.
 */
export const mockEventLinks = {
  'evt-101': { locationId: 'loc-101', evidenceId: 'ev-101' },
  'evt-102': { locationId: 'loc-104', evidenceId: 'ev-102' },
  'evt-103': { evidenceId: 'ev-103' },
  'evt-104': { locationId: 'loc-102', evidenceId: 'ev-102' },
  'evt-105': { locationId: 'loc-103' },
  'evt-202': { locationId: 'loc-202', evidenceId: 'ev-202' },
  'evt-301': { locationId: 'loc-301', evidenceId: 'ev-303' },
  'evt-302': { locationId: 'loc-304', evidenceId: 'ev-302' },
  'evt-304': { locationId: 'loc-301', evidenceId: 'ev-301' },
  'evt-305': { locationId: 'loc-303', evidenceId: 'ev-302' },
  'evt-701': { locationId: 'loc-702', evidenceId: 'ev-702' },
  'evt-702': { locationId: 'loc-701', evidenceId: 'ev-702' },
  'evt-703': { evidenceId: 'ev-702' },
  'evt-704': { locationId: 'loc-701', evidenceId: 'ev-701' },
  'evt-705': { locationId: 'loc-702', evidenceId: 'ev-702' },
};

export default mockEventLinks;
