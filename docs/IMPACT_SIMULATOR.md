# The Evidence Impact Simulator

## 1. Purpose

One question, asked of any record in the case:

> **What would this case look like if this evidence had never been filed?**

It matters because an investigation's confidence is not evenly distributed. Some
conclusions rest on five independent systems agreeing; others rest entirely on a
single FIR that nobody has re-checked. Both look identical on a graph. The
simulator makes the difference visible *before* a case is built on the second
kind.

It is a thought experiment, and the UI says so on every result. Withholding a
record does not suggest the record is wrong, and nothing in the case is
modified.

## 2. How it works

The pipeline is **re-run from the source files with the record withheld** —
ingestion, extraction, identity resolution, graph construction, analytics,
pattern detection and contradiction detection all recompute — and the result is
diffed against the case as recorded.

```
                 data/raw/  (never modified)
                      |
        +-------------+-------------+
        |                           |
   full pipeline            pipeline with the
   (the baseline)           record withheld
        |                           |
        +----------- diff ----------+
                      |
        links removed / weakened · subjects isolated
        identities that come apart · contradictions
        resolved or introduced · patterns that stop
        firing · influence ranking movement
```

A full re-run costs about **0.25 s** on the Operation Meridian corpus, so there
is no reason to approximate.

### Why not adjust the finished graph instead

Because the interesting effects happen upstream of the graph.

Withdrawing a record can change **identity resolution**. Two people merged on a
phone number quoted only in that record come apart again — and every link,
ranking and finding that depended on them being one person changes with them. An
adjustment applied to the completed graph cannot show that. A re-run does, and
it is often the most important thing the simulation has to say.

Recomputing edge weights after the fact is also not possible in general: CDR and
transaction edges take weights derived from call counts and amounts
(`1.0 + n/25`, `1.0 + min(amount/5e6, 3)`) that are not recoverable from the
stored per-source records.

## 3. Aligning the two runs

Person ids are **positional** — `P0001`, `P0002`, … assigned over sorted
clusters — so withholding one record renumbers every subject after it. Diffing
on ids would report the entire network as rebuilt every time.

Subjects are therefore matched between the two runs by **what identifies them**:
phone numbers, account numbers and name forms. Matching is greedy,
highest-overlap-first, over a sorted candidate list, so two runs over the same
corpus align identically.

Every other node type already has a deterministic id derived from its label
(`L-Kurla`, `V-MH01AB1234`, `F-FIR/2026/0101`, and a SHA-1 of the name for
organisations) and needs no alignment.

The alignment is also what surfaces an **identity split**: one baseline subject
matching two counterfactual subjects means the withheld record was the only
thing holding that identity together.

Contradictions and pattern findings are renumbered on every run (`C001…`,
`A001…`), so they are compared on `(type, title)` rather than on id.

## 4. Granularity

| Withhold | Meaning | Example |
|---|---|---|
| `source_id` | a whole document or feed | `FIR/2026/0101`, `SUR/2026/05`, `CR0007`, `CDR`, `TXN` |
| `record_id` | one row inside a feed | a CDR call id, a transaction id |

Row-level granularity exists because the contradiction engine cites its evidence
at that level. A timeline conflict names two specific calls, so the simulator
must be able to withhold exactly those two calls — which is what closes the loop
between the two engines.

## 5. API

```
GET /api/impact?source_id=…&record_id=…        (both repeatable)
```

Requires `evidence:read`; writes a `SIMULATE_EVIDENCE_REMOVAL` audit entry.
`400` if nothing was named, `404` if a source id is not an ingested document.

Returns:

```
withheld[]                  what was held back, with a summary of each record
summary                     before/after counts: subjects, links, contradictions,
                            patterns, resolved entities, links removed/weakened
removed_links[]             links that disappear entirely
weakened_links[]            confidence, observation and independent-source deltas
introduced_links[]          links that only appear once the record is withheld
isolated_subjects[]         subjects left with no link to the rest of the case
identity_splits[]           subjects that come apart into several identities
contradictions_resolved[]   conflicts that stop firing
contradictions_introduced[] conflicts that start firing
findings_resolved[]         patterns that stop firing
findings_introduced[]       patterns that start firing
influence_changes[]         ranking movement, subjects that actually moved
method, disclaimer
```

## 6. Worked examples

Real output from the Operation Meridian corpus.

**Withhold the two CDR rows behind contradiction C001**

```
links 138 → 138 · subjects 53 → 53 · contradictions 5 → 4
resolved: timeline_conflict — Rajesh Kumar Singh between Kurla and Ghatkopar
```

The conflict disappears and nothing else moves — the two calls support the
contradiction and no relationship.

**Withhold `CR0002`, the criminal record carrying R. Kumar's phone**

```
links 138 → 132 · contradictions 5 → 4 · patterns 23 → 20
resolved: timeline_conflict
```

More interesting: `CR0002` is what attributes handset `9000000002` to Rajesh
Kumar Singh. Without it his CDR sightings are no longer his, so six links and
three patterns go with them — and the timeline conflict resolves for a
completely different reason than in the first example.

**Withhold `FIR/2026/0107`**

```
links 138 → 131 · subjects 53 → 51 · patterns 23 → 23
ranking: Vikram Sethi #3 → #2, Imran Qureshi #2 → #3
```

One FIR is enough to reorder who the case considers most central.

**Withhold the whole CDR feed**

```
links 138 → 118 · contradictions 5 → 3 · patterns 23 → 5
```

Eighteen of the twenty-three patterns rest on call records.

## 7. Limitations

- **It answers "without this record", not "if this record were wrong".** A
  falsified record is not the same as an absent one; the simulator models
  absence only.
- **Withheld evidence is removed, not weighted down.** There is no partial
  discount for a record an investigator merely doubts.
- **Second-order effects on the corpus are not modelled.** If a record would
  never have been filed, neither might others that cite it — the simulator does
  not reason about that.
- **Feed-level withholding is coarse.** Excluding `CDR` removes every call;
  excluding a subset means naming the rows.
- **Comparing findings on `(type, title)`** means a finding whose title changes
  slightly is reported as one resolved and one introduced rather than as
  modified.
- **`identity_splits` has no natural trigger in this corpus.** Merges in
  Operation Meridian are supported by more than one record each, so the path is
  exercised by unit test rather than by the demo data.
- **Cost scales with the corpus.** A quarter of a second here; a full re-run per
  simulation is not the right design at agency scale, where an incremental
  recompute would be needed.

## 8. Relationship to the contradiction engine

The two are designed to compose, and the composition is the point.

The contradiction engine reports *what disagrees* and names the records
responsible. The simulator answers *what it would cost to set those records
aside*. In the UI the simulator is seeded directly from a contradiction's own
provenance — the "if this evidence were withheld" panel in the evidence drawer
withholds exactly the records the conflict cites.

See `docs/CONTRADICTION_ENGINE.md`.
