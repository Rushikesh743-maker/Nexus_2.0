import { USE_MOCK_API, api, mockLatency, clone } from './api';
import { HYPOTHESIS_TEMPLATES, GAP_TEMPLATES, MOCK_NOTIFICATIONS } from '@/mock/mockAnalysis';
import * as intelligenceService from './intelligenceService';
import * as evidenceService from './evidenceService';
import { RELATIONSHIP_TYPES } from '@/lib/constants';
import { hashString } from '@/lib/utils';
import * as cnaService from './cnaService';

/**
 * NEXUS Intelligence — mock analysis service.
 *
 * FRONTEND MOCK: every function resolves clearly-labelled presentation data
 * (deterministically derived from the case's own mock records). None of the
 * engines (contradiction detection, hypothesis assessment, gap detection,
 * impact simulation, re-evaluation, copilot) exist yet — swap each function
 * for its backend/AI API without touching the UI. `askCopilot` is the
 * future streaming hook.
 */

async function caseDataset(investigationId) {
  const [network, evidenceList] = await Promise.all([
    intelligenceService.getNetwork(investigationId),
    evidenceService.list(investigationId),
  ]);
  // `evidenceService.list` answers with { items, total }; every consumer below
  // treats `evidence` as a plain array.
  const evidence = evidenceList?.items ?? [];
  const byId = Object.fromEntries(network.entities.map((e) => [e.id, e]));
  const rels = [...network.relationships].sort((a, b) => b.strength - a.strength);
  const named = (r) => {
    const a = byId[r.sourceId]?.name || 'Entity A';
    const b = byId[r.targetId]?.name || 'Entity B';
    const meta = RELATIONSHIP_TYPES[r.type] || RELATIONSHIP_TYPES.associate;
    return { a, b, label: r.label || meta.label };
  };
  return { network, evidence, rels, named };
}

/* ---------- Intelligence Center summary ---------- */

export async function getSummary(investigationId) {
  if (!USE_MOCK_API) {
    const { data } = await api.get(`/investigations/${investigationId}/analysis/summary`);
    return data;
  }
  await mockLatency(140);
  const { rels, evidence } = await caseDataset(investigationId);
  const h = hashString(investigationId);
  return clone({
    // Mock value: a real confidence score is computed by backend services.
    confidence: rels.length ? Math.round(rels.reduce((s, r) => s + r.strength, 0) / rels.length) : 60,
    conflictingEvidence: 2 + (h % 3),
    openGaps: GAP_TEMPLATES.length,
    activeHypotheses: HYPOTHESIS_TEMPLATES.length,
    evidenceCount: evidence.length,
  });
}

/* ---------- Contradiction Engine (real backend) ---------- */

/**
 * Contradictions are the one intelligence surface that is no longer mocked:
 * they are computed by `backend/app/intelligence/contradiction_engine.py` from
 * the ingested corpus and served by `GET /cna-api/contradictions`.
 *
 * That engine analyses the case the analysis backend holds, and it is a
 * single-case service. A mock investigation has no counterpart in it, so this
 * function reports that plainly rather than returning the invented supporting
 * and contradicting records it used to generate. Showing one case's real
 * contradictions under another case's name would be worse than showing none.
 *
 * `investigation.analysisBackend === 'cna'` marks the backend-backed case; its
 * contradictions are rendered by `pages/analysis/ConflictsPage`.
 */
export async function getContradictions(investigationId, { analysisBackend } = {}) {
  if (analysisBackend !== 'cna') {
    return clone({
      items: [],
      total: 0,
      unavailable: true,
      reason:
        'Contradiction analysis runs in the analysis backend against its ingested corpus. ' +
        'This case is not backed by it, so no contradictions can be computed for it.',
    });
  }
  const data = await cnaService.getContradictions();
  return data;
}

/* ---------- Competing Hypotheses (mock presentation) ---------- */

export async function getHypotheses(investigationId) {
  if (!USE_MOCK_API) {
    const { data } = await api.get(`/investigations/${investigationId}/analysis/hypotheses`);
    return data;
  }
  await mockLatency();
  const { rels } = await caseDataset(investigationId);
  const base = rels[0]?.strength || 60;
  const items = HYPOTHESIS_TEMPLATES.map((t, i) => ({
    ...t,
    confidence: Math.max(8, base - i * 17 - (hashString(investigationId + t.id) % 6)),
    supportingCount: 3 - i > 0 ? 3 - i : 1,
    contradictingCount: i,
  }));
  return clone({ items, total: items.length });
}

/* ---------- Investigation Gap Detector (mock presentation) ---------- */

export async function getGaps(investigationId) {
  if (!USE_MOCK_API) {
    const { data } = await api.get(`/investigations/${investigationId}/analysis/gaps`);
    return data;
  }
  await mockLatency();
  return clone({
    items: GAP_TEMPLATES.map((g, i) => ({ ...g, id: `gap-${i + 1}` })),
    total: GAP_TEMPLATES.length,
  });
}

/* ---------- Evidence Impact Simulator (mock) ---------- */

export async function simulateEvidenceRemoval(investigationId, evidenceId) {
  if (!USE_MOCK_API) {
    const { data } = await api.post(`/investigations/${investigationId}/analysis/simulate`, { evidenceId });
    return data;
  }
  await mockLatency(600);
  const { rels, evidence, named } = await caseDataset(investigationId);
  const target = evidence.find((e) => e.id === evidenceId);
  const rel = rels[0];
  const names = rel ? named(rel) : { a: 'A', b: 'B' };
  const h = hashString(evidenceId || 'x');
  return clone({
    evidence: target ? { id: target.id, refNo: target.refNo, title: target.title } : null,
    affectedRelationship: rel
      ? { id: rel.id, label: `${names.a} ↔ ${names.b}`, relationshipLabel: names.label, before: rel.strength, after: Math.max(12, rel.strength - 25 - (h % 15)) }
      : null,
    affectedHypothesis: { id: 'H1', title: HYPOTHESIS_TEMPLATES[0].title },
    leadsAffected: 1 + (h % 3),
  });
}

/* ---------- Dynamic Re-evaluation (mock) ---------- */

export async function getReevaluation(investigationId) {
  if (!USE_MOCK_API) {
    const { data } = await api.get(`/investigations/${investigationId}/analysis/reevaluation`);
    return data;
  }
  await mockLatency(180);
  const { evidence, rels, named } = await caseDataset(investigationId);
  const latest = evidence[0];
  const rel = rels[0];
  const names = rel ? named(rel) : { a: 'A', b: 'B' };
  return clone({
    evidence: latest ? { refNo: latest.refNo, title: latest.title } : { refNo: '—', title: 'the latest record' },
    changes: [
      { id: 'ch-1', icon: 'Share2', label: `${Math.min(3, rels.length)} relationships changed`, detail: `${names.a} ↔ ${names.b} reassessed` },
      { id: 'ch-2', icon: 'Lightbulb', label: '2 hypotheses changed', detail: 'H1 and H2 confidence updated' },
      { id: 'ch-3', icon: 'CheckCircle2', label: '1 contradiction resolved', detail: 'Timeline conflict closed' },
      { id: 'ch-4', icon: 'Search', label: '2 new gaps identified', detail: 'Second-source statement · device attribution' },
    ],
  });
}

/* ---------- Notifications (mock global feed) ---------- */

export async function getNotifications() {
  if (!USE_MOCK_API) {
    const { data } = await api.get('/notifications');
    return data;
  }
  await mockLatency(120);
  const now = Date.now();
  return clone({
    items: MOCK_NOTIFICATIONS.map((n) => ({
      ...n,
      at: new Date(now - n.minutesAgo * 60000).toISOString(),
    })),
    unread: 3,
  });
}

/* ---------- Investigation Copilot (mock — future streaming hook) ---------- */

/**
 * Mock copilot: keyword-matched canned responses over the case's own data.
 * Replace with a streaming backend endpoint (SSE/WebSocket) — the UI only
 * awaits this function and renders the returned message + links.
 */
export async function askCopilot(investigationId, question) {
  if (!USE_MOCK_API) {
    const { data } = await api.post(`/investigations/${investigationId}/copilot`, { question });
    return data;
  }
  await mockLatency(700 + Math.random() * 600);
  const { rels, evidence, named } = await caseDataset(investigationId);
  const rel = rels[0];
  const names = rel ? named(rel) : { a: 'the tracked entities', b: '' };
  const q = question.toLowerCase();
  const evidenceId = evidence[0]?.id;

  if (q.includes('connect') || q.includes('why') || q.includes('relationship')) {
    return clone({
      answer: `${names.a} and ${names.b} have ${Math.max(2, rels.length - 1)} recorded links — ${names.label.toLowerCase()} is the strongest at ${rel?.strength || 0}% analyst confidence. Supporting records back the link; one timeline record conflicts with the current assessment.`,
      links: evidenceId ? [{ label: 'View Evidence', to: `/investigations/${investigationId}/evidence?evidence=${evidenceId}` }] : [],
    });
  }
  if (q.includes('contradict') || q.includes('conflict')) {
    return clone({
      answer: 'The contradiction engine flags one relationship with conflicting records: a witness statement that does not match the recorded timeline. Confidence for that link is revised down until resolved.',
      links: [{ label: 'Open Contradictions', to: `/investigations/${investigationId}/intelligence?tab=contradictions` }],
    });
  }
  if (q.includes('change') || q.includes('new evidence') || q.includes('re-evaluat')) {
    return clone({
      answer: 'After the latest evidence was processed, several relationships were reassessed, two hypotheses shifted and two new gaps were identified. Open the re-evaluation panel for the full change list.',
      links: [{ label: 'Review Changes', to: `/investigations/${investigationId}/intelligence` }],
    });
  }
  if (q.includes('missing') || q.includes('gap') || q.includes('next')) {
    return clone({
      answer: 'The most impactful open gap is independent location verification — current movement assessments rest on a single source. Vehicle ownership and remaining-period call records follow.',
      links: [{ label: 'Investigation Gaps', to: `/investigations/${investigationId}/intelligence?tab=gaps` }],
    });
  }
  return clone({
    answer: `This case currently tracks ${evidence.length} evidence records and ${rels.length} relationships. Ask me why two entities are connected, what contradicts a relationship, what changed after new evidence, or what information is missing.`,
    links: [],
  });
}
