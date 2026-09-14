"""Stage 7 — case-level processing orchestration (real job, real stages).

``POST /cases/{id}/process`` creates a ``CaseProcessingJob`` row and
returns ``{job_id, case_id, status: "queued"}`` immediately. The worker
(``run_processing_job``, background-safe: own session) then walks the
case's documents through the EXISTING per-document pipeline —

    ingest -> text extraction -> OCR -> language detection ->
    normalization -> entity extraction -> relationship extraction ->
    review candidates

— via ``document_service.process_document`` (no duplicated algorithms),
updating the job row's real stage and aggregate counts as it goes.

Rules honoured:

* **No fake progress.** ``current_stage`` names the document actually in
  flight; the stage *checklist* in ``processing/status`` is derived from
  persisted artifacts (extraction row, language column, candidate
  counts) — every tick is a real database fact.
* **Failure isolation.** One document failing never stops the job or the
  case: the remaining documents still process, the job finishes
  COMPLETED with ``failed_documents`` > 0 and the error listing each
  failed file, and ``RETRY FAILED`` re-runs exactly those documents.
* **State machine.** The job drives the case lifecycle:
  (UPLOADING|STALE|READY_FOR_ANALYSIS|REVIEW_REQUIRED) -> PROCESSING on
  start, and -> REVIEW_REQUIRED | READY_FOR_ANALYSIS | DRAFT on finish,
  derived from the real queue/confirmed counts.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from ..models import (Case, CaseProcessingJob, Document, DocumentExtraction,
                      Entity, EntityCandidate, EntityMatchSuggestion,
                      Relationship, RelationshipCandidate)
from ..security.rbac import CurrentUser
from . import case_state_machine as sm
from .auth_service import record_audit
from .document_service import process_document

logger = logging.getLogger("nexus.case_processing")

# The documented pipeline, shown as a checklist in processing/status.
# Each stage is *derived* from a persisted artifact — never guessed.
PIPELINE_STAGES = (
    "ingestion",            # document stored (storage_path set)
    "text_extraction",      # DocumentExtraction row with text
    "language_detection",   # document.language set by the detector
    "normalization",        # translation_status NORMALIZED | NOT_REQUIRED
    "entity_extraction",    # document reached PROCESSED (extractor ran)
    "relationship_extraction",  # same run produced relationship candidates
    "review_candidates",    # every candidate of the document decided
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _job_out(job: CaseProcessingJob) -> dict:
    return {
        "job_id": job.job_id,
        "case_id": job.case_id,
        "status": job.status,
        "current_stage": job.current_stage,
        "total_documents": job.total_documents,
        "processed_documents": job.processed_documents,
        "failed_documents": job.failed_documents,
        "extracted_counts": job.extracted_counts,
        "error": job.error,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


# ------------------------------------------------------------------ start

def start_processing_job(db: Session, case: Case, current: CurrentUser,
                         only_failed: bool = False) -> dict:
    """Create a QUEUED case processing job (the POST /process response).

    The job's work: process every document that has not started yet, wait
    for documents already in flight (uploads start their own background
    processing — stage 2), and, with ``only_failed``, re-run the FAILED
    ones (the RETRY FAILED action). The final aggregates always describe
    the whole case from the database."""
    from ..core.errors import ApiError

    if case.workflow_state == sm.CLOSED:
        raise ApiError("CASE_CLOSED",
                       "This case is closed — open it again to process "
                       "documents.", 409)
    docs = db.scalars(
        select(Document).where(Document.case_id == case.id)
        .order_by(Document.id)).all()
    if not docs:
        raise ApiError("NO_DOCUMENTS",
                       "This case has no documents to process.", 409)
    if only_failed:
        targets = [d for d in docs if d.processing_status == "FAILED"]
        if not targets:
            raise ApiError("NOTHING_TO_RETRY",
                           "No failed documents to retry.", 409)
    else:
        # A job is valid even when every document already reached a
        # terminal state: it still settles the case (state machine) and
        # publishes the real aggregates.
        targets = [d for d in docs if d.processing_status in
                   ("UPLOADED", "PROCESSING", "FAILED")]
    job = CaseProcessingJob(
        job_id=str(uuid.uuid4()), case_id=case.id, status="QUEUED",
        total_documents=len(docs) if not only_failed else len(targets),
        created_by=current.user.id)
    db.add(job)
    db.commit()
    db.refresh(job)
    record_audit(db, current, "PROCESSING_JOB_STARTED", "case", str(case.id),
                 {"job_id": job.job_id,
                  "documents": len(targets),
                  "retry_failed": only_failed})
    return _job_out(job)


def _doc_states(db: Session, case_id: int) -> dict[int, str]:
    """Fresh document statuses, read as raw columns.

    The worker holds one long-lived session (``expire_on_commit=False``),
    so entity selects would keep returning identity-mapped instances with
    stale attributes. Column selects always hit the database.
    """
    rows = db.execute(select(Document.id, Document.processing_status)
                      .where(Document.case_id == case_id)).all()
    return {doc_id: status for doc_id, status in rows}


def _doc_names(db: Session, case_id: int) -> dict[int, str]:
    rows = db.execute(select(Document.id, Document.filename)
                      .where(Document.case_id == case_id)).all()
    return {doc_id: name for doc_id, name in rows}


def _docs_in_flight(db: Session, case_id: int) -> int:
    """Documents still in a non-terminal state (UPLOADED/PROCESSING)."""
    from sqlalchemy import func
    return db.execute(
        select(func.count()).select_from(Document).where(
            Document.case_id == case_id,
            Document.processing_status.in_(("UPLOADED", "PROCESSING")))).scalar_one()


def run_processing_job(job_id: str, retry_failed: bool = False) -> None:
    """Background-safe worker: drive the case's documents to a terminal
    state, then settle the case.

    Uploads already start their own background processing (stage 2), so
    this worker mostly *waits* for those to finish; it starts any document
    still sitting at UPLOADED, and — when ``retry_failed`` — re-runs the
    FAILED ones (the RETRY FAILED action). It loops until every document
    is PROCESSED or FAILED (bounded by a timeout), updating the job's real
    stage and database-derived aggregates as it goes. No fake progress.
    """
    import time as _time

    db = SessionLocal()
    deadline = _time.monotonic() + 120.0  # hard bound for the wait loop
    try:
        job = db.scalar(select(CaseProcessingJob).where(
            CaseProcessingJob.job_id == job_id))
        if job is None:
            return
        case = db.get(Case, job.case_id)
        if case is None:
            job.status = "FAILED"
            job.error = "case disappeared"
            db.commit()
            return

        sm.transition(db, case, sm.PROCESSING)
        job.status = "RUNNING"
        job.started_at = _now()
        job.current_stage = "queued"
        db.commit()

        # Documents we are allowed to (re)start ourselves.
        if retry_failed:
            kickable = ("FAILED", "UPLOADED")
        else:
            kickable = ("UPLOADED",)

        retried: set[int] = set()
        while _time.monotonic() < deadline:
            states = _doc_states(db, case.id)

            # Kick off any document still at a startable state (once each).
            started_any = False
            for did, stt in states.items():
                if stt in kickable and did not in retried:
                    names = _doc_names(db, case.id)
                    retried.add(did)
                    job.current_stage = (f"retrying: {names.get(did, str(did))}"
                                         if stt == "FAILED"
                                         else f"processing: {names.get(did, str(did))}")
                    db.commit()
                    # Phase 1: hand the document to the background worker
                    # queue when a worker is running (the loop below keeps
                    # polling real document state until it settles). With
                    # no worker (e.g. WORKER_ENABLED=false) the case job
                    # still processes it directly, so the workflow works
                    # either way — no silent no-op.
                    from . import processing_worker
                    if processing_worker.worker_active():
                        processing_worker.enqueue_document_job(
                            db, did, case.id)
                        db.commit()
                    else:
                        process_document(did)  # own session, atomic
                    started_any = True
                    break  # re-read fresh states after each kick

            states = _doc_states(db, case.id)
            names = _doc_names(db, case.id)
            in_flight = [names.get(d, str(d)) for d, s in states.items()
                         if s == "PROCESSING"]
            pending = [names.get(d, str(d)) for d, s in states.items()
                       if s in kickable and d not in retried]
            # Exit only when every document is truly terminal. A doc the
            # case job just enqueued for the background worker is briefly
            # UPLOADED (kicked, so not in `pending`, but not PROCESSING
            # yet either) — it must keep the loop alive, otherwise the
            # case job would finish while the doc is still queued.
            non_terminal = [d for d, s in states.items()
                            if s in ("UPLOADED", "PROCESSING")]
            # Reflect the real in-flight document in the stage.
            if in_flight:
                job.current_stage = f"processing: {in_flight[0]}"
            elif pending:
                job.current_stage = f"queued: {pending[0]}"
            # Publish database-derived aggregates while we wait.
            n_proc = sum(1 for s in states.values() if s == "PROCESSED")
            n_fail = sum(1 for s in states.values() if s == "FAILED")
            job.processed_documents = n_proc
            job.failed_documents = n_fail
            job.extracted_counts = _extracted_counts(db, case.id)
            db.commit()

            if not non_terminal:
                break  # every document is terminal
            if started_any:
                continue  # a kick may have just flipped a state
            _time.sleep(0.3)

        # Final aggregates from the database (the source of truth).
        states = _doc_states(db, case.id)
        names = _doc_names(db, case.id)
        n_proc = sum(1 for s in states.values() if s == "PROCESSED")
        n_fail = sum(1 for s in states.values() if s == "FAILED")
        n_total = len(states)
        failed_names = [names.get(i, str(i)) for i, s in states.items()
                        if s == "FAILED"]
        job.total_documents = n_total
        job.processed_documents = n_proc
        job.failed_documents = n_fail
        job.extracted_counts = _extracted_counts(db, case.id)
        job.current_stage = ("ready for review" if n_proc
                             else "completed with failures")
        job.status = "COMPLETED"
        job.finished_at = _now()
        job.error = ("; ".join(failed_names) if failed_names else None)
        db.commit()

        _settle_case_state(db, case)
        record_audit(db, None, "PROCESSING_JOB_COMPLETED", "case", str(case.id),
                     {"job_id": job.job_id, "processed": n_proc,
                      "failed": n_fail, "retry_failed": retry_failed})
        logger.info("Processing job %s done: %d processed, %d failed (case %s)",
                    job_id, n_proc, n_fail, case.id)
    except Exception as exc:  # noqa: BLE001 — the job must not die silently
        db.rollback()
        logger.exception("Processing job %s crashed", job_id)
        try:
            job2 = db.scalar(select(CaseProcessingJob).where(
                CaseProcessingJob.job_id == job_id))
            if job2 is not None:
                job2.status = "FAILED"
                job2.error = f"worker error: {exc.__class__.__name__}"
                job2.finished_at = _now()
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
    finally:
        db.close()


def _extracted_counts(db: Session, case_id: int) -> dict:
    """Row counts from the database (never estimated)."""
    from sqlalchemy import func
    def _c(model, *where):
        q = select(func.count()).select_from(model)
        for w in where:
            q = q.where(w)
        return db.execute(q).scalar_one()
    return {
        "entities": _c(EntityCandidate,
                       EntityCandidate.case_id == case_id,
                       EntityCandidate.status.in_(("PENDING", "DEFERRED"))),
        "matches": _c(EntityMatchSuggestion,
                      EntityMatchSuggestion.case_id == case_id,
                      EntityMatchSuggestion.status == "PENDING"),
        "relationships": _c(RelationshipCandidate,
                            RelationshipCandidate.case_id == case_id,
                            RelationshipCandidate.status == "PENDING"),
    }


def settle_after_document(db: Session, case: Case) -> None:
    """Drive the lifecycle forward after ONE document finished processing
    (the upload auto-process path has no case job). Idempotent: a no-op
    when the case is already past PROCESSING or in a terminal state.

    The case state is re-read from the database (the in-memory ``case``
    may be stale — this session has been open since the upload), and the
    settle only happens once every document of the case is in a terminal
    state, so a mid-batch settle can never get ahead of the documents.
    """
    fresh = db.execute(
        select(Case.workflow_state).where(Case.id == case.id)
    ).scalar_one()
    case.workflow_state = fresh
    if fresh in (sm.UPLOADING, sm.STALE):
        sm.transition(db, case, sm.PROCESSING)
    case.workflow_state = db.execute(
        select(Case.workflow_state).where(Case.id == case.id)
    ).scalar_one()
    if case.workflow_state == sm.PROCESSING and _docs_in_flight(db, case.id) == 0:
        _settle_case_state(db, case)


def _settle_case_state(db: Session, case: Case) -> None:
    """Derive the post-processing workflow state from real counts."""
    from sqlalchemy import func
    def _c(model, *where):
        q = select(func.count()).select_from(model)
        for w in where:
            q = q.where(w)
        return db.execute(q).scalar_one()

    pending = _c(EntityCandidate, EntityCandidate.case_id == case.id,
                 EntityCandidate.status.in_(("PENDING", "DEFERRED")))
    pending += _c(RelationshipCandidate, RelationshipCandidate.case_id == case.id,
                  RelationshipCandidate.status == "PENDING")
    confirmed = _c(Entity, Entity.case_id == case.id) + _c(
        Relationship, Relationship.case_id == case.id)
    docs = db.scalars(select(Document).where(
        Document.case_id == case.id)).all()
    if not docs:
        target = sm.DRAFT
    elif pending > 0:
        target = sm.REVIEW_REQUIRED
    elif confirmed > 0:
        target = sm.READY_FOR_ANALYSIS
    else:
        target = sm.DRAFT
    sm.transition(db, case, target)


def latest_job(db: Session, case: Case) -> CaseProcessingJob | None:
    return db.scalar(select(CaseProcessingJob).where(
        CaseProcessingJob.case_id == case.id).order_by(
        CaseProcessingJob.id.desc()).limit(1))


def stage_checklist(db: Session, case: Case) -> list[dict]:
    """The real per-stage checklist (spec: ingestion ✓ … ready for review).

    A document counts as stage-complete only when the persisted artifact
    proving that stage exists. Nothing is interpolated.
    """
    docs = db.scalars(select(Document).where(
        Document.case_id == case.id).order_by(Document.id)).all()
    extractions = {e.document_id: e for e in db.scalars(
        select(DocumentExtraction).join(
            Document, DocumentExtraction.document_id == Document.id).where(
            Document.case_id == case.id)).all()}
    cand_counts = {}
    pending_cands = {}
    for c in db.scalars(select(EntityCandidate).where(
            EntityCandidate.case_id == case.id)).all():
        cand_counts[c.document_id] = cand_counts.get(c.document_id, 0) + 1
        if c.status in ("PENDING", "DEFERRED"):
            pending_cands[c.document_id] = pending_cands.get(
                c.document_id, 0) + 1

    def stage_done(stage: str, d: Document) -> bool:
        ex = extractions.get(d.id)
        if stage == "ingestion":
            return bool(d.storage_path)
        if stage == "text_extraction":
            return ex is not None and bool(ex.raw_text)
        if stage == "language_detection":
            return d.language is not None
        if stage == "normalization":
            return d.translation_status in ("NORMALIZED", "NOT_REQUIRED")
        if stage in ("entity_extraction", "relationship_extraction"):
            return d.processing_status == "PROCESSED"
        if stage == "review_candidates":
            return d.processing_status == "PROCESSED" and \
                pending_cands.get(d.id, 0) == 0
        return False

    total = len(docs)
    return [
        {"stage": s, "done": sum(1 for d in docs if stage_done(s, d)),
         "total": total}
        for s in PIPELINE_STAGES
    ]
