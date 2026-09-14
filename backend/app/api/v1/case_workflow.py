"""Case-workflow API (stage 6 + stage 7) — the ONE surface the case
workspace uses.

Routes (JWT-authenticated, case-scoped, audited):

    POST /cases/{case_id}/process             case processing job (INVESTIGATOR+)
    POST /cases/{case_id}/analysis/run        run all intelligence (INVESTIGATOR+)
    POST /cases/{case_id}/analysis/recalculate  [RECALCULATE] stale findings
    GET  /cases/{case_id}/analysis/status     real pipeline state (one call)
    GET  /cases/{case_id}/processing/status   job + per-document states
    GET  /cases/{case_id}/summary             all case counts from the DB
    GET  /cases/{case_id}/lifecycle           state machine position
    POST /cases/{case_id}/close               terminal state (SUPERVISOR+)
    POST /cases/{case_id}/graph/build         rebuild the confirmed graph (ANALYST+)
    GET  /cases/{case_id}/graph               nodes + edges + provenance (+filters)
    GET  /cases/{case_id}/review/queue        the five human-review sections
    POST /cases/{case_id}/review/bulk         explicit bulk confirm/reject

Every response reflects persisted backend state; nothing here fakes
progress or returns canned data. The router delegates to
``services.case_analysis`` / ``services.case_processing`` (which in turn
reuse the existing engines — no intelligence logic is duplicated).
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...security.rbac import CurrentUser, get_current_user, require_roles
from ...services.case_access import require_case_access
from ...services import case_analysis as svc
from ...services import case_processing
from ...services import case_state_machine as sm
from ...services.auth_service import record_audit
from .deps import get_db_checked

router = APIRouter(tags=["case-workflow"])


# ------------------------------------------------------------- processing

@router.post("/cases/{case_id}/process",
             summary="Queue a case processing job (real per-document work)")
def case_process(case_id: int,
                 background: BackgroundTasks,
                 retry_failed: bool = False,
                 db: Session = Depends(get_db_checked),
                 current: CurrentUser = Depends(
                     require_roles("INVESTIGATOR", "SUPERVISOR"))):
    """Create a QUEUED job and return {job_id, case_id, status:"queued"}
    immediately; the worker processes the case's documents through the
    existing per-document pipeline (failure isolation: one failed
    document never stops the case). ``retry_failed=true`` re-runs only
    the FAILED documents."""
    case = require_case_access(db, case_id, current)
    out = case_processing.start_processing_job(
        db, case, current, only_failed=retry_failed)
    background.add_task(case_processing.run_processing_job,
                        out["job_id"], retry_failed)
    return {"job_id": out["job_id"], "case_id": case.id, "status": "queued"}


# ------------------------------------------------------------- analysis

@router.post("/cases/{case_id}/analysis/run",
             summary="Run all intelligence for this case (one call)")
def analysis_run(case_id: int,
                 db: Session = Depends(get_db_checked),
                 current: CurrentUser = Depends(
                     require_roles("INVESTIGATOR", "SUPERVISOR"))):
    case = require_case_access(db, case_id, current)
    out = svc.run_full_analysis(db, case, current)
    out["analysis"] = svc.analysis_block(db, case)
    return out


@router.post("/cases/{case_id}/analysis/recalculate",
             summary="[RECALCULATE] re-run after the case went STALE")
def analysis_recalculate(case_id: int,
                         db: Session = Depends(get_db_checked),
                         current: CurrentUser = Depends(
                             require_roles("INVESTIGATOR", "SUPERVISOR"))):
    case = require_case_access(db, case_id, current)
    out = svc.recalculate(db, case, current)
    out["analysis"] = svc.analysis_block(db, case)
    return out


# ------------------------------------------------------------- lifecycle

@router.get("/cases/{case_id}/lifecycle",
            summary="Case lifecycle position (state machine)")
def case_lifecycle(case_id: int,
                   db: Session = Depends(get_db_checked),
                   current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    return svc.lifecycle(db, case)


@router.post("/cases/{case_id}/close", status_code=200,
             summary="Close the case (terminal state, SUPERVISOR+)")
def case_close(case_id: int,
               db: Session = Depends(get_db_checked),
               current: CurrentUser = Depends(
                   require_roles("SUPERVISOR", "ADMIN"))):
    case = require_case_access(db, case_id, current)
    if case.workflow_state == sm.CLOSED:
        return svc.lifecycle(db, case)
    sm.transition(db, case, sm.CLOSED)
    record_audit(db, current, "CASE_CLOSED", "case", str(case.id),
                 {})
    return svc.lifecycle(db, case)


# ------------------------------------------------------------- review

class ReviewBulkIn(BaseModel):
    category: str  # entity | relationship | match
    action: str    # confirm | reject
    item_ids: list[int]


@router.post("/cases/{case_id}/review/bulk",
             summary="Explicit bulk confirm/reject of SELECTED items only")
def review_bulk(case_id: int,
                body: ReviewBulkIn,
                db: Session = Depends(get_db_checked),
                current: CurrentUser = Depends(
                    require_roles("INVESTIGATOR", "SUPERVISOR"))):
    case = require_case_access(db, case_id, current)
    return svc.bulk_review(db, case, current,
                           body.category, body.action, body.item_ids)



@router.get("/cases/{case_id}/analysis/status",
            summary="Real analysis/processing state for this case")
def analysis_status(case_id: int,
                    db: Session = Depends(get_db_checked),
                    current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    return svc.analysis_status(db, case)


@router.get("/cases/{case_id}/processing/status",
            summary="Per-document processing states (async job polling)")
def processing_status(case_id: int,
                      db: Session = Depends(get_db_checked),
                      current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    return svc.processing_status(db, case)


@router.get("/cases/{case_id}/summary",
            summary="All case counts (documents, entities, findings, ...)")
def case_summary(case_id: int,
                 db: Session = Depends(get_db_checked),
                 current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    return svc.summary(db, case)


@router.post("/cases/{case_id}/graph/build",
             summary="Rebuild the confirmed case graph (NetworkX)")
def graph_build(case_id: int,
                db: Session = Depends(get_db_checked),
                current: CurrentUser = Depends(require_roles("ANALYST"))):
    case = require_case_access(db, case_id, current)
    return svc.build_graph(db, case, current)


@router.get("/cases/{case_id}/graph",
            summary="Graph nodes + edges with per-edge evidence provenance")
def graph_get(case_id: int,
              entity_type: str | None = None,
              relationship_type: str | None = None,
              min_confidence: float | None = None,
              limit: int | None = None,
              db: Session = Depends(get_db_checked),
              current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    return svc.graph_payload(db, case,
                             entity_type=entity_type,
                             relationship_type=relationship_type,
                             min_confidence=min_confidence,
                             limit=limit)


@router.get("/cases/{case_id}/audit",
            summary="Case-scoped audit trail (read-only)")
def case_audit(case_id: int,
               limit: int = 200,
               db: Session = Depends(get_db_checked),
               current: CurrentUser = Depends(require_roles("ANALYST"))):
    case = require_case_access(db, case_id, current)
    return svc.audit_trail(db, case, limit=limit)


@router.get("/cases/{case_id}/review/queue",
            summary="Case-level review queue (entities, matches, "
                    "relationships, claims, contradictions)")
def review_queue(case_id: int,
                 db: Session = Depends(get_db_checked),
                 current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    return svc.review_queue(db, case)
