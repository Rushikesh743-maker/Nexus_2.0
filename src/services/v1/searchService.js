import { request } from './client';

/**
 * Global investigation search across cases, entities, evidence, documents,
 * relationships, findings, hypotheses, and locations.
 */
export async function search(query, caseId = null, limit = 40) {
  if (!query || query.trim().length < 1) {
    return { query: '', total: 0, results: [], counts_by_type: {} };
  }
  const params = { q: query.trim(), limit };
  if (caseId) params.case_id = caseId;
  return request('get', '/search', null, { params });
}

export default { search };
