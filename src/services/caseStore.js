import { mockEntities } from '@/mock/mockEntities';
import { mockRelationships } from '@/mock/mockRelationships';
import { mockEvents } from '@/mock/mockEvents';
import { mockEventLinks } from '@/mock/mockEventLinks';
import { mockLocations } from '@/mock/mockLocations';
import { mockEvidence } from '@/mock/mockEvidence';
import { mockInsights } from '@/mock/mockIntelligence';
import { mockReports } from '@/mock/mockReports';

/**
 * Single mutable case dataset for the frontend build.
 *
 * Every service used to keep its own private `[...mockX]` copy, so records
 * created at runtime (an evidence upload, an extracted entity) were visible
 * to exactly one service and invisible to the tab counters, the network view
 * and the timeline. They all share these arrays now: whatever the ingestion
 * pipeline writes here is what every surface reads back.
 */
export const entityStore = [...mockEntities];
export const relationshipStore = [...mockRelationships];
export const eventStore = [...mockEvents];
export const locationStore = [...mockLocations];
export const evidenceStore = [...mockEvidence];
export const insightStore = [...mockInsights];
export const reportStore = [...mockReports];

/** Event → location/evidence links. Seeded from the mock link table. */
export const eventLinks = { ...mockEventLinks };

export function byInvestigation(store, investigationId) {
  return store.filter((r) => r.investigationId === investigationId);
}

/** Counters used by the case header tabs and the caseload table. */
export function caseCounts(investigationId) {
  return {
    entities: byInvestigation(entityStore, investigationId).length,
    relationships: byInvestigation(relationshipStore, investigationId).length,
    evidence: byInvestigation(evidenceStore, investigationId).length,
    events: byInvestigation(eventStore, investigationId).length,
    locations: byInvestigation(locationStore, investigationId).length,
    insights: byInvestigation(insightStore, investigationId).length,
  };
}
