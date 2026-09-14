/**
 * v1 case services — the live-backed case area.
 *
 * Every function hits the platform API. There is no mock fallback here on
 * purpose: the case workspace shows what the backend actually holds, and the
 * pages render explicit offline/empty/error states instead of inventing data.
 */
import { request } from './client';

export function listCases() {
  return request('get', '/cases');
}

export function getCase(caseId) {
  return request('get', `/cases/${caseId}`);
}

export function createCase(payload) {
  return request('post', '/cases', payload);
}

export function listDocuments(caseId) {
  return request('get', `/cases/${caseId}/documents`);
}

export function listEntities(caseId) {
  return request('get', `/cases/${caseId}/entities`);
}

/** Phase 2: the full profile of one confirmed entity (connections with
 *  provenance, claims with original text, events, locations, findings,
 *  computed metrics, analysis freshness). */
export function getEntityProfile(caseId, entityId) {
  return request('get', `/cases/${caseId}/entities/${entityId}`);
}

/** Phase 2: immutable case snapshots (version 1..N) + current version. */
export function listSnapshots(caseId) {
  return request('get', `/cases/${caseId}/snapshots`);
}

export function createSnapshot(caseId, label) {
  return request('post', `/cases/${caseId}/snapshots`, label ? { label } : {});
}

export function getSnapshot(caseId, snapshotId) {
  return request('get', `/cases/${caseId}/snapshots/${snapshotId}`);
}

/** Pure diff of two immutable snapshots (new / removed / changed). */
export function compareSnapshots(caseId, fromSeq, toSeq) {
  return request('get', `/cases/${caseId}/snapshots/compare`, null, {
    params: { from_seq: fromSeq, to_seq: toSeq },
  });
}

export function listRelationships(caseId) {
  return request('get', `/cases/${caseId}/relationships`);
}

export function listEvidence(caseId) {
  return request('get', `/cases/${caseId}/evidence`);
}

export function listTimeline(caseId) {
  return request('get', `/cases/${caseId}/timeline`);
}

export function listLocations(caseId) {
  return request('get', `/cases/${caseId}/locations`);
}

export function listHypotheses(caseId) {
  return request('get', `/cases/${caseId}/hypotheses`);
}

export function listContradictions(caseId) {
  return request('get', `/cases/${caseId}/contradictions`);
}

export function listGaps(caseId) {
  return request('get', `/cases/${caseId}/gaps`);
}

export function listSimulations(caseId) {
  return request('get', `/cases/${caseId}/simulations`);
}

export function createSimulation(caseId, payload) {
  return request('post', `/cases/${caseId}/simulations`, payload);
}

export default {
  listCases, getCase, createCase,
  listDocuments, listEntities, getEntityProfile, listRelationships, listEvidence,
  listTimeline, listLocations, listHypotheses, listContradictions,
  listGaps, listSimulations, createSimulation,
  listSnapshots, createSnapshot, getSnapshot, compareSnapshots,
};
