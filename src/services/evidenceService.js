import { USE_MOCK_API, api, mockLatency, clone } from './api';
import { ACCEPTED_EXTENSIONS } from '@/lib/constants';
import { hashString } from '@/lib/utils';
import { evidenceStore as store } from './caseStore';
import { ingestEvidence, refreshInsights } from './extraction/ingest';

/**
 * Evidence service. Mock mode works on the in-memory mock store;
 * API mode maps onto /investigations/:id/evidence endpoints.
 *
 * UI components call these functions only — no transport or upload logic
 * lives in components.
 */

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

/**
 * Language is detected from the file's own text by the ingestion pipeline
 * (see `detectLanguage`). Non-textual formats simply have none.
 */
function languagePlaceholder(ext) {
  return TEXTUAL_EXTENSIONS.includes(ext) ? null : null;
}

/**
 * A file's terminal status is now the real outcome of the ingestion pipeline:
 * a document we could read and pull records from is `processed`; one we could
 * read but found nothing in, or could not text-extract at all, is flagged for
 * a human (`needs_review`) rather than silently passed.
 */
function outcomeFor(result) {
  if (!result.readable) return 'needs_review';
  if (!result.entities && !result.events) return 'needs_review';
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

    // Phase 2 — read and analyse the file for real.
    onProgress?.(file.name, { phase: 'processing' });

    const now = new Date().toISOString();
    const record = {
      id: `ev-${Date.now()}-${created.length}`,
      investigationId,
      refNo: `EV/${String(store.filter((e) => e.investigationId === investigationId).length + 1).padStart(3, '0')}`,
      title: file.name,
      fileType: canonicalExt,
      category: null,
      type: EXT_CATEGORY_MAP[canonicalExt] || 'digital',
      size: Number(file.size) || 0,
      language: languagePlaceholder(canonicalExt),
      status: 'processing',
      description: '',
      source: 'Direct upload',
      collectedBy: uploadedBy,
      collectedAt: now,
      tags: ['upload'],
      hash: randomHash(),
      extractedEntities: null,
      extractedEvents: null,
      relationshipRefs: null,
      chainOfCustody: [{ at: now, by: uploadedBy, action: 'Uploaded via NEXUS' }],
    };

    // `file` is the browser File when one was dropped in; the demo-file
    // shortcut stages name/size only, and the pipeline reports that plainly.
    let result;
    try {
      result = await ingestEvidence(investigationId, file.blob || file, record);
    } catch (err) {
      result = { readable: false, reason: err.message, entities: 0, events: 0, locations: 0, relationships: 0 };
    }

    // Phase 3 — terminal state + record creation.
    const outcome = outcomeFor(result);
    const finishedAt = new Date().toISOString();
    const custodyAction = result.readable
      ? `Extraction complete — ${result.entities} entities, ${result.events} events, ${result.locations} locations, ${result.relationships} links`
      : `Flagged for review — ${result.reason || 'no readable text'}`;

    record.status = outcome;
    record.language = result.language ?? record.language;
    record.extractedEntities = result.entities;
    record.extractedEvents = result.events;
    record.relationshipRefs = result.relationships;
    record.extractedLocations = result.locations;
    record.processingNote = result.reason || null;
    record.chainOfCustody.push({ at: finishedAt, by: 'NEXUS extraction pipeline', action: custodyAction });

    store.unshift(record);
    created.push(clone(record));
    onProgress?.(file.name, {
      phase: 'done',
      status: outcome,
      record,
      extracted: {
        entities: result.entities,
        events: result.events,
        locations: result.locations,
        relationships: result.relationships,
      },
      message: result.reason || null,
    });
  }

  // Insights are derived from the whole case, so they are rebuilt once every
  // file in the batch has landed.
  if (created.length) refreshInsights(investigationId);

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
