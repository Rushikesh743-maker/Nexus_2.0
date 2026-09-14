/**
 * v1 graph intelligence services (stage 3) — analysis trigger, findings,
 * per-entity metrics, bridges, clusters, cross-case links and paths.
 *
 * Live-backed only, on the shared v1 client (JWT + normalized errors).
 * All results come from CONFIRMED case data; the service layer adds no
 * intelligence of its own.
 */
import { request } from './client';

/** Run the engine for the case; idempotent while the data is unchanged. */
export function analyzeCaseGraph(caseId) {
  return request('post', `/cases/${caseId}/graph/analyze`, {});
}

/** Current-run findings plus stale history (versioned by the backend). */
export function listGraphFindings(caseId, { includeStale = true } = {}) {
  return request('get', `/cases/${caseId}/graph/findings`, null, {
    params: { include_stale: includeStale },
  });
}

export function reviewFinding(caseId, findingId, note) {
  return request('post', `/cases/${caseId}/graph/findings/${findingId}/review`, note ? { note } : {});
}

export function dismissFinding(caseId, findingId, note) {
  return request('post', `/cases/${caseId}/graph/findings/${findingId}/dismiss`, note ? { note } : {});
}

export function getGraphMetrics(caseId) {
  return request('get', `/cases/${caseId}/graph/metrics`);
}

export function getGraphBridges(caseId) {
  return request('get', `/cases/${caseId}/graph/bridges`);
}

export function getGraphClusters(caseId) {
  return request('get', `/cases/${caseId}/graph/clusters`);
}

export function getGraphCrossCase(caseId) {
  return request('get', `/cases/${caseId}/graph/cross-case`);
}

export function findGraphPaths(caseId, sourceEntityId, targetEntityId, { maxDepth, maxPaths } = {}) {
  return request('get', `/cases/${caseId}/graph/paths`, null, {
    params: {
      source_entity_id: sourceEntityId,
      target_entity_id: targetEntityId,
      ...(maxDepth ? { max_depth: maxDepth } : {}),
      ...(maxPaths ? { max_paths: maxPaths } : {}),
    },
  });
}
