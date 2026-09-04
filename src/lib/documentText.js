/**
 * Text extraction for uploaded evidence files.
 *
 * The ingestion pipeline can only find entities, events and locations in a
 * document it can actually read, so this is the first stage of every upload.
 * PDFs go through pdf.js; plain-text formats are read directly. Formats we
 * cannot read in the browser (docx, xlsx, images) return `null` and the file
 * is still recorded as evidence — just with nothing extracted from it.
 */

const PLAIN_EXTENSIONS = ['txt', 'csv', 'json', 'md', 'log'];

let pdfjsPromise = null;

async function loadPdfjs() {
  if (!pdfjsPromise) {
    pdfjsPromise = (async () => {
      const pdfjs = await import('pdfjs-dist');
      const worker = await import('pdfjs-dist/build/pdf.worker.min.mjs?url');
      pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
      return pdfjs;
    })();
  }
  return pdfjsPromise;
}

function extOf(name = '') {
  const match = String(name).toLowerCase().match(/\.([a-z0-9]+)$/);
  return match ? match[1] : '';
}

/**
 * Re-assemble a PDF page's text items into lines.
 *
 * pdf.js hands back positioned glyph runs, not lines. Extraction rules are
 * line-oriented ("Name: …", "12 Sept 2026, 21:15 — …"), so runs are grouped
 * by their baseline (transform[5]) and joined in reading order.
 */
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
  return [...rows.entries()]
    .sort((a, b) => b[0] - a[0])
    .map(([, row]) =>
      row
        .sort((a, b) => a.x - b.x)
        .map((c) => c.str)
        .join('')
        .replace(/\s+/g, ' ')
        .trim()
    )
    .filter(Boolean);
}

/**
 * Re-join lines a PDF broke purely for layout.
 *
 * A page wraps "…near Deccan Gymkhana…" across two visual lines, which would
 * hide the place name from the extractor. Only four things genuinely start a
 * new block in a case document — a heading, a labelled field, a dated timeline
 * row, and the sentence after a full stop — so every other line is folded back
 * into the one above it.
 */
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

async function readPdf(file) {
  const pdfjs = await loadPdfjs();
  const buffer = await file.arrayBuffer();
  const doc = await pdfjs.getDocument({ data: new Uint8Array(buffer), isEvalSupported: false }).promise;
  const pages = [];
  for (let n = 1; n <= doc.numPages; n += 1) {
    // Sequential on purpose: pdf.js page rendering is not safely concurrent.
    // eslint-disable-next-line no-await-in-loop
    const page = await doc.getPage(n);
    // eslint-disable-next-line no-await-in-loop
    const content = await page.getTextContent();
    pages.push(reflow(pageLines(content.items)).join('\n'));
  }
  await doc.destroy();
  return pages.join('\n');
}

/**
 * Read an uploaded file as text.
 * Returns `{ text, readable, reason }` — `readable: false` means the format
 * carries no machine-readable text in this build.
 */
export async function readDocumentText(file) {
  const ext = extOf(file?.name);

  if (typeof file?.arrayBuffer !== 'function' && typeof file?.text !== 'function') {
    return { text: '', readable: false, reason: 'No file content available (demo placeholder file).' };
  }

  try {
    if (ext === 'pdf') {
      const text = await readPdf(file);
      if (!text.trim()) {
        return { text: '', readable: false, reason: 'PDF contains no extractable text layer (scanned image).' };
      }
      return { text, readable: true, reason: null };
    }
    if (PLAIN_EXTENSIONS.includes(ext)) {
      const text = await file.text();
      return { text, readable: true, reason: null };
    }
    return {
      text: '',
      readable: false,
      reason: `.${ext || 'unknown'} files are stored but not text-extracted in this build.`,
    };
  } catch (err) {
    return { text: '', readable: false, reason: `Could not read the file: ${err.message}` };
  }
}

export { extOf };
