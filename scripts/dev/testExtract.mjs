import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const { extractFromText } = await import(path.join(root, 'src/services/extraction/extractor.js'));

const file = process.argv[2];
const text = fs.readFileSync(file, 'utf8');
const f = extractFromText(text, { evidenceId: 'ev-test', evidenceRef: 'EV/001' });
console.log('structured:', f.structured, '| lines:', f.lineCount);
console.log('\n=== ENTITIES (%d) ===', f.candidates.length);
f.candidates.sort((a,b)=>a.type.localeCompare(b.type)||b.mentions-a.mentions)
  .forEach(c=>console.log(` ${c.type.padEnd(14)} ${c.name.padEnd(34)} x${c.mentions}  ${c.role||''}`));
console.log('\n=== EVENTS (%d) ===', f.events.length);
f.events.forEach(e=>console.log(` ${e.datetime.slice(0,16)} [${e.type.padEnd(12)}] @${(e.locationName||'-').padEnd(22)} ${e.title.slice(0,70)}`));
console.log('\n=== PLACES (%d) ===', f.places.length);
f.places.forEach(p=>console.log(` ${p.name.padEnd(28)} ${p.lat},${p.lng}  x${p.mentions}`));
console.log('\n=== PAIRS (%d) ===', f.coOccurrence.length);
