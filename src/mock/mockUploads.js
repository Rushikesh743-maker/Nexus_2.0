/**
 * Demo evidence bundle.
 *
 * These are real files served from `public/demo/`, not placeholders: the
 * "Add demo case file" shortcut fetches them and hands the ingestion pipeline
 * genuine bytes, so the entities, timeline, map and intelligence a demo
 * audience sees are extracted live from the document — the same path a file
 * dropped from disk takes.
 */
export const DEMO_CASE_FILES = [
  {
    name: 'NEXUS_demo_case_missing_person.pdf',
    url: '/demo/NEXUS_demo_case_missing_person.pdf',
    type: 'application/pdf',
    label: 'Missing person case bundle (NEX-2026-120)',
  },
  {
    name: 'tower_dump.csv',
    url: '/demo/tower_dump.csv',
    type: 'text/csv',
    label: 'Tower dump — call and registration log',
  },
];

/** Fetch the demo bundle as real File objects the dropzone can accept. */
export async function loadDemoCaseFiles() {
  return Promise.all(
    DEMO_CASE_FILES.map(async (entry) => {
      const response = await fetch(entry.url);
      if (!response.ok) throw new Error(`Could not load ${entry.name} (${response.status}).`);
      const blob = await response.blob();
      return new File([blob], entry.name, { type: entry.type });
    })
  );
}

export default DEMO_CASE_FILES;
