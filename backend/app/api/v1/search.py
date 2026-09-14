"""Global Investigation Search API.

Searches across Cases, Entities, Evidence, Documents, Relationships,
Findings, Hypotheses, and Locations with strict RBAC enforcement.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...models import (Case, Document, Entity, Evidence, GraphFinding,
                       Hypothesis, Location, Relationship)
from ...security.rbac import CurrentUser, get_current_user
from ...services import case_access
from ...services.auth_service import record_audit
from .deps import get_db_checked

logger = logging.getLogger("nexus.api.search")
router = APIRouter(prefix="/search", tags=["search"])


class SearchResultItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str | int
    result_type: str  # case | entity | evidence | document | relationship | finding | hypothesis | location
    label: str
    sub: str | None = None
    case_id: int | None = None
    case_number: str | None = None
    verification_status: str | None = None
    relevance: float = 1.0
    url: str | None = None
    metadata: dict[str, Any] | None = None


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResultItem]
    counts_by_type: dict[str, int]


def _match_score(query: str, *fields: str | None) -> float:
    q = query.lower().strip()
    score = 0.0
    for field in fields:
        if not field:
            continue
        f = field.lower()
        if q == f:
            score = max(score, 1.0)
        elif f.startswith(q):
            score = max(score, 0.9)
        elif q in f:
            score = max(score, 0.75)
    return score


@router.get("", response_model=SearchResponse, summary="Global investigation search")
def search(
    q: str = Query(..., min_length=1, description="Search query"),
    case_id: int | None = Query(default=None, description="Optional case scope"),
    limit: int = Query(default=40, ge=1, le=200, description="Max results to return"),
    db: Session = Depends(get_db_checked),
    current: CurrentUser = Depends(get_current_user),
) -> SearchResponse:
    query = q.strip()
    allowed_case_ids = case_access.accessible_case_ids(db, current.user)

    if case_id is not None:
        case_access.require_case_access(db, case_id, current)
        target_case_ids = {case_id}
    elif allowed_case_ids is not None:
        target_case_ids = allowed_case_ids
    else:
        target_case_ids = None

    results: list[SearchResultItem] = []
    pattern = f"%{query}%"

    # 1. Cases
    case_stmt = select(Case).where(
        or_(
            Case.case_number.ilike(pattern),
            Case.title.ilike(pattern),
            Case.description.ilike(pattern),
        )
    )
    if target_case_ids is not None:
        case_stmt = case_stmt.where(Case.id.in_(target_case_ids))

    for c in db.scalars(case_stmt.limit(10)).all():
        score = _match_score(query, c.case_number, c.title, c.description)
        results.append(
            SearchResultItem(
                id=c.id,
                result_type="case",
                label=f"{c.case_number} — {c.title}",
                sub=f"Status: {c.status} · Priority: {c.priority}",
                case_id=c.id,
                case_number=c.case_number,
                verification_status=c.status,
                relevance=score,
                url=f"/cases/{c.id}",
            )
        )

    # Helper to resolve case numbers
    cases_lookup = {c.id: c.case_number for c in db.scalars(select(Case)).all()}

    # 2. Entities
    ent_stmt = select(Entity).where(
        or_(
            Entity.canonical_name.ilike(pattern),
            Entity.entity_type.ilike(pattern),
        )
    )
    if target_case_ids is not None:
        ent_stmt = ent_stmt.where(Entity.case_id.in_(target_case_ids))

    for e in db.scalars(ent_stmt.limit(15)).all():
        score = _match_score(query, e.canonical_name, e.entity_type)
        c_num = cases_lookup.get(e.case_id, f"Case #{e.case_id}")
        results.append(
            SearchResultItem(
                id=e.id,
                result_type="entity",
                label=e.canonical_name,
                sub=f"{e.entity_type.title()} · {c_num}",
                case_id=e.case_id,
                case_number=c_num,
                verification_status="CONFIRMED",
                relevance=score,
                url=f"/cases/{e.case_id}/entities/{e.id}",
                metadata={"type": e.entity_type},
            )
        )

    # 3. Evidence
    ev_stmt = select(Evidence).where(
        or_(
            Evidence.source_reference.ilike(pattern),
            Evidence.description.ilike(pattern),
            Evidence.evidence_type.ilike(pattern),
        )
    )
    if target_case_ids is not None:
        ev_stmt = ev_stmt.where(Evidence.case_id.in_(target_case_ids))

    for ev in db.scalars(ev_stmt.limit(10)).all():
        score = _match_score(query, ev.source_reference, ev.description, ev.evidence_type)
        c_num = cases_lookup.get(ev.case_id, f"Case #{ev.case_id}")
        results.append(
            SearchResultItem(
                id=ev.id,
                result_type="evidence",
                label=f"{ev.source_reference} ({ev.evidence_type.upper()})",
                sub=f"{ev.description[:90]} · {c_num}" if ev.description else c_num,
                case_id=ev.case_id,
                case_number=c_num,
                verification_status="VERIFIED" if ev.is_verified else "UPLOADED",
                relevance=score,
                url=f"/cases/{ev.case_id}/evidence?evidenceId={ev.id}",
            )
        )

    # 4. Documents
    doc_stmt = select(Document).where(
        or_(
            Document.filename.ilike(pattern),
            Document.file_type.ilike(pattern),
        )
    )
    if target_case_ids is not None:
        doc_stmt = doc_stmt.where(Document.case_id.in_(target_case_ids))

    for doc in db.scalars(doc_stmt.limit(10)).all():
        score = _match_score(query, doc.filename, doc.file_type)
        c_num = cases_lookup.get(doc.case_id, f"Case #{doc.case_id}")
        results.append(
            SearchResultItem(
                id=doc.id,
                result_type="document",
                label=doc.filename,
                sub=f"{doc.file_type.upper()} ({doc.processing_status}) · {c_num}",
                case_id=doc.case_id,
                case_number=c_num,
                verification_status=doc.processing_status,
                relevance=score,
                url=f"/cases/{doc.case_id}/documents/{doc.id}",
            )
        )

    # 5. Relationships
    rel_stmt = select(Relationship).where(
        Relationship.relationship_type.ilike(pattern)
    )
    if target_case_ids is not None:
        rel_stmt = rel_stmt.where(Relationship.case_id.in_(target_case_ids))

    for rel in db.scalars(rel_stmt.limit(8)).all():
        score = _match_score(query, rel.relationship_type)
        c_num = cases_lookup.get(rel.case_id, f"Case #{rel.case_id}")
        src_name = rel.source.canonical_name if rel.source else f"Entity #{rel.source_entity_id}"
        tgt_name = rel.target.canonical_name if rel.target else f"Entity #{rel.target_entity_id}"
        results.append(
            SearchResultItem(
                id=rel.id,
                result_type="relationship",
                label=f"{src_name} ──[{rel.relationship_type}]──> {tgt_name}",
                sub=f"Confidence: {int(rel.confidence * 100)}% · {c_num}",
                case_id=rel.case_id,
                case_number=c_num,
                verification_status="CONFIRMED",
                relevance=score,
                url=f"/cases/{rel.case_id}/relationships",
            )
        )

    # 6. Graph Findings
    finding_stmt = select(GraphFinding).where(
        or_(
            GraphFinding.title.ilike(pattern),
            GraphFinding.summary.ilike(pattern),
            GraphFinding.finding_type.ilike(pattern),
        )
    )
    if target_case_ids is not None:
        finding_stmt = finding_stmt.where(GraphFinding.case_id.in_(target_case_ids))

    for f in db.scalars(finding_stmt.limit(8)).all():
        score = _match_score(query, f.title, f.summary, f.finding_type)
        c_num = cases_lookup.get(f.case_id, f"Case #{f.case_id}")
        results.append(
            SearchResultItem(
                id=f.id,
                result_type="finding",
                label=f.title,
                sub=f"{f.finding_type} · {c_num}",
                case_id=f.case_id,
                case_number=c_num,
                verification_status="ACTIVE" if not f.stale else "STALE",
                relevance=score,
                url=f"/cases/{f.case_id}/investigation",
            )
        )

    # 7. Hypotheses
    hyp_stmt = select(Hypothesis).where(
        or_(
            Hypothesis.title.ilike(pattern),
            Hypothesis.description.ilike(pattern),
        )
    )
    if target_case_ids is not None:
        hyp_stmt = hyp_stmt.where(Hypothesis.case_id.in_(target_case_ids))

    for h in db.scalars(hyp_stmt.limit(8)).all():
        score = _match_score(query, h.title, h.description)
        c_num = cases_lookup.get(h.case_id, f"Case #{h.case_id}")
        results.append(
            SearchResultItem(
                id=h.id,
                result_type="hypothesis",
                label=h.title,
                sub=f"Status: {h.status} · Score: {h.score:.2f} · {c_num}",
                case_id=h.case_id,
                case_number=c_num,
                verification_status=h.status,
                relevance=score,
                url=f"/cases/{h.case_id}/hypotheses",
            )
        )

    # 8. Locations
    loc_stmt = select(Location).where(
        or_(
            Location.name.ilike(pattern),
            Location.address.ilike(pattern),
        )
    )
    if target_case_ids is not None:
        loc_stmt = loc_stmt.where(Location.case_id.in_(target_case_ids))

    for loc in db.scalars(loc_stmt.limit(8)).all():
        score = _match_score(query, loc.name, loc.address)
        c_num = cases_lookup.get(loc.case_id, f"Case #{loc.case_id}")
        results.append(
            SearchResultItem(
                id=loc.id,
                result_type="location",
                label=loc.name,
                sub=f"{loc.address or 'Mapped coordinate'} · {c_num}",
                case_id=loc.case_id,
                case_number=c_num,
                verification_status="CONFIRMED",
                relevance=score,
                url=f"/cases/{loc.case_id}/map",
            )
        )

    # Sort results by relevance descending
    results.sort(key=lambda r: (-r.relevance, r.result_type, str(r.label)))
    limited_results = results[:limit]

    # Calculate counts by type
    counts: dict[str, int] = {}
    for r in results:
        counts[r.result_type] = counts.get(r.result_type, 0) + 1

    record_audit(db, current, "GLOBAL_SEARCH", "search", query, {"match_count": len(results)})
    return SearchResponse(
        query=query,
        total=len(results),
        results=limited_results,
        counts_by_type=counts,
    )
