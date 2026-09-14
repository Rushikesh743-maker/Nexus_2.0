/**
 * v1 document services — upload, processing, and the review workflow.
 *
 * Live-backed only, on the shared v1 client (JWT + normalized errors).
 * There is deliberately no mock fallback: document states shown in the UI
 * are whatever the backend reports, and nothing pretends to be processed.
 */
import { request } from './client';

export function uploadDocument(caseId, file) {
  const form = new FormData();
  form.append('file', file, file.name);
  return request('post', `/cases/${caseId}/documents`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  });
}

export function listCaseDocuments(caseId) {
  return request('get', `/cases/${caseId}/documents`);
}

export function getDocument(documentId) {
  return request('get', `/documents/${documentId}`);
}

export function getDocumentStatus(documentId) {
  return request('get', `/documents/${documentId}/status`);
}

/** Start or retry processing. Returns 202 while work is in flight. */
export function processDocument(documentId) {
  return request('post', `/documents/${documentId}/process`);
}

export function getExtraction(documentId) {
  return request('get', `/documents/${documentId}/extraction`);
}

// ------------------------------------------------------------------ review

export function acceptCandidate(documentId, candidateId) {
  return request('post', `/documents/${documentId}/extraction/candidates/${candidateId}/accept`);
}

export function rejectCandidate(documentId, candidateId, note) {
  return request('post', `/documents/${documentId}/extraction/candidates/${candidateId}/reject`, { note });
}

export function deferCandidate(documentId, candidateId) {
  return request('post', `/documents/${documentId}/extraction/candidates/${candidateId}/defer`);
}

export function acceptRelationship(documentId, relId) {
  return request('post', `/documents/${documentId}/extraction/relationships/${relId}/accept`);
}

export function rejectRelationship(documentId, relId, note) {
  return request('post', `/documents/${documentId}/extraction/relationships/${relId}/reject`, { note });
}

export function acceptMatch(documentId, matchId) {
  return request('post', `/documents/${documentId}/extraction/matches/${matchId}/accept`);
}

export function rejectMatch(documentId, matchId) {
  return request('post', `/documents/${documentId}/extraction/matches/${matchId}/reject`);
}

export default {
  uploadDocument, listCaseDocuments, getDocument, getDocumentStatus,
  processDocument, getExtraction,
  acceptCandidate, rejectCandidate, deferCandidate,
  acceptRelationship, rejectRelationship, acceptMatch, rejectMatch,
};
