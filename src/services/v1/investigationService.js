/**
 * v1 investigation intelligence services (stage 4) — the case-scoped
 * investigation reasoning & evidence intelligence API.
 *
 * Live-backed only, on the shared v1 client (JWT + normalized errors).
 * All results are analytical over CONFIRMED case data: potential leads
 * for investigator review, never proof or conclusions.
 */
import { request } from './client';

/** Run the full investigation analysis (idempotent per data version). */
export function analyzeInvestigation(caseId) {
  return request('post', `/cases/${caseId}/investigation/analyze`, {});
}

/** Analysis state: not-analyzed / up-to-date / stale / insufficient. */
export function getInvestigationStatus(caseId) {
  return request('get', `/cases/${caseId}/investigation/status`);
}

/** All stage-4 findings (current run + stale history). */
export function listInvestigationFindings(caseId, { includeStale = true } = {}) {
  return request('get', `/cases/${caseId}/investigation/findings`, null, {
    params: { include_stale: includeStale },
  });
}

/** Phase 2: one finding resolved to its full evidence chain
 *  (entities / relationships / evidence behind it, plus explicit
 *  "missing" notes when a link has no rows). */
export function getFindingDetail(caseId, findingId) {
  return request('get', `/cases/${caseId}/investigation/findings/${findingId}`);
}

/** Potential contradictions only. */
export function listContradictions(caseId, { includeStale = true } = {}) {
  return request('get', `/cases/${caseId}/investigation/contradictions`, null, {
    params: { include_stale: includeStale },
  });
}

/** Potential investigation gaps only. */
export function listInvestigationGaps(caseId, { includeStale = true } = {}) {
  return request('get', `/cases/${caseId}/investigation/gaps`, null, {
    params: { include_stale: includeStale },
  });
}

/** Competing hypotheses with transparent scores. */
export function listHypotheses(caseId, { includeStale = true } = {}) {
  return request('get', `/cases/${caseId}/investigation/hypotheses`, null, {
    params: { include_stale: includeStale },
  });
}

/** Investigator-created hypothesis (scored with the same formula). */
export function createHypothesis(caseId, payload) {
  return request('post', `/cases/${caseId}/investigation/hypotheses`, payload);
}

/** Per-evidence analytical linkage + impact scores. */
export function getEvidenceImpact(caseId) {
  return request('get', `/cases/${caseId}/investigation/evidence-impact`);
}

/** Impact of one evidence record. */
export function getEvidenceImpactOne(caseId, evidenceId) {
  return request('get', `/cases/${caseId}/investigation/evidence/${evidenceId}/impact`);
}

/** In-memory removal simulation — never deletes or modifies anything. */
export function simulateEvidenceImpact(caseId, evidenceId) {
  return request('post', `/cases/${caseId}/investigation/evidence/${evidenceId}/simulate-impact`, {});
}

/** Timeline intelligence results (overlaps, proximity, sequence, gaps). */
export function getTimelineAnalysis(caseId) {
  return request('get', `/cases/${caseId}/investigation/timeline`);
}

/** Geospatial results (co-location, proximity, sequence) + observations. */
export function getGeospatialAnalysis(caseId) {
  return request('get', `/cases/${caseId}/investigation/geospatial`);
}

/** Review or dismiss a stage-4 finding (kept auditable, never deleted). */
export function reviewInvestigationFinding(caseId, findingId, note) {
  return request('post', `/cases/${caseId}/investigation/findings/${findingId}/review`, note ? { note } : {});
}

export function dismissInvestigationFinding(caseId, findingId, note) {
  return request('post', `/cases/${caseId}/investigation/findings/${findingId}/dismiss`, note ? { note } : {});
}

/** Review or dismiss a hypothesis. */
export function reviewHypothesis(caseId, hypothesisId, note) {
  return request('post', `/cases/${caseId}/investigation/hypotheses/${hypothesisId}/review`, note ? { note } : {});
}

export function dismissHypothesis(caseId, hypothesisId, note) {
  return request('post', `/cases/${caseId}/investigation/hypotheses/${hypothesisId}/dismiss`, note ? { note } : {});
}
