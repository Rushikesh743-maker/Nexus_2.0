/**
 * Builds the NEXUS demo case bundle as a PDF.
 *
 * The PDF is a plain, text-layer document on purpose: the ingestion pipeline
 * reads it with pdf.js exactly the way it reads a real case file, so what a
 * demo audience sees on screen is genuinely extracted from this document and
 * not seeded anywhere in the app.
 *
 *   node scripts/generateDemoCase.mjs
 *   → docs/demo/NEXUS_demo_case_missing_person.pdf
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import PDFDocument from 'pdfkit';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const source = path.join(root, 'docs/demo/case_bundle.txt');
const target = path.join(root, 'docs/demo/NEXUS_demo_case_missing_person.pdf');

const INK = '#12213a';
const MUTED = '#5a6b85';
const RULE = '#c8d2e0';
const ACCENT = '#0f766e';

const lines = fs.readFileSync(source, 'utf8').split(/\r?\n/);

const doc = new PDFDocument({ size: 'A4', margins: { top: 62, bottom: 62, left: 58, right: 58 }, info: {
  Title: 'NEXUS demonstration case file — NEX-2026-120',
  Author: 'NEXUS (demonstration)',
  Subject: 'Synthetic missing-person case bundle for platform demonstration',
} });
doc.pipe(fs.createWriteStream(target));

const width = doc.page.width - doc.page.margins.left - doc.page.margins.right;
const isHeading = (l) => /^[A-Z0-9 ,.'’—–-]+$/.test(l) && l.trim().length > 3 && l === l.toUpperCase() && !/^\d/.test(l);

function rule() {
  doc.moveDown(0.25);
  doc.save().strokeColor(RULE).lineWidth(0.75)
    .moveTo(doc.page.margins.left, doc.y).lineTo(doc.page.margins.left + width, doc.y).stroke().restore();
  doc.moveDown(0.55);
}

/* Cover block */
doc.fillColor(ACCENT).fontSize(9).font('Helvetica-Bold')
  .text('N E X U S   ·   I N V E S T I G A T I O N   I N T E L L I G E N C E', { characterSpacing: 0.4 });
doc.moveDown(0.9);
doc.fillColor(INK).font('Helvetica-Bold').fontSize(21).text('Case bundle — NEX-2026-120');
doc.moveDown(0.25);
doc.fillColor(MUTED).font('Helvetica').fontSize(10.5)
  .text('Missing person · Pune City · Filed 02 September 2026');
doc.moveDown(0.7);
doc.roundedRect(doc.page.margins.left, doc.y, width, 30, 4).fillAndStroke('#fff7ed', '#fdba74');
doc.fillColor('#9a3412').font('Helvetica-Bold').fontSize(8.5)
  .text('DEMONSTRATION DOCUMENT — EVERY PERSON, NUMBER, ADDRESS AND RECORD IN THIS FILE IS SYNTHETIC AND FICTIONAL.',
    doc.page.margins.left + 12, doc.y - 21, { width: width - 24 });
doc.y += 20;
doc.moveDown(0.6);

/* Body */
let skippedBanner = false;
lines.forEach((raw) => {
  const line = raw.replace(/\s+$/, '');

  if (!line.trim()) {
    doc.moveDown(0.35);
    return;
  }
  // The banner and title are already rendered in the cover block above.
  if (/^NEXUS DEMONSTRATION CASE FILE$/.test(line)) return;
  if (/^DEMONSTRATION DATA/.test(line)) {
    skippedBanner = true;
    return;
  }
  if (skippedBanner && /^CASE SUMMARY$/.test(line)) skippedBanner = false;

  if (isHeading(line)) {
    doc.moveDown(0.7);
    doc.fillColor(ACCENT).font('Helvetica-Bold').fontSize(10).text(line, { characterSpacing: 0.6 });
    rule();
    return;
  }

  const labelled = line.match(/^([A-Za-z][A-Za-z'’ ./-]{1,28}?):\s*(.+)$/);
  if (labelled && !/^\d/.test(line)) {
    doc.font('Helvetica-Bold').fontSize(9.5).fillColor(MUTED)
      .text(`${labelled[1]}: `, { continued: true })
      .font('Helvetica').fillColor(INK).text(labelled[2]);
    return;
  }

  // Timeline rows keep their leading timestamp visually distinct.
  const dated = line.match(/^(\d{1,2} [A-Za-z]+ \d{4}, \d{2}:\d{2})\s*—\s*(.+)$/);
  if (dated) {
    doc.font('Courier-Bold').fontSize(8.5).fillColor(ACCENT)
      .text(`${dated[1]} — `, { continued: true })
      .font('Helvetica').fontSize(9.5).fillColor(INK).text(dated[2]);
    doc.moveDown(0.12);
    return;
  }

  doc.font('Helvetica').fontSize(9.5).fillColor(INK).text(line, { align: 'left', lineGap: 1.5 });
});

/* Footer on every page */
const range = doc.bufferedPageRange();
for (let i = range.start; i < range.start + range.count; i += 1) {
  doc.switchToPage(i);
  doc.font('Helvetica').fontSize(7.5).fillColor(MUTED).text(
    `NEX-2026-120 · synthetic demonstration data · page ${i + 1} of ${range.count}`,
    doc.page.margins.left,
    doc.page.height - 44,
    { width, align: 'center' }
  );
}

doc.end();
console.log(`→ ${path.relative(root, target)}`);
