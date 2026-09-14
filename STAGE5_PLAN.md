# Stage 5 implementation plan (working doc)

## Phases
- [x] A. Language module: detect (en/hi/mr/ur), transliterate (Devanagari + Urdu→Latin), normalize_for_match
- [x] B. Resolution upgrade: cross-script transliteration match, initial-at-any-token, near-phonetic (edit≤1)
- [x] C. Models: EvidenceClaim table; document cols (language_confidence, translation_status, processing_method); extraction cols (original_text, normalized_text, language, language_confidence, claims JSON); _ensure_columns migration
- [x] D. Extraction: multilingual branch (alias gazetteer data file, person pattern, was_at claim pattern, located_at rule); ExtractionResult.language/.claims
- [x] E. document_service: persist language fields + original/normalized text; materialize EvidenceClaim rows on candidate/match acceptance
- [x] F. Claim contradiction engine R4 → EVIDENCE_CONTRADICTION findings; claims into Stage4Data + version hash
- [x] G. Multilingual search endpoint GET /cases/{id}/search
- [x] H. Copilot package: intent, retrieval, context, providers (deterministic + gemini), i18n, service, audit; routes (ask/status/suggestions) + platform /copilot upgrade
- [x] I. Demo seeder CASE-DEMO-MULTILING-01 (EN/HI/MR/UR docs through the real pipeline + review actions)
- [x] J. Frontend: case Copilot console tab (language selector, question, suggestions, citations, actions), evidence deep links, search panel, doc text panel, sanity entries
- [x] K. Tests: test_multilingual.py, test_evidence_claims.py, test_copilot.py
- [x] L. Regression: pytest ×3, build, sanity, auth, stage4-live-smoke; new stage5-live-smoke.py
- [x] M. Docs: README/ARCHITECTURE/API/DATABASE + docs/COPILOT.md + docs/MULTILINGUAL.md + STAGE5_REPORT.md

## Key decisions
- Claims stored in extraction record (JSON) at processing; materialized to evidence_claim + extracted_claim evidence rows only on acceptance (stage-2 invariant: acceptance is the only confirmed-data writer).
- R4 EVIDENCE_CONTRADICTION: same subject + was_at + Δt ≤ 15 min + different confirmed location_id (or different object for same subject+predicate+time); severity HIGH if Δt < 5 min.
- Copilot: ask = INVESTIGATOR+ (it can trigger the impact simulator; gives a real 403 test), status/suggestions/search = any authenticated (case read floor, same as entities).
- Provider chain: gemini (if GEMINI_API_KEY set) → validated (citations ⊆ context; neutral-language guard; no unknown names) else deterministic; response always carries provider + fallback flags. Claims/citations/confidence always from the deterministic layer; LLM only writes the prose.
- Confidence: computed per intent from retrieved data (documented formulas), never invented.
- "E17" in questions = evidence row id 17 (documented convention).
- CHANGE_AFTER_UPLOAD: document_id param or latest uploaded doc; report records whose provenance chain ties to it (evidence, accepted candidates→entities, relationships by source_document_id, events via evidence, findings/hypotheses citing its evidence).
