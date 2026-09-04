import { extractFromText } from './extractor';
import { readDocumentText } from '@/lib/documentText';
import {
  entityStore,
  relationshipStore,
  eventStore,
  locationStore,
  insightStore,
  eventLinks,
} from '../caseStore';

/**
 * Ingestion pipeline.
 *
 * Reads an uploaded evidence file, runs the extraction engine over its text
 * and commits the findings to the shared case store, so the Network, Timeline,
 * Map and Intelligence tabs are populated by the documents the user actually
 * uploaded rather than by seeded fixtures.
 *
 * Records already in the case are matched by name and reused — uploading a
 * second document about the same person adds mentions and links, it does not
 * create a duplicate node.
 */

let sequence = 0;
const nextId = (prefix) => `${prefix}-x${Date.now().toString(36)}${(sequence += 1).toString(36)}`;

const norm = (s) => String(s || '').toLowerCase().replace(/[^a-z0-9]/g, '');

const ENTITY_TYPE_ORDER = ['person', 'organization', 'phone_number', 'vehicle', 'bank_account', 'address', 'asset'];

/** Risk is never inferred from a document. Everything ingested starts neutral. */
const DEFAULT_RISK = 'low';

const RELATIONSHIP_RULES = [
  { when: (a, b) => pair(a, b, 'person', 'phone_number'), type: 'used', label: 'Number linked in record' },
  { when: (a, b) => pair(a, b, 'person', 'vehicle'), type: 'used', label: 'Vehicle linked in record' },
  { when: (a, b) => pair(a, b, 'person', 'bank_account'), type: 'financial', label: 'Account linked in record' },
  { when: (a, b) => pair(a, b, 'person', 'organization'), type: 'associate', label: 'Named together with' },
  { when: (a, b) => pair(a, b, 'person', 'address'), type: 'co_located', label: 'Address in record' },
  { when: (a, b) => pair(a, b, 'phone_number', 'phone_number'), type: 'communication', label: 'Numbers in same record' },
  { when: (a, b) => pair(a, b, 'person', 'person'), type: 'associate', label: 'Named in the same record' },
];

function pair(a, b, t1, t2) {
  return (a.type === t1 && b.type === t2) || (a.type === t2 && b.type === t1);
}

function relationshipFor(a, b) {
  const rule = RELATIONSHIP_RULES.find((r) => r.when(a, b));
  return rule ? { type: rule.type, label: rule.label } : { type: 'associate', label: 'Co-mentioned in evidence' };
}

/* ---------- store lookups ---------- */

function findEntity(investigationId, type, name) {
  const key = norm(name);
  return entityStore.find(
    (e) => e.investigationId === investigationId && e.type === type && norm(e.name) === key
  );
}

function findLocation(investigationId, name) {
  const key = norm(name);
  return locationStore.find((l) => l.investigationId === investigationId && norm(l.name) === key);
}

function entityCode(investigationId) {
  const count = entityStore.filter((e) => e.investigationId === investigationId).length + 1;
  return `ENT/${String(count).padStart(3, '0')}`;
}

function locationTypeFor(name) {
  const n = String(name).toLowerCase();
  if (/station|terminus|depot|stand|bus|airport|toll|highway|nh-|road|junction/.test(n)) return 'transit';
  if (/school|college|hospital|bank|hotel|cafe|mall|store|shop|club|office|godown|warehouse/.test(n)) return 'business';
  if (/flat|house|residence|society|apartment|colony/.test(n)) return 'residence';
  if (/tower|cell|cctv|camera/.test(n)) return 'surveillance';
  return null;
}

/** Event type → the kind of place it implies, for localities the name alone cannot classify. */
const TYPE_FROM_EVENT = {
  travel: 'transit',
  call: 'surveillance',
  surveillance: 'surveillance',
  transaction: 'business',
  meeting: 'business',
  search: 'crime_scene',
  incident: 'crime_scene',
  report: 'business',
};

/**
 * Classify a bare locality ("Swargate") by what the case records happening
 * there, rather than defaulting everything to "business".
 */
function classifyLocations(investigationId) {
  const events = eventStore.filter((e) => e.investigationId === investigationId);
  locationStore
    .filter((l) => l.investigationId === investigationId && l.extracted && !l.typeFromName)
    .forEach((location) => {
      const here = events.filter((e) => e.locationId === location.id);
      if (!here.length) return;
      const tally = {};
      here.forEach((e) => {
        const kind = TYPE_FROM_EVENT[e.type];
        if (kind) tally[kind] = (tally[kind] || 0) + 1;
      });
      const best = Object.keys(tally).sort((a, b) => tally[b] - tally[a])[0];
      if (best) location.type = best;
    });
}

/**
 * Script-based language detection.
 *
 * The old build assigned a language by hashing the file name, which is why an
 * English README could be labelled Hindi. This reads the actual characters:
 * Devanagari is separated into Marathi and Hindi by a handful of markers that
 * only occur in one of the two, and anything else is reported as English.
 */
function detectLanguage(text) {
  const devanagari = (text.match(/[\u0900-\u097F]/g) || []).length;
  const latin = (text.match(/[A-Za-z]/g) || []).length;
  if (devanagari > latin * 0.15 && devanagari > 20) {
    return /\u0933|\u0928\u094D\u0939\u0940|\u0906\u0939\u0947|\u092F\u093E\u0902\u091A\u094D\u092F\u093E/.test(text) ? 'Marathi' : 'Hindi';
  }
  if (latin > 0) return 'English';
  return null;
}

/* ---------- commit ---------- */

/**
 * Ingest a single evidence record.
 * @returns `{ readable, reason, entities, events, locations, relationships, insights }` counts
 */
export async function ingestEvidence(investigationId, file, evidenceRecord) {
  const { text, readable, reason } = await readDocumentText(file);
  if (!readable || !text.trim()) {
    return { readable: false, reason, language: null, entities: 0, events: 0, locations: 0, relationships: 0, newEntities: [] };
  }
  const language = detectLanguage(text);

  const findings = extractFromText(text, {
    fileName: evidenceRecord.title,
    evidenceId: evidenceRecord.id,
    evidenceRef: evidenceRecord.refNo,
  });

  const now = new Date().toISOString();
  /** extraction key → stored entity */
  const resolved = new Map();
  const newEntities = [];

  // Entities — strongest signal first so a person outranks a stray org match.
  const ordered = [...findings.candidates].sort(
    (a, b) => ENTITY_TYPE_ORDER.indexOf(a.type) - ENTITY_TYPE_ORDER.indexOf(b.type) || b.mentions - a.mentions
  );

  ordered.forEach((cand) => {
    // A one-off bare capitalised phrase is too weak to stand as a person on
    // its own; labelled fields and identifiers always pass.
    const weak = cand.type === 'person' && cand.mentions < 2 && cand.role === 'Named person';
    if (weak && findings.candidates.length > 6) return;

    let entity = findEntity(investigationId, cand.type, cand.name);
    if (entity) {
      entity.mentions = (entity.mentions || 1) + cand.mentions;
      if (!entity.sourceEvidenceIds) entity.sourceEvidenceIds = [];
      if (!entity.sourceEvidenceIds.includes(evidenceRecord.id)) entity.sourceEvidenceIds.push(evidenceRecord.id);
    } else {
      entity = {
        id: nextId('ent'),
        investigationId,
        code: entityCode(investigationId),
        type: cand.type,
        name: cand.name,
        aliases: [],
        role: cand.role || 'Extracted from evidence',
        risk: DEFAULT_RISK,
        notes: cand.lines[0] ? `Extracted from ${evidenceRecord.refNo} — "${cand.lines[0].slice(0, 160)}"` : `Extracted from ${evidenceRecord.refNo}.`,
        attributes: { extractedFrom: evidenceRecord.title, mentions: String(cand.mentions) },
        createdAt: now,
        mentions: cand.mentions,
        extracted: true,
        sourceEvidenceIds: [evidenceRecord.id],
      };
      entityStore.push(entity);
      newEntities.push(entity);
    }
    resolved.set(cand.key, entity);
  });

  // Locations
  const resolvedPlaces = new Map();
  findings.places.forEach((place) => {
    let location = findLocation(investigationId, place.name);
    if (!location) {
      location = {
        id: nextId('loc'),
        investigationId,
        name: place.name,
        type: locationTypeFor(place.name) || 'transit',
        typeFromName: Boolean(locationTypeFor(place.name)),
        lat: place.lat,
        lng: place.lng,
        address: place.address || place.name,
        notes: `Referenced in ${evidenceRecord.refNo} (${place.mentions} mention${place.mentions === 1 ? '' : 's'}).`,
        entityIds: [],
        lastActivityAt: place.lastActivityAt,
        extracted: true,
      };
      locationStore.push(location);
    } else if (place.lastActivityAt && (!location.lastActivityAt || place.lastActivityAt > location.lastActivityAt)) {
      location.lastActivityAt = place.lastActivityAt;
    }
    resolvedPlaces.set(place.key, location);
  });

  // Events
  let eventCount = 0;
  findings.events.forEach((event) => {
    const entityIds = [...new Set(event.entityKeys.map((k) => resolved.get(k)?.id).filter(Boolean))];
    const location = event.placeKey ? resolvedPlaces.get(event.placeKey) : null;

    const duplicate = eventStore.find(
      (e) =>
        e.investigationId === investigationId &&
        e.datetime === event.datetime &&
        norm(e.title) === norm(event.title)
    );
    if (duplicate) return;

    const record = {
      id: nextId('evt'),
      investigationId,
      type: event.type,
      title: event.title || 'Recorded activity',
      description: event.description,
      datetime: event.datetime,
      locationName: location?.name || event.locationName || null,
      locationId: location?.id || null,
      evidenceId: evidenceRecord.id,
      entityIds,
      source: `${evidenceRecord.refNo} · ${evidenceRecord.title}`,
      confidence: event.confidence,
      extracted: true,
    };
    eventStore.push(record);
    eventLinks[record.id] = { locationId: record.locationId, evidenceId: record.evidenceId };
    eventCount += 1;

    // Link the location to the entities present at it.
    if (location) {
      location.entityIds = [...new Set([...(location.entityIds || []), ...entityIds])];
    }
  });

  // Relationships from co-occurrence
  let relCount = 0;
  findings.coOccurrence.forEach(({ a, b, count, lines }) => {
    const ea = resolved.get(a);
    const eb = resolved.get(b);
    if (!ea || !eb || ea.id === eb.id) return;

    const existing = relationshipStore.find(
      (r) =>
        r.investigationId === investigationId &&
        ((r.sourceId === ea.id && r.targetId === eb.id) || (r.sourceId === eb.id && r.targetId === ea.id))
    );
    // Confidence is the co-occurrence count, capped — a transparent count,
    // not a model score.
    const strength = Math.min(95, 45 + count * 12);
    if (existing) {
      existing.strength = Math.max(existing.strength, strength);
      existing.cooccurrences = (existing.cooccurrences || 1) + count;
      return;
    }
    const { type, label } = relationshipFor(ea, eb);
    relationshipStore.push({
      id: nextId('rel'),
      investigationId,
      sourceId: ea.id,
      targetId: eb.id,
      type,
      label,
      strength,
      note: lines[0] ? `Co-mentioned in ${evidenceRecord.refNo}: "${lines[0].slice(0, 140)}"` : `Co-mentioned in ${evidenceRecord.refNo}.`,
      cooccurrences: count,
      extracted: true,
    });
    relCount += 1;
  });

  classifyLocations(investigationId);

  return {
    readable: true,
    reason: null,
    language,
    entities: newEntities.length,
    events: eventCount,
    locations: resolvedPlaces.size,
    relationships: relCount,
    newEntities,
  };
}

/* ---------- derived insights ---------- */

/**
 * Rebuild the case's extracted insights from what is now in the store.
 *
 * Every insight below is a statement about the ingested corpus that an
 * analyst can verify from the case data itself — a count, a span, a repeated
 * location. Nothing is predicted or scored by a model.
 */
export function refreshInsights(investigationId) {
  const entities = entityStore.filter((e) => e.investigationId === investigationId);
  const rels = relationshipStore.filter((r) => r.investigationId === investigationId);
  const events = eventStore
    .filter((e) => e.investigationId === investigationId)
    .sort((a, b) => new Date(a.datetime) - new Date(b.datetime));
  const locations = locationStore.filter((l) => l.investigationId === investigationId);

  // Drop the previous generation so counts never double up.
  for (let i = insightStore.length - 1; i >= 0; i -= 1) {
    if (insightStore[i].investigationId === investigationId && insightStore[i].extracted) insightStore.splice(i, 1);
  }
  if (!entities.length && !events.length) return [];

  const now = new Date().toISOString();
  const created = [];
  const add = (insight) => {
    const record = { id: `int-${Math.random().toString(36).slice(2, 9)}`, investigationId, status: 'new', createdAt: now, extracted: true, ...insight };
    insightStore.push(record);
    created.push(record);
  };

  // 1 — Most connected entity.
  const degree = {};
  rels.forEach((r) => {
    degree[r.sourceId] = (degree[r.sourceId] || 0) + 1;
    degree[r.targetId] = (degree[r.targetId] || 0) + 1;
  });
  const topId = Object.keys(degree).sort((a, b) => degree[b] - degree[a])[0];
  const top = entities.find((e) => e.id === topId);
  if (top && degree[topId] >= 2) {
    add({
      category: 'link',
      title: `${top.name} is the most connected record in this case`,
      summary: `${top.name} shares ${degree[topId]} link${degree[topId] === 1 ? '' : 's'} with other extracted records, the highest count in the case. Links are co-mentions inside uploaded evidence — they indicate where to look, not what happened.`,
      confidence: Math.min(90, 50 + degree[topId] * 8),
      linkedEntityIds: [top.id],
      source: 'Link extraction (document co-mention)',
    });
  }

  // 2 — Timeline span and largest gap.
  if (events.length >= 2) {
    const first = events[0];
    const last = events[events.length - 1];
    let gap = { hours: 0, from: null, to: null };
    for (let i = 1; i < events.length; i += 1) {
      const hours = (new Date(events[i].datetime) - new Date(events[i - 1].datetime)) / 36e5;
      if (hours > gap.hours) gap = { hours, from: events[i - 1], to: events[i] };
    }
    add({
      category: 'temporal',
      title: `Timeline covers ${events.length} events across ${Math.max(1, Math.round((new Date(last.datetime) - new Date(first.datetime)) / 864e5))} day(s)`,
      summary: `Earliest: "${first.title}" (${new Date(first.datetime).toLocaleString('en-IN')}). Latest: "${last.title}" (${new Date(last.datetime).toLocaleString('en-IN')}).${gap.hours >= 3 ? ` Largest unaccounted gap is ${Math.round(gap.hours)} hours, between "${gap.from.title}" and "${gap.to.title}" — a coverage gap worth filling.` : ''}`,
      confidence: 88,
      linkedEntityIds: [...new Set(events.flatMap((e) => e.entityIds || []))].slice(0, 6),
      source: 'Timeline reconstruction over ingested evidence',
    });
  }

  // 3 — Last mapped position.
  const lastMapped = [...events].reverse().find((e) => e.locationId);
  if (lastMapped) {
    const loc = locations.find((l) => l.id === lastMapped.locationId);
    if (loc) {
      add({
        category: 'geo',
        title: `Last mapped position: ${loc.name}`,
        summary: `The most recent event with a resolvable location is "${lastMapped.title}" at ${loc.name} on ${new Date(lastMapped.datetime).toLocaleString('en-IN')}. ${locations.length} location${locations.length === 1 ? '' : 's'} in this case could be placed on the map from the uploaded documents.`,
        confidence: 84,
        linkedEntityIds: lastMapped.entityIds || [],
        source: 'Geospatial resolution (gazetteer + coordinates in evidence)',
      });
    }
  }

  // 4 — Repeated location.
  const visits = {};
  events.forEach((e) => e.locationId && (visits[e.locationId] = (visits[e.locationId] || 0) + 1));
  const repeatId = Object.keys(visits).sort((a, b) => visits[b] - visits[a])[0];
  if (repeatId && visits[repeatId] >= 2) {
    const loc = locations.find((l) => l.id === repeatId);
    add({
      category: 'pattern',
      title: `${loc?.name || 'One location'} appears in ${visits[repeatId]} separate events`,
      summary: `Multiple independent records place activity at ${loc?.name}. Repetition across documents is a corroboration signal — confirm each underlying record before relying on it.`,
      confidence: Math.min(88, 55 + visits[repeatId] * 8),
      linkedEntityIds: loc?.entityIds?.slice(0, 5) || [],
      source: 'Pattern detection over extracted events',
    });
  }

  // 5 — Unverified identifiers needing follow-up.
  const identifiers = entities.filter((e) => ['phone_number', 'vehicle', 'bank_account', 'asset'].includes(e.type));
  const orphans = identifiers.filter((e) => !(degree[e.id] > 0));
  if (orphans.length) {
    add({
      category: 'anomaly',
      title: `${orphans.length} identifier${orphans.length === 1 ? '' : 's'} extracted with no owner in the case`,
      summary: `${orphans.slice(0, 4).map((e) => e.name).join(', ')}${orphans.length > 4 ? ` and ${orphans.length - 4} more` : ''} appear in evidence but are not yet tied to a named person. Subscriber or registration checks would close this gap.`,
      confidence: 70,
      linkedEntityIds: orphans.slice(0, 6).map((e) => e.id),
      source: 'Coverage check over extracted entities',
    });
  }

  return created;
}
