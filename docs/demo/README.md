# NEXUS demo case — NEX-2026-120 (missing person)

Everything in this folder is synthetic. No real person, number, address, account
or location is referenced.

## Files

| File | What it is | What the pipeline gets from it |
| --- | --- | --- |
| `NEXUS_demo_case_missing_person.pdf` | Three-page case bundle: FIR summary, persons, reconstructed timeline, two witness statements, CDR summary | 23 entities, 15 timeline events, 5 mapped locations, ~36 links |
| `tower_dump.csv` | Nine-row tower registration / call log with coordinates | 9 further timeline events; merges into the same four phone numbers |
| `case_bundle.txt` | Plain-text source the PDF is generated from | Same extraction as the PDF — useful for testing |

Copies of the first two are served from `public/demo/`, which is what the
**Add demo case file** shortcut in the upload dialog fetches.

Regenerate the PDF after editing `case_bundle.txt`:

```
npm run demo:case
```

## Running the demo

1. **Investigations → New investigation.** Title `Missing person — Ananya Deshpande`,
   type *Missing Person*, priority *High*. The case opens with every tab at zero —
   say so out loud; that is the point.
2. **Evidence → Upload evidence → Add demo case file → Upload.** The dialog reports
   per file what was pulled out of it (`23 entities · 15 events · 5 locations`).
3. **Network.** Ananya Deshpande, Manish Kharat and their numbers are linked because
   the documents put them together; hover any edge to see the sentence it came from.
4. **Timeline.** 24 events in order across 1–3 September, each traceable to the file
   it was read out of.
5. **Map.** Kothrud → Deccan Gymkhana → Swargate → Katraj → Satara, drawn from the
   coordinates in the tower dump and gazetteer-resolved place names in the bundle.
6. **Intelligence.** Five findings, each one a checkable statement about the corpus —
   the largest unaccounted gap, the last mapped position, the repeated location, and
   three identifiers with no owner yet.

## What is real and what is not

Real: the text extraction (pdf.js), the entity and event extraction, the link
building, the geospatial resolution, and every count and insight on screen — all
computed from the uploaded bytes at upload time.

Not real: the case itself, and the seeded fixture cases that ship with the app.
There is no server; the extracted case lives in memory and is cleared on reload.
