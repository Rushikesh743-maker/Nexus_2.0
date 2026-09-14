# NEXUS — Multilingual Support (Stage 5)

NEXUS supports four languages across the case pipeline: **English (`en`),
Hindi (`hi`), Marathi (`mr`) and Urdu (`ur`)**. The guiding principle is
*language-neutral case data, original-language evidence*:

> The confirmed case graph stores **canonical (language-neutral) names** and
> structured facts. Documents, snippets, aliases and surface forms keep
> their **original script and word form** — nothing is overwritten or
> "corrected". An investigator can read, search and ask in any supported
> language and get back the same verified facts.

All synthetic multilingual material is labelled **SYNTHETIC DEMONSTRATION
DATA** and uses the fictional names from the Stage-5 specification.

---

## 1. Language detection — documents

`app/services/language/detect.py` detects the dominant language of a
document using two signals, and reports them honestly:

1. **Dominant script** — character-count ratio across Devanagari
   (`\u0900–\u097F`), Perso-Arabic (`\u0600–\u06FF`) and Latin.
2. **Lexicon hits** — per-script function-word lexicons (e.g. Marathi
   *आणि, आहे, नाही, झाले* vs Hindi *है, का, में, पर*).

`detect_language(text) → LanguageInfo(code, name, script, confidence,
signals)`. The `signals` list explains **why** each score was reached
("dominant script devanagari (82%)", "marathi lexicon hits: आणि, आहे…"),
so a mixed-script document is never silently mislabelled. Confidence is
derived from the evidence, not invented; undetectable text yields
`code=None` and is stored as-is (extraction still runs its language rules
on whatever script is present).

The detected language is persisted per document (`Document.language`,
`language_confidence`) and shown in the document review panel next to the
**verbatim original text**.

## 2. Language detection — questions (script-aware)

Investigator questions are usually *mixed script*: a Marathi question that
names people in Latin script ("Rajesh Kumar आणि Vikram Rao जोडलेले का
आहेत?"). Character counting would misread that as English, so the copilot
uses a separate resolver:

`detect_question_language(text) → "en" | "hi" | "mr" | "ur"`

* any **Devanagari** present → the question is in a Devanagari language;
  hi vs mr is decided by the lexicons **over the Devanagari words only**
  (tie → `mr`, the region default);
* any **Perso-Arabic** present → `ur`;
* pure Latin → `en`.

Latin fragments in a local-script question are treated as names/numbers —
they never flip the language. Document-level detection is intentionally
unchanged (character dominance is the right signal for documents).

## 3. Multilingual entity resolution

`data/raw/multilingual_aliases.json` is the **alias registry** (data, not
logic): canonical name → surface forms per script, e.g.

```
Rajesh Kumar:
  en  [Rajesh Kumar, R. Kumar, Rakesh Kumar, Rajesh K.]
  hi  [राजेश कुमार, राजकुमार …]
  mr  [राजेश कुमार, …]
  ur  [راجش کمار, …]
```

How it is used:

* **Extraction** — the multilingual gazetteer matches surface forms in a
  document and emits a candidate with the *canonical* name + the original
  surface form as alias (`method=multilingual:gazetteer`, with the
  language). The case graph therefore stays language-neutral.
* **Matching** — `best_match` compares candidates against existing
  entities through IIT-style **transliteration** (`language/transliterate.py`),
  so "राजेश कुमार" ↔ "Rajesh Kumar" ↔ "راجش کمار" converge to one
  confirmed entity with an explained similarity.
* **Acceptance preserves the original script** — when a candidate is
  accepted (as new entity or matched to an existing one), its surface
  forms are folded into the entity's alias list
  (`document_service._fold_aliases`). The confirmed entity therefore
  resolves in **every** script it has been seen in. A one-off backfill
  (`backfill_entity_alias_surface_forms`) restored this for entities
  accepted before the preservation existed.
* **Search & NLQ** — the copilot name index maps every surface form
  (canonical + aliases, any script) to the entity id, so
  "राजेश कुमार कोणाशी जोडलेला आहे?" resolves to *Rajesh Kumar* and
  `nlq/search` accepts Devanagari/Arabic queries.

## 4. Multilingual structured claims

`entity_extraction` derives **`was_at`** claims from each language with
language-specific trigger patterns and an adjacent ISO timestamp
(`method=multilingual:claim_was_at:{lang}`, confidence 0.70):

| Language | Trigger (abridged) |
|---|---|
| English | "<person> was/were seen/observed/found … at/in <location>" or "<person> was at <location>" |
| Hindi / Marathi | "<person> <location>-locative> + दिसा/देखा-verb family" (e.g. *पुण्यात दिसून आला*, *मुंबई में देखे गए*) |
| Urdu | "<person> <location> + دیکھا/نظر ملا verb family" |

The person must resolve through the alias registry or case-confirmed
entities; the location must equal (or start with, at a word boundary) a
known location. The **original sentence** is stored as the claim's
`source_snippet` with line provenance — never a translation.

These claims feed the contradiction engine unchanged: a Marathi claim
"*seen in Pune at 21:10*" and a Hindi claim "*seen in Mumbai at 21:15*"
for the same resolved person produce the **R4 EVIDENCE_CONTRADICTION
(spatial)** exactly like English claims.

## 5. Multilingual Q&A (acceptance #11–12)

Ask in Marathi/Hindi/Urdu → **answer in that language**, same facts:

* the parser resolves names in the question's script (§3) and classifies
  intent with per-language anchors (see `docs/COPILOT.md` §3);
* `detect_question_language` stamps `data.question_language`;
* the deterministic provider computes facts/citations/confidence as usual,
  then `localize.render_answer(intent, data, lang, ctx)` re-renders the
  prose from the structured `data` in the requested language — **13 intent
  templates × 3 languages** (12 intents + unsupported), all in the neutral
  register ("फक्त पुष्ट संबंधांमधून तयार झाला आहे — नोंदवलेला सहसंबंध,
  वागणाचा आरोप नाही");
* facts, citations and confidence are **never localized away** — the MR
  answer and the EN answer for the same question cite the identical record
  set (asserted in tests and the live smoke);
* if a template is missing for an (intent, language) pair, the answer
  stays English and `data.localization_note` says so honestly.

## 6. Honest limitations

* Cross-script *comprehension* (e.g. an English query fully matching a
  Marathi document's phrasing) is provided via the alias registry +
  transliteration for **names and known triggers**, not by a general
  machine translation. The platform does not claim document-level MT.
* The hi/mr lexicon comparison is a heuristic; short Devanagari questions
  with no lexicon words fall to the region default (`mr`) — which is the
  conservative choice for this deployment and is visible in
  `question_language`.
* Urdu uses Perso-Arabic; Naskh vs Nastaliq rendering is a display concern
  only.

## 7. Demonstration data

The seeded case **CASE-DEMO-MULTILING-01** ("Multilingual demonstration —
one incident, four languages") carries one incident in **EN, HI, MR and
UR** documents (all labelled SYNTHETIC DEMONSTRATION DATA). Verified end
state after analyze:

* 4 documents detected `en/hi/mr/ur`;
* confirmed persons/locations are language-neutral (ASCII canonicals);
* original-script aliases preserved on the confirmed entities;
* **4 `was_at` claims** (one per document);
* **exactly one HIGH EVIDENCE_CONTRADICTION** — *Rajesh Kumar: Mumbai vs
  Pune* (R4 spatial, Δt ≈ 0 min) — with both evidence records cited;
* multilingual Q&A: MR/HI/UR questions answered in the asked language with
  identical citations to the English counterpart.
