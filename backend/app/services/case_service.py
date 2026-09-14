"""Case business logic.

The router talks to this service; the service talks to the repository.
Keeping the three layers separate means later stages (document upload,
extraction hooks, analytics) can grow here without touching HTTP code.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..repositories import case_repository as repo
from ..schemas.v1 import (CaseDetail, CaseListItem, CrossCaseLink)


def list_cases_out(db: Session, only_ids: list[int] | None = None) -> list[CaseListItem]:
    """Case registry. ``only_ids=None`` means unrestricted (supervisor /
    admin / analyst); otherwise only those case ids are listed — the
    stage-7 access model keeps other investigators' cases invisible."""
    out = []
    for case in repo.list_cases(db):
        if only_ids is not None and case.id not in only_ids:
            continue
        out.append(CaseListItem(
            **{c.name: getattr(case, c.name) for c in case.__table__.columns},
            counts=repo.counts_for(case),
            latest_event_at=repo.latest_event_at(case),
        ))
    return out


def get_case_detail(db: Session, case_id: int,
                    allowed_ids: list[int] | None = None) -> CaseDetail:
    case = repo.get_case(db, case_id)
    if case is None:
        from ..core.errors import not_found

        not_found("CASE_NOT_FOUND", "No case with this id.")

    degrees = repo.entity_degrees(case)
    key_entities = [
        {"id": e.id, "type": e.entity_type, "canonical_name": e.canonical_name,
         "aliases": (e.meta or {}).get("aliases", []),
         "connection_count": degrees.get(e.id, 0),
         "metadata": e.meta}
        for e in repo.entities(db, case)[:25]
    ]
    latest = [
        {"id": ev.id, "event_type": ev.event_type, "timestamp": ev.timestamp,
         "description": ev.description}
        for ev in reversed(repo.timeline_events(db, case)[:8])
    ]
    links = [CrossCaseLink(**{**l, "shared_count": len(l.get("shared_entities", []))})
             for l in repo.cross_case_links(db, case, allowed_ids=allowed_ids)]

    return CaseDetail(
        **{c.name: getattr(case, c.name) for c in case.__table__.columns},
        created_by_name=case.created_by_name,
        counts=repo.counts_for(case),
        key_entities=key_entities,
        cross_case_links=links,
        latest_events=latest,
    )
