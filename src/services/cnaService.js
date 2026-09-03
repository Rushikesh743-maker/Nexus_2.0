/**
 * Criminal-network-analysis service.
 *
 * Wraps the FastAPI backend in `backend/` (ingestion → extraction → identity
 * resolution → graph → analytics → findings). Unlike the rest of the service
 * layer this one has **no mock branch**: these screens exist to show real
 * pipeline output, so when the backend is not running they report that plainly
 * instead of substituting invented data.
 *
 * Every call carries an `X-Auth-Token`. The backend checks the caller's
 * permission, writes a hash-chained audit entry, and only then answers — so
 * the role selected here genuinely changes what comes back.
 */
import axios from 'axios';
import { storage } from '@/lib/storage';

export const CNA_BASE_URL = import.meta.env.VITE_CNA_API_BASE_URL || '/cna-api';

const ROLE_KEY = 'nexus.cna.role';

/** The two demo principals the backend ships with. */
export const CNA_ROLES = [
  {
    token: 'demo-investigator',
    role: 'investigator',
    label: 'Investigator',
    description: 'Read case data, run queries, generate reports, file new records.',
  },
  {
    token: 'demo-admin',
    role: 'admin',
    label: 'Administrator',
    description: 'Everything an investigator can do, plus the audit log, bulk ingest and exports.',
  },
];

export function getRoleToken() {
  const stored = storage.getItem(ROLE_KEY);
  return CNA_ROLES.some((r) => r.token === stored) ? stored : 'demo-investigator';
}

export function setRoleToken(token) {
  if (CNA_ROLES.some((r) => r.token === token)) storage.setItem(ROLE_KEY, token);
}

const cna = axios.create({ baseURL: CNA_BASE_URL, timeout: 30000 });

cna.interceptors.request.use((config) => {
  config.headers['X-Auth-Token'] = getRoleToken();
  return config;
});

/**
 * Normalise transport failures so the UI can distinguish "the backend is not
 * running" from "you are not allowed to see this" — two very different
 * messages for an investigator.
 */
export class CnaError extends Error {
  constructor(message, { status, offline = false, forbidden = false } = {}) {
    super(message);
    this.name = 'CnaError';
    this.status = status;
    this.offline = offline;
    this.forbidden = forbidden;
  }
}

const OFFLINE_MESSAGE =
  'The analysis backend is not reachable. Start it with ./start.sh (or backend/run.py) and reload.';

function toCnaError(error) {
  // No response at all: DNS/connection failure when the page is served by the
  // backend itself, or the request was aborted.
  if (!error?.response) return new CnaError(OFFLINE_MESSAGE, { offline: true });

  const { status, data } = error.response;
  const detail = typeof data?.detail === 'string' ? data.detail : null;

  if (status === 403) {
    return new CnaError(detail || 'Your role does not carry the permission for this view.', {
      status,
      forbidden: true,
    });
  }

  // The backend reports a missing optional capability as a 503 *with* a detail
  // explaining what to install.
  if (status === 503 && detail) return new CnaError(detail, { status });

  // A 5xx carrying no detail did not come from the application: in development
  // the Vite proxy answers 500 with an empty body when the target is down, and
  // a gateway in front of the API behaves the same way. Either means the
  // backend is not answering, which is what the analyst needs told.
  if (status >= 500 && !detail) return new CnaError(OFFLINE_MESSAGE, { status, offline: true });

  return new CnaError(detail || `Request failed (${status}).`, { status });
}

async function get(path, params) {
  try {
    const { data } = await cna.get(path, { params });
    return data;
  } catch (error) {
    throw toCnaError(error);
  }
}

async function post(path, body, config) {
  try {
    const { data } = await cna.post(path, body, config);
    return data;
  } catch (error) {
    throw toCnaError(error);
  }
}

/* ── identity ─────────────────────────────────────────────────────────── */

/** The principal the backend resolved from the current token. */
export const me = () => get('/me');

/* ── graph & statistics ───────────────────────────────────────────────── */

/** Pipeline + graph statistics, including which optional capabilities are active. */
export const getStats = () => get('/stats');

/** Case dashboard: tiles, severity split, findings by type, sources, weekly activity. */
export const getDashboard = () => get('/dashboard');

/**
 * Nodes and edges.
 * @param {{minConfidence?: number, edgeTypes?: string[], types?: string[]}} filters
 */
export const getGraph = ({ minConfidence = 0, edgeTypes, types } = {}) =>
  get('/graph', {
    min_confidence: minConfidence,
    edge_types: edgeTypes?.length ? edgeTypes.join(',') : undefined,
    types: types?.length ? types.join(',') : undefined,
  });

/** Flat entity list (id, label, type, aliases, phones, prior cases). */
export const getEntities = () => get('/entities');

/** Full subject profile: narrative, links with evidence strings, findings, influence. */
export const getEntity = (id) => get(`/entity/${encodeURIComponent(id)}`);

/* ── analytics ────────────────────────────────────────────────────────── */

/** Ranked key individuals with the exact Shapley attribution per component. */
export const getInfluencers = (limit = 25) => get('/influencers', { limit });

/** Detected sub-groups and the modularity of the partition. */
export const getCommunities = () => get('/communities');

/** Connection analysis between two subjects, with per-leg source records. */
export const getPath = (a, b, cutoff = 5) => get('/path', { a, b, cutoff });

/** The source records behind one link — the "why do you say this?" view. */
export const getEvidence = (a, b) => get('/evidence', { a, b });

/** Suspicious-pattern findings, optionally filtered to one severity. */
export const getFindings = (severity) => get('/findings', severity ? { severity } : undefined);

/** Links ranked by how many independent source systems support them. */
export const getCorroboration = (minLevel = 1) => get('/corroboration', { min_level: minLevel });

/* ── natural language ─────────────────────────────────────────────────── */

/**
 * Ask a question in plain English. The reply always restates the backend's own
 * interpretation, so a misread question is visible immediately.
 */
export const ask = (q) => post('/query', { q });

/* ── transparency ─────────────────────────────────────────────────────── */

/** What the extractor found and which identity merges were applied, with reasons. */
export const getPipeline = () => get('/pipeline');

/** One source document, verbatim. */
export const getDocument = (id) => get(`/document/${id}`);

/** What OCR read, at what confidence, and what it skipped. */
export const getOcr = () => get('/ocr');

/* ── reporting ────────────────────────────────────────────────────────── */

/** Case summary as markdown plus the statistics behind it. */
export const getOverview = () => get('/report/overview');

/* ── system, security & integrations ──────────────────────────────────── */

/** Roles, permissions and audit-encryption status. */
export const getSecurity = () => get('/security');

/** The audit log (administrators only). */
export const getAudit = (limit = 200) => get('/audit', { limit });

/** Re-walk the hash chain and name the first broken entry, if any. */
export const verifyAudit = () => get('/audit/verify');

/** CCTNS / ICJS adapter status and field mappings. */
export const getIntegrations = () => get('/integrations');

/** Fetch external records through an adapter. Authorisation is required. */
export const previewIntegration = (key, authorisation) =>
  get(`/integrations/${encodeURIComponent(key)}/preview`, { authorisation });

/* ── case intake ──────────────────────────────────────────────────────── */

/** What the intake forms must send — the UI builds itself from this. */
export const getCaseSchema = () => get('/case/schema');

/** File one new document; the pipeline reruns immediately. */
export const quickAdd = (kind, fields) => post('/case/quick-add', { kind, fields });

/** Load or replace a whole source file. */
export function uploadSource(kind, file, mode = 'append') {
  const form = new FormData();
  form.append('kind', kind);
  form.append('mode', mode);
  form.append('file', file);
  return post('/case/upload', form);
}

/** Re-run the whole pipeline from the current source files. */
export const reload = () => post('/reload');

/* ── downloads ────────────────────────────────────────────────────────── */

/**
 * Build an absolute URL for a binary endpoint (PDF, Cypher).
 *
 * These are fetched rather than linked because the backend authenticates on a
 * header, and a plain <a href> cannot carry one.
 */
function absolute(path, params) {
  const url = new URL(`${CNA_BASE_URL}${path}`, window.location.origin);
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null) url.searchParams.set(k, v);
  });
  return url.toString();
}

/**
 * Fetch a binary endpoint and hand the browser a download.
 * Returns the byte length so the caller can report what was produced.
 */
export async function download(path, filename, params) {
  let response;
  try {
    response = await cna.get(path, { params, responseType: 'blob' });
  } catch (error) {
    // A blob response body has to be read back as text before the message
    // inside it (e.g. "PDF export needs reportlab") can be surfaced.
    const blob = error?.response?.data;
    if (blob instanceof Blob) {
      try {
        const parsed = JSON.parse(await blob.text());
        if (parsed?.detail) {
          throw new CnaError(parsed.detail, {
            status: error.response.status,
            forbidden: error.response.status === 403,
          });
        }
      } catch (inner) {
        if (inner instanceof CnaError) throw inner;
      }
    }
    throw toCnaError(error);
  }

  const blob = new Blob([response.data], {
    type: response.headers['content-type'] || 'application/octet-stream',
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  return { bytes: blob.size, headers: response.headers };
}

/** Case summary as a court-ready PDF. */
export const downloadOverviewPdf = () =>
  download('/report/overview.pdf', 'network-analysis-summary.pdf');

/** Subject profile as a court-ready PDF. */
export const downloadEntityPdf = (id, label) =>
  download(`/entity/${encodeURIComponent(id)}/report.pdf`, `subject-${label || id}.pdf`);

/** Connection analysis as a court-ready PDF. */
export const downloadPathPdf = (a, b, cutoff = 5) =>
  download('/path.pdf', 'connection-analysis.pdf', { a, b, cutoff });

/** The whole graph as a loadable Cypher script. */
export const downloadCypher = () => download('/export/cypher', 'graph.cypher');

export { absolute as cnaUrl };
