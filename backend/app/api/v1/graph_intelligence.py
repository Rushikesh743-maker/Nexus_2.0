"""Graph intelligence API (stage 3).

Routes (all JWT-authenticated; role floor ANALYST = every authenticated
role can view, run and review — matching the stage-3 access matrix):

    POST /cases/{case_id}/graph/analyze      run engine + persist findings
    GET  /cases/{case_id}/graph/findings     current + stale findings
    POST /cases/{case_id}/graph/findings/{fid}/review
    POST /cases/{case_id}/graph/findings/{fid}/dismiss
    GET  /cases/{case_id}/graph/metrics      per-entity metrics
    GET  /cases/{case_id}/graph/bridges      bridge entities
    GET  /cases/{case_id}/graph/clusters     network clusters
    GET  /cases/{case_id}/graph/cross-case   cross-case connections
    GET  /cases/{case_id}/graph/paths        confirmed paths A -> B

Analysis runs only on CONFIRMED data; results are explainable and
traceable to the confirmed relationships/evidence behind them. The
router delegates everything to the graph-intelligence service.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...schemas.v1 import (GraphAnalysisOut, GraphBridgesOut, GraphClustersOut,
                           GraphCrossCaseOut, GraphFindingOut, GraphFindingsOut,
                           GraphMetricsOut, GraphPathsOut, ReviewDecision)
from ...security.rbac import CurrentUser, get_current_user, require_roles
from ...services.graph_intelligence import endpoints as gp
from ...services.graph_intelligence.finding_service import (
    apply_review, list_findings, require_finding, run_analysis)
from ...services.case_access import require_case_access
from ...services.graph_intelligence.graph_builder import MAX_PATH_DEPTH, MAX_PATHS
from .deps import get_db_checked

router = APIRouter(tags=["graph-intelligence"])


@router.post("/cases/{case_id}/graph/analyze", response_model=GraphAnalysisOut,
             summary="Run graph analysis and persist findings")
def analyze_case_graph(case_id: int,
                       db: Session = Depends(get_db_checked),
                       current: CurrentUser = Depends(require_roles("ANALYST"))):
    case = require_case_access(db, case_id, current)
    out = run_analysis(db, case, current)
    from ...services.case_analysis import analysis_block
    out["analysis"] = analysis_block(db, case)
    return out


@router.get("/cases/{case_id}/graph/findings", response_model=GraphFindingsOut,
            summary="List findings (current run + stale history)")
def graph_findings(case_id: int,
                   include_stale: bool = Query(default=True),
                   db: Session = Depends(get_db_checked),
                   current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    out = list_findings(db, case, include_stale=include_stale)
    from ...services.case_analysis import analysis_block
    out["analysis"] = analysis_block(db, case)
    return out


@router.post("/cases/{case_id}/graph/findings/{finding_id}/review",
             response_model=GraphFindingOut,
             summary="Mark a finding as reviewed (kept auditable)")
def review_finding(case_id: int, finding_id: int,
                   body: ReviewDecision | None = None,
                   db: Session = Depends(get_db_checked),
                   current: CurrentUser = Depends(require_roles("ANALYST"))):
    case = require_case_access(db, case_id, current)
    finding = require_finding(db, case_id, finding_id)
    return apply_review(db, case, finding, current, "reviewed",
                        body.note if body else None)


@router.post("/cases/{case_id}/graph/findings/{finding_id}/dismiss",
             response_model=GraphFindingOut,
             summary="Dismiss a finding (kept auditable, never deleted)")
def dismiss_finding(case_id: int, finding_id: int,
                    body: ReviewDecision | None = None,
                    db: Session = Depends(get_db_checked),
                    current: CurrentUser = Depends(require_roles("ANALYST"))):
    case = require_case_access(db, case_id, current)
    finding = require_finding(db, case_id, finding_id)
    return apply_review(db, case, finding, current, "dismissed",
                        body.note if body else None)


@router.get("/cases/{case_id}/graph/metrics", response_model=GraphMetricsOut,
            summary="Per-entity graph metrics (confirmed data)")
def graph_metrics(case_id: int,
                  db: Session = Depends(get_db_checked),
                  current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    out = gp.get_metrics(db, case_id)
    from ...services.case_analysis import analysis_block
    out["analysis"] = analysis_block(db, case)
    return out


@router.get("/cases/{case_id}/graph/bridges", response_model=GraphBridgesOut,
            summary="Bridge entities (articulation + betweenness)")
def graph_bridges(case_id: int,
                  db: Session = Depends(get_db_checked),
                  current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    out = gp.get_bridges(db, case_id)
    from ...services.case_analysis import analysis_block
    out["analysis"] = analysis_block(db, case)
    return out


@router.get("/cases/{case_id}/graph/clusters", response_model=GraphClustersOut,
            summary="Network clusters (connected components)")
def graph_clusters(case_id: int,
                   db: Session = Depends(get_db_checked),
                   current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    out = gp.get_clusters(db, case_id)
    from ...services.case_analysis import analysis_block
    out["analysis"] = analysis_block(db, case)
    return out


@router.get("/cases/{case_id}/graph/cross-case", response_model=GraphCrossCaseOut,
            summary="Cross-case connections (confirmed shared entities)")
def graph_cross_case(case_id: int,
                     db: Session = Depends(get_db_checked),
                     current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    from ...services import case_access
    from ...services.case_analysis import analysis_block
    out = gp.get_cross_case(
        db, case_id,
        allowed_ids=case_access.accessible_case_ids(db, current.user))
    out["analysis"] = analysis_block(db, case)
    return out


@router.get("/cases/{case_id}/graph/paths", response_model=GraphPathsOut,
            summary="Confirmed paths between two entities")
def graph_paths(case_id: int,
                source_entity_id: int = Query(...),
                target_entity_id: int = Query(...),
                max_depth: int = Query(default=MAX_PATH_DEPTH, ge=1, le=MAX_PATH_DEPTH),
                max_paths: int = Query(default=MAX_PATHS, ge=1, le=MAX_PATHS),
                db: Session = Depends(get_db_checked),
                current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    out = gp.get_paths(db, case_id, source_entity_id, target_entity_id,
                       max_depth, max_paths)
    from ...services.case_analysis import analysis_block
    out["analysis"] = analysis_block(db, case)
    return out
