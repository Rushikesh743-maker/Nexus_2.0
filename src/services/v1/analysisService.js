/**
 * v1 case-workflow services (stage 6) — the ONE surface the case workspace
 * uses for processing state, one-call intelligence, graph, review queue,
 * summary and the case-scoped audit trail.
 *
 * Live-backed only, on the shared v1 client (JWT + normalized errors).
 * Every response is real persisted backend state — no progress percentages,
 * no canned data.
 */
import { request } from './client';

/** Run all intelligence for the case (idempotent per data version). */
export function runCaseAnalysis(caseId) {
  return request('post', `/cases/${caseId}/analysis/run`, {});
}

/** Real analysis/processing state for the case (one call). */
export function getAnalysisStatus(caseId) {
  return request('get', `/cases/${caseId}/analysis/status`);
}

/** Per-document processing states (async job polling). */
export function getProcessingStatus(caseId) {
  return request('get', `/cases/${caseId}/processing/status`);
}

/** All case counts from the database (one call). */
export function getCaseSummary(caseId) {
  return request('get', `/cases/${caseId}/summary`);
}

/** Rebuild the confirmed case graph (NetworkX, from confirmed data). */
export function buildCaseGraph(caseId) {
  return request('post', `/cases/${caseId}/graph/build`, {});
}

/** Graph nodes + edges with per-edge evidence provenance. */
export function getCaseGraph(caseId) {
  return request('get', `/cases/${caseId}/graph`);
}

/** The five human-review sections of the case. */
export function getReviewQueue(caseId) {
  return request('get', `/cases/${caseId}/review/queue`);
}

/** Case-scoped audit trail (read-only). */
export function getCaseAudit(caseId, { limit = 200 } = {}) {
  return request('get', `/cases/${caseId}/audit`, null, { params: { limit } });
}

export const analysisService = {
  runCaseAnalysis,
  getAnalysisStatus,
  getProcessingStatus,
  getCaseSummary,
  buildCaseGraph,
  getCaseGraph,
  getReviewQueue,
  getCaseAudit,
};
