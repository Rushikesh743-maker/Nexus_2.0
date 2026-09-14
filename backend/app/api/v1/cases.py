"""Case API: list, create, detail, and the case-scoped read endpoints the
front end renders its workspace from.

Write scope for this stage: create a case and create a simulation record.
Everything analytical (extraction, resolution, scoring, simulation runs)
belongs to later stages and is deliberately not faked here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ...core.errors import not_found
from ...repositories import case_repository as repo
from ...models import User
from ...schemas.v1 import (CaseCreate, CaseDetail, CaseListItem,
                           ContradictionOut, DocumentOut, EntityOut,
                           EntityProfileOut, EvidenceOut, GapOut,
                           HypothesisOut, LocationOut, RelationshipOut,
                           SimulationCreate, SimulationOut, SnapshotCreateIn,
                           SnapshotListOut, SnapshotOut, TimelineEventOut)
from ...security.rbac import CurrentUser, get_current_user, require_roles
from ...services import case_access, case_service
from ...services.auth_service import record_audit
from .deps import get_db_checked
from .pagination import LIMIT_QUERY, OFFSET_QUERY, apply_pagination

logger = logging.getLogger("nexus.api.cases")
router = APIRouter(prefix="/cases", tags=["cases"])


def _require_case(db: Session, case_id: int, current: CurrentUser):
    return case_access.require_case_access(db, case_id, current)


@router.get("", response_model=list[CaseListItem], summary="List cases")
def list_cases(limit: int | None = LIMIT_QUERY, offset: int | None = OFFSET_QUERY,
               response: Response = None,
               db: Session = Depends(get_db_checked),
               current: CurrentUser = Depends(get_current_user)) -> list[CaseListItem]:
    """Case registry — filtered by the case access model (stage 7):
    investigators see their own cases; supervisors/admins/analysts see
    all of them. Nothing else leaks.

    Pagination is opt-in: without limit/offset the full (access-filtered)
    list is returned, as before; X-Total-Count is always sent."""
    allowed = case_access.accessible_case_ids(db, current.user)
    items = case_service.list_cases_out(db, only_ids=allowed)
    return apply_pagination(items, limit, offset, response)


@router.post("", response_model=CaseListItem, status_code=201,
             summary="Open a new case (INVESTIGATOR+)")
def create_case(body: CaseCreate, db: Session = Depends(get_db_checked),
                current: CurrentUser = Depends(require_roles("INVESTIGATOR"))) -> CaseListItem:
    from sqlalchemy import select

    from ...models import Case

    exists = db.scalars(select(Case).where(Case.case_number == body.case_number.upper())).first()
    if exists:
        from ...core.errors import ApiError

        raise ApiError("CASE_EXISTS", f"Case number {body.case_number.upper()} is already taken.", 409)
    case = repo.create_case(db, case_number=body.case_number, title=body.title,
                            description=body.description, status=body.status,
                            priority=body.priority, user=current.user)
    record_audit(db, current, "CREATE_CASE", "case", str(case.id),
                 {"case_number": case.case_number})
    logger.info("Case %s created by %s", case.case_number, current.user.email)
    item = case_service.list_cases_out(db)
    return next(i for i in item if i.id == case.id)


@router.get("/{case_id}", response_model=CaseDetail, summary="Case detail + aggregates")
def get_case(case_id: int, db: Session = Depends(get_db_checked),
             current: CurrentUser = Depends(get_current_user)) -> CaseDetail:
    _require_case(db, case_id, current)
    detail = case_service.get_case_detail(
        db, case_id,
        allowed_ids=case_access.accessible_case_ids(db, current.user))
    record_audit(db, current, "VIEW_CASE", "case", str(case_id))
    return detail


# -------------------------------------------------------- case-scoped reads

@router.get("/{case_id}/documents", response_model=list[DocumentOut])
def case_documents(case_id: int, limit: int | None = LIMIT_QUERY,
                   offset: int | None = OFFSET_QUERY, response: Response = None,
                   db: Session = Depends(get_db_checked),
                   current: CurrentUser = Depends(get_current_user)):
    case = _require_case(db, case_id, current)
    from ...repositories import document_repository as doc_repo

    counts = doc_repo._candidate_counts(db, case.id)
    items = [DocumentOut(**doc_repo.document_out_fields(db, case, d, counts))
             for d in repo.documents(db, case)]
    return apply_pagination(items, limit, offset, response)


@router.get("/{case_id}/entities", response_model=list[EntityOut])
def case_entities(case_id: int, limit: int | None = LIMIT_QUERY,
                  offset: int | None = OFFSET_QUERY, response: Response = None,
                  db: Session = Depends(get_db_checked),
                  current: CurrentUser = Depends(get_current_user)):
    case = _require_case(db, case_id, current)
    items = [EntityOut.model_validate(e) for e in repo.entities(db, case)]
    return apply_pagination(items, limit, offset, response)


@router.get("/{case_id}/entities/{entity_id}",
            response_model=EntityProfileOut,
            summary="One confirmed entity resolved to its full profile")
def case_entity_profile(case_id: int, entity_id: int,
                        db: Session = Depends(get_db_checked),
                        current: CurrentUser = Depends(get_current_user)):
    case = _require_case(db, case_id, current)
    from ...services import entity_profile as ep
    return ep.entity_profile(db, case, entity_id)


@router.post("/{case_id}/snapshots", response_model=SnapshotOut,
             status_code=201,
             summary="Capture the case's confirmed state as version N+1")
def case_create_snapshot(case_id: int, body: SnapshotCreateIn,
                         db: Session = Depends(get_db_checked),
                         current: CurrentUser = Depends(
                             require_roles("INVESTIGATOR", "SUPERVISOR",
                                           "ADMIN"))):
    case = _require_case(db, case_id, current)
    from ...services import case_snapshot as snap
    s = snap.create_snapshot(db, case, current, label=body.label)
    return _snapshot_fields(db, s)


@router.get("/{case_id}/snapshots", response_model=SnapshotListOut,
            summary="All immutable case snapshots (version 1..N)")
def case_list_snapshots(case_id: int,
                        db: Session = Depends(get_db_checked),
                        current: CurrentUser = Depends(get_current_user)):
    case = _require_case(db, case_id, current)
    from ...services import case_snapshot as snap
    from ...services.case_analysis import analysis_block
    rows = snap.list_snapshots(db, case)
    ab = analysis_block(db, case)
    return {"case_id": case.id,
            "current_graph_version": ab["graph_version"],
            "analysis": ab,
            "snapshots": [_snapshot_fields(db, s, summary=True)
                          for s in rows]}


@router.get("/{case_id}/snapshots/compare",
            summary="Diff two immutable snapshots (new/removed/changed)")
def case_compare_snapshots(case_id: int, from_seq: int, to_seq: int,
                           db: Session = Depends(get_db_checked),
                           current: CurrentUser = Depends(get_current_user)):
    case = _require_case(db, case_id, current)
    from ...services import case_snapshot as snap
    return snap.compare_snapshots(db, case, from_seq, to_seq)


@router.get("/{case_id}/snapshots/{snapshot_id}", response_model=SnapshotOut,
            summary="One immutable snapshot (full payload)")
def case_get_snapshot(case_id: int, snapshot_id: int,
                      db: Session = Depends(get_db_checked),
                      current: CurrentUser = Depends(get_current_user)):
    case = _require_case(db, case_id, current)
    from ...services import case_snapshot as snap
    s = snap.get_snapshot(db, case, snapshot_id)
    return _snapshot_fields(db, s)


def _snapshot_fields(db: Session, s, summary: bool = False) -> dict:
    creator = db.get(User, s.created_by) if s.created_by else None
    out = {"id": s.id,
           "case_id": s.case_id,
           "sequence": s.sequence,
           "label": s.label,
           "graph_version": s.graph_version,
           "entity_count": s.entity_count,
           "relationship_count": s.relationship_count,
           "evidence_count": s.evidence_count,
           "created_by_name": creator.name if creator else None,
           "created_at": s.created_at}
    if not summary:
        out["payload"] = s.payload
    return out


@router.get("/{case_id}/relationships", response_model=list[RelationshipOut])
def case_relationships(case_id: int, limit: int | None = LIMIT_QUERY,
                       offset: int | None = OFFSET_QUERY, response: Response = None,
                       db: Session = Depends(get_db_checked),
                       current: CurrentUser = Depends(get_current_user)):
    case = _require_case(db, case_id, current)
    items = [RelationshipOut.model_validate(r) for r in repo.relationships(db, case)]
    return apply_pagination(items, limit, offset, response)


@router.get("/{case_id}/evidence")
def case_evidence(case_id: int,
                  evidence_type: str | None = None,
                  offset: int | None = None,
                  limit: int | None = None,
                  response: Response = None,
                  db: Session = Depends(get_db_checked),
                  current: CurrentUser = Depends(get_current_user)):
    """Case evidence. Without ``limit`` returns the full list (the
    stage-1/6 contract); with ``limit`` (+ ``offset``) returns a paged
    envelope {items, total, offset, limit} — the stage-7 pagination.
    X-Total-Count is always sent."""
    case = _require_case(db, case_id, current)
    rows = [e for e in repo.evidence(db, case)
            if not evidence_type or e.evidence_type == evidence_type]
    total = len(rows)
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
    if limit is None:
        out = []
        for e in rows:
            item = EvidenceOut.model_validate(e)
            item.document_filename = e.document.filename if e.document else None
            out.append(item)
        return out
    lo = max(offset or 0, 0)
    hi = lo + max(limit, 1)
    out = []
    for e in rows[lo:hi]:
        item = EvidenceOut.model_validate(e)
        item.document_filename = e.document.filename if e.document else None
        out.append(item)
    return {"items": out, "total": total,
            "offset": lo, "limit": hi - lo}


@router.get("/{case_id}/timeline", response_model=list[TimelineEventOut])
def case_timeline(case_id: int,
                  entity_id: int | None = None,
                  event_type: str | None = None,
                  location_id: int | None = None,
                  from_date: datetime | None = None,
                  to_date: datetime | None = None,
                  limit: int | None = LIMIT_QUERY,
                  offset: int | None = OFFSET_QUERY,
                  response: Response = None,
                  db: Session = Depends(get_db_checked),
                  current: CurrentUser = Depends(get_current_user)):
    """Case timeline with stage-7 filters (entity / event type / location /
    date range) — all server-side, all case-scoped."""
    case = _require_case(db, case_id, current)
    # query params arrive naive; stored timestamps are timezone-aware
    if from_date is not None and from_date.tzinfo is None:
        from_date = from_date.replace(tzinfo=timezone.utc)
    if to_date is not None and to_date.tzinfo is None:
        to_date = to_date.replace(tzinfo=timezone.utc)
    rows = []
    for e in repo.timeline_events(db, case):
        if entity_id is not None and e.entity_id != entity_id:
            continue
        if event_type is not None and e.event_type != event_type:
            continue
        if location_id is not None and e.location_id != location_id:
            continue
        if from_date is not None and (e.timestamp is None
                                      or e.timestamp < from_date):
            continue
        if to_date is not None and (e.timestamp is None
                                    or e.timestamp > to_date):
            continue
        rows.append(e)
    items = [TimelineEventOut.model_validate(e) for e in rows]
    return apply_pagination(items, limit, offset, response)


@router.get("/{case_id}/locations", response_model=list[LocationOut])
def case_locations(case_id: int, limit: int | None = LIMIT_QUERY,
                   offset: int | None = OFFSET_QUERY, response: Response = None,
                   db: Session = Depends(get_db_checked),
                   current: CurrentUser = Depends(get_current_user)):
    case = _require_case(db, case_id, current)
    items = [LocationOut.model_validate(l) for l in repo.locations(db, case)]
    return apply_pagination(items, limit, offset, response)


@router.get("/{case_id}/hypotheses", response_model=list[HypothesisOut])
def case_hypotheses(case_id: int, limit: int | None = LIMIT_QUERY,
                    offset: int | None = OFFSET_QUERY, response: Response = None,
                    db: Session = Depends(get_db_checked),
                    current: CurrentUser = Depends(get_current_user)):
    case = _require_case(db, case_id, current)
    items = [HypothesisOut.model_validate(h) for h in repo.hypotheses(db, case)]
    return apply_pagination(items, limit, offset, response)


@router.get("/{case_id}/contradictions", response_model=list[ContradictionOut])
def case_contradictions(case_id: int, limit: int | None = LIMIT_QUERY,
                        offset: int | None = OFFSET_QUERY, response: Response = None,
                        db: Session = Depends(get_db_checked),
                        current: CurrentUser = Depends(get_current_user)):
    case = _require_case(db, case_id, current)
    items = [ContradictionOut.model_validate(c) for c in repo.contradictions(db, case)]
    return apply_pagination(items, limit, offset, response)


@router.get("/{case_id}/gaps", response_model=list[GapOut])
def case_gaps(case_id: int, limit: int | None = LIMIT_QUERY,
              offset: int | None = OFFSET_QUERY, response: Response = None,
              db: Session = Depends(get_db_checked),
              current: CurrentUser = Depends(get_current_user)):
    case = _require_case(db, case_id, current)
    items = [GapOut.model_validate(g) for g in repo.gaps(db, case)]
    return apply_pagination(items, limit, offset, response)


# ------------------------------------------------------------ simulations

@router.get("/{case_id}/simulations", response_model=list[SimulationOut])
def case_simulations(case_id: int, limit: int | None = LIMIT_QUERY,
                     offset: int | None = OFFSET_QUERY, response: Response = None,
                     db: Session = Depends(get_db_checked),
                     current: CurrentUser = Depends(get_current_user)):
    case = _require_case(db, case_id, current)
    items = [SimulationOut.model_validate(s) for s in repo.simulations(db, case)]
    return apply_pagination(items, limit, offset, response)


@router.post("/{case_id}/simulations", response_model=SimulationOut, status_code=201,
             summary="Register a simulation run (INVESTIGATOR+)")
def create_simulation(case_id: int, body: SimulationCreate,
                      db: Session = Depends(get_db_checked),
                      current: CurrentUser = Depends(require_roles("INVESTIGATOR"))) -> SimulationOut:
    case = _require_case(db, case_id, current)
    sim = repo.create_simulation(db, case, name=body.name, description=body.description,
                                 user=current.user)
    record_audit(db, current, "CREATE_SIMULATION", "simulation", str(sim.id),
                 {"case_id": case_id, "name": sim.name})
    return SimulationOut.model_validate(sim)
