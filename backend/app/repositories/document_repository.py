"""Document data access: lists with extraction counts, and the candidate
collections a review session needs (loaded in a few queries, not per row)."""

from __future__ import annotations

from sqlalchemy import case as sa_case
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (Document, DocumentExtraction, Entity, EntityCandidate,
                      EntityMatchSuggestion, Evidence, RelationshipCandidate)


def documents(db: Session, case) -> list[Document]:
    return sorted(case.documents, key=lambda d: (d.uploaded_at, d.id))


def _candidate_counts(db: Session, case_id: int) -> dict[int, dict[str, int]]:
    rows = db.execute(
        select(EntityCandidate.document_id,
               func.count(EntityCandidate.id),
               func.sum(sa_case(
                   (EntityCandidate.status == "PENDING", 1),
                   (EntityCandidate.status == "DEFERRED", 1),
                   else_=0)),
               func.sum(sa_case((EntityCandidate.status == "ACCEPTED", 1),
                                else_=0)))
        .where(EntityCandidate.case_id == case_id)
        .group_by(EntityCandidate.document_id)
    ).all()
    rels = dict(db.execute(
        select(RelationshipCandidate.document_id, func.count(RelationshipCandidate.id))
        .where(RelationshipCandidate.case_id == case_id)
        .group_by(RelationshipCandidate.document_id)
    ).all())
    out: dict[int, dict[str, int]] = {}
    for doc_id, total, pending, accepted in rows:
        out[doc_id] = {"entities": total or 0,
                       "pending": pending or 0,
                       "accepted": accepted or 0,
                       "relationships": rels.get(doc_id, 0)}
    return out


def document_out_fields(db: Session, case, doc: Document,
                        counts: dict[int, dict[str, int]] | None = None) -> dict:
    """Document row + the display fields the API adds (never the path)."""
    if counts is None:
        counts = _candidate_counts(db, case.id)
    c = counts.get(doc.id, {"entities": 0, "pending": 0, "accepted": 0,
                            "relationships": 0})
    uploader_name = doc.uploader.name if doc.uploader is not None else None
    # phase 1: the background job for this document (queue state visible)
    processing_job = job_for(db, doc.id)
    return {
        "id": doc.id, "case_id": doc.case_id, "filename": doc.filename,
        "file_type": doc.file_type, "language": doc.language,
        "file_size": doc.file_size, "uploaded_at": doc.uploaded_at,
        "processing_status": doc.processing_status,
        "mime_type": doc.mime_type, "sha256": doc.sha256,
        "uploaded_by_name": uploader_name, "processed_at": doc.processed_at,
        "processing_error": doc.processing_error,
        "extracted_entities": c["entities"],
        "extracted_relationships": c["relationships"],
        "pending_review": c["pending"],
        # stage 5 multilingual provenance
        "language_confidence": doc.language_confidence,
        "translation_status": doc.translation_status,
        "processing_method": doc.processing_method,
        # stage 7 real processing provenance
        "processing_started_at": doc.processing_started_at,
        "processing_seconds": doc.processing_seconds,
        "page_count": doc.page_count,
        # phase 1: background processing job (never an internal path)
        "processing_job": processing_job,
    }


def job_for(db: Session, doc_id: int) -> dict | None:
    """Phase 1: the background processing job row for a document (API
    shape), or None when the document has no job yet."""
    from ..models import DocumentProcessingJob

    job = db.scalar(select(DocumentProcessingJob)
                    .where(DocumentProcessingJob.document_id == doc_id))
    if job is None:
        return None
    return {
        "id": job.id, "status": job.status, "attempts": job.attempts,
        "error": job.error, "created_at": job.created_at,
        "started_at": job.started_at, "finished_at": job.finished_at,
    }


def get_document(db: Session, doc_id: int) -> Document | None:
    return db.get(Document, doc_id)


def extraction_for(db: Session, doc: Document) -> DocumentExtraction | None:
    return db.scalars(select(DocumentExtraction)
                      .where(DocumentExtraction.document_id == doc.id)).first()


def candidates_for_document(db: Session, doc: Document) -> list[EntityCandidate]:
    cands = db.scalars(select(EntityCandidate)
                       .where(EntityCandidate.document_id == doc.id)
                       .order_by(EntityCandidate.entity_type,
                                 EntityCandidate.candidate_name,
                                 EntityCandidate.id)).all()
    return list(cands)


def matches_for(db: Session, candidate_ids: list[int]) -> dict[int, list[EntityMatchSuggestion]]:
    """candidate_id -> its RANKED suggestions (phase 2), best first.

    A candidate may now have several PENDING suggestions (name similarity
    + contextual signals). Order is (rank, id) so rank 1 is always first.
    """
    if not candidate_ids:
        return {}
    rows = db.scalars(select(EntityMatchSuggestion)
                      .where(EntityMatchSuggestion.candidate_id.in_(candidate_ids))
                      .order_by(EntityMatchSuggestion.rank,
                                EntityMatchSuggestion.id)).all()
    out: dict[int, list[EntityMatchSuggestion]] = {}
    for m in rows:
        out.setdefault(m.candidate_id, []).append(m)
    return out


def primary_match(matches: dict[int, list[EntityMatchSuggestion]]) -> dict[int, EntityMatchSuggestion]:
    """Back-compat view: the top-ranked (rank 1) suggestion per candidate."""
    return {cid: ms[0] for cid, ms in matches.items() if ms}


def entity_names(db: Session, ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {e.id: e.canonical_name for e in db.scalars(
        select(Entity).where(Entity.id.in_(ids))).all()}


def relationships_for_document(db: Session, doc: Document) -> list[RelationshipCandidate]:
    return list(db.scalars(select(RelationshipCandidate)
                           .where(RelationshipCandidate.document_id == doc.id)
                           .order_by(RelationshipCandidate.id)).all())


def evidence_generated_for(db: Session, doc: Document) -> int:
    return db.scalar(select(func.count(Evidence.id)).where(
        Evidence.document_id == doc.id,
        Evidence.evidence_type.in_(["extracted_entity", "extracted_relationship"]))) or 0


def summary_for(db: Session, case, doc: Document) -> dict:
    cands = candidates_for_document(db, doc)
    rels = relationships_for_document(db, doc)
    ext = extraction_for(db, doc)
    pending = sum(1 for c in cands if c.status in ("PENDING", "DEFERRED"))
    accepted = sum(1 for c in cands if c.status == "ACCEPTED")
    rejected = sum(1 for c in cands if c.status == "REJECTED")
    matches = matches_for(db, [c.id for c in cands])
    # phase 2: several ranked suggestions per candidate are possible
    n_matches = sum(1 for ms in matches.values()
                    for m in ms if m.status == "PENDING")
    # stage 5: preserved source text, display-capped so a large document
    # cannot bloat the response. The full text remains in storage/DB.
    _cap = 20_000
    original = ext.original_text if ext else None
    normalized = ext.normalized_text if ext else None
    return {
        "source_type": ext.source_type if ext else None,
        "stats": ext.stats if ext else None,
        "entities": len(cands),
        "relationships": len(rels),
        "matches": n_matches,
        "pending": pending,
        "accepted": accepted,
        "rejected": rejected,
        "evidence_generated": evidence_generated_for(db, doc),
        "language": ext.language if ext else None,
        "language_confidence": ext.language_confidence if ext else None,
        "original_text": (original[:_cap] if original else None),
        "normalized_text": (normalized[:_cap] if normalized else None),
    }
