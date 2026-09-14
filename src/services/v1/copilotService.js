/**
 * v1 copilot — platform status + the stage-5 case-scoped console API.
 *
 * The case copilot answers over CONFIRMED case data only (deterministic
 * engine), cites every record it uses, and answers in the language the
 * investigator asked (EN/HI/MR/UR). These calls are read-only except for
 * the impact simulation, which changes nothing (simulation_only).
 */
import { request } from './client';

/** Platform capability statement: GET /copilot */
export function status() {
  return request('get', '/copilot');
}

/** Per-case engine status: GET /cases/{id}/copilot/status */
export function caseStatus(caseId) {
  return request('get', `/cases/${caseId}/copilot/status`);
}

/** Data-driven suggested questions: GET /cases/{id}/copilot/suggestions */
export function suggestions(caseId) {
  return request('get', `/cases/${caseId}/copilot/suggestions`);
}

/** Ask the copilot: POST /cases/{id}/copilot/ask  (INVESTIGATOR+) */
export function ask(caseId, question) {
  return request('post', `/cases/${caseId}/copilot/ask`, { question });
}

/** Simulate removing one evidence record (changes nothing): POST /impact */
export function impact(caseId, evidenceId) {
  return request('post', `/cases/${caseId}/copilot/impact`, {
    evidence_id: evidenceId,
  });
}

/** Multilingual NLQ search over confirmed records: POST /nlq/search */
export function nlqSearch(caseId, query, k = 20) {
  return request('post', `/cases/${caseId}/copilot/nlq/search`, { query, k });
}

export default { status, caseStatus, suggestions, ask, impact, nlqSearch };
