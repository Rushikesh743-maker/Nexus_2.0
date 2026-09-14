"""Background document processing: a real job queue on the existing stack.

Phase 1 production foundation. Document processing used to run inside the
web process as a FastAPI background task attached to the upload request.
It now runs through a durable job queue:

    upload / retry  ->  one QUEUED row in ``document_processing_job``
                       -> the HTTP response returns immediately
    worker          ->  claims rows with ``SELECT ... FOR UPDATE SKIP LOCKED``
                       -> runs the EXISTING pipeline
                          (``document_service.process_document``)
                       -> finalizes the job row from the real document state

Two deployment shapes, one worker implementation:

* **in-process** (development / single-node): the API starts the worker
  thread on startup (``WORKER_ENABLED`` defaults to true).
* **separate process** (scaled production): ``python -m
  app.workers.document_worker`` runs the same worker against the same
  database. Any number of workers may run at once — the row lock is what
  prevents double-processing, not a single process.

Guarantees (all verifiable in the database, none faked):

* **No double processing.** ``document_id`` is unique on the job table;
  a document with a QUEUED/PROCESSING job is never re-queued, and a
  PROCESSED document is never reprocessed.
* **Retries are visible.** The retry action reuses the job row and
  increments ``attempts`` — the history of how often a document was
  (re)processed is in the row.
* **Crash recovery.** A worker that dies between claiming a job and
  finishing it leaves the job PROCESSING; the reconciliation pass
  finalizes such jobs from the document's real state, and a job that has
  been stuck for ``WORKER_STUCK_TIMEOUT_MINUTES`` is failed honestly
  with the document reset to UPLOADED (retryable).
* **Honest errors.** ``job.error`` mirrors the document's user-safe
  ``processing_error`` (no tracebacks, no filesystem paths).
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ..core.database import SessionLocal
from ..models import Document, DocumentProcessingJob
from . import document_service

logger = logging.getLogger("nexus.worker.documents")

QUEUED = "QUEUED"
PROCESSING = "PROCESSING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"

TERMINAL = (COMPLETED, FAILED)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ enqueue

def enqueue_document_job(db, doc_id: int, case_id: int) -> tuple[DocumentProcessingJob, str]:
    """Idempotently ensure the document has a job.

    Returns ``(job, action)`` where action is one of:

    * ``created``          — a new QUEUED job was created
    * ``already_queued``   — a live job already exists (nothing done)
    * ``already_processing`` — a live job exists and is in flight
    * ``completed``        — the document already finished successfully
                             (nothing done — never reprocessed)
    * ``requeued``         — a FAILED job (or a completed job whose
                             document was reset to UPLOADED) was put
                             back in the queue; ``attempts`` counts it

    The caller commits.
    """
    job = db.scalar(select(DocumentProcessingJob)
                    .where(DocumentProcessingJob.document_id == doc_id))
    if job is None:
        job = DocumentProcessingJob(document_id=doc_id, case_id=case_id,
                                    status=QUEUED)
        db.add(job)
        db.flush()
        return job, "created"

    if job.status in (QUEUED, PROCESSING):
        return job, ("already_queued" if job.status == QUEUED
                     else "already_processing")

    doc = db.get(Document, doc_id)
    needs_work = doc is not None and doc.processing_status == "UPLOADED"
    if job.status == COMPLETED and not needs_work:
        return job, "completed"

    # FAILED (the normal retry path), or COMPLETED but the document row
    # was reset to UPLOADED by an operator — requeue the same row.
    job.status = QUEUED
    job.error = None
    job.finished_at = None
    return job, "requeued"


def job_out(job: DocumentProcessingJob) -> dict:
    """The API-facing shape of a job (never internal details)."""
    return {
        "id": job.id,
        "document_id": job.document_id,
        "status": job.status,
        "attempts": job.attempts,
        "error": job.error,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


# ------------------------------------------------- standalone job execution
# These are module-level (own session) so the SAME code can run in the
# worker thread OR as a FastAPI background-task fallback when no worker is
# running (WORKER_ENABLED=false with no standalone worker). Either way the
# job row is finalized from the document's real state.


def finalize_job(job_id: int, error_override: str | None = None) -> None:
    """Set the job to COMPLETED/FAILED from the document's real state."""
    db = SessionLocal()
    try:
        job = db.get(DocumentProcessingJob, job_id)
        if job is None:
            return
        doc = db.get(Document, job.document_id)
        if doc is None:
            job.status = FAILED
            job.error = error_override or "document no longer exists"
            job.finished_at = _now()
        elif doc.processing_status == "PROCESSED":
            job.status = COMPLETED
            job.error = None
            job.finished_at = _now()
        elif doc.processing_status == "FAILED":
            job.status = FAILED
            job.error = error_override or doc.processing_error
            job.finished_at = _now()
        elif error_override:
            job.status = FAILED
            job.error = error_override
            job.finished_at = _now()
        else:
            # Not terminal yet (should not happen — process_document always
            # settles it). Leave the job as-is; reconciliation finalizes it.
            logger.warning("finalize_job(%s): document %s is %s (not terminal)",
                           job_id, job.document_id, doc.processing_status)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("Failed to finalize job %s", job_id)
    finally:
        db.close()


def run_job(job_id: int) -> None:
    """Run the pipeline for one job and finalize the job row.

    Background-task-safe: own session, never raises, always leaves the job
    in a coherent state. If the document is no longer retryable (e.g. a
    worker already processed it first), this finalizes without re-running.
    """
    db = SessionLocal()
    try:
        job = db.get(DocumentProcessingJob, job_id)
        if job is None:
            return
        if job.status not in (QUEUED, PROCESSING):
            return  # already settled by someone else
        doc = db.get(Document, job.document_id)
        doc_id = job.document_id
        retryable = (doc is not None
                     and doc.processing_status in ("UPLOADED", "FAILED"))
    finally:
        db.close()

    from ..core import logging as nexus_logging
    nexus_logging.set_job_context(job_id)
    result: dict = {}
    try:
        if retryable:
            result = document_service.process_document(doc_id)
        if not retryable or result.get("status") == "NOT_FOUND":
            finalize_job(job_id, error_override=(
                None if retryable
                else "document was deleted before the job could run"))
        else:
            finalize_job(job_id)
    except Exception:  # noqa: BLE001
        logger.exception("run_job(%s) crashed", job_id)
        finalize_job(job_id, error_override="worker crashed while "
                     "processing the document")
    finally:
        nexus_logging.set_job_context(None)


# ------------------------------------------------------------------- worker

class DocumentProcessingWorker:
    """A polling worker over the ``document_processing_job`` queue.

    One instance may run in any process; instances coordinate purely
    through the database (row locks). The loop never dies on a bad job —
    every step is isolated.
    """

    def __init__(self, poll_interval: float | None = None,
                 batch_size: int | None = None,
                 stuck_timeout_minutes: int | None = None):
        from ..core.config import get_settings
        s = get_settings()
        self.poll_interval = (s.worker_poll_interval
                              if poll_interval is None else poll_interval)
        self.batch_size = (s.worker_batch_size
                           if batch_size is None else batch_size)
        self.stuck_timeout = timedelta(minutes=(
            s.worker_stuck_timeout_minutes
            if stuck_timeout_minutes is None else stuck_timeout_minutes))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.started_at: datetime | None = None
        self.last_poll_at: datetime | None = None
        self.jobs_completed = 0
        self.jobs_failed = 0
        self.processing_job_id: int | None = None

    # -- lifecycle -----------------------------------------------------
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self.started_at = _now()
        self._thread = threading.Thread(
            target=self._loop, name="nexus-document-worker", daemon=True)
        self._thread.start()
        logger.info("Document worker started (poll=%.2fs batch=%d)",
                    self.poll_interval, self.batch_size)

    def stop(self) -> None:
        if not self.running:
            return
        self._stop.set()
        assert self._thread is not None
        self._thread.join(timeout=5)
        logger.info("Document worker stopped (completed=%d failed=%d)",
                    self.jobs_completed, self.jobs_failed)

    # -- the loop -------------------------------------------------------
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.reconcile()
                if self.claim_and_process():
                    continue  # queue was non-empty; loop without sleeping
            except Exception:  # noqa: BLE001 — the worker must never die
                logger.exception("Document worker loop error (continuing)")
            self.last_poll_at = _now()
            self._stop.wait(self.poll_interval)

    def _claim(self, db) -> list[DocumentProcessingJob]:
        """Atomically claim up to ``batch_size`` QUEUED jobs."""
        jobs = db.execute(
            select(DocumentProcessingJob)
            .where(DocumentProcessingJob.status == QUEUED)
            .order_by(DocumentProcessingJob.id)
            .limit(self.batch_size)
            .with_for_update(skip_locked=True)
        ).scalars().all()
        for job in jobs:
            job.status = PROCESSING
            job.attempts += 1
            job.started_at = _now()
        if jobs:
            db.commit()
        return list(jobs)

    def claim_and_process(self) -> bool:
        """One queue drain: claim a batch and process each document.

        Returns True when work was claimed (the caller should loop again
        without sleeping), False when the queue was empty.
        """
        db = SessionLocal()
        try:
            jobs = self._claim(db)
        finally:
            db.close()
        if not jobs:
            return False
        for job in jobs:
            self.processing_job_id = job.id
            try:
                self._process_one(job.id)
            except Exception:  # noqa: BLE001 — isolated per job
                logger.exception("Worker failed to process job %s "
                                 "(document %s)", job.id, job.document_id)
                self._finalize(job.id, error_override="worker crashed "
                                 "while processing the document")
            finally:
                self.processing_job_id = None
        return True

    def _process_one(self, job_id: int) -> None:
        """Run the existing pipeline for the job's document, then finalize
        the job row from the document's real state. Delegates to the
        module-level ``run_job`` so the worker thread and the background
        fallback execute byte-identical code."""
        run_job(job_id)
        self._tally(job_id)

    def _tally(self, job_id: int) -> None:
        """Update the worker's completion counters from the job row."""
        db = SessionLocal()
        try:
            job = db.get(DocumentProcessingJob, job_id)
            if job is not None and job.status in TERMINAL:
                if job.status == COMPLETED:
                    self.jobs_completed += 1
                else:
                    self.jobs_failed += 1
        finally:
            db.close()

    # -- crash recovery ---------------------------------------------------
    def reconcile(self) -> None:
        """Finalize jobs the worker did not get to finalize.

        * PROCESSING whose document reached a terminal state -> finalize
          (the worker died between the pipeline commit and the job update).
        * PROCESSING stuck longer than ``stuck_timeout`` with the document
          still PROCESSING -> the pipeline process is gone; fail the job
          honestly and reset the document to UPLOADED (retryable).
        """
        db = SessionLocal()
        try:
            stuck_before = _now() - self.stuck_timeout
            jobs = db.scalars(
                select(DocumentProcessingJob)
                .where(DocumentProcessingJob.status == PROCESSING)
            ).all()
            changed = False
            for job in jobs:
                doc = db.get(Document, job.document_id)
                if doc is None:
                    job.status = FAILED
                    job.error = "document no longer exists"
                    job.finished_at = _now()
                    self.jobs_failed += 1
                    changed = True
                elif doc.processing_status in ("PROCESSED", "FAILED"):
                    self._apply_terminal(db, job, doc)
                    changed = True
                elif (job.started_at is not None
                      and job.started_at < stuck_before):
                    job.status = FAILED
                    job.error = ("processing timed out after "
                                 f"{int(self.stuck_timeout.total_seconds() // 60)} "
                                 "minutes with no result")
                    job.finished_at = _now()
                    doc.processing_status = "UPLOADED"
                    doc.processing_error = None
                    self.jobs_failed += 1
                    changed = True
                    logger.warning("Job %s (document %s) stuck — reset to "
                                   "UPLOADED for retry", job.id, job.document_id)
            if changed:
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("Reconciliation pass failed (continuing)")
        finally:
            db.close()

    def _apply_terminal(self, db, job: DocumentProcessingJob,
                        doc: Document) -> None:
        if doc.processing_status == "PROCESSED":
            job.status = COMPLETED
            job.error = None
            self.jobs_completed += 1
        else:
            job.status = FAILED
            job.error = doc.processing_error
            self.jobs_failed += 1
        job.finished_at = _now()

    # -- observability ------------------------------------------------------
    def status(self) -> dict:
        """Live state for the readiness endpoint (all real, all queryable)."""
        from sqlalchemy import func
        db = SessionLocal()
        try:
            queued = db.execute(
                select(func.count()).select_from(DocumentProcessingJob)
                .where(DocumentProcessingJob.status == QUEUED)).scalar_one()
            in_flight = db.execute(
                select(func.count()).select_from(DocumentProcessingJob)
                .where(DocumentProcessingJob.status == PROCESSING)).scalar_one()
        finally:
            db.close()
        return {
            "running": self.running,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_poll_at": (self.last_poll_at.isoformat()
                             if self.last_poll_at else None),
            "queued": queued,
            "in_flight": in_flight,
            "jobs_completed": self.jobs_completed,
            "jobs_failed": self.jobs_failed,
        }


# ------------------------------------------------------- process registry

_registry: list[DocumentProcessingWorker] = []
_registry_lock = threading.Lock()


def start_inprocess_worker() -> DocumentProcessingWorker | None:
    """Start (once) the worker that lives with the API process."""
    from ..core.config import get_settings
    if not get_settings().worker_enabled:
        logger.info("In-process document worker disabled (WORKER_ENABLED=false)")
        return None
    with _registry_lock:
        for w in list(_registry):
            if w.running:
                return w
        worker = DocumentProcessingWorker()
        _registry.append(worker)
    worker.start()
    return worker


def stop_inprocess_worker() -> None:
    with _registry_lock:
        for w in list(_registry):
            w.stop()
        _registry.clear()


def worker_active() -> bool:
    """True when at least one worker (in-process or standalone) is running
    in this process — used to decide whether the case-level job enqueues
    documents for the worker or processes them directly."""
    with _registry_lock:
        return any(w.running for w in _registry)


def worker_status() -> dict:
    with _registry_lock:
        workers = [_worker_status(w) for w in list(_registry)]
    return {"workers": workers, "active": any(w["running"] for w in workers)}


def _worker_status(w: DocumentProcessingWorker) -> dict:
    st = w.status()
    st["in_process"] = True
    return st


def register_standalone_worker(worker: DocumentProcessingWorker) -> None:
    """The standalone entry point registers itself so readiness and the
    case-level job see it exactly like the in-process worker."""
    with _registry_lock:
        _registry.append(worker)
    return worker
