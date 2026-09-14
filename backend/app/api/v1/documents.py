"""Document intake, processing and review API (stage 2).

Routes (all JWT-authenticated; role floors via the existing ladder):

    POST   /cases/{case_id}/documents                 upload (multipart)
    GET    /documents/{document_id}                   detail + summary
    GET    /documents/{document_id}/status             poll status
    POST   /documents/{document_id}/process            start / retry processing
    GET    /documents/{document_id}/extraction         candidates + matches
    POST   /documents/{document_id}/extraction/candidates/{id}/accept | reject | defer
    POST   /documents/{document_id}/extraction/relationships/{id}/accept | reject
    POST   /documents/{document_id}/extraction/matches/{id}/accept | reject

Processing runs on the background job queue (phase 1): an upload creates a
queued ``document_processing_job`` row and returns immediately; a worker
(in-process in development, or a separate ``app.workers.document_worker``
process in production) claims it and runs the existing pipeline with its
own session. The front end polls the real status — the job row is exposed
on the document so the queue state is visible, never faked.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from sqlalchemy.orm import Session

from ...core.errors import not_found
from ...repositories import case_repository as case_repo
from ...repositories import document_repository as repo
from ...schemas.v1 import (DocumentDetailOut, DocumentOut, DocumentStatusOut,
                           EntityCandidateOut, ExtractionOut,
                           MatchSuggestionOut, RelationshipCandidateOut,
                           ReviewDecision)
from ...security.rbac import CurrentUser, get_current_user, require_roles
from ...services import document_service
from ...services import case_access
from ...services.auth_service import record_audit
from .deps import get_db_checked

logger = logging.getLogger("nexus.api.documents")
router = APIRouter(tags=["documents"])


def _require_case(db: Session, case_id: int, current: CurrentUser):
    return case_access.require_case_access(db, case_id, current)


def _require_document(db: Session, doc_id: int):
    doc = repo.get_document(db, doc_id)
    if doc is None:
        not_found("DOCUMENT_NOT_FOUND", f"No document with id {doc_id}.")
    return doc


# ------------------------------------------------------------------- upload

@router.post("/cases/{case_id}/documents", response_model=DocumentOut,
             status_code=201, summary="Upload a document (all roles)")
def upload_document(case_id: int,
                    background: BackgroundTasks,
                    file: UploadFile = File(...),
                    db: Session = Depends(get_db_checked),
                    current: CurrentUser = Depends(require_roles("ANALYST"))):
    case = _require_case(db, case_id, current)
    doc = document_service.upload_document(db, case, current, file)
    # Phase 1: enqueue the document for the background worker instead of
    # attaching processing to the request lifecycle. The worker picks the
    # job up; the upload itself is done. If no worker is running (a
    # WORKER_ENABLED=false deployment without a standalone worker), a
    # background task runs the same job so the workflow still completes —
    # the job row is finalized from the real document state either way.
    from ...services import processing_worker
    job, action = processing_worker.enqueue_document_job(db, doc.id, doc.case_id)
    record_audit(db, current, "PROCESSING_JOB_QUEUED", "document", str(doc.id),
                 {"job_id": job.id, "action": action, "case_id": case.id})
    db.commit()
    db.refresh(doc)
    if not processing_worker.worker_active():
        background.add_task(processing_worker.run_job, job.id)
    return DocumentOut(**repo.document_out_fields(db, case, doc))


# ------------------------------------------------------------------- detail

def _detail_fields(db: Session, doc) -> dict:
    case = doc.case
    return repo.document_out_fields(db, case, doc)


@router.get("/documents/{document_id}", response_model=DocumentDetailOut,
            summary="Document detail + extraction summary")
def document_detail(document_id: int, db: Session = Depends(get_db_checked),
                    current: CurrentUser = Depends(get_current_user)):
    doc = _require_document(db, document_id)
    return DocumentDetailOut(
        document=DocumentOut(**_detail_fields(db, doc)),
        summary=repo.summary_for(db, doc.case, doc),
    )


@router.delete("/cases/{case_id}/documents/{document_id}", status_code=204,
               summary="Delete a document from the case")
def delete_document(case_id: int, document_id: int,
                    db: Session = Depends(get_db_checked),
                    current: CurrentUser = Depends(
                        require_roles("INVESTIGATOR", "SUPERVISOR"))):
    """Delete the document row, its file, and its still-unconfirmed
    candidates (they cascade). Confirmed entities/relationships/claims
    belong to the case, not the file: they stay (their provenance
    metadata keeps the document id), so deleting a file can never
    silently erase intelligence. Evidence rows keep existing with
    document_id SET NULL."""
    doc = _require_document(db, document_id)
    if doc.case_id != case_id:
        not_found("DOCUMENT_NOT_FOUND",
                  f"No document {document_id} in case {case_id}.")
    if doc.processing_status == "PROCESSING":
        from ...core.errors import ApiError
        raise ApiError("DOCUMENT_PROCESSING",
                       "This document is still processing — wait for it "
                       "to finish (or fail) before deleting it.", 409)
    from ...services import document_service
    document_service.delete_document(db, doc, current)
    return None


@router.get("/documents/{document_id}/status", response_model=DocumentStatusOut,
            summary="Poll processing status")
def document_status(document_id: int, db: Session = Depends(get_db_checked),
                    current: CurrentUser = Depends(get_current_user)):
    doc = _require_document(db, document_id)
    summary = repo.summary_for(db, doc.case, doc)
    return DocumentStatusOut(
        id=doc.id, case_id=doc.case_id, filename=doc.filename,
        processing_status=doc.processing_status,
        processed_at=doc.processed_at, processing_error=doc.processing_error,
        processing_job=repo.job_for(db, doc.id),
        summary=summary,
    )


@router.post("/documents/{document_id}/process", response_model=DocumentStatusOut,
             status_code=202, summary="Start (or retry) processing")
def process_document(document_id: int,
                     db: Session = Depends(get_db_checked),
                     current: CurrentUser = Depends(require_roles("ANALYST"))):
    doc = _require_document(db, document_id)
    if doc.processing_status == "PROCESSED":
        from ...core.errors import ApiError

        raise ApiError("DOCUMENT_ALREADY_PROCESSED",
                       "This document has already been processed successfully.", 409)
    if doc.processing_status == "PROCESSING":
        from ...core.errors import ApiError

        raise ApiError("DOCUMENT_PROCESSING",
                       "Processing is already in progress for this document.", 409)
    # Phase 1: the retry reuses the document's job row (attempts + 1) and
    # puts it back in the queue for the worker — no duplicate processing.
    from ...services import processing_worker
    job, action = processing_worker.enqueue_document_job(db, doc.id, doc.case_id)
    record_audit(db, current, "PROCESS_REQUESTED", "document", str(doc.id),
                 {"case_id": doc.case_id, "job_id": job.id, "action": action})
    db.commit()
    doc = repo.get_document(db, document_id)
    return DocumentStatusOut(
        id=doc.id, case_id=doc.case_id, filename=doc.filename,
        processing_status=doc.processing_status,
        processed_at=doc.processed_at, processing_error=doc.processing_error,
        processing_job=repo.job_for(db, doc.id),
    )


# ----------------------------------------------------------------- extraction

def _extraction_out(db: Session, doc) -> ExtractionOut:
    case = doc.case
    cands = repo.candidates_for_document(db, doc)
    matches = repo.matches_for(db, [c.id for c in cands])  # candidate -> ranked list
    entity_names = repo.entity_names(
        db, [m.existing_entity_id for ms in matches.values() for m in ms])

    cand_outs: list[EntityCandidateOut] = []
    for c in cands:
        cand_out = EntityCandidateOut.model_validate(c)
        # the candidate's `match` field stays the single top-ranked
        # suggestion (back-compat); the full ranked list is in `matches`
        ms = matches.get(c.id) or []
        if ms:
            m = ms[0]
            cand_out.match = MatchSuggestionOut(
                **{k: getattr(m, k) for k in ("id", "candidate_id",
                                              "existing_entity_id", "similarity",
                                              "reasons", "status", "rank")},
                candidate_name=c.candidate_name,
                existing_entity_name=entity_names.get(m.existing_entity_id),
            )
        cand_outs.append(cand_out)

    cand_by_id = {c.id: c for c in cands}
    rel_outs: list[RelationshipCandidateOut] = []
    for r in repo.relationships_for_document(db, doc):
        src = cand_by_id.get(r.source_candidate_id)
        tgt = cand_by_id.get(r.target_candidate_id)
        out = RelationshipCandidateOut.model_validate(r)
        out.source_name = src.candidate_name if src else None
        out.target_name = tgt.candidate_name if tgt else None
        out.endpoints_confirmed = bool(
            src and tgt and src.status == "ACCEPTED" and tgt.status == "ACCEPTED")
        rel_outs.append(out)

    # Phase 2: the full RANKED list (every suggestion row, best first)
    match_outs = [
        MatchSuggestionOut(
            **{k: getattr(m, k) for k in ("id", "candidate_id",
                                          "existing_entity_id", "similarity",
                                          "reasons", "status", "rank")},
            candidate_name=cand_by_id[m.candidate_id].candidate_name
            if m.candidate_id in cand_by_id else None,
            existing_entity_name=entity_names.get(m.existing_entity_id),
        )
        for ms in matches.values()
        for m in ms
    ]
    match_outs.sort(key=lambda x: (x.candidate_id, x.rank))
    return ExtractionOut(summary=repo.summary_for(db, case, doc),
                         entities=cand_outs, relationships=rel_outs,
                         matches=match_outs)


@router.get("/documents/{document_id}/extraction", response_model=ExtractionOut,
            summary="Extraction results: candidates, relationships, matches")
def extraction(document_id: int, db: Session = Depends(get_db_checked),
               current: CurrentUser = Depends(get_current_user)):
    doc = _require_document(db, document_id)
    return _extraction_out(db, doc)


# ------------------------------------------------------------------- review

@router.post("/documents/{document_id}/extraction/candidates/{candidate_id}/accept",
             response_model=EntityCandidateOut, summary="Accept an entity candidate")
def accept_candidate(document_id: int, candidate_id: int,
                     body: ReviewDecision | None = None,
                     db: Session = Depends(get_db_checked),
                     current: CurrentUser = Depends(require_roles("ANALYST"))):
    doc = _require_document(db, document_id)
    cand = document_service._get_candidate(db, doc, candidate_id)
    return document_service.accept_entity_candidate(db, doc, cand, current)


@router.post("/documents/{document_id}/extraction/candidates/{candidate_id}/reject",
             response_model=EntityCandidateOut, summary="Reject an entity candidate")
def reject_candidate(document_id: int, candidate_id: int,
                     body: ReviewDecision | None = None,
                     db: Session = Depends(get_db_checked),
                     current: CurrentUser = Depends(require_roles("ANALYST"))):
    doc = _require_document(db, document_id)
    cand = document_service._get_candidate(db, doc, candidate_id)
    return document_service.reject_entity_candidate(
        db, doc, cand, current, note=body.note if body else None)


@router.post("/documents/{document_id}/extraction/candidates/{candidate_id}/defer",
             response_model=EntityCandidateOut, summary="Mark a candidate for later review")
def defer_candidate(document_id: int, candidate_id: int,
                    db: Session = Depends(get_db_checked),
                    current: CurrentUser = Depends(require_roles("ANALYST"))):
    doc = _require_document(db, document_id)
    cand = document_service._get_candidate(db, doc, candidate_id)
    return document_service.defer_entity_candidate(db, doc, cand, current)


@router.post("/documents/{document_id}/extraction/relationships/{rel_id}/accept",
             response_model=RelationshipCandidateOut,
             summary="Accept a relationship candidate (endpoints must be accepted)")
def accept_relationship(document_id: int, rel_id: int,
                        body: ReviewDecision | None = None,
                        db: Session = Depends(get_db_checked),
                        current: CurrentUser = Depends(require_roles("ANALYST"))):
    doc = _require_document(db, document_id)
    rel = document_service._get_rel_candidate(db, doc, rel_id)
    return document_service.accept_relationship_candidate(db, doc, rel, current)


@router.post("/documents/{document_id}/extraction/relationships/{rel_id}/reject",
             response_model=RelationshipCandidateOut,
             summary="Reject a relationship candidate")
def reject_relationship(document_id: int, rel_id: int,
                        body: ReviewDecision | None = None,
                        db: Session = Depends(get_db_checked),
                        current: CurrentUser = Depends(require_roles("ANALYST"))):
    doc = _require_document(db, document_id)
    rel = document_service._get_rel_candidate(db, doc, rel_id)
    return document_service.reject_relationship_candidate(
        db, doc, rel, current, note=body.note if body else None)


@router.post("/documents/{document_id}/extraction/matches/{match_id}/accept",
             response_model=MatchSuggestionOut,
             summary="Accept a suggested match (candidate folds into the entity)")
def accept_match(document_id: int, match_id: int,
                 db: Session = Depends(get_db_checked),
                 current: CurrentUser = Depends(require_roles("ANALYST"))):
    doc = _require_document(db, document_id)
    m = document_service._get_match(db, doc, match_id)
    return document_service.accept_match(db, doc, m, current)


@router.post("/documents/{document_id}/extraction/matches/{match_id}/reject",
             response_model=MatchSuggestionOut,
             summary="Reject a suggested match (candidate stays independent)")
def reject_match(document_id: int, match_id: int,
                 db: Session = Depends(get_db_checked),
                 current: CurrentUser = Depends(require_roles("ANALYST"))):
    doc = _require_document(db, document_id)
    m = document_service._get_match(db, doc, match_id)
    return document_service.reject_match(db, doc, m, current)
