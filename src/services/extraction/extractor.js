import { resolvePlace, isKnownPlace, GAZETTEER } from './gazetteer';

/** Every word that appears in a gazetteer place name — never part of a person's name. */
const PLACE_WORDS = new Set(
  GAZETTEER.flatMap(([name]) => name.toLowerCase().split(/\s+/)).filter((w) => w.length > 2)
);

/**
 * Rule-based extraction engine.
 *
 * Turns the text of an uploaded document into candidate entities, events,
 * locations and relationships. It is deliberately transparent — every finding
 * carries the line it came from, so an analyst can check the source — and
 * deliberately conservative: it reports what the document literally says and
 * never infers identity, guilt or intent.
 *
 * Pure functions only. Nothing here touches the case store.
 */

/* ---------------- patterns ---------------- */

const RE = {
  phone: /(?:\+91[\s-]?)?\b[6-9]\d{4}[\s-]?\d{5}\b/g,
  vehicle: /\b(?:MH|DL|KA|GJ|TN|AP|TS|RJ|UP|MP|WB|KL|HR|PB|GA)[\s-]?\d{1,2}[\s-]?[A-Z]{1,3}[\s-]?\d{3,4}\b/g,
  account: /\b(?:A\/C|Account(?:\s+No\.?)?|Acc\.?\s*No\.?)[:\s#]*([Xx*•\d]{6,20})\b/g,
  imei: /\bIMEI[:\s#]*(\d{14,16})\b/gi,
  email: /\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b/g,
  money: /(?:₹|Rs\.?|INR)\s?[\d,]+(?:\.\d+)?(?:\s?(?:lakh|lakhs|crore|crores|k))?/gi,
  coords: /(-?\d{1,2}\.\d{3,7})\s*[,\s]\s*(-?\d{2,3}\.\d{3,7})/g,
};

/** Titles that reliably precede a person's name in Indian case documents. */
const HONORIFICS =
  'Mr|Mrs|Ms|Miss|Shri|Smt|Sri|Dr|Prof|Adv|Insp|Inspector|Sub-Inspector|PSI|API|ASI|Constable|Head Constable|HC|PI|SI|DCP|ACP|SP|DySP|Kum';

const PERSON_LABELS = [
  'name',
  'full name',
  'missing person',
  'subject',
  'suspect',
  'accused',
  'complainant',
  'informant',
  'witness',
  'victim',
  'reported by',
  'reporting person',
  'father',
  'father name',
  "father's name",
  'mother',
  "mother's name",
  'guardian',
  'friend',
  'classmate',
  'last seen by',
  'investigating officer',
  'io',
  'lead officer',
  'driver',
  'owner',
  'contact person',
];

const ORG_SUFFIXES = [
  'School',
  'College',
  'University',
  'Vidyalaya',
  'Junior College',
  'Academy',
  'Institute',
  'Coaching',
  'Classes',
  'Hospital',
  'Clinic',
  'Nursing Home',
  'Police Station',
  'Chowky',
  'Bank',
  'Society',
  'Club',
  'Gymkhana',
  'Hotel',
  'Lodge',
  'Restaurant',
  'Cafe',
  'Café',
  'Mall',
  'Stores',
  'Store',
  'Shop',
  'Enterprises',
  'Traders',
  'Industries',
  'Logistics',
  'Transport',
  'Travels',
  'Pvt Ltd',
  'Ltd',
  'LLP',
  'Trust',
  'Foundation',
  'NGO',
  'Depot',
  'Terminus',
  'Godown',
  'Warehouse',
];

/**
 * Labels that attach an identifier to whoever the current block is about.
 * A case file lists "Suspect: Manish Kharat" and then "Contact: +91 …" on the
 * next line — the two never share a line, so line-level co-occurrence alone
 * would leave every phone number ownerless.
 */
const CONTACT_LABELS = ['contact', 'phone', 'mobile', 'mobile no', 'phone no', 'number', 'vehicle', 'vehicle no', 'email', 'e-mail', 'imei', 'account no', 'account', 'a/c', 'address', 'school', 'college', 'employer'];

const OWNABLE_TYPES = ['phone_number', 'vehicle', 'bank_account', 'asset', 'address', 'organization'];

const PLACE_LABELS = ['location', 'place', 'address', 'last seen at', 'last known location', 'venue', 'scene', 'residence', 'from', 'to', 'destination'];

/** Words that must never be treated as a person's name. */
const NOT_A_NAME = new Set(
  [
    'the','and','for','with','from','this','that','case','file','report','police','station','date','time','name','age','sex',
    'male','female','statement','witness','evidence','summary','details','description','note','notes','ref','fir','number',
    'section','act','ipc','crpc','signed','signature','officer','india','indian','maharashtra','sunday','monday','tuesday',
    'wednesday','thursday','friday','saturday','january','february','march','april','may','june','july','august','september',
    'october','november','december','jan','feb','mar','apr','jun','jul','aug','sep','sept','oct','nov','dec','missing','person',
    'timeline','network','intelligence','analysis','contact','phone','mobile','vehicle','account','bank','school','college',
    'hospital','last','seen','known','approx','approximately','about','around','near','opposite','behind','before','after',
    'she','her','him','his','they','them','their','was','were','has','have','had','said','told','states','stated','confirms',
    'confirmed','reported','observed','recovered','found','entry','exit','camera','cctv','footage','image','video','audio',
    'call','sms','message','whatsapp','instagram','yes','no','none','nil','unknown','other','page','annexure','exhibit',
  ].map((w) => w)
);

/* ---------------- small helpers ---------------- */

const clean = (s) => String(s || '').replace(/\s+/g, ' ').trim();

function titleCaseName(raw) {
  return clean(raw)
    .replace(new RegExp(`^(?:${HONORIFICS})\\.?\\s+`, 'i'), '')
    .replace(/[.,;:]+$/, '')
    .trim();
}

function looksLikeName(candidate) {
  const name = clean(candidate);
  if (name.length < 4 || name.length > 48) return false;
  const words = name.split(' ');
  if (words.length < 2 || words.length > 4) return false;
  if (isKnownPlace(name)) return false;
  // "Pune City", "Satara Road" — a name built from place words is a place.
  if (words.some((w) => PLACE_WORDS.has(w.toLowerCase()))) return false;
  return words.every((w) => {
    const bare = w.replace(/[^A-Za-z]/g, '');
    if (bare.length < 2) return false;
    if (NOT_A_NAME.has(bare.toLowerCase())) return false;
    return /^[A-Z][a-z'’-]+$/.test(w) || /^[A-Z]\.$/.test(w);
  });
}

function normKey(type, value) {
  return `${type}:${clean(value).toLowerCase().replace(/[^a-z0-9]/g, '')}`;
}

function normalisePhone(raw) {
  const digits = String(raw).replace(/\D/g, '').slice(-10);
  return `+91 ${digits.slice(0, 5)} ${digits.slice(5)}`;
}

function normaliseVehicle(raw) {
  const bare = String(raw).toUpperCase().replace(/[^A-Z0-9]/g, '');
  const m = bare.match(/^([A-Z]{2})(\d{1,2})([A-Z]{1,3})(\d{3,4})$/);
  return m ? `${m[1]}-${m[2]} ${m[3]} ${m[4]}` : String(raw).toUpperCase();
}

/* ---------------- date parsing ---------------- */

const MONTHS = {
  jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, sept: 8, oct: 9, nov: 10, dec: 11,
};

/**
 * Parse the leading date/time of a line.
 * Supports `2026-09-01 21:15`, `01/09/2026 21:15`, `1 Sept 2026, 21:15`,
 * `Sept 1, 2026 9:15 PM` and bare dates (time defaults to 09:00).
 * Returns `{ iso, rest }` or null.
 */
export function parseLeadingDate(line) {
  const text = clean(line).replace(/^[-•*•|\[]+\s*/, '');

  const patterns = [
    // 2026-09-01T21:15 / 2026-09-01 21:15
    /^(\d{4})-(\d{2})-(\d{2})(?:[T\s]+(\d{1,2}):(\d{2}))?/,
    // 01/09/2026 21:15 or 01-09-2026
    /^(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?:[,\s]+(\d{1,2}):(\d{2}))?/,
    // 1 Sept 2026, 21:15
    /^(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{4})(?:[,\s]+(\d{1,2}):(\d{2}))?/,
    // Sept 1, 2026 21:15
    /^([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})(?:[,\s]+(\d{1,2}):(\d{2}))?/,
  ];

  for (let i = 0; i < patterns.length; i += 1) {
    const m = text.match(patterns[i]);
    if (!m) continue;

    let year;
    let month;
    let day;
    let hour = m[4];
    let minute = m[5];

    if (i === 0) [, year, month, day] = m.map(Number);
    else if (i === 1) {
      day = Number(m[1]);
      month = Number(m[2]);
      year = Number(m[3]);
    } else if (i === 2) {
      day = Number(m[1]);
      month = MONTHS[m[2].toLowerCase().slice(0, 4)] ?? MONTHS[m[2].toLowerCase().slice(0, 3)];
      if (month === undefined) continue;
      month += 1;
      year = Number(m[3]);
    } else {
      month = MONTHS[m[1].toLowerCase().slice(0, 4)] ?? MONTHS[m[1].toLowerCase().slice(0, 3)];
      if (month === undefined) continue;
      month += 1;
      day = Number(m[2]);
      year = Number(m[3]);
    }

    if (!(month >= 1 && month <= 12) || !(day >= 1 && day <= 31)) continue;

    const rest = clean(text.slice(m[0].length));
    // 21:15 hrs / 9:15 PM appearing just after the date.
    let h = hour !== undefined ? Number(hour) : null;
    let min = minute !== undefined ? Number(minute) : 0;
    let tail = rest;
    if (h === null) {
      const t = rest.match(/^[^\dA-Za-z]*(\d{1,2}):(\d{2})\s*(hrs|hours|am|pm|AM|PM)?/);
      if (t) {
        h = Number(t[1]);
        min = Number(t[2]);
        if (/pm/i.test(t[3] || '') && h < 12) h += 12;
        if (/am/i.test(t[3] || '') && h === 12) h = 0;
        tail = clean(rest.slice(t[0].length));
      }
    } else {
      const ampm = rest.match(/^\s*(am|pm)\b/i);
      if (ampm) {
        if (/pm/i.test(ampm[1]) && h < 12) h += 12;
        if (/am/i.test(ampm[1]) && h === 12) h = 0;
        tail = clean(rest.slice(ampm[0].length));
      }
    }
    if (h === null) h = 9;
    if (h > 23 || min > 59) continue;

    const pad = (n) => String(n).padStart(2, '0');
    return {
      iso: `${year}-${pad(month)}-${pad(day)}T${pad(h)}:${pad(min)}:00+05:30`,
      rest: clean(tail.replace(/^[-–—:|,]+\s*/, '')),
    };
  }
  return null;
}

/* ---------------- event typing ---------------- */

const EVENT_KEYWORDS = [
  ['call', /\b(call|called|dialled|dialed|rang|missed call|cdr|sms|texted|whatsapp|message[sd]?)\b/i],
  ['transaction', /\b(paid|payment|transferred|transfer|deposit|withdraw|withdrawal|upi|atm|debit|credit|₹|rs\.?\s?\d)/i],
  ['travel', /\b(travel|travelled|boarded|bus|train|auto|rickshaw|cab|taxi|rode|drove|departed|arrived|reached|toll|route|left (?:the |her |his )?(?:residence|house|home|premises|campus)|heading (?:towards|to))\b/i],
  ['surveillance', /\b(cctv|camera|footage|observed|surveillance|spotted|sighted|seen at|captured)\b/i],
  ['search', /\b(search|raid|seized|recovered|warrant|panchnama|inspection)\b/i],
  ['meeting', /\b(met|meeting|gathered|assembled|handed over|handover)\b/i],
  ['incident', /\b(missing|disappear|abduct|kidnap|assault|theft|robbery|break-in|incident|fir registered|complaint)\b/i],
  ['report', /\b(statement|reported|filed|recorded|noted|register|log)\b/i],
];

function typeForText(text) {
  for (const [type, re] of EVENT_KEYWORDS) if (re.test(text)) return type;
  return 'report';
}

/* ---------------- CSV support ---------------- */

function splitCsvLine(line) {
  const out = [];
  let cur = '';
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (ch === '"') {
      if (quoted && line[i + 1] === '"') {
        cur += '"';
        i += 1;
      } else quoted = !quoted;
    } else if ((ch === ',' || ch === '\t' || ch === ';') && !quoted) {
      out.push(cur);
      cur = '';
    } else cur += ch;
  }
  out.push(cur);
  return out.map(clean);
}

function findColumn(headers, candidates) {
  return headers.findIndex((h) => candidates.some((c) => h.toLowerCase().replace(/[^a-z]/g, '').includes(c)));
}

/**
 * Structured rows from a CSV/TSV document — call detail records, location
 * logs, transaction statements. Yields the same shape as narrative lines
 * (`{ iso, text, place, coords }`) so downstream handling is identical.
 */
function csvRows(text) {
  const lines = text.split(/\r?\n/).filter((l) => clean(l));
  if (lines.length < 2) return null;
  const headers = splitCsvLine(lines[0]);
  if (headers.length < 2) return null;

  const dateCol = findColumn(headers, ['datetime', 'timestamp', 'date', 'time']);
  const timeCol = findColumn(headers, ['time']);
  if (dateCol === -1) return null;

  const latCol = findColumn(headers, ['lat']);
  const lngCol = findColumn(headers, ['lng', 'lon', 'long']);
  const placeCol = findColumn(headers, ['location', 'place', 'tower', 'cell', 'site', 'address', 'area']);
  const descCol = findColumn(headers, ['description', 'detail', 'note', 'activity', 'event', 'remark', 'type', 'source']);

  const rows = [];
  for (let i = 1; i < lines.length; i += 1) {
    const cells = splitCsvLine(lines[i]);
    if (cells.length < 2) continue;
    const dateText =
      timeCol !== -1 && timeCol !== dateCol ? `${cells[dateCol]} ${cells[timeCol]}` : cells[dateCol];
    const parsed = parseLeadingDate(dateText);
    if (!parsed) continue;

    const rest = cells
      .filter((_, idx) => idx !== dateCol && idx !== timeCol && idx !== latCol && idx !== lngCol)
      .filter(Boolean)
      .join(' · ');

    const lat = latCol !== -1 ? Number(cells[latCol]) : null;
    const lng = lngCol !== -1 ? Number(cells[lngCol]) : null;

    rows.push({
      iso: parsed.iso,
      text: rest || clean(cells.join(' ')),
      placeHint: placeCol !== -1 ? cells[placeCol] : null,
      coords: Number.isFinite(lat) && Number.isFinite(lng) && (lat || lng) ? { lat, lng } : null,
      descHint: descCol !== -1 ? cells[descCol] : null,
      row: true,
    });
  }
  return rows.length ? rows : null;
}

/* ---------------- entity harvesting ---------------- */

function bumpPair(coOccurrence, keyA, keyB, line) {
  if (!keyA || !keyB || keyA === keyB) return;
  const pairKey = [keyA, keyB].sort().join('||');
  const entry = coOccurrence.get(pairKey) || { count: 0, lines: [] };
  entry.count += 1;
  if (entry.lines.length < 3) entry.lines.push(line);
  coOccurrence.set(pairKey, entry);
}

function addCandidate(map, { type, name, role, note, line }) {
  const value = clean(name);
  if (!value) return null;
  const key = normKey(type, value);
  const existing = map.get(key);
  if (existing) {
    existing.mentions += 1;
    if (role && !existing.role) existing.role = role;
    if (line && existing.lines.length < 4 && !existing.lines.includes(line)) existing.lines.push(line);
    return existing;
  }
  const record = { key, type, name: value, role: role || null, note: note || null, mentions: 1, lines: line ? [line] : [] };
  map.set(key, record);
  return record;
}

/** Collect every identifier and name a single line offers. */
function harvestLine(line, candidates, coOccurrence) {
  const found = [];
  const push = (rec) => rec && found.push(rec);

  // Labelled fields: "Missing person: Ananya Deshpande", "Father: ..."
  const labelled = line.match(/^([A-Za-z][A-Za-z'’\s./-]{1,28}?)\s*[:\-–]\s*(.+)$/);
  let label = null;
  let value = line;
  if (labelled) {
    label = clean(labelled[1]).toLowerCase().replace(/\.$/, '');
    value = clean(labelled[2]);
  }

  if (label && PERSON_LABELS.includes(label)) {
    // A labelled person field may carry "Name (age 17), +91 …" — take the name part.
    const namePart = clean(value.split(/[,(]/)[0]);
    const name = titleCaseName(namePart);
    if (looksLikeName(name)) {
      const roleMap = {
        'missing person': 'Missing person',
        subject: 'Subject',
        suspect: 'Person of interest',
        accused: 'Person of interest',
        complainant: 'Complainant',
        informant: 'Informant',
        witness: 'Witness',
        victim: 'Victim',
        father: 'Family',
        'father name': 'Family',
        "father's name": 'Family',
        mother: 'Family',
        "mother's name": 'Family',
        guardian: 'Family',
        friend: 'Associate',
        classmate: 'Associate',
        'reported by': 'Complainant',
        'reporting person': 'Complainant',
        'investigating officer': 'Investigating officer',
        io: 'Investigating officer',
        'lead officer': 'Investigating officer',
        driver: 'Person of interest',
        owner: 'Registered owner',
        'last seen by': 'Witness',
      };
      push(addCandidate(candidates, { type: 'person', name, role: roleMap[label] || 'Named person', line }));
    }
  }

  // Honorific-led names anywhere in the line.
  const honorRe = new RegExp(`\\b(?:${HONORIFICS})\\.?\\s+([A-Z][a-z'’-]+(?:\\s+[A-Z][a-z'’-]+){0,2})`, 'g');
  for (const m of line.matchAll(honorRe)) {
    const name = titleCaseName(m[1]);
    if (looksLikeName(name) || /^[A-Z][a-z]+\s+[A-Z][a-z]+/.test(name)) {
      push(addCandidate(candidates, { type: 'person', name, role: 'Named person', line }));
    }
  }

  // Bare capitalised two/three-word names in narrative text.
  for (const m of line.matchAll(/\b([A-Z][a-z'’-]{2,}(?:\s+[A-Z][a-z'’-]{2,}){1,2})\b/g)) {
    const name = clean(m[1]);
    if (!looksLikeName(name)) continue;
    if (ORG_SUFFIXES.some((s) => name.endsWith(s))) continue;
    push(addCandidate(candidates, { type: 'person', name, role: 'Named person', line }));
  }

  // Organisations by suffix.
  for (const suffix of ORG_SUFFIXES) {
    const re = new RegExp(`\\b((?:[A-Z][A-Za-z'’.&-]*\\s+){0,3}${suffix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})\\b`, 'g');
    for (const m of line.matchAll(re)) {
      const name = clean(m[1]);
      if (name.split(' ').length < 2) continue;
      // "Police Station" on its own is a field label, not an organisation —
      // an organisation needs a distinguishing word in front of the suffix.
      if (ORG_SUFFIXES.some((sfx) => sfx.toLowerCase() === name.toLowerCase())) continue;
      push(addCandidate(candidates, { type: 'organization', name, role: 'Organisation', line }));
    }
  }

  // Identifiers.
  for (const m of line.matchAll(RE.phone)) {
    push(addCandidate(candidates, { type: 'phone_number', name: normalisePhone(m[0]), role: 'Number in record', line }));
  }
  for (const m of line.matchAll(RE.vehicle)) {
    push(addCandidate(candidates, { type: 'vehicle', name: normaliseVehicle(m[0]), role: 'Vehicle in record', line }));
  }
  for (const m of line.matchAll(RE.account)) {
    push(addCandidate(candidates, { type: 'bank_account', name: `A/C ${clean(m[1])}`, role: 'Account in record', line }));
  }
  for (const m of line.matchAll(RE.imei)) {
    push(addCandidate(candidates, { type: 'asset', name: `IMEI ${m[1]}`, role: 'Device identifier', line }));
  }
  for (const m of line.matchAll(RE.email)) {
    push(addCandidate(candidates, { type: 'asset', name: m[0].toLowerCase(), role: 'Online identifier', line }));
  }

  // Addresses from labelled place fields.
  if (label && PLACE_LABELS.includes(label) && value.length > 3) {
    push(addCandidate(candidates, { type: 'address', name: clean(value).slice(0, 80), role: 'Address in record', line }));
  }

  // Everything named on one line is at least co-mentioned.
  const ids = [...new Set(found.map((f) => f.key))];
  for (let i = 0; i < ids.length; i += 1) {
    for (let j = i + 1; j < ids.length; j += 1) bumpPair(coOccurrence, ids[i], ids[j], line);
  }
  return { ids, label };
}

/* ---------------- main entry point ---------------- */

/**
 * Extract findings from one document.
 *
 * @param {string} text  Document text.
 * @param {object} meta  `{ fileName, evidenceId, evidenceRef }`.
 * @returns findings — candidate entities (keyed, de-duplicated), events,
 *          places and co-occurrence pairs, all tagged with their source line.
 */
export function extractFromText(text, meta = {}) {
  const candidates = new Map();
  const coOccurrence = new Map();
  const events = [];
  const places = new Map();

  const rows = csvRows(text);
  const rawLines = text.split(/\r?\n/).map(clean).filter((l) => l.length > 1);

  const notePlace = (hint, coords, at) => {
    const resolved = coords ? { name: clean(hint) || `${coords.lat.toFixed(4)}, ${coords.lng.toFixed(4)}`, ...coords } : resolvePlace(hint);
    if (!resolved) return null;
    const key = normKey('place', resolved.name);
    const existing = places.get(key);
    if (existing) {
      existing.mentions += 1;
      if (at && (!existing.lastActivityAt || at > existing.lastActivityAt)) existing.lastActivityAt = at;
      return existing;
    }
    const record = { key, name: resolved.name, lat: resolved.lat, lng: resolved.lng, mentions: 1, lastActivityAt: at || null, address: clean(hint) || resolved.name };
    places.set(key, record);
    return record;
  };

  /* --- structured rows (CDR / location log / statement) --- */
  if (rows) {
    rows.forEach((row, index) => {
      const { ids: entityKeys } = harvestLine(row.text, candidates, coOccurrence);
      const place = notePlace(row.placeHint || row.text, row.coords, row.iso);
      events.push({
        localId: `${meta.evidenceId || 'doc'}-r${index}`,
        datetime: row.iso,
        type: typeForText(`${row.descHint || ''} ${row.text}`),
        title: clean(row.descHint || row.text).slice(0, 110) || 'Logged record',
        description: clean(row.text),
        entityKeys,
        placeKey: place?.key || null,
        locationName: place?.name || clean(row.placeHint) || null,
        sourceLine: clean(row.text),
        confidence: 88,
      });
    });
  }

  if (!rows) {
    /* --- narrative lines --- */
    // The person a labelled block is about, so identifiers listed beneath them
    // ("Suspect: … / Contact: … / Vehicle: …") attach to the right person.
    let blockSubject = null;

    rawLines.forEach((line, index) => {
      const isHeadingLine = /^[A-Z0-9][A-Z0-9 ,.'’—–&-]{4,}$/.test(line) && line === line.toUpperCase();
      if (isHeadingLine) blockSubject = null;

      const { ids: entityKeys, label } = harvestLine(line, candidates, coOccurrence);

      const personKeys = entityKeys.filter((k) => candidates.get(k)?.type === 'person');
      if (personKeys.length) {
        blockSubject = personKeys[personKeys.length - 1];
      } else if (blockSubject && label && CONTACT_LABELS.includes(label)) {
        entityKeys
          .filter((k) => OWNABLE_TYPES.includes(candidates.get(k)?.type))
          .forEach((k) => bumpPair(coOccurrence, blockSubject, k, line));
      }

      // Explicit coordinates anywhere in the text become mapped places.
      for (const m of line.matchAll(RE.coords)) {
        const lat = Number(m[1]);
        const lng = Number(m[2]);
        if (Math.abs(lat) <= 90 && Math.abs(lng) <= 180) {
          notePlace(line.replace(m[0], '').replace(/[^A-Za-z ,]/g, ' '), { lat, lng }, null);
        }
      }

      const dated = parseLeadingDate(line);
      if (!dated || !dated.rest || dated.rest.length < 4) return;

      const place = notePlace(dated.rest, null, dated.iso);
      events.push({
        localId: `${meta.evidenceId || 'doc'}-l${index}`,
        datetime: dated.iso,
        type: typeForText(dated.rest),
        title: dated.rest.split(/(?<=[a-z0-9)\]])[.;](?=\s+[A-Z]|\s*$)/)[0].slice(0, 110),
        description: dated.rest,
        entityKeys,
        placeKey: place?.key || null,
        locationName: place?.name || null,
        sourceLine: line,
        confidence: 82,
      });
    });

  }

  // A place named in a labelled field but never in a dated line still maps.
  if (!rows) rawLines.forEach((line) => {
    const labelled = line.match(/^([A-Za-z][A-Za-z'’\s./-]{1,28}?)\s*[:\-–]\s*(.+)$/);
    if (!labelled) return;
    const label = clean(labelled[1]).toLowerCase().replace(/\.$/, '');
    if (PLACE_LABELS.includes(label)) notePlace(labelled[2], null, null);
  });

  // A person candidate that is just the opening words of an organisation
  // ("Vidya Bhavan Junior" from "Vidya Bhavan Junior College") is that
  // organisation, not a person.
  const orgNames = [...candidates.values()].filter((c) => c.type === 'organization').map((c) => c.name.toLowerCase());
  [...candidates.values()].forEach((c) => {
    if (c.type !== 'person') return;
    const lower = c.name.toLowerCase();
    if (orgNames.some((o) => o !== lower && o.startsWith(lower))) candidates.delete(c.key);
  });

  return {
    candidates: [...candidates.values()],
    events,
    places: [...places.values()],
    coOccurrence: [...coOccurrence.entries()].map(([pair, v]) => {
      const [a, b] = pair.split('||');
      return { a, b, count: v.count, lines: v.lines };
    }),
    lineCount: rawLines.length,
    structured: Boolean(rows),
  };
}

export const __testables = { looksLikeName, normalisePhone, normaliseVehicle, typeForText, csvRows };
