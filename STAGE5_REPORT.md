# STAGE 5 — Investigation Copilot: Final Report

**Status: COMPLETE & VERIFIED.** All stage-5 acceptance items are implemented,
tested offline (pytest) and verified live against the running stack
(`stage4-live-smoke.py`, `stage5-live-smoke.py`). The six existing engines
(contradiction / hypothesis / impact / timeline / geospatial / NetworkX) are
**untouched** — the copilot is a new read-only intelligence layer on top of
the confirmed case data.

---

## 1. What Stage 5 delivered

1. **Deterministic-first investigation copilot** — case-scoped Q&A over
   confirmed records with 12 intents, computed confidence, verified
   citations and a fixed neutral register. No hallucination path exists:
   out-of-domain questions return `unsupported` with confidence 0 and zero
   citations.
2. **Optional, non-authoritative LLM** — a Gemini provider may re-render
   *prose* from the deterministic `data` payload; it is validated
   (citations must survive) and is **never** a source of facts. With no
   key configured, the platform states that honestly. The LLM is never
   presented as active when it is not.
3. **Structured `was_at` claims + EVIDENCE_CONTRADICTION** — a fourth
   contradiction type (R4) now fires on *structured claims* from the
   documents (same person, different locations, tight time window) in any
   supported language. Claims are materialized only on **accepted**
   candidates, are idempotent, keep the original snippet + provenance, and
   attach to the confirmed entity.
4. **Multilingual EN/HI/MR/UR** — document language detection with honest
   signals, multilingual entity resolution via an alias registry +
   transliteration, per-language claim extraction, multilingual NLQ search,
   and **question-in-script → answer-in-script** Q&A (acceptance #11–12).
5. **Impact simulation endpoint** — `POST /copilot/impact` shows what
   removing one evidence record *would* do (edges removed, newly isolated
   entities, affected findings) with `simulation_only: true`. The database
   is provably unchanged.
6. **Frontend** — per-case Copilot console (ask/answer/citations/deep
   links, EN/HI/MR/UR), platform copilot page, verbatim **original text
   panel** in document review (the target of citation deep links), evidence
   deep-link highlighting.
7. **RBAC + audit** — ask/impact at INVESTIGATOR floor, read floor for
   status/suggestions/search; every copilot action audited (actor, case,
   timestamp, question, intent, result count) with no secrets.

## 2. Architecture (additive layer only)

```
POST /api/v1/cases/{id}/copilot/ask
   └─ CopilotQuestionParser (intents.py)
        │  case-scoped name resolution: canonical + aliases, any script
        │  language-specific intent anchors (EN/HI/MR/UR)
        │  stamps data.question_language (script-aware resolver)
        └─ DeterministicProvider.answer(ctx, intent)
             │  12 intent handlers over Stage4Data (confirmed only)
             │  data (structured facts) + confidence (computed) + citations (verified)
             │  neutral template prose
             │  localize.render_answer(intent, data, lang, ctx)  ← HI/MR/UR
             └─ CopilotAnswer{intent, status, answer_text, confidence,
                              confidence_basis, citations, data, provider}
        [optional] GeminiProvider — prose re-render ONLY, validated,
        falls back to deterministic text on any failure (flagged `fallback`)
```

`CaseContext` loads one case's confirmed entities/relationships/evidence/
events/locations/claims + findings/hypotheses. Every citation id is
resolved against this context before serving; anything unresolvable is
dropped, and a question with nothing to cite is answered honestly.

## 3. Intent engine — 12 intents

`impact_simulation` · `evidence_lookup` (E-ids) · `relationship_path` (2
names) · `neighbourhood` (1 name) · `contradictions` · `gaps` ·
`hypotheses` · `timeline` · `location_query` · `case_overview` ·
`entity_profile` (1 name) · `entity_search` (honest no-match) ·
`unsupported` (out-of-domain fallback).

Ordering is most-specific-first (E-id impact > E-id lookup > 2-name path >
1-name neighbourhood > thematic > profile > search > fallback), so the
English regression suite's questions parse exactly as before, and the
multilingual anchors (जोडलेले/जुड़ा/संबंध/جڑ, काय घडले/क्या हुआ/کیا ہوا,
विसंगति/تضاد, सारांश/خلاصہ, ठिकाण/स्थान/مقام, …) only *add* coverage.

## 4. No-hallucination contract (verified)

| Property | Verification |
|---|---|
| Every cited id exists in the case | `test_copilot.py` (citation ⊆ context) + live smoke §6 "all cited records exist in the case (no fabricated ids)" |
| Out-of-domain → honest refusal | live smoke: zero citations, `unsupported`-class answer, confidence 0 |
| No confident invented answer | confidence is computed per intent with a stated `confidence_basis` (e.g. "engine evaluated N confirmed pairs") |
| Neutral language | banned-phrase assertions (`proves`, `guilty`) in unit tests and live smoke; fixed neutral templates |
| Confirmed data only | providers read `Stage4Data` (accepted rows); candidates invisible — proven by the E2E claims test where only accepted candidates produce claims |
| LLM honesty | `/copilot` reports `gemini: active=false, reason="Not configured…"` and the answer payload carries `provider` + `fallback` truthfully |

## 5. Structured claims → EVIDENCE_CONTRADICTION (R4)

* Triggers per language (`multilingual:claim_was_at:{en,hi,mr,ur}`),
  person resolved via alias registry / confirmed entities, location matched
  against known locations at a word boundary, adjacent ISO timestamp
  required; confidence 0.70, method recorded.
* Materialized **only on acceptance** of the candidate
  (`_materialize_claims`), idempotent by `source_reference`
  (`candidate:<id>`), and attached to the confirmed (matched) entity.
* The contradiction engine gained `detect_claim_contradictions` (R4):
  same resolved person, ≥2 locations, Δt within tolerance →
  **EVIDENCE_CONTRADICTION** (`details.rule="R4"`, `variant="spatial"`,
  HIGH at Δt≈0) with both evidence records in `supporting_evidence_ids` and
  the neutral explanation "…requires investigator review…".
* Verified end state on CASE-DEMO-MULTILING-01: **4 claims, exactly 1
  HIGH EVIDENCE_CONTRADICTION (Mumbai vs Pune, Δt 0 min), 2 hypotheses**.

## 6. Multilingual (acceptance #11–12 — verified)

Live matrix (all pass, smoke §7b):

| Question (abridged) | Intent | q_lang | answer_language | Script |
|---|---|---|---|---|
| `राजेश कुमार आणि … जोडलेले का आहे?` | relationship_path | mr | mr | Devanagari |
| `राजेश कुमार कोणाशी जोडलेला?` | neighbourhood | mr | mr | Devanagari |
| `राजेश कुमार कुठे?` | location_query | mr | mr | Devanagari |
| `इस केस में … किन लोगों से संबंध है?` | neighbourhood | hi | hi | Devanagari |
| `راجش کمار اور … کیسے جڑے ہوئے ہیں؟` | relationship_path | ur | ur | Perso-Arabic |
| `How are Rajesh Kumar and Vikram Rao connected?` | relationship_path | en | en | Latin |

* The MR and EN versions of the same question return **identical citation
  sets** (facts unchanged by localization).
* Names resolve in the question's script because acceptance now preserves
  original-script surface forms on confirmed entities
  (`_fold_aliases` + backfill for pre-existing entities).
* Mixed-script questions ("Rajesh Kumar आणि …") stay local — the
  question resolver keys on the presence of the local script, not on
  character-count dominance (document detection unchanged).
* Localization layer: `copilot/localize.py` — 13 templates × 3 languages
  (12 intents + unsupported), rendering the handler's `data` with the same
  numbers/E-refs and the neutral register; any template failure degrades to
  the validated English text (`localization_note` reported honestly).

## 7. Impact simulation — verified unchanged DB

`POST /cases/{id}/copilot/impact` returns
`{simulation_only: true, edges_removed, newly_isolated_entities, diff,
affected_findings, …}` computed on a graph copy. Stage-5 demo step 25:
graph hash before == after (asserted in the demo script; the endpoint has
no write path).

## 8. RBAC & audit — verified

* ANALYST: `GET findings` 200, `POST ask` **403** (smoke §9).
* No token: rejected (401/403). Unknown case: 404.
* Audit rows for ask/impact/search carry actor, case, timestamp, question,
  intent, result count — no secrets (unit-asserted).

## 9. Frontend (Phase J)

* `/cases/:id/copilot` — case copilot console: engine status, suggested
  questions, ask box (EN/HI/MR/UR), answer card (status/intent/language
  badges, answer text, confidence + basis, structured facts, citations with
  deep links: *View evidence* → highlighted row; *Open document* → verbatim
  original text; *Show in graph / timeline / map / hypotheses /
  contradictions*), follow-up chips, earlier-question history, honest
  neutral-register footer.
* `/copilot` — platform capability statement + route into per-case
  consoles (lists cases with entity counts).
* Document review — **Original document text** panel (verbatim, language +
  confidence shown); extraction never modifies the text.
* Evidence page — citation deep links (`?evidence=<id>` highlights the
  row, paging disabled so the cited record is always visible; "Clear"
  dismisses), document column links straight to the original text.

## 10. Regression & verification evidence

| Gate | Result |
|---|---|
| `pytest` (backend, full suite, ×3) | **378 passed / 1 skipped** each run (the sole skip is the live-Neo4j integration test — intentional) |
| `npm run build` | ✓ (10.2s) |
| `npm run test:frontend-sanity` | **45/45** pages render |
| `npm run test:frontend-auth` | **passed** (offline/online flow checks) |
| `scripts/stage4-live-smoke.py` | **all checks passed** (stage-4 engines + contradiction demo intact) |
| `scripts/stage5-live-smoke.py` | **34/34 checks passed** (incl. multilingual Q&A, no-fabricated-ids, RBAC, claims, stage-4 regression) |
| New unit tests | `tests/test_copilot_multilingual.py` — 27 tests (question-language resolver, ML intents, localization rendering, E2E localized ask, alias preservation) |

No existing test was weakened or deleted; the pre-existing
`test_evidence_claims.py` E2E (two-language R4 pipeline) passes unchanged.

## 11. Acceptance checklist (final demo)

| # | Item | Status |
|---|---|---|
| 1–10 | Platform status honest (stage-5, deterministic active, no fake LLM), per-case status, data-driven suggestions, analyze yields the contradiction, overview/profile/relationship/location/contradiction Q&A all answered + cited | ✅ live smoke §1–5 |
| 11–12 | Ask in Marathi → answer in Marathi (Hindi/Urdu likewise; EN unchanged) | ✅ live smoke §7b + E2E tests |
| 13–15 | Citations open the original source (evidence row highlight, document verbatim text, graph/timeline/map deep links) | ✅ frontend deep links + raw-text panel |
| 16–24 | Relationship/contradiction/gap/hypothesis/timeline/impact questions incl. simulation before/after (simulation_only) | ✅ unit + live smoke |
| 25 | Original DB unchanged after simulation | ✅ `simulation_only`, no write path, demo assertion |
| 26 | All actions audited (actor/case/ts/question/intent/result count, no secrets) | ✅ unit-asserted |

## 12. Known limitations (stated, not hidden)

* Cross-script understanding is provided by the alias registry +
  transliteration for names/triggers — not by general machine translation.
* Short Devanagari questions without lexicon words default hi→mr (region
  default); visible in `question_language`.
* The Gemini provider is architecturally present and validated but
  unconfigured in this deployment (no key); the platform says so.
* Neo4j is optional; the graph layer degrades to the SQL graph (the
  skipped test reflects the absent live Neo4j, intentionally).

## 13. Key files

```
backend/app/services/copilot/
  intents.py                 parser: 12 intents + ML anchors + question_language
  context.py                 CaseContext (confirmed data, name index any script)
  localize.py                13×3 localization templates (hi/mr/ur)
  providers/base.py          CopilotAnswer, Citation, provider contract
  providers/deterministic.py 12 intent handlers (facts+confidence+citations)
  providers/gemini.py        optional validated prose re-render (never facts)
backend/app/services/language/detect.py      document detection + detect_question_language
backend/app/services/language/transliterate.py  IIT transliteration + match normalization
backend/app/services/document_service.py     _fold_aliases, alias backfill, claim materialization
backend/app/services/entity_extraction.py    multilingual gazetteer + per-language was_at claims
backend/app/services/finding_service.py      claim-contradiction detection (R4) hook
backend/app/api/v1/copilot.py                platform + case copilot endpoints
backend/tests/test_copilot.py                copilot contract (12 intents, RBAC, audit, guards)
backend/tests/test_copilot_multilingual.py   multilingual QA + alias preservation (27 tests)
backend/tests/test_evidence_claims.py        two-language claims → R4 E2E (pre-existing)
scripts/stage5-live-smoke.py                 34 live checks
data/raw/multilingual_aliases.json           alias registry (SYNTHETIC DEMONSTRATION DATA)
src/pages/cases/CaseCopilotPage.jsx          case copilot console
src/pages/cases/CopilotPage.jsx              platform copilot page
src/pages/cases/DocumentReviewPage.jsx       + verbatim original-text panel
src/pages/cases/CaseEvidencePage.jsx         + citation deep links
src/services/v1/copilotService.js            case copilot API client
docs/COPILOT.md · docs/MULTILINGUAL.md       stage-5 documentation
```

## 14. How to run

```bash
# backend (port 8000) — seeders run at startup, idempotent
python3 backend/run.py
# frontend (port 5173, proxies /api/v1)
npm install && npm run dev
# verification
cd backend && python3 -m pytest tests/ -q        # 378 passed / 1 skipped
python3 scripts/stage4-live-smoke.py             # stage-4 engines intact
python3 scripts/stage5-live-smoke.py             # 34/34 stage-5 checks
npm run build && npm run test:frontend-sanity && npm run test:frontend-auth
```

Log in with `admin@nexus.local` / `nexus2026` (or
`demo-investigator@nexus.local`), open **CASE-DEMO-MULTILING-01**, and use
its **Copilot** tab — ask in English, मराठी, हिन्दी or اردو.
