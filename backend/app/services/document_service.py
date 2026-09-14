"""Document lifecycle: upload -> processing -> review -> confirmed data.

Ownership of state transitions lives here (routers stay thin):

    upload_document      validate, store file + row, status UPLOADED
    process_document     PROCESSING -> PROCESSED | FAILED (background-safe;
                         owns its own session and a single atomic commit
                         for the whole extraction result)
    accept/reject/defer  the investigator review workflow; acceptance is
                         what (and only what) creates confirmed Entities,
                         Relationships, Evidence and TimelineEvents.

The original uploaded file and the extraction result are never modified or
deleted by review decisions — rejected candidates stay in the table with
their provenance, for audit.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.errors import ApiError, not_found
from ..core.storage import (DocumentInvalidError, store_file, validate_upload)
from ..models import (Case, Document, DocumentExtraction, Entity, EntityCandidate,
                      EntityMatchSuggestion, Evidence, EvidenceClaim, Location,
                      Relationship, RelationshipCandidate, TimelineEvent, User)
from ..security.rbac import CurrentUser
from .auth_service import record_audit
from .document_processor import ProcessingError, extract_content
from .entity_extraction import (ExtractionError, ExtractionResult,
                                get_extraction_provider)
from .entity_resolution import (best_match, combine_scores, contextual_signals,
                                normalize, normalize_multilingual,
                                ranked_matches)
from .language.transliterate import transliterate

logger = logging.getLogger("nexus.documents")


# --------------------------------------------------------------------- upload

def upload_document(db: Session, case: Case, current: CurrentUser,
                    upload: UploadFile) -> Document:
    settings = get_settings()
    try:
        validated = validate_upload(upload, settings.max_upload_mb * 1024 * 1024)
    except DocumentInvalidError as exc:
        raise ApiError(exc.code, str(exc), 400) from exc

    existing = db.scalars(
        select(Document).where(Document.case_id == case.id,
                               Document.sha256 == validated.sha256)).first()
    if existing is not None:
        raise ApiError(
            "DOCUMENT_DUPLICATE",
            f"This document already exists for this case (document {existing.id}, "
            f"{existing.filename}).", 409,
            {"existing_document_id": existing.id})

    doc = Document(
        case_id=case.id,
        filename=validated.filename[:255],
        file_type=validated.extension.lstrip("."),
        mime_type=validated.mime_type,
        file_size=validated.size,
        processing_status="UPLOADED",
        uploaded_by=current.user.id,
    )
    db.add(doc)
    db.flush()  # need the id for the storage path
    try:
        doc.storage_path = store_file(validated, case.id, doc.id)
    except OSError as exc:
        db.rollback()
        raise ApiError("DOCUMENT_INVALID",
                       "The file could not be saved to storage.", 500) from exc
    doc.sha256 = validated.sha256
    db.commit()
    db.refresh(doc)
    record_audit(db, current, "DOCUMENT_UPLOADED", "document", str(doc.id),
                 {"case_id": case.id, "filename": doc.filename, "sha256": doc.sha256})
    # stage 7: lifecycle — a fresh case moves DRAFT -> UPLOADING; an
    # analyzed case becomes STALE (its intelligence no longer covers the
    # new document). Other states keep their position.
    _upload_state_transition(db, case)
    logger.info("Document %s (%s) uploaded to case %s by %s",
                doc.id, doc.filename, case.id, current.user.email)
    return doc


def _upload_state_transition(db: Session, case: Case) -> None:
    """DRAFT -> UPLOADING on first upload; ANALYSIS_COMPLETE -> STALE on an
    upload after the case was analyzed (the documented STALE -> PROCESSING
    -> … path). Any other state keeps its position: the next processing
    job drives it through PROCESSING."""
    from . import case_state_machine as sm
    try:
        if case.workflow_state == sm.DRAFT:
            sm.transition(db, case, sm.UPLOADING)
        elif case.workflow_state == sm.ANALYSIS_COMPLETE:
            sm.transition(db, case, sm.STALE)
    except Exception as exc:  # noqa: BLE001 — state must never break upload
        db.rollback()
        logger.warning("Upload state transition failed for case %s: %s",
                       case.id, exc)


def delete_document(db: Session, doc: Document, current: CurrentUser) -> None:
    """Stage 7: delete a document from the case.

    Removes the stored file and the document row; its unconfirmed
    candidates, match suggestions and relationship candidates cascade
    (DB-level ON DELETE CASCADE). Confirmed analytical rows (entities,
    relationships, claims) are case data, not file data — they stay,
    with their provenance metadata still pointing at the (now deleted)
    document id. Evidence rows survive with document_id set to NULL.
    """
    from ..core.storage import delete_file
    delete_file(doc.storage_path)
    doc_id = doc.id
    case_id = doc.case_id
    record_audit(db, current, "DOCUMENT_DELETED", "document", str(doc_id),
                 {"case_id": case_id, "filename": doc.filename,
                  "sha256": doc.sha256})
    db.delete(doc)
    db.commit()


# --------------------------------------------------------------- processing

def _uploader_current(db: Session, doc: Document) -> CurrentUser | None:
    if doc.uploaded_by is None:
        return None
    user = db.get(User, doc.uploaded_by)
    if user is None:
        return None
    return CurrentUser(user=user, payload=None)


def _mark_failed(db: Session, doc: Document, message: str) -> None:
    doc.processing_status = "FAILED"
    doc.processing_error = message[:2000]
    db.commit()


def _case_entity_rows(db: Session, case: Case) -> list[Entity]:
    """The case's confirmed entities, read from the database.

    Sessions are created with expire_on_commit=False, so in a long-lived
    session (seeder, batch job) the case.entities collection — once
    loaded — can miss entities confirmed earlier in the same session. A
    direct SELECT (after a flush, so uncommitted rows in the same
    transaction are visible) is always current.
    """
    db.flush()
    return list(db.scalars(select(Entity).where(Entity.case_id == case.id)).all())


def _case_entity_index(db: Session, case: Case) -> dict[str, list[str]]:
    """entity_type -> [canonical names + aliases] for the case's confirmed
    entities — the case's own vocabulary, used as a first-class gazetteer."""
    index: dict[str, list[str]] = {}
    for e in _case_entity_rows(db, case):
        names = [e.canonical_name]
        aliases = (e.meta or {}).get("aliases") or []
        names.extend(a for a in aliases if isinstance(a, str))
        index.setdefault(e.entity_type, [])
        for n in names:
            if n and n not in index[e.entity_type]:
                index[e.entity_type].append(n)
    return index


def process_document(doc_id: int) -> dict:
    """Run the full pipeline for one document. Background-safe: creates its
    own session, commits the extraction atomically, and always leaves the
    document in a coherent state (PROCESSED or FAILED with a message)."""
    from ..core.database import SessionLocal

    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        if doc is None:
            logger.warning("process_document: document %s missing", doc_id)
            return {"document_id": doc_id, "status": "NOT_FOUND"}
        if doc.processing_status not in ("UPLOADED", "FAILED"):
            return {"document_id": doc_id, "status": doc.processing_status,
                    "message": "Document is not in a retryable state."}

        doc.processing_status = "PROCESSING"
        doc.processing_error = None
        doc.processing_started_at = datetime.now(timezone.utc)
        db.commit()
        record_audit(db, _uploader_current(db, doc), "DOCUMENT_PROCESSING_STARTED",
                     "document", str(doc.id), {"case_id": doc.case_id})

        case = doc.case
        content = extract_content(doc)
        provider = get_extraction_provider()
        result = provider.extract(content, _case_entity_index(db, case))

        _persist_extraction(db, doc, case, content, result, provider.name)

        doc.processing_status = "PROCESSED"
        doc.processed_at = datetime.now(timezone.utc)
        # real processing duration + real page count (PDFs only — the
        # extractor's own page list, never guessed)
        if doc.processing_started_at is not None:
            doc.processing_seconds = round(
                (doc.processed_at - doc.processing_started_at).total_seconds(), 2)
        doc.page_count = (len(content.pages)
                          if content.kind in ("pdf", "image") else None)
        db.commit()
        # stage 7: settle the case lifecycle from the real counts (the
        # upload auto-process path has no case job to do it)
        try:
            from . import case_processing as _cp
            _cp.settle_after_document(db, case)
        except Exception as exc:  # noqa: BLE001 — never break processing
            db.rollback()
            logger.warning("Post-processing settle failed for case %s: %s",
                           case.id, exc)
        record_audit(db, _uploader_current(db, doc), "DOCUMENT_PROCESSING_COMPLETED",
                     "document", str(doc.id),
                     {"case_id": doc.case_id,
                      "entities": len(result.entities),
                      "relationships": len(result.relationships)})
        logger.info("Document %s processed: %d entities, %d relationships (%s)",
                    doc.id, len(result.entities), len(result.relationships), provider.name)
        return {"document_id": doc_id, "status": "PROCESSED",
                "entities": len(result.entities),
                "relationships": len(result.relationships)}
    except (ProcessingError, ExtractionError) as exc:
        db.rollback()
        _fail_fresh(doc_id, str(exc))
        return {"document_id": doc_id, "status": "FAILED", "message": str(exc)}
    except Exception as exc:  # noqa: BLE001 — never leave PROCESSING stuck
        db.rollback()
        message = f"Unexpected processing error: {exc.__class__.__name__}"
        logger.exception("Document %s processing crashed", doc_id)
        _fail_fresh(doc_id, message)
        return {"document_id": doc_id, "status": "FAILED", "message": message}
    finally:
        db.close()


def _fail_fresh(doc_id: int, message: str) -> None:
    from ..core.database import SessionLocal

    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        if doc is not None:
            doc.processing_status = "FAILED"
            doc.processing_error = message[:2000]
            if doc.processing_started_at is not None:
                doc.processing_seconds = round(
                    (datetime.now(timezone.utc) - doc.processing_started_at
                     ).total_seconds(), 2)
            db.commit()
            record_audit(db, _uploader_current(db, doc), "DOCUMENT_PROCESSING_FAILED",
                         "document", str(doc.id), {"error": message[:500]})
    finally:
        db.close()


def _persist_extraction(db: Session, doc: Document, case: Case, content,
                        result: ExtractionResult, provider_name: str) -> None:
    """One atomic write: extraction record + candidates + match suggestions.

    Idempotent: re-processing the same document never duplicates a candidate
    with the same (type, name, source location).
    """
    stats: dict = {"chars": len(content.raw_text), "provider": provider_name,
                   "warnings": list(result.warnings)}
    if content.kind in ("pdf", "image"):
        stats["pages"] = len(content.pages)
    elif content.kind == "txt":
        stats["lines"] = len(content.lines)
    else:
        stats["rows"] = len(content.csv_rows)
        stats["columns"] = content.csv_columns
    # Phase 1: OCR provenance — which pages needed OCR (never guessed).
    ocr_pages = getattr(content, "ocr_pages", 0)
    if ocr_pages:
        stats["ocr_pages"] = ocr_pages
        stats["ocr_engine"] = "tesseract"

    # -- stage 5: language provenance (never overwrites the original text) --
    lang = result.language
    lang_code = (lang or {}).get("code")
    is_non_latin = lang_code in ("hi", "mr", "ur")

    doc.language = lang_code if lang_code in ("en", "hi", "mr", "ur") else None
    doc.language_confidence = (lang or {}).get("confidence")
    base_method = (f"rules+multilingual:{lang_code}" if is_non_latin
                   else ("rules" if provider_name == "rules" else provider_name))
    # Phase 1: mark when OCR actually ran (honest provenance).
    doc.processing_method = (f"{base_method}+ocr" if ocr_pages else base_method)
    if is_non_latin:
        doc.translation_status = "NORMALIZED"
    elif lang_code == "en":
        doc.translation_status = "NOT_REQUIRED"
    else:
        doc.translation_status = "PENDING"

    extraction = db.scalars(
        select(DocumentExtraction).where(DocumentExtraction.document_id == doc.id)).first()
    if extraction is None:
        extraction = DocumentExtraction(document_id=doc.id)
        db.add(extraction)
    extraction.source_type = content.kind
    # original_text is the untouched source (full, display-capped later);
    # raw_text remains the processing-cap copy. The original is never edited.
    extraction.original_text = content.raw_text
    extraction.raw_text = content.raw_text[:get_settings().extraction_max_chars]
    if is_non_latin:
        extraction.normalized_text = transliterate(content.raw_text)
    else:
        extraction.normalized_text = None
    extraction.language = lang_code if lang_code in ("en", "hi", "mr", "ur") else None
    extraction.language_confidence = (lang or {}).get("confidence")
    extraction.claims = [c.model_dump() for c in result.claims] or None
    extraction.pages = (
        [{"page": p["page"], "chars": p["chars"], "text_head": p["text_head"],
          **({"ocr": p["ocr"]} if p.get("ocr") else {})}
         for p in content.pages] if content.kind in ("pdf", "image") else None)
    extraction.rows = (
        {"columns": content.csv_columns,
         "rows": [[row.get(c, "") for c in content.csv_columns] for _, row in content.csv_rows[:500]]}
        if content.kind == "csv" else None)
    extraction.stats = stats
    if lang_code:
        stats["language"] = lang_code
        stats["language_confidence"] = (lang or {}).get("confidence")
    db.flush()

    # ---- entity candidates (dedup on type + normalized name + location) --
    existing_keys = {
        (c.entity_type, normalize(c.candidate_name), _loc_key(c.source_location or {}))
        for c in db.scalars(select(EntityCandidate).where(
            EntityCandidate.document_id == doc.id)).all()
    }
    created: list[EntityCandidate] = []
    rel_endpoints: dict[tuple, EntityCandidate] = {}  # (type, normname) -> candidate
    skipped_rel: list[str] = []

    for e in result.entities:
        loc = e.source.model_dump(exclude_none=True)
        key = (e.type, normalize(e.name), _loc_key(loc))
        if key in existing_keys:
            continue
        cand = EntityCandidate(
            case_id=case.id, document_id=doc.id,
            entity_type=e.type, candidate_name=e.name[:255],
            aliases=e.aliases or None, confidence=e.confidence,
            source_location=loc, source_snippet=(e.source.snippet or "")[:512],
            extraction_method=f"{e.method}"[:64], status="PENDING")
        db.add(cand)
        db.flush()
        existing_keys.add(key)
        created.append(cand)
        # first occurrence wins for relationship endpoints
        rel_endpoints.setdefault((e.type, normalize(e.name)), cand)

    # ---- relationship candidates (endpoints must be candidates) ----------
    existing_rel = {
        (r.source_candidate_id, r.target_candidate_id, r.relationship_type)
        for r in db.scalars(select(RelationshipCandidate).where(
            RelationshipCandidate.document_id == doc.id)).all()
    }
    for r in result.relationships:
        src_c = rel_endpoints.get((r.source_type, normalize(r.source_name)))
        tgt_c = rel_endpoints.get((r.target_type, normalize(r.target_name)))
        if src_c is None or tgt_c is None or src_c.id == tgt_c.id:
            skipped_rel.append(f"{r.source_name} {r.relationship_type} {r.target_name}")
            continue
        if (src_c.id, tgt_c.id, r.relationship_type) in existing_rel:
            continue
        db.add(RelationshipCandidate(
            case_id=case.id, document_id=doc.id,
            source_candidate_id=src_c.id, target_candidate_id=tgt_c.id,
            relationship_type=r.relationship_type, confidence=r.confidence,
            source_location=r.supporting.model_dump(exclude_none=True),
            source_snippet=(r.supporting.snippet or "")[:512],
            extraction_method=r.method[:64], status="PENDING"))
        existing_rel.add((src_c.id, tgt_c.id, r.relationship_type))
    if skipped_rel:
        stats.setdefault("warnings", []).append(
            f"Relationships skipped (endpoint not a detected candidate): {', '.join(skipped_rel[:5])}")

    # ---- match suggestions against the case's confirmed entities ---------
    # Every created candidate gets its own review items (the same name on
    # different lines/rows is different provenance and different evidence).
    # Phase 2: up to THREE ranked suggestions per candidate (best first,
    # rank 1..N), each combining the name-similarity reasons with
    # contextual signals (shared phone / vehicle / account / email /
    # location). Suggestions only — the investigator confirms; nothing is
    # auto-merged.
    existing_sug_candidates = {
        m.candidate_id for m in db.scalars(
            select(EntityMatchSuggestion).where(
                EntityMatchSuggestion.case_id == case.id)).all()}
    case_rows = _case_entity_rows(db, case)
    case_index = _case_entity_index(db, case)
    cand_assoc = _candidate_associations(db, doc.id, created)
    ent_assoc = _entity_associations(db, case, case_rows)
    for cand in created:
        if cand.id in existing_sug_candidates:
            continue
        ranked = ranked_matches(cand.candidate_name,
                                case_index.get(cand.entity_type, []),
                                top_k=3)
        if not ranked:
            continue
        rows = []
        for rank, (name, sim, reasons) in enumerate(ranked, start=1):
            existing = next((e for e in case_rows
                             if e.entity_type == cand.entity_type
                             and _norms_match(e, name)), None)
            if existing is None:
                continue
            bonus, ctx_reasons = contextual_signals(
                cand_assoc.get(cand.id, {}),
                ent_assoc.get(existing.id, {}))
            total, all_reasons = combine_scores(
                sim, reasons, bonus, ctx_reasons)
            rows.append(EntityMatchSuggestion(
                case_id=case.id, candidate_id=cand.id, rank=rank,
                existing_entity_id=existing.id, similarity=round(total, 3),
                reasons=all_reasons, status="PENDING"))
        if rows:
            db.add_all(rows)


def _norms_match(entity: Entity, name: str) -> bool:
    names = {normalize(entity.canonical_name)}
    for a in (entity.meta or {}).get("aliases") or []:
        if isinstance(a, str):
            names.add(normalize(a))
    return normalize(name) in names


# Phase 2: contextual entity-resolution signals. The kinds of ASSOCIATED
# entities that strengthen a name-based match (the candidate's person row
# linked to a phone in its document + the existing person linked to the
# SAME confirmed phone).
_ASSOC_KINDS = {"phone": "phone", "vehicle": "vehicle",
                "account": "account", "email": "email", "location": "location"}


def _candidate_associations(db: Session, document_id: int,
                            cands: list[EntityCandidate]) -> dict[int, dict[str, set]]:
    """Candidate id -> {kind: {normalized identifiers}} from THIS document's
    relationship candidates (e.g. candidate person —OWNS—> candidate phone).
    Unconfirmed by construction: it only tells us what the document links
    together, which is exactly what contextual similarity needs."""
    by_id = {c.id: c for c in cands}
    out: dict[int, dict[str, set]] = {c.id: {} for c in cands}
    rels = db.scalars(select(RelationshipCandidate).where(
        RelationshipCandidate.document_id == document_id)).all()
    for r in rels:
        for cid, other_id in ((r.source_candidate_id, r.target_candidate_id),
                              (r.target_candidate_id, r.source_candidate_id)):
            c, other = by_id.get(cid), by_id.get(other_id)
            if c is None or other is None:
                continue
            kind = _ASSOC_KINDS.get(other.entity_type)
            if kind and other.candidate_name:
                out[c.id].setdefault(kind, set()).add(
                    normalize(other.candidate_name))
    return out


def _entity_associations(db: Session, case: Case,
                         case_rows: list[Entity]) -> dict[int, dict[str, set]]:
    """Confirmed entity id -> {kind: {normalized identifiers}} from the
    case's CONFIRMED relationships (e.g. entity person —OWNS—> entity
    phone). Confirmed data only, by construction."""
    by_id = {e.id: e for e in case_rows}
    out: dict[int, dict[str, set]] = {e.id: {} for e in case_rows}
    rels = db.scalars(select(Relationship).where(
        Relationship.case_id == case.id)).all()
    for r in rels:
        for eid, other_id in ((r.source_entity_id, r.target_entity_id),
                              (r.target_entity_id, r.source_entity_id)):
            e, other = by_id.get(eid), by_id.get(other_id)
            if e is None or other is None:
                continue
            kind = _ASSOC_KINDS.get(other.entity_type)
            if kind and other.canonical_name:
                out[e.id].setdefault(kind, set()).add(
                    normalize(other.canonical_name))
    return out


def _loc_key(loc: dict) -> str:
    for k in ("page", "row", "line"):
        if loc.get(k) is not None:
            return f"{k}:{loc[k]}"
    return "-"


# ------------------------------------------------------------------- review

def _get_document(db: Session, doc_id: int) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None:
        not_found("DOCUMENT_NOT_FOUND", f"No document with id {doc_id}.")
    return doc


def _get_candidate(db: Session, doc: Document, cand_id: int) -> EntityCandidate:
    cand = db.get(EntityCandidate, cand_id)
    if cand is None or cand.document_id != doc.id:
        not_found("ENTITY_NOT_FOUND", f"No candidate with id {cand_id} for this document.")
    return cand


def _get_rel_candidate(db: Session, doc: Document, rel_id: int) -> RelationshipCandidate:
    rel = db.get(RelationshipCandidate, rel_id)
    if rel is None or rel.document_id != doc.id:
        not_found("RELATIONSHIP_NOT_FOUND", f"No relationship candidate with id {rel_id}.")
    return rel


def _get_match(db: Session, doc: Document, match_id: int) -> EntityMatchSuggestion:
    m = db.get(EntityMatchSuggestion, match_id)
    if m is None or m.candidate.document_id != doc.id:
        not_found("MATCH_NOT_FOUND", f"No match suggestion with id {match_id}.")
    return m


def _settle_case_state_after_review(db: Session, case: Case) -> None:
    """Stage 7: after a review decision, if the case's review queue is now
    empty, move it REVIEW_REQUIRED -> READY_FOR_ANALYSIS (confirmed data
    exists) or -> DRAFT (nothing confirmed). Decisions in any other state
    are no-ops. Never raises: the decision itself is already committed."""
    from sqlalchemy import func
    from . import case_state_machine as sm

    try:
        if case.workflow_state != sm.REVIEW_REQUIRED:
            return
        def _c(model, *where):
            q = select(func.count()).select_from(model)
            for w in where:
                q = q.where(w)
            return db.execute(q).scalar_one()
        pending = _c(EntityCandidate, EntityCandidate.case_id == case.id,
                     EntityCandidate.status == "PENDING")
        pending += _c(EntityMatchSuggestion,
                      EntityMatchSuggestion.case_id == case.id,
                      EntityMatchSuggestion.status == "PENDING")
        pending += _c(RelationshipCandidate,
                      RelationshipCandidate.case_id == case.id,
                      RelationshipCandidate.status == "PENDING")
        if pending > 0:
            return
        confirmed = _c(Entity, Entity.case_id == case.id) + _c(
            Relationship, Relationship.case_id == case.id)
        sm.transition(db, case, sm.READY_FOR_ANALYSIS if confirmed else sm.DRAFT)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("Post-review state settle failed for case %s: %s",
                       case.id, exc)


def _decision(db, current, cand: EntityCandidate, status: str, note: str | None = None):
    if cand.status not in ("PENDING", "DEFERRED"):
        raise ApiError("CANDIDATE_ALREADY_REVIEWED",
                       f"Candidate {cand.id} is already {cand.status.lower()}.", 409)
    cand.status = status
    cand.decision_by = current.user.id
    cand.decided_at = datetime.now(timezone.utc)
    cand.decision_note = note


def _fold_aliases(entity: Entity, names) -> None:
    """Fold a candidate's surface forms (any supported script) into the
    confirmed entity's alias list.

    Original-language name forms (e.g. "राजेश कुमार", "راجش کمار") are
    provenance data and the anchors for multilingual name resolution —
    the canonical name stays the normalized display name, but the
    original scripts must remain resolvable on the confirmed entity.
    """
    have = {normalize(entity.canonical_name)}
    for a in (entity.meta or {}).get("aliases") or []:
        if isinstance(a, str):
            have.add(normalize(a))
    extra = [n for n in (names or [])
             if isinstance(n, str) and n.strip() and normalize(n) not in have]
    if extra:
        aliases = list((entity.meta or {}).get("aliases") or [])
        aliases.extend(extra)
        entity.meta = {**(entity.meta or {}), "aliases": aliases}


def backfill_entity_alias_surface_forms(db: Session, case: Case) -> int:
    """One-off backfill: restore original-script surface forms on
    confirmed entities from candidates accepted before the accept paths
    preserved them (see ``_fold_aliases``). Idempotent; returns the
    number of surface forms added."""
    cands = db.execute(
        select(EntityCandidate).where(
            EntityCandidate.case_id == case.id,
            EntityCandidate.accepted_entity_id.is_not(None))).scalars().all()
    by_entity: dict[int, list] = {}
    for c in cands:
        by_entity.setdefault(c.accepted_entity_id, []).extend(c.aliases or [])
    added = 0
    for e in _case_entity_rows(db, case):
        before = len((e.meta or {}).get("aliases") or [])
        _fold_aliases(e, by_entity.get(e.id, []))
        added += len((e.meta or {}).get("aliases") or []) - before
    return added


def _confirmed_entity(db: Session, case: Case, etype: str, name: str) -> Entity:
    """Find-or-create the confirmed entity for an accepted candidate
    (deterministic dedup: case + type + normalized name)."""
    target = normalize(name)
    for e in _case_entity_rows(db, case):
        if e.entity_type != etype:
            continue
        names = {normalize(e.canonical_name)}
        for a in (e.meta or {}).get("aliases") or []:
            if isinstance(a, str):
                names.add(normalize(a))
        if target in names:
            return e
    entity = Entity(case_id=case.id, entity_type=etype, canonical_name=name[:255],
                    meta={"extracted": True})
    db.add(entity)
    db.flush()
    return entity


def _add_evidence(db: Session, case: Case, doc: Document, evidence_type: str,
                  description: str, source_reference: str,
                  confidence: float | None) -> Evidence:
    ev = Evidence(case_id=case.id, document_id=doc.id, evidence_type=evidence_type,
                  description=description, source_reference=source_reference[:255],
                  confidence=confidence)
    db.add(ev)
    # flush so ev.id exists before dependent rows (e.g. evidence_claim)
    # reference it; the caller still owns the commit.
    db.flush()
    return ev


def _parse_event_stamp(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(value.strip(), fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# ------------------------------------------------------- claim materialization
def _case_location_by_norm_name(db: Session, case: Case, name: str):
    """(location_entity, location_row) for a confirmed location whose
    normalized name matches — the same documented (case, name) join rule
    the stage-4 geospatial engine uses. Read via _case_entity_rows so the
    lookup is correct even in long-lived sessions (see that helper)."""
    target = normalize_multilingual(name or "")
    if not target:
        return None, None
    entity = next((e for e in _case_entity_rows(db, case)
                   if e.entity_type == "location"
                   and normalize_multilingual(e.canonical_name) == target), None)
    if entity is None:
        return None, None
    row = next((l for l in db.scalars(
                    select(Location).where(Location.case_id == case.id)).all()
                if normalize_multilingual(l.name) == target), None)
    return entity, row


def _materialize_claims(db: Session, case: Case, entity: Entity,
                        candidate: EntityCandidate, evidence: Evidence) -> int:
    """Create confirmed evidence_claim rows for the accepted candidate.

    Only claims whose subject matches this candidate are materialized, and
    only now — while the candidate is still pending, its claims exist only
    as JSON on the extraction record. Idempotent: one claim per
    (candidate, extraction claim index), keyed by source_reference.
    """
    extraction = db.scalars(select(DocumentExtraction).where(
        DocumentExtraction.document_id == candidate.document_id)).first()
    raw_claims = (extraction.claims if extraction else None) or []
    if not raw_claims:
        return 0
    subject_norm = normalize_multilingual(candidate.candidate_name)
    created = 0
    for idx, claim in enumerate(raw_claims):
        if normalize_multilingual(claim.get("subject_name") or "") != subject_norm:
            continue
        ref = f"candidate:{candidate.id}#claim:{idx}"
        if db.scalars(select(EvidenceClaim).where(
                EvidenceClaim.source_reference == ref)).first() is not None:
            continue
        predicate = claim.get("predicate") or "was_at"
        event_time = _parse_event_stamp(claim.get("event_time"))
        norm_value = normalize_multilingual(
            claim.get("location_name") or claim.get("object_value") or "")
        # Content idempotency across candidates: the same extracted claim is
        # not materialized twice for one document even when the subject
        # appears on several lines (one accepted candidate per line).
        same_time = (EvidenceClaim.event_time.is_(None)
                     if event_time is None
                     else EvidenceClaim.event_time == event_time)
        if db.scalars(select(EvidenceClaim).join(
                Evidence, Evidence.id == EvidenceClaim.evidence_id).where(
            EvidenceClaim.case_id == case.id,
            EvidenceClaim.subject_entity_id == entity.id,
            EvidenceClaim.predicate == predicate,
            EvidenceClaim.normalized_value == norm_value,
            same_time,
            Evidence.document_id == candidate.document_id,
        )).first() is not None:
            continue
        loc_entity, loc_row = (None, None)
        if claim.get("location_name"):
            loc_entity, loc_row = _case_location_by_norm_name(
                db, case, claim["location_name"])
        db.add(EvidenceClaim(
            case_id=case.id, evidence_id=evidence.id,
            subject_entity_id=entity.id,
            predicate=predicate,
            object_entity_id=loc_entity.id if loc_entity else None,
            object_value=claim.get("location_name")
            or claim.get("object_value"),
            event_time=event_time,
            location_id=loc_row.id if loc_row else None,
            normalized_value=norm_value,
            confidence=claim.get("confidence"),
            source_reference=ref,
            original_text=((claim.get("source") or {}).get("snippet") or "")[:2000],
            language=claim.get("language")))
        created += 1
    return created


def _ensure_location_row(db: Session, case: Case, name: str) -> Location | None:
    """The case's Location row for a confirmed location entity (idempotent).

    Coordinates stay NULL: the platform geocodes only when a geocoder is
    configured and never fabricates coordinates. The row exists so the
    geospatial engine, the locations API and claim joins see real data.
    """
    target = normalize_multilingual(name or "")
    if not target:
        return None
    existing = next((l for l in db.scalars(
        select(Location).where(Location.case_id == case.id)).all()
        if normalize_multilingual(l.name) == target), None)
    if existing is not None:
        return existing
    row = Location(case_id=case.id, name=(name or "").strip(),
                   latitude=None, longitude=None)
    db.add(row)
    db.flush()
    return row


def _backfill_claim_locations(db: Session, case: Case, entity: Entity) -> int:
    """When a LOCATION entity is confirmed after some claims were already
    materialized, attach the location to the claims that refer to it by
    value. Keeps claim contradictions resolvable regardless of the review
    order."""
    target = normalize_multilingual(entity.canonical_name)
    if not target:
        return 0
    db.flush()
    loc_row = next((l for l in db.scalars(
                    select(Location).where(Location.case_id == case.id)).all()
                    if normalize_multilingual(l.name) == target), None)
    updated = 0
    for claim in db.scalars(select(EvidenceClaim).where(
            EvidenceClaim.case_id == case.id,
            EvidenceClaim.object_entity_id.is_(None))).all():
        if claim.object_value and \
                normalize_multilingual(claim.object_value) == target:
            claim.object_entity_id = entity.id
            claim.location_id = loc_row.id if loc_row else None
            updated += 1
    return updated


def accept_entity_candidate(db: Session, doc: Document, cand: EntityCandidate,
                            current: CurrentUser) -> EntityCandidate:
    pending_match = next((m for m in cand.matches if m.status == "PENDING"), None)
    if pending_match is not None:
        raise ApiError("MATCH_REVIEW_REQUIRED",
                       "A suggested match is pending for this candidate. Accept or "
                       "reject the match first.", 409,
                       {"match_id": pending_match.id})
    case = doc.case
    _decision(db, current, cand, "ACCEPTED")
    entity = _confirmed_entity(db, case, cand.entity_type, cand.candidate_name)
    # Preserve original-script surface forms (e.g. "राजेश कुमार") so the
    # confirmed entity resolves in every supported script.
    _fold_aliases(entity, cand.aliases or [])
    cand.accepted_entity_id = entity.id
    ev = _add_evidence(db, case, doc, "extracted_entity",
                       f"{cand.candidate_name} ({cand.entity_type}) — extracted from {doc.filename}",
                       f"candidate:{cand.id}", cand.confidence)
    if cand.entity_type == "event":
        ts = _parse_event_stamp((cand.source_location or {}).get("value"))
        db.add(TimelineEvent(
            case_id=case.id, entity_id=entity.id, event_type="extracted",
            timestamp=ts, description=(cand.source_snippet or cand.candidate_name)[:2000],
            evidence_id=ev.id))
    # stage 5: materialize this candidate's structured claims (confirmed-only)
    claims_created = _materialize_claims(db, case, entity, cand, ev)
    if cand.entity_type == "location":
        # stage 6: the confirmed location gets its (coordinate-less) row,
        # then claims referring to it are attached.
        _ensure_location_row(db, case, entity.canonical_name)
        _backfill_claim_locations(db, case, entity)
    db.commit()
    db.refresh(cand)
    record_audit(db, current, "ENTITY_ACCEPTED", "entity_candidate", str(cand.id),
                 {"case_id": case.id, "document_id": doc.id,
                  "name": cand.candidate_name, "type": cand.entity_type,
                  "entity_id": entity.id,
                  **({"claims_materialized": claims_created}
                     if claims_created else {})})
    _settle_case_state_after_review(db, case)
    return cand


def reject_entity_candidate(db: Session, doc: Document, cand: EntityCandidate,
                            current: CurrentUser, note: str | None = None) -> EntityCandidate:
    _decision(db, current, cand, "REJECTED", note)
    db.flush()
    # Relationships that depend on a rejected endpoint can never be confirmed.
    for rel in db.scalars(select(RelationshipCandidate).where(
            RelationshipCandidate.status == "PENDING")).all():
        if rel.document_id != doc.id:
            continue
        if rel.source_candidate_id == cand.id or rel.target_candidate_id == cand.id:
            rel.status = "REJECTED"
            rel.decision_by = current.user.id
            rel.decided_at = datetime.now(timezone.utc)
            rel.decision_note = "endpoint entity rejected"
    db.commit()
    db.refresh(cand)
    record_audit(db, current, "ENTITY_REJECTED", "entity_candidate", str(cand.id),
                 {"case_id": doc.case_id, "document_id": doc.id,
                  "name": cand.candidate_name})
    _settle_case_state_after_review(db, doc.case)
    return cand


def defer_entity_candidate(db: Session, doc: Document, cand: EntityCandidate,
                           current: CurrentUser) -> EntityCandidate:
    _decision(db, current, cand, "DEFERRED")
    db.commit()
    db.refresh(cand)
    record_audit(db, current, "ENTITY_DEFERRED", "entity_candidate", str(cand.id),
                 {"case_id": doc.case_id, "document_id": doc.id})
    return cand


def accept_relationship_candidate(db: Session, doc: Document, rel: RelationshipCandidate,
                                  current: CurrentUser) -> RelationshipCandidate:
    src, tgt = db.get(EntityCandidate, rel.source_candidate_id), db.get(EntityCandidate, rel.target_candidate_id)
    for c in (src, tgt):
        if c is None or c.status != "ACCEPTED" or c.accepted_entity_id is None:
            raise ApiError("CANDIDATE_NOT_CONFIRMED",
                           "Both endpoint entities must be accepted before the "
                           "relationship can be confirmed.", 409)
    if rel.status != "PENDING":
        raise ApiError("CANDIDATE_ALREADY_REVIEWED",
                       f"Relationship candidate {rel.id} is already {rel.status.lower()}.", 409)
    case = doc.case
    # Deterministic dedup: one confirmed relationship per
    # (case, source entity, target entity, type).
    existing = db.scalars(select(Relationship).where(
        Relationship.case_id == case.id,
        Relationship.source_entity_id == src.accepted_entity_id,
        Relationship.target_entity_id == tgt.accepted_entity_id,
        Relationship.relationship_type == rel.relationship_type)).first()
    if existing is None:
        existing = Relationship(
            case_id=case.id,
            source_entity_id=src.accepted_entity_id,
            target_entity_id=tgt.accepted_entity_id,
            relationship_type=rel.relationship_type,
            confidence=rel.confidence,
            meta={"source_document_id": doc.id,
                  "source_location": rel.source_location,
                  "source_snippet": rel.source_snippet,
                  "extraction_method": rel.extraction_method,
                  "candidate_id": rel.id})
        db.add(existing)
    db.flush()
    ev = _add_evidence(db, case, doc, "extracted_relationship",
                       f"{src.candidate_name} —{rel.relationship_type}— {tgt.candidate_name} "
                       f"(from {doc.filename})",
                       f"candidate:{rel.id}", rel.confidence)
    # stage 6: link the confirmed relationship row to its evidence row so
    # the graph edge can jump straight to the supporting evidence.
    meta = dict(existing.meta or {})
    meta["source_evidence_id"] = ev.id
    existing.meta = meta
    rel.status = "ACCEPTED"
    rel.decision_by = current.user.id
    rel.decided_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rel)
    record_audit(db, current, "RELATIONSHIP_ACCEPTED", "relationship_candidate", str(rel.id),
                 {"case_id": case.id, "document_id": doc.id,
                  "relationship_id": existing.id, "type": rel.relationship_type})
    _settle_case_state_after_review(db, case)
    return rel


def reject_relationship_candidate(db: Session, doc: Document, rel: RelationshipCandidate,
                                  current: CurrentUser, note: str | None = None) -> RelationshipCandidate:
    if rel.status != "PENDING":
        raise ApiError("CANDIDATE_ALREADY_REVIEWED",
                       f"Relationship candidate {rel.id} is already {rel.status.lower()}.", 409)
    rel.status = "REJECTED"
    rel.decision_by = current.user.id
    rel.decided_at = datetime.now(timezone.utc)
    rel.decision_note = note
    db.commit()
    db.refresh(rel)
    record_audit(db, current, "RELATIONSHIP_REJECTED", "relationship_candidate", str(rel.id),
                 {"case_id": doc.case_id, "document_id": doc.id})
    _settle_case_state_after_review(db, doc.case)
    return rel


def accept_match(db: Session, doc: Document, match: EntityMatchSuggestion,
                 current: CurrentUser) -> EntityMatchSuggestion:
    if match.status != "PENDING":
        raise ApiError("MATCH_ALREADY_REVIEWED",
                       f"Match suggestion {match.id} is already {match.status.lower()}.", 409)
    cand = match.candidate
    if cand.status not in ("PENDING", "DEFERRED"):
        raise ApiError("MATCH_NOT_ALLOWED",
                       "The candidate has already been reviewed.", 409)
    case = doc.case
    entity = db.get(Entity, match.existing_entity_id)
    if entity is None or entity.case_id != case.id:
        not_found("ENTITY_NOT_FOUND", "The suggested entity no longer exists.")
    # Fold the candidate into the existing entity (alias), confirm it.
    # Preserve the original-script surface forms, not just the canonical.
    _fold_aliases(entity, [cand.candidate_name] + (cand.aliases or []))
    _decision(db, current, cand, "ACCEPTED", note=f"matched to entity {entity.id}")
    cand.accepted_entity_id = entity.id
    match_ev = _add_evidence(db, case, doc, "extracted_entity",
                  f"{cand.candidate_name} matched to existing entity "
                  f"\"{entity.canonical_name}\" ({entity.entity_type})",
                  f"candidate:{cand.id}", cand.confidence)
    # stage 5: the matched candidate's structured claims attach to the
    # confirmed (existing) entity.
    _materialize_claims(db, case, entity, cand, match_ev)
    if entity.entity_type == "location":
        _ensure_location_row(db, case, entity.canonical_name)
        _backfill_claim_locations(db, case, entity)
    match.status = "ACCEPTED"
    match.decision_by = current.user.id
    match.decided_at = datetime.now(timezone.utc)
    # Phase 2: a candidate may carry several RANKED suggestions. Accepting
    # one resolves the candidate, so its remaining PENDING alternatives
    # are superseded by this decision — they can no longer be offered as
    # live choices (dead suggestions would be noise in the review queue).
    superseded: list[int] = []
    for s in db.scalars(select(EntityMatchSuggestion).where(
            EntityMatchSuggestion.candidate_id == cand.id,
            EntityMatchSuggestion.status == "PENDING",
            EntityMatchSuggestion.id != match.id)).all():
        s.status = "SUPERSEDED"
        s.decision_by = current.user.id
        s.decided_at = match.decided_at
        superseded.append(s.id)
    db.commit()
    db.refresh(match)
    record_audit(db, current, "ENTITY_MATCH_ACCEPTED", "entity_match_suggestion", str(match.id),
                 {"case_id": case.id, "document_id": doc.id,
                  "candidate_id": cand.id, "entity_id": entity.id,
                  "similarity": match.similarity,
                  "superseded_suggestions": superseded})
    _settle_case_state_after_review(db, case)
    return match


def reject_match(db: Session, doc: Document, match: EntityMatchSuggestion,
                 current: CurrentUser) -> EntityMatchSuggestion:
    if match.status != "PENDING":
        raise ApiError("MATCH_ALREADY_REVIEWED",
                       f"Match suggestion {match.id} is already {match.status.lower()}.", 409)
    match.status = "REJECTED"
    match.decision_by = current.user.id
    match.decided_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(match)
    record_audit(db, current, "ENTITY_MATCH_REJECTED", "entity_match_suggestion", str(match.id),
                 {"case_id": doc.case_id, "document_id": doc.id,
                  "candidate_id": match.candidate_id})
    _settle_case_state_after_review(db, doc.case)
    return match
