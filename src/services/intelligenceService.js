import { USE_MOCK_API, api, mockLatency, clone } from './api';
import { mockUsers } from '@/mock/mockUsers';
import {
  entityStore,
  relationshipStore,
  eventStore,
  locationStore,
  insightStore,
  reportStore,
  evidenceStore,
  eventLinks,
} from './caseStore';
import { ENTITY_RESOLUTION } from '@/lib/constants';
import { hashString } from '@/lib/utils';

/**
 * Intelligence service — entities, relationships, events, locations,
 * analysis insights and report records for a case. Mock mode reads the
 * in-memory mock store; API mode maps onto /investigations/:id/* endpoints.
 */

const byDatetimeDesc = (a, b) => new Date(b.datetime) - new Date(a.datetime);

/* ---------- events ---------- */

/** Attach location/evidence links to an event (mock link table). */
function enrichEvent(event) {
  const link = eventLinks[event.id] || {};
  // An extracted event already carries its own links; the link table is the
  // fallback for the seeded fixtures.
  return {
    ...event,
    locationId: event.locationId ?? link.locationId ?? null,
    evidenceId: event.evidenceId ?? link.evidenceId ?? null,
  };
}

/* ---------- entity directory (enriched entities for explorer/details) ---------- */

/**
 * Mock identity-resolution placeholder. Produces a stable, neutral
 * resolution status per entity until the backend resolution service
 * replaces it. NEXUS presents matches — it never labels people.
 */
function resolutionFor(entity) {
  const h = hashString(entity.id);
  if (h % 5 === 0) return { resolution: 'possible_match', resolutionConfidence: 68 + (h % 28) };
  if (h % 7 === 0) return { resolution: 'unverified', resolutionConfidence: null };
  return { resolution: 'verified', resolutionConfidence: 84 + (h % 15) };
}

/** Enrich entities with connections, event links and mock aggregates. */
function enrichEntities(investigationId, entities, relationships, events) {
  const degree = {};
  relationships.forEach((r) => {
    degree[r.sourceId] = (degree[r.sourceId] || 0) + 1;
    degree[r.targetId] = (degree[r.targetId] || 0) + 1;
  });
  const eventCount = {};
  events.forEach((e) => (e.entityIds || []).forEach((id) => (eventCount[id] = (eventCount[id] || 0) + 1)));

  return entities.map((entity) => {
    const h = hashString(`${entity.id}:${investigationId}`);
    return {
      ...entity,
      connections: degree[entity.id] || 0,
      eventsCount: eventCount[entity.id] || 0,
      // Extracted entities know exactly which files they came from; seeded
      // fixtures keep the deterministic placeholder.
      evidenceCount: entity.sourceEvidenceIds ? entity.sourceEvidenceIds.length : 2 + (h % 14),
      ...resolutionFor(entity),
    };
  });
}

/* ---------- entities & relationships ---------- */

export async function getEntities(investigationId) {
  if (!USE_MOCK_API) {
    const { data } = await api.get(`/investigations/${investigationId}/entities`);
    return data;
  }
  await mockLatency();
  return clone(entityStore.filter((e) => e.investigationId === investigationId));
}

export async function getRelationships(investigationId) {
  if (!USE_MOCK_API) {
    const { data } = await api.get(`/investigations/${investigationId}/relationships`);
    return data;
  }
  await mockLatency();
  return clone(relationshipStore.filter((r) => r.investigationId === investigationId));
}

/**
 * Full case dataset for the workspace: entities enriched with connection /
 * event / evidence aggregates and resolution status, plus relationships,
 * events, optional evidence graph nodes and structural insights.
 */
export async function getNetwork(investigationId, { includeEvidence = false } = {}) {
  if (!USE_MOCK_API) {
    const { data } = await api.get(`/investigations/${investigationId}/network`, {
      params: { includeEvidence },
    });
    return data;
  }
  const [entities, relationships, events] = await Promise.all([
    getEntities(investigationId),
    getRelationships(investigationId),
    getEvents(investigationId),
  ]);
  const enriched = enrichEntities(investigationId, entities, relationships, events.items);
  const evidenceGraph = includeEvidence
    ? evidenceGraphNodes(investigationId, entities.map((e) => e.id))
    : { nodes: [], edges: [] };
  return clone({
    entities: enriched,
    relationships,
    events: events.items,
    evidenceNodes: evidenceGraph.nodes,
    evidenceEdges: evidenceGraph.edges,
    insights: graphInsights(entities, relationships),
  });
}

/* ---------- events ---------- */

export async function getEvents(investigationId, { type = 'all' } = {}) {
  if (!USE_MOCK_API) {
    const { data } = await api.get(`/investigations/${investigationId}/events`, { params: { type } });
    return data;
  }
  await mockLatency();
  let items = eventStore.filter((e) => e.investigationId === investigationId).map(enrichEvent);
  if (type !== 'all') items = items.filter((e) => e.type === type);
  items = [...items].sort(byDatetimeDesc);
  return clone({ items, total: items.length });
}

/* ---------- locations ---------- */

/** Locations enriched with event/entity/evidence aggregates for map popups. */
function enrichLocation(location, events) {
  const linkedEvents = events.filter((e) => e.locationId === location.id);
  const h = hashString(`${location.id}:evidence`);
  return {
    ...location,
    eventsCount: linkedEvents.length,
    lastRecordedAt: linkedEvents.length
      ? linkedEvents.reduce((max, e) => (new Date(e.datetime) > new Date(max) ? e.datetime : max), linkedEvents[0].datetime)
      : location.lastActivityAt || null,
    // Placeholder until the pipeline geotags evidence records.
    evidenceCount: location.extracted
      ? new Set(linkedEvents.map((e) => e.evidenceId).filter(Boolean)).size
      : 1 + (h % 7),
  };
}

export async function getLocations(investigationId) {
  if (!USE_MOCK_API) {
    const { data } = await api.get(`/investigations/${investigationId}/locations`);
    return data;
  }
  await mockLatency();
  const events = eventStore.filter((e) => e.investigationId === investigationId).map(enrichEvent);
  return clone(locationStore.filter((l) => l.investigationId === investigationId).map((l) => enrichLocation(l, events)));
}

/**
 * Recorded movement trace: consecutive mapped locations in event
 * chronological order. All coordinates come from the mock location store —
 * nothing is invented in the UI.
 */
export async function getMovement(investigationId) {
  if (!USE_MOCK_API) {
    const { data } = await api.get(`/investigations/${investigationId}/movement`);
    return data;
  }
  await mockLatency(120);
  const events = eventStore
    .filter((e) => e.investigationId === investigationId)
    .map(enrichEvent)
    .sort((a, b) => new Date(a.datetime) - new Date(b.datetime));
  const byId = Object.fromEntries(
    locationStore.filter((l) => l.investigationId === investigationId).map((l) => [l.id, l])
  );

  const stops = [];
  events.forEach((e) => {
    if (e.locationId && byId[e.locationId]) {
      const last = stops[stops.length - 1];
      if (last && last.locationId === e.locationId) {
        last.at = e.datetime;
        return;
      }
      stops.push({ locationId: e.locationId, at: e.datetime, eventTitle: e.title });
    }
  });

  const legs = [];
  for (let i = 0; i < stops.length - 1; i += 1) {
    const from = byId[stops[i].locationId];
    const to = byId[stops[i + 1].locationId];
    legs.push({
      id: `leg-${i}`,
      from: { id: from.id, name: from.name, lat: from.lat, lng: from.lng, at: stops[i].at },
      to: { id: to.id, name: to.name, lat: to.lat, lng: to.lng, at: stops[i + 1].at },
      eventTitle: stops[i + 1].eventTitle,
    });
  }
  return clone({ legs, total: legs.length });
}

/* ---------- graph extras (network view) ---------- */

/**
 * Evidence records as graph nodes ("Mentioned In" links). Entity→evidence
 * links are deterministic placeholders until the extraction pipeline maps
 * them — clearly labelled in the UI.
 */
function evidenceGraphNodes(investigationId, entityIds) {
  const evidence = evidenceStore.filter((e) => e.investigationId === investigationId);
  const nodes = evidence.map((e) => ({
    id: e.id,
    investigationId,
    type: 'evidence',
    name: `${e.refNo} — ${e.title}`,
    role: 'Evidence record',
    aliases: [],
    notes: null,
    attributes: {},
    createdAt: e.collectedAt,
    connections: 0,
    eventsCount: 0,
    evidenceCount: null,
    resolution: 'verified',
    resolutionConfidence: null,
    refNo: e.refNo,
  }));
  const edges = [];
  evidence.forEach((e) => {
    if (!entityIds.length) return;
    const h = hashString(e.id);
    const links = new Set([entityIds[h % entityIds.length]]);
    if (entityIds.length > 2 && h % 3 === 0) links.add(entityIds[(h + 7) % entityIds.length]);
    [...links].forEach((entityId, i) => {
      edges.push({
        id: `rel-${e.id}-${i}`,
        investigationId,
        sourceId: entityId,
        targetId: e.id,
        type: 'mentioned_in',
        label: 'Mentioned In',
        strength: 55 + (h % 35),
        placeholder: true,
      });
    });
  });
  return { nodes, edges };
}

/**
 * Structural graph insights — simple, transparent heuristics over the case
 * graph. Presentation aids for analysts only; these are NOT risk scores or
 * predictions of any kind.
 */
function graphInsights(entities, relationships) {
  const degree = {};
  relationships.forEach((r) => {
    degree[r.sourceId] = (degree[r.sourceId] || 0) + 1;
    degree[r.targetId] = (degree[r.targetId] || 0) + 1;
  });
  const neighbors = {};
  entities.forEach((e) => (neighbors[e.id] = new Set()));
  relationships.forEach((r) => {
    if (neighbors[r.sourceId] && neighbors[r.targetId]) {
      neighbors[r.sourceId].add(r.targetId);
      neighbors[r.targetId].add(r.sourceId);
    }
  });

  // High-connectivity: degree in the top quartile (min 2 links).
  const degrees = Object.values(degree);
  const threshold = degrees.length
    ? Math.max(2, [...degrees].sort((a, b) => b - a)[Math.floor(degrees.length * 0.25)])
    : 0;
  const hubs = entities
    .filter((e) => (degree[e.id] || 0) >= threshold)
    .map((e) => ({ id: e.id, name: e.name, value: degree[e.id] }));

  // Potential bridge: entity's neighbours rarely interconnect.
  const bridges = entities
    .filter((e) => (degree[e.id] || 0) >= 3)
    .filter((e) => {
      const nb = [...neighbors[e.id]];
      let linked = 0;
      for (let i = 0; i < nb.length; i += 1) {
        for (let j = i + 1; j < nb.length; j += 1) {
          if (neighbors[nb[i]]?.has(nb[j])) linked += 1;
        }
      }
      const pairs = (nb.length * (nb.length - 1)) / 2;
      return pairs > 0 && linked / pairs <= 0.2;
    })
    .map((e) => ({ id: e.id, name: e.name, value: degree[e.id] }));

  // Cross-case: deterministic mock flag — real deployments resolve this
  // against the full case database on the backend.
  const crossCase = entities
    .filter((e) => hashString(`${e.id}:crosscase`) % 9 === 0)
    .map((e) => ({ id: e.id, name: e.name, withCase: 'another case file (mock)' }));

  // Potential cluster: connected components with ≥3 members.
  const seen = new Set();
  const clusters = [];
  entities.forEach((e) => {
    if (seen.has(e.id)) return;
    const component = [];
    const queue = [e.id];
    seen.add(e.id);
    while (queue.length) {
      const current = queue.shift();
      component.push(current);
      neighbors[current].forEach((n) => {
        if (!seen.has(n)) {
          seen.add(n);
          queue.push(n);
        }
      });
    }
    if (component.length >= 3) {
      clusters.push({
        id: `c${clusters.length + 1}`,
        label: `Potential cluster ${String.fromCharCode(65 + clusters.length)}`,
        entityIds: component,
      });
    }
  });

  return { hubs, bridges, crossCase, clusters };
}

/* ---------- insights ---------- */

export async function getInsights(investigationId, { category = 'all', status = 'all' } = {}) {
  if (!USE_MOCK_API) {
    const { data } = await api.get(`/investigations/${investigationId}/insights`, {
      params: { category, status },
    });
    return data;
  }
  await mockLatency();
  let items = insightStore.filter((i) => i.investigationId === investigationId);
  if (category !== 'all') items = items.filter((i) => i.category === category);
  if (status !== 'all') items = items.filter((i) => i.status === status);
  items = [...items].sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
  return clone({ items, total: items.length });
}

export async function markInsightReviewed(id, status = 'reviewed') {
  if (!USE_MOCK_API) {
    const { data } = await api.patch(`/insights/${id}`, { status });
    return data;
  }
  await mockLatency();
  const record = insightStore.find((i) => i.id === id);
  if (!record) {
    const err = new Error(`Insight "${id}" was not found.`);
    err.status = 404;
    throw err;
  }
  record.status = status;
  return clone(record);
}

/* ---------- reports ---------- */

const byCreatedDesc = (a, b) => new Date(b.createdAt) - new Date(a.createdAt);

export async function getReports(investigationId) {
  if (!USE_MOCK_API) {
    const { data } = await api.get(`/investigations/${investigationId}/reports`);
    return data;
  }
  await mockLatency();
  const items = [...reportStore].filter((r) => r.investigationId === investigationId).sort(byCreatedDesc);
  return clone({ items, total: items.length });
}

export async function createReport(investigationId, { type, format = 'PDF', note = '' }) {
  if (!USE_MOCK_API) {
    const { data } = await api.post(`/investigations/${investigationId}/reports`, { type, format, note });
    return data;
  }
  await mockLatency(500);
  const record = {
    id: `rep-${Date.now()}`,
    investigationId,
    type,
    title: `${type.replace('_', ' ')} · requested ${new Date().toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
    })}`,
    format,
    status: 'queued',
    requestedBy: mockUsers[0].name,
    createdAt: new Date().toISOString(),
  };
  reportStore.unshift(record);
  return clone(record);
}
