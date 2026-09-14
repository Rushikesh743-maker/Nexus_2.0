"""Top-level read namespaces for the platform resources.

Each of /documents, /entities, /relationships, /evidence, /timeline,
/locations, /hypotheses, /contradictions, /gaps, /simulations exposes a
list endpoint, optionally filtered by `case_id`. One factory builds them
all from (model, schema, repository function) triples so the API contract
stays uniform and there is no per-resource copy-paste.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.errors import not_found
from ...repositories import case_repository as repo
from ...schemas.v1 import (ContradictionOut, DocumentOut, EntityOut,
                           EvidenceOut, GapOut, HypothesisOut, LocationOut,
                           RelationshipOut, SimulationOut, TimelineEventOut)
from ...security.rbac import CurrentUser, get_current_user
from ...services import case_access
from .deps import get_db_checked
from .pagination import LIMIT_QUERY, OFFSET_QUERY, apply_pagination

logger = logging.getLogger("nexus.api.resources")


def _require_case(db: Session, case_id: int, current: CurrentUser):
    return case_access.require_case_access(db, case_id, current)


def _collect(case_id: int | None, fn: Callable,
             db: Session, current: CurrentUser) -> list:
    if case_id is not None:
        case = _require_case(db, case_id, current)
        return fn(db, case)
    allowed = case_access.accessible_case_ids(db, current.user)
    items = []
    for case in repo.list_cases(db):
        if allowed is not None and case.id not in allowed:
            continue  # never leak another investigator's records
        items.extend(fn(db, case))
    return items


def _list(case_id: int | None, fn: Callable) -> Callable:
    def _handler(limit: int | None = LIMIT_QUERY,
                 offset: int | None = OFFSET_QUERY,
                 response: Response = None,
                 db: Session = Depends(get_db_checked),
                 current: CurrentUser = Depends(get_current_user)):
        raw = _collect(case_id, fn, db, current)
        items = [schema.model_validate(i) for i in raw]
        return apply_pagination(items, limit, offset, response)

    return _handler


def make_resource_router(name: str, schema: type[BaseModel],
                         fn: Callable) -> APIRouter:
    r = APIRouter(tags=[name])

    @r.get("", response_model=list[schema])
    def list_resource(case_id: int | None = Query(default=None),
                      limit: int | None = LIMIT_QUERY,
                      offset: int | None = OFFSET_QUERY,
                      response: Response = None,
                      db: Session = Depends(get_db_checked),
                      current: CurrentUser = Depends(get_current_user)):
        return _list(case_id, fn)(limit, offset, response, db, current)

    return r


resources: dict[str, Any] = {
    "documents": (DocumentOut, repo.documents),
    "entities": (EntityOut, repo.entities),
    "relationships": (RelationshipOut, repo.relationships),
    "evidence": (EvidenceOut, repo.evidence),
    "timeline": (TimelineEventOut, repo.timeline_events),
    "locations": (LocationOut, repo.locations),
    "hypotheses": (HypothesisOut, repo.hypotheses),
    "contradictions": (ContradictionOut, repo.contradictions),
    "gaps": (GapOut, repo.gaps),
    "simulations": (SimulationOut, repo.simulations),
}


def build_resource_routers() -> list[APIRouter]:
    out = []
    for name, (schema, fn) in resources.items():
        r = APIRouter(prefix=f"/{name}", tags=[name])

        def _make(schema=schema, fn=fn):
            def _handler(case_id: int | None = Query(default=None),
                         limit: int | None = LIMIT_QUERY,
                         offset: int | None = OFFSET_QUERY,
                         response: Response = None,
                         db: Session = Depends(get_db_checked),
                         current: CurrentUser = Depends(get_current_user)):
                raw = _collect(case_id, fn, db, current)
                items = [schema.model_validate(i) for i in raw]
                return apply_pagination(items, limit, offset, response)
            return _handler

        r.add_api_route("", _make(), response_model=list[schema],
                        summary=f"List {name} (optionally per case)")
        out.append(r)
    return out
