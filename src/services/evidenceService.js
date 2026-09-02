import { USE_MOCK_API, api, mockLatency, clone } from './api';
import { mockEvidence } from '@/mock/mockEvidence';
import { ACCEPTED_EXTENSIONS } from '@/lib/constants';
import { hashString } from '@/lib/utils';

/**
 * Evidence service. Mock mode works on the in-memory mock store;
 * API mode maps onto /investigations/:id/evidence endpoints.
 *
 * UI components call these functions only — no transport or upload logic
 * lives in components.
 */

const store = [...mockEvidence];

const byCollectedDesc = (a, b) => new Date(b.collectedAt) - new Date(a.collectedAt);

const DAY_MS = 24 * 60 * 60 * 1000;

function extOf(name = '') {
  const match = name.toLowerCase().match(/\.([a-z0-9]+)$/);
  return match ? match[1] : '';
}

function randomHash() {
  const bytes = new Uint8Array(8);
  (globalThis.crypto || {}).getRandomValues?.(bytes) ||
    bytes.forEach((_, i) => (bytes[i] = Math.floor(Math.random() * 256)));
  return `sha256:${Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')}`;
}

const TEXTUAL_EXTENSIONS = ['pdf', 'docx', 'txt', 'csv', 'xlsx', 'json'];

const EXT_CATEGORY_MAP = {
  pdf: 'document',
  docx: 'document',
  txt: 'document',
  csv: 'digital',
  xlsx: 'digital',
  json: 'digital',
  jpg: 'image',
  jpeg: 'image',
  png: 'image',
};

function languageFor(ext, hash) {
  if (!TEXTUAL_EXTENSIONS.includes(ext)) return null;
  return ['English', 'Marathi', 'Hindi'][hash % 3];
}

/** Deterministic per-file outcome so the demo shows all lifecycle states. */
function outcomeFor(seed) {
  const hash = hashString(seed);
  if (hash % 13 === 0) return 'failed';
  if (hash % 8 === 0) return 'needs_review';
  return 'processed';
}

/* ---------- queries ---------- */

export async function list(
  investigationId,
  { search = '', fileType = 'all', language = 'all', status = 'all', uploadedWithin = 'all' } = {}
) {
  if (!USE_MOCK_API) {
    const { data } = await api.get(`/investigations/${investigationId}/evidence`, {
      params: { search, fileType, language, status, uploadedWithin },
    });
    return data;
  }
  await mockLatency();
  const term = search.trim().toLowerCase();
  const cutoff = uploadedWithin === 'all' ? 0 : Date.now() - parseInt(uploadedWithin, 10) * DAY_MS;

  let items = store.filter((e) => {
    if (e.investigationId !== investigationId) return false;
    if (fileType !== 'all' && (e.fileType || '') !== fileType) return false;
    if (language !== 'all') {
      if (language === 'unknown') {
        if (e.language) return false;
      } else if (e.language !== language) return false;
    }
    if (status !== 'all' && e.status !== status) return false;
    if (cutoff && new Date(e.collectedAt).getTime() < cutoff) return false;
    if (term) {
      const haystack = [e.title, e.refNo, e.category, e.source, e.language, ...(e.tags || [])]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      if (!haystack.includes(term)) return false;
    }
    return true;
  });

  items = [...items].sort(byCollectedDesc);
  return clone({ items, total: items.length });
}

/** Summary counters for the evidence page header. */
export async function getStats(investigationId) {
  if (!USE_MOCK_API) {
    const { data } = await api.get(`/investigations/${investigationId}/evidence/stats`);
    return data;
  }
  await mockLatency(120);
  const items = store.filter((e) => e.investigationId === investigationId);
  return clone({
    total: items.length,
    processed: items.filter((e) => e.status === 'processed').length,
    processing: items.filter((e) => e.status === 'processing').length,
    needsReview: items.filter((e) => e.status === 'needs_review').length,
    failed: items.filter((e) => e.status === 'failed').length,
    uploaded: items.filter((e) => e.status === 'uploaded').length,
  });
}

export async function get(id) {
  if (!USE_MOCK_API) {
    const { data } = await api.get(`/evidence/${id}`);
    return data;
  }
  await mockLatency();
  const record = store.find((e) => e.id === id);
  if (!record) {
    const err = new Error(`Evidence "${id}" was not found.`);
    err.status = 404;
    throw err;
  }
  return clone(record);
}

/* ---------- mutations ---------- */

/**
 * Upload evidence files for an investigation.
 *
 * Mock mode simulates the full lifecycle per file: upload progress ticks →
 * "processing" delay → terminal status (processed | needs_review | failed),
 * reporting every transition through `onProgress(fileName, update)` so the
 * UI can render realistic progress without any transport code.
 *
 * files: Array<{ name, size }> or real File objects (only name/size are read).
 */
export async function uploadFiles(investigationId, files, { onProgress, uploadedBy = 'Unassigned' } = {}) {
  if (!USE_MOCK_API) {
    const form = new FormData();
    files.forEach((file) => form.append('files', file));
    const { data } = await api.post(`/investigations/${investigationId}/evidence/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  }

  const created = [];
  for (const file of files) {
    const ext = extOf(file.name);
    const canonicalExt = ext === 'jpeg' ? 'jpg' : ext;

    if (!ACCEPTED_EXTENSIONS.includes(canonicalExt)) {
      onProgress?.(file.name, {
        phase: 'failed',
        status: 'failed',
        message: `Unsupported file type (.${ext || '?'})`,
      });
      continue;
    }

    const hash = hashString(`${file.name}:${file.size}`);

    // Phase 1 — simulated upload progress.
    let progress = 0;
    for (;;) {
      onProgress?.(file.name, { phase: 'uploading', progress });
      await new Promise((resolve) => setTimeout(resolve, 90 + (hash % (progress + 4)) * 10));
      progress = Math.min(100, progress + 7 + (hash % 17));
      if (progress >= 100) {
        onProgress?.(file.name, { phase: 'uploading', progress: 100 });
        break;
      }
    }

    // Phase 2 — simulated backend processing queue.
    onProgress?.(file.name, { phase: 'processing' });
    await new Promise((resolve) => setTimeout(resolve, 1500 + (hash % 1800)));

    // Phase 3 — terminal state + record creation.
    const outcome = outcomeFor(`${file.name}:${file.size}`);
    const now = new Date().toISOString();
    const custodyAction =
      outcome === 'failed'
        ? 'Automated processing failed'
        : outcome === 'needs_review'
          ? 'Automated processing flagged this file for review'
          : 'Automated processing completed';

    const record = {
      id: `ev-${Date.now()}-${created.length}`,
      investigationId,
      refNo: `EV/${String(store.length + 1).padStart(3, '0')}`,
      title: file.name,
      fileType: canonicalExt,
      category: null,
      type: EXT_CATEGORY_MAP[canonicalExt] || 'digital',
      size: Number(file.size) || 0,
      language: languageFor(canonicalExt, hash),
      status: outcome,
      description: '',
      source: 'Direct upload',
      collectedBy: uploadedBy,
      collectedAt: now,
      tags: ['upload'],
      hash: randomHash(),
      extractedEntities: outcome === 'processed' ? 2 + (hash % 22) : null,
      extractedEvents: outcome === 'processed' ? 1 + (hash % 10) : null,
      relationshipRefs: outcome === 'processed' ? hash % 5 : null,
      chainOfCustody: [
        { at: now, by: uploadedBy, action: 'Uploaded via NEXUS' },
        { at: now, by: 'Processing pipeline (mock)', action: custodyAction },
      ],
    };
    store.unshift(record);
    created.push(clone(record));
    onProgress?.(file.name, { phase: 'done', status: outcome, record });
  }
  return created;
}

export async function remove(id) {
  if (!USE_MOCK_API) {
    await api.delete(`/evidence/${id}`);
    return { ok: true };
  }
  await mockLatency();
  const index = store.findIndex((e) => e.id === id);
  if (index === -1) {
    const err = new Error(`Evidence "${id}" was not found.`);
    err.status = 404;
    throw err;
  }
  store.splice(index, 1);
  return { ok: true };
}
