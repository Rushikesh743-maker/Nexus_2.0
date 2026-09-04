import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
globalThis.window = { localStorage: { setItem(){}, removeItem(){}, getItem(){return null;} } };
globalThis.import_meta_env = {};

const evidenceService = await import(path.join(root, 'src/services/evidenceService.js'));
const intel = await import(path.join(root, 'src/services/intelligenceService.js'));
const inv = await import(path.join(root, 'src/services/investigationService.js'));

const investigation = await inv.create({ title: 'missing girl', caseType: 'missing_person', priority: 'high' });
console.log('case:', investigation.code, investigation.id, 'stats before:', investigation.stats);

const asFile = (rel, name) => {
  const buf = fs.readFileSync(path.join(root, rel));
  return { name, size: buf.length, text: async () => buf.toString('utf8'), arrayBuffer: async () => buf };
};

await evidenceService.uploadFiles(
  investigation.id,
  [asFile('docs/demo/case_bundle.txt', 'NEXUS_demo_case.txt'), asFile('docs/demo/tower_dump.csv', 'tower_dump.csv')],
  { uploadedBy: 'Demo Investigator' }
);

const after = await inv.getById(investigation.id);
console.log('\nSTATS AFTER:', after.stats);

const net = await intel.getNetwork(investigation.id, { includeEvidence: true });
console.log(`\nNETWORK  entities=${net.entities.length} relationships=${net.relationships.length} evidenceNodes=${net.evidenceNodes.length}`);
console.log('  hubs:', net.insights.hubs.map(h=>`${h.name}(${h.value})`).join(', '));
console.log('  clusters:', net.insights.clusters.length);
console.log('  sample links:');
const byId = Object.fromEntries(net.entities.map(e=>[e.id,e]));
net.relationships.slice(0,8).forEach(r=>console.log(`    ${byId[r.sourceId]?.name} --[${r.type}/${r.strength}]-- ${byId[r.targetId]?.name}`));

const events = await intel.getEvents(investigation.id);
console.log(`\nTIMELINE events=${events.total}; with location=${events.items.filter(e=>e.locationId).length}; with evidence=${events.items.filter(e=>e.evidenceId).length}`);

const locs = await intel.getLocations(investigation.id);
console.log(`\nMAP locations=${locs.length}`);
locs.forEach(l=>console.log(`  ${l.name.padEnd(20)} ${l.lat},${l.lng}  type=${l.type} events=${l.eventsCount} entities=${l.entityIds.length}`));
const move = await intel.getMovement(investigation.id);
console.log(`  movement legs=${move.total}`);

const ins = await intel.getInsights(investigation.id);
console.log(`\nINTELLIGENCE insights=${ins.total}`);
ins.items.forEach(i=>console.log(`  [${i.category}] ${i.title}\n      ${i.summary.slice(0,150)}`));

const ev = await evidenceService.list(investigation.id);
console.log('\nEVIDENCE:', ev.items.map(e=>`${e.refNo} ${e.title} status=${e.status} lang=${e.language} ent=${e.extractedEntities} evt=${e.extractedEvents}`).join('\n  '));
