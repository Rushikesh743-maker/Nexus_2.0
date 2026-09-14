# NEXUS — Investigation Copilot (Stage 5)

The case copilot answers investigator questions **only from the confirmed
records of one case** — entities, relationships, evidence, timeline events,
locations, structured claims, findings, gaps and hypotheses. It is
**deterministic-first**: the offline engine computes every answer with a
fixed, neutral template over verified data; an LLM (Gemini) may be
configured to re-render *prose* but is never a source of facts and never
fabricates records.

---

## 1. Design invariants

| Invariant | Enforcement |
|---|---|
| No hallucination | Every cited id is validated against the case context before the answer is served. Out-of-domain questions return `unsupported` with **zero** citations. |
| Confirmed data only | The provider reads `Stage4Data` (accepted/confirmed rows). Candidates, unaccepted matches and rejected items are invisible to the copilot. |
| Neutral register | Fixed vocabulary: *potential connection, analytical support, potential contradiction, requires review, insufficient evidence*. Banned wording (`proves`, `guilty`, …) is asserted in tests. |
| LLM never a fact source | The Gemini provider only re-renders prose from the deterministic `data` payload and is rejected (with a logged reason) if it omits or alters required citations. With no key, the platform states this honestly. |
| Read-only | `ask`, `suggestions`, `status`, search never write. The impact endpoint is a pure simulation (`simulation_only: true`) — the database is unchanged (asserted in the demo). |
| Audited | Every ask/impact/search records actor, case, timestamp, question, intent and result counts. No secrets in the audit payload. |

---

## 2. API surface

All case endpoints are scoped to one case and protected by the platform
JWT/RBAC. Ask/impact require **INVESTIGATOR** or above; status/suggestions/
search are readable at the **ANALYST** floor (case access still required).

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/copilot` | Platform capability statement (stage, available/planned, honest provider state) |
| `GET` | `/api/v1/cases/{case_id}/copilot/status` | Per-case provider list (`active` flag + reason, model) |
| `GET` | `/api/v1/cases/{case_id}/copilot/suggestions` | Data-driven suggested questions |
| `POST` | `/api/v1/cases/{case_id}/copilot/ask` | Ask a question (`{question}` ≤ 500 chars) |
| `POST` | `/api/v1/cases/{case_id}/copilot/impact` | Simulate removing one evidence record (`{evidence_id}`) |
| `POST` | `/api/v1/cases/{case_id}/copilot/nlq/search` | Multilingual search over confirmed records (`{query, k}`) |
| `GET` | `/api/v1/cases/{case_id}/search?q=…` | Same search, GET form |

### Ask response contract

```json
{
  "intent": "relationship_path",
  "interpretation": "Find how Rajesh Kumar is connected to Vikram Rao",
  "status": "answered",            // answered | not_enough_data | unsupported | error
  "answer_text": "…",              // neutral prose (localized when asked in HI/MR/UR)
  "confidence": 0.9,               // computed per intent, never invented
  "confidence_basis": "…",
  "citations": [
    {"kind": "entity", "id": 76, "label": "Rajesh Kumar", "record": {"entity_type": "person", …}}
  ],
  "data": { … },                   // structured facts (localized prose is re-rendered from this)
  "provider": "deterministic",     // or "gemini" when the LLM re-rendered prose
  "fallback": false                // true when a provider failure fell back to deterministic
}
```

Citation kinds: `entity`, `relationship`, `evidence`, `finding`,
`hypothesis`, `event`, `location`, `claim`. `record` carries the minimal
verifiable facts (type, source reference, document id, timestamp, …) — the
frontend turns them into deep links to the original source.

---

## 3. Intent taxonomy

`CopilotQuestionParser` (deterministic, case-scoped) classifies the
question using the case's confirmed names (canonical + aliases, **any
supported script**) and language-specific intent anchors:

| # | Intent | Trigger (English / multilingual anchors) |
|---|---|---|
| 1 | `impact_simulation` | an `E<id>` reference + what-if verbs (*what if / remove / impact / काय होईल / क्या होगा / کیا ہوگا*) |
| 2 | `evidence_lookup` | any other `E<id>` reference (*evidence / prove / पुराव / साक्ष / ثبوت*) |
| 3 | `relationship_path` | ≥ 2 names + connection verbs (*connect / between / how is / जोडलेले / जुड़ा / संबंध / جڑ / رابطہ / تعلق*) |
| 4 | `neighbourhood` | 1 name + *connected to / around / network of / जोडलेला / संबंध / جڑ* |
| 5 | `contradictions` | *contradiction / inconsistency / विसंगति / विरोधाभास / تضاد* |
| 6 | `gaps` | *gap / missing / insufficient / गहाळ / गुम / غائب* |
| 7 | `hypotheses` | *hypothesis / explanation / rebuttal / गृहितक / कल्पना / مفروضہ* |
| 8 | `timeline` | *timeline / sequence / what happened / when / काय घडले / क्या हुआ / کیا ہوا* |
| 9 | `location_query` | *where / location / move / ठिकाण / स्थान / مقام / कुठे / कहाँ / کہاں* |
| 10 | `case_overview` | *summary / overview / big picture / सारांश / संक्षेप / خلاصہ* |
| 11 | `entity_profile` | exactly one confirmed name, no stronger intent |
| 12 | `entity_search` | a search-like question with no confirmed name → honest no-match over the confirmed corpus |
| — | `unsupported` | out-of-domain (no case basis) → confidence 0, no citations |

Ordering is most-specific-first; a question that names two people and asks
"how are they connected?" is always `relationship_path`, never a profile.

The parser stamps `data.question_language` (`en|hi|mr|ur`) with the
script-aware question resolver (see `docs/MULTILINGUAL.md` §2).

---

## 4. The deterministic provider

`DeterministicProvider.answer(ctx, intent)` dispatches to one handler per
intent. Each handler:

1. reads only `ctx.data` (confirmed rows) + `ctx.findings` / `ctx.hypotheses`;
2. computes `data` (structured facts), `confidence` (per-intent formula,
   explained in `confidence_basis`) and the citation list;
3. renders neutral prose from `data` with a fixed template;
4. **localizes the prose** when the question was asked in HI/MR/UR —
   `localize.render_answer(intent, data, lang, ctx)` re-renders the *same*
   facts in the requested script. Facts, citations, confidence and status
   are never touched. If no template exists for the pair (intent, language),
   the answer honestly stays English with `data.localization_note`.

Example neutral wording (relationship path, Marathi):
> *पुष्ट संबंध: Rajesh Kumar → Vikram Rao, 1 पायरी. … हा मार्ग फक्त पुष्ट
> संबंधांमधून तयार झाला आहे — नोंदवलेला सहसंबंध, वागणाचा आरोप नाही.*
> ("This path is built only from confirmed relationships — a recorded
> association, not an accusation of conduct.")

---

## 5. Impact simulation (what-if)

`POST /copilot/impact` with `{evidence_id}`:

* removes that evidence's relationships from a **copy** of the graph,
* reports edges removed, newly isolated entities, affected findings and the
  structural diff,
* sets `simulation_only: true` — **the database is not modified** (verified
  in the stage-5 demo: the graph is byte-identical before and after).

---

## 6. Multilingual search (NLQ)

`POST /copilot/nlq/search` and `GET /cases/{id}/search` search the confirmed
corpus (entity names + aliases in every script, relationships, evidence,
events, locations, claims). Non-Latin queries are transliterated/matched
against the alias registry, so a Devanagari query ("पुणे") finds the
confirmed location **Pune** — and English queries still work. Results are
hits with `kind`, `label` and snippet; they are search results, never
conclusions.

---

## 7. Frontend

* **`/cases/:id/copilot`** — the case copilot console (v1 case tab
  *Copilot*): engine status, suggested questions, ask box (EN/HI/MR/UR),
  answer card with status/intent/language badges, confidence + basis,
  structured facts, and the citation list with **deep links to the original
  source** (view evidence → highlighted row; open document → the verbatim
  original text; show in graph / timeline / map / hypotheses /
  contradictions).
* **`/copilot`** — platform capability statement + route into the
  per-case consoles.
* **Document review** shows the **verbatim original text** of each document
  (extraction never modifies it) — the target of citation deep links.

---

## 8. Testing

* `tests/test_copilot.py` — all 12 intents, confirmed-only answers,
  citation ⊆ context, confidence, neutral language, RBAC, audit, and the
  Gemini validation guards (prose-only contract).
* `tests/test_copilot_multilingual.py` — script-aware question-language
  resolution, multilingual intent parsing, localization rendering
  (HI/MR/UR, facts preserved), E2E "ask in MR/HI/UR → answer in that
  language with the same citations", and original-script alias
  preservation on accepted entities.
* `scripts/stage5-live-smoke.py` — 34 live checks incl. the multilingual
  Q&A acceptance (Marathi/Hindi/Urdu question → localized answer, English
  control unchanged, citations identical across languages).
