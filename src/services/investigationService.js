import { USE_MOCK_API, api, mockLatency, clone } from './api';
import { mockInvestigations } from '@/mock/mockInvestigations';
import { mockActivity } from '@/mock/mockActivity';
import { mockEntities } from '@/mock/mockEntities';
import { mockRelationships } from '@/mock/mockRelationships';
import { mockEvidence } from '@/mock/mockEvidence';
import { mockEvents } from '@/mock/mockEvents';
import { mockLocations } from '@/mock/mockLocations';
import { mockInsights } from '@/mock/mockIntelligence';
import { mockUsers } from '@/mock/mockUsers';
import { ACTIVITY_TYPES, caseTypeLabel } from '@/lib/constants';

/**
 * Investigation (case) service. Mock mode works on the in-memory mock store;
 * API mode maps 1:1 onto REST endpoints (see README).
 */

const store = [...mockInvestigations];

/* ---------- helpers ---------- */

function enrich(record) {
  const id = record.id;
  return {
    ...record,
    caseTypeLabel: caseTypeLabel(record.caseType),
    lead: mockUsers.find((u) => u.id === record.leadId) || null,
    team: (record.teamIds || []).map((uid) => mockUsers.find((u) => u.id === uid)).filter(Boolean),
    stats: {
      entities: mockEntities.filter((x) => x.investigationId === id).length,
      relationships: mockRelationships.filter((x) => x.investigationId === id).length,
      evidence: mockEvidence.filter((x) => x.investigationId === id).length,
      events: mockEvents.filter((x) => x.investigationId === id).length,
      locations: mockLocations.filter((x) => x.investigationId === id).length,
      insights: mockInsights.filter((x) => x.investigationId === id).length,
    },
  };
}

function byUpdatedDesc(a, b) {
  return new Date(b.updatedAt) - new Date(a.updatedAt);
}

function nextCode() {
  const year = new Date().getFullYear();
  const numbers = store
    .map((c) => c.code.match(/^NEX-\d{4}-(\d+)$/))
    .filter(Boolean)
    .map((m) => parseInt(m[1], 10));
  const next = (numbers.length ? Math.max(...numbers) : 0) + 1;
  return `NEX-${year}-${String(next).padStart(3, '0')}`;
}

/* ---------- public API ---------- */

export async function list({ search = '', status = 'all', priority = 'all' } = {}) {
  if (!USE_MOCK_API) {
    const { data } = await api.get('/investigations', { params: { search, status, priority } });
    return data;
  }
  await mockLatency();
  const term = search.trim().toLowerCase();
  let items = store.filter((c) => {
    if (status !== 'all' && c.status !== status) return false;
    if (priority !== 'all' && c.priority !== priority) return false;
    if (!term) return true;
    return [c.title, c.code, c.summary, c.jurisdiction, ...(c.tags || [])]
      .join(' ')
      .toLowerCase()
      .includes(term);
  });
  const counts = store.reduce(
    (acc, c) => ({ ...acc, [c.status]: (acc[c.status] || 0) + 1 }),
    { active: 0, pending_review: 0, closed: 0, archived: 0 }
  );
  items = [...items].sort(byUpdatedDesc).map(enrich);
  return clone({ items, total: items.length, counts });
}

export async function getById(id) {
  if (!USE_MOCK_API) {
    const { data } = await api.get(`/investigations/${id}`);
    return data;
  }
  await mockLatency();
  const record = store.find((c) => c.id === id);
  if (!record) {
    const err = new Error(`Investigation "${id}" was not found.`);
    err.status = 404;
    throw err;
  }
  return clone(enrich(record));
}

export async function create(payload) {
  if (!USE_MOCK_API) {
    const { data } = await api.post('/investigations', payload);
    return data;
  }
  await mockLatency(420);
  const now = new Date().toISOString();
  const record = {
    id: `inv-${Date.now()}`,
    code: nextCode(),
    title: payload.title,
    caseType: payload.caseType || 'other',
    summary: payload.summary || payload.description?.slice(0, 140) || '',
    description: payload.description || '',
    status: 'active',
    priority: payload.priority || 'medium',
    leadId: payload.leadId || null,
    teamIds: payload.teamIds || [],
    tags: payload.tags || [],
    jurisdiction: payload.jurisdiction || '',
    openedAt: now,
    updatedAt: now,
  };
  store.unshift(record);
  return clone(enrich(record));
}

export async function update(id, patch) {
  if (!USE_MOCK_API) {
    const { data } = await api.patch(`/investigations/${id}`, patch);
    return data;
  }
  await mockLatency();
  const index = store.findIndex((c) => c.id === id);
  if (index === -1) {
    const err = new Error(`Investigation "${id}" was not found.`);
    err.status = 404;
    throw err;
  }
  store[index] = { ...store[index], ...patch, updatedAt: new Date().toISOString() };
  return clone(enrich(store[index]));
}

/** Aggregate counters for the dashboard. */
export async function getDashboardStats() {
  if (!USE_MOCK_API) {
    const { data } = await api.get('/investigations/stats');
    return data;
  }
  await mockLatency();
  const statusCounts = {
    active: 0,
    pending_review: 0,
    closed: 0,
    archived: 0,
  };
  store.forEach((c) => {
    statusCounts[c.status] = (statusCounts[c.status] || 0) + 1;
  });
  return clone({
    activeCases: statusCounts.active + statusCounts.pending_review,
    underReview: statusCounts.pending_review,
    evidenceLogged: mockEvidence.length,
    entitiesTracked: mockEntities.length,
    relationshipsTracked: mockRelationships.length,
    insightsPending: mockInsights.filter((i) => i.status === 'new').length,
    statusCounts,
  });
}

/** Dashboard activity feed (mock UI events; backend event bus in production). */
export async function getRecentActivity(limit = 8) {
  if (!USE_MOCK_API) {
    const { data } = await api.get('/activity', { params: { limit } });
    return data;
  }
  await mockLatency(180);
  const items = [...mockActivity]
    .sort((a, b) => new Date(b.at) - new Date(a.at))
    .slice(0, limit)
    .map((event) => {
      const inv = store.find((c) => c.id === event.investigationId);
      const section = ACTIVITY_TYPES[event.type] ? { evidence_added: 'evidence', entity_match: 'network', relationship_detected: 'network', timeline_updated: 'timeline', report_generated: 'reports' }[event.type] : '';
      return {
        ...event,
        caseCode: inv?.code || '—',
        to: inv ? `/investigations/${inv.id}${section ? `/${section}` : ''}` : '/investigations',
      };
    });
  return clone({ items, total: items.length });
}

/**
 * Case-scoped activity for the investigation overview. Combines recorded
 * feed events with derived timeline updates — presentation-only mock.
 */
export async function getInvestigationActivity(investigationId, limit = 6) {
  if (!USE_MOCK_API) {
    const { data } = await api.get(`/investigations/${investigationId}/activity`, { params: { limit } });
    return data;
  }
  await mockLatency(150);
  const inv = store.find((c) => c.id === investigationId);

  const recorded = mockActivity
    .filter((event) => event.investigationId === investigationId)
    .map((event) => ({
      id: event.id,
      type: event.type,
      message: event.message,
      detail: event.detail,
      at: event.at,
      to: '/investigations/' + investigationId,
    }));

  const derived = mockEvents
    .filter((e) => e.investigationId === investigationId)
    .sort((a, b) => new Date(b.datetime) - new Date(a.datetime))
    .slice(0, 4)
    .map((e) => ({
      id: `act-${e.id}`,
      type: 'timeline_updated',
      message: 'Timeline updated',
      detail: e.title,
      at: e.datetime,
      to: `/investigations/${investigationId}/timeline`,
    }));

  const items = [...recorded, ...derived]
    .sort((a, b) => new Date(b.at) - new Date(a.at))
    .slice(0, limit);
  return clone({ items, caseCode: inv?.code || '', total: items.length });
}

/** Cross-domain frontend search over investigations, entities and evidence. */
export async function globalSearch(query) {
  if (!USE_MOCK_API) {
    const { data } = await api.get('/search', { params: { query } });
    return data;
  }
  await mockLatency(160);
  const term = String(query).trim().toLowerCase();
  if (term.length < 2) return { investigations: [], entities: [], evidence: [], total: 0 };

  const investigations = store
    .filter((c) => [c.title, c.code, c.caseType, c.jurisdiction, ...(c.tags || [])].join(' ').toLowerCase().includes(term))
    .slice(0, 4)
    .map((c) => ({
      id: c.id,
      label: c.title,
      sub: `${c.code} · ${caseTypeLabel(c.caseType)}`,
      to: `/investigations/${c.id}`,
    }));

  const entities = mockEntities
    .filter((e) => [e.name, ...(e.aliases || []), e.role, e.notes || ''].join(' ').toLowerCase().includes(term))
    .slice(0, 5)
    .map((e) => ({
      id: e.id,
      label: e.name,
      sub: `${e.role || 'Entity'} · ${store.find((c) => c.id === e.investigationId)?.code || ''}`,
      to: `/investigations/${e.investigationId}/network?entity=${e.id}`,
    }));

  const evidence = mockEvidence
    .filter((ev) => [ev.title, ev.refNo, ev.source, ...(ev.tags || [])].join(' ').toLowerCase().includes(term))
    .slice(0, 4)
    .map((ev) => ({
      id: ev.id,
      label: ev.title,
      sub: `${ev.refNo} · ${store.find((c) => c.id === ev.investigationId)?.code || ''}`,
      to: `/investigations/${ev.investigationId}/evidence`,
    }));

  const events = mockEvents
    .filter((e) => [e.title, e.source, e.locationName || ''].join(' ').toLowerCase().includes(term))
    .slice(0, 3)
    .map((e) => ({
      id: e.id,
      label: e.title,
      sub: `${new Date(e.datetime).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })} · event`,
      to: `/investigations/${e.investigationId}/timeline`,
    }));

  const locations = mockLocations
    .filter((l) => [l.name, l.address || '', l.notes || ''].join(' ').toLowerCase().includes(term))
    .slice(0, 3)
    .map((l) => ({
      id: l.id,
      label: l.name,
      sub: l.address || 'Mapped location',
      to: `/investigations/${l.investigationId}/map`,
    }));

  const relationships = mockRelationships
    .filter((r) => {
      const a = mockEntities.find((e) => e.id === r.sourceId);
      const b = mockEntities.find((e) => e.id === r.targetId);
      return [r.label || '', a?.name || '', b?.name || ''].join(' ').toLowerCase().includes(term);
    })
    .slice(0, 3)
    .map((r) => {
      const a = mockEntities.find((e) => e.id === r.sourceId);
      const b = mockEntities.find((e) => e.id === r.targetId);
      return {
        id: r.id,
        label: `${a?.name || 'Entity A'} ↔ ${b?.name || 'Entity B'}`,
        sub: r.label || 'Relationship',
        to: `/investigations/${r.investigationId}/network?entity=${r.sourceId}`,
      };
    });

  return clone({
    investigations,
    entities,
    evidence,
    events,
    locations,
    relationships,
    total:
      investigations.length + entities.length + evidence.length +
      events.length + locations.length + relationships.length,
  });
}
