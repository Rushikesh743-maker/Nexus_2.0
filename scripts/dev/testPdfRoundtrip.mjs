import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const pdfjs = await import('pdfjs-dist/legacy/build/pdf.mjs');
const { extractFromText } = await import(path.join(root, 'src/services/extraction/extractor.js'));

// Mirrors src/lib/documentText.js pageLines()
function pageLines(items) {
  const rows = new Map();
  items.forEach((item) => {
    if (!item.str) return;
    const y = Math.round(item.transform[5]);
    const key = [...rows.keys()].find((k) => Math.abs(k - y) <= 2);
    const row = key === undefined ? [] : rows.get(key);
    row.push({ x: item.transform[4], str: item.str });
    if (key === undefined) rows.set(y, row);
  });
  return [...rows.entries()].sort((a, b) => b[0] - a[0])
    .map(([, r]) => r.sort((a, b) => a.x - b.x).map((c) => c.str).join('').replace(/\s+/g, ' ').trim())
    .filter(Boolean);
}

const isHeading = (line) =>
  /^[A-Z0-9][A-Z0-9 ,.'\u2019\u2014\u2013&-]{4,}$/.test(line) && line === line.toUpperCase();

const isLabelledField = (line) => /^[A-Za-z][A-Za-z'\u2019 ./-]{1,28}:\s/.test(line);

const isDatedRow = (line) =>
  /^\d{1,2}[/\s-]/.test(line) && /\d{4}/.test(line.slice(0, 24));

function startsNewBlock(line) {
  return isHeading(line) || isLabelledField(line) || isDatedRow(line);
}

function reflow(lines) {
  const out = [];
  lines.forEach((line) => {
    const previous = out[out.length - 1];
    const continues =
      previous && !startsNewBlock(line) && !isHeading(previous) && !/[.:;]$/.test(previous);
    if (continues) {
      out[out.length - 1] = previous.endsWith('-') ? previous.slice(0, -1) + line : `${previous} ${line}`;
    } else {
      out.push(line);
    }
  });
  return out;
}

const data = new Uint8Array(fs.readFileSync(process.argv[2]));
const doc = await pdfjs.getDocument({ data, isEvalSupported: false }).promise;
const pages = [];
for (let n = 1; n <= doc.numPages; n++) {
  const page = await doc.getPage(n);
  pages.push(reflow(pageLines((await page.getTextContent()).items)).join('\n'));
}
const text = pages.join('\n');
console.log(`pages: ${doc.numPages}  chars: ${text.length}`);
console.log('--- first 12 recovered lines ---');
console.log(text.split('\n').slice(0, 12).join('\n'));
const f = extractFromText(text, { evidenceId: 'ev-pdf' });
console.log(`\nENTITIES ${f.candidates.length} | EVENTS ${f.events.length} | PLACES ${f.places.length} | PAIRS ${f.coOccurrence.length}`);
const by = {};
f.candidates.forEach(c => (by[c.type] = (by[c.type]||0)+1));
console.log(by);
console.log('\nEVENTS:');
f.events.forEach(e => console.log(` ${e.datetime.slice(0,16)} [${e.type.padEnd(11)}] @${(e.locationName||'-').padEnd(18)} ${e.title.slice(0,64)}`));
console.log('\nPLACES:', f.places.map(p=>p.name).join(', '));
console.log('\nPERSONS:', f.candidates.filter(c=>c.type==='person').map(c=>`${c.name} (${c.role})`).join(' | '));
