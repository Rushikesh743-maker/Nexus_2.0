"""Investigation intelligence API (stage 4).

Routes (JWT-authenticated, case-scoped, audited):

    POST /cases/{case_id}/investigation/analyze       full analysis (INVESTIGATOR+)
    GET  /cases/{case_id}/investigation/status        not-analyzed/analyzing/up-to-date/stale/insufficient
    GET  /cases/{case_id}/investigation/findings      all stage-4 findings
    GET  /cases/{case_id}/investigation/contradictions
    GET  /cases/{case_id}/investigation/gaps
    GET  /cases/{case_id}/investigation/hypotheses
    POST /cases/{case_id}/investigation/hypotheses    investigator hypothesis (INVESTIGATOR+)
    GET  /cases/{case_id}/investigation/evidence-impact
    GET  /cases/{case_id}/investigation/evidence/{eid}/impact
    POST /cases/{case_id}/investigation/evidence/{eid}/simulate-impact  (INVESTIGATOR+)
    GET  /cases/{case_id}/investigation/timeline
    GET  /cases/{case_id}/investigation/geospatial
    POST /cases/{case_id}/investigation/findings/{fid}/review    (INVESTIGATOR+)
    POST /cases/{case_id}/investigation/findings/{fid}/dismiss   (INVESTIGATOR+)
    POST /cases/{case_id}/investigation/hypotheses/{hid}/review  (INVESTIGATOR+)
    POST /cases/{case_id}/investigation/hypotheses/{hid}/dismiss (INVESTIGATOR+)

Read endpoints work for ANALYST and above; analysis and review actions
require INVESTIGATOR or SUPERVISOR. The router delegates everything to
the investigation-intelligence service.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...schemas.v1 import (EvidenceImpact, EvidenceImpactSummary,
                           EvidenceSimulation, FindingDetailOut,
                           GeospatialAnalysis, GeoObservationOut,
                           GeoResultOut, InvestigationAnalysis,
                           InvestigationFinding, InvestigationFindings,
                           InvestigationHypothesisOut,
                           InvestigationHypotheses,
                           InvestigatorHypothesisIn,
                           InvestigationStatus, ReviewDecision,
                           TimelineAnalysis, TimelineResultOut)
from ...security.rbac import CurrentUser, get_current_user, require_roles
from ...services.case_access import require_case_access
from ...services.investigation_intelligence import evidence_impact
from ...services.investigation_intelligence import finding_service as svc
from ...services.investigation_intelligence import (gap_engine,
                                                    timeline_engine,
                                                    geospatial_engine)
from ...services.investigation_intelligence.data import (
    compute_stage4_version, load_stage4_data)
from .deps import get_db_checked

router = APIRouter(tags=["investigation-intelligence"])


@router.post("/cases/{case_id}/investigation/analyze",
             response_model=InvestigationAnalysis,
             summary="Run investigation analysis (idempotent per data version)")
def investigate_analyze(case_id: int,
                        db: Session = Depends(get_db_checked),
                        current: CurrentUser = Depends(
                            require_roles("INVESTIGATOR", "SUPERVISOR"))):
    case = require_case_access(db, case_id, current)
    from ...services.case_analysis import analysis_block
    out = svc.run_analysis(db, case, current)
    out["analysis"] = analysis_block(db, case)
    return out


@router.get("/cases/{case_id}/investigation/status",
            response_model=InvestigationStatus,
            summary="Analysis state: not-analyzed / up-to-date / stale / insufficient")
def investigate_status(case_id: int,
                       db: Session = Depends(get_db_checked),
                       current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    data = load_stage4_data(db, case.id)
    version = compute_stage4_version(data)
    all_findings = svc._stage4_findings(db, case.id)
    current_rows = [f for f in all_findings if f.graph_version == version]
    stale_rows = [f for f in all_findings if f.graph_version != version]
    analyzed = bool(current_rows)
    insufficient = not (data.entities and data.relationships)
    if insufficient:
        state = "insufficient"
        reason = ("No confirmed entities/relationships in this case — "
                  "analysis needs confirmed graph data.")
    elif analyzed:
        state = "up-to-date"
        reason = (f"{len(current_rows)} finding(s) for the current "
                  f"confirmed-data snapshot {version}."
                  + (f" {len(stale_rows)} finding(s) from earlier "
                     "snapshots are kept as stale." if stale_rows else ""))
    elif stale_rows:
        state = "stale"
        reason = (f"Confirmed data changed since the last analysis "
                  f"({len(stale_rows)} stale finding(s) kept) — "
                  "re-analyze to refresh.")
    else:
        state = "not-analyzed"
        reason = "No investigation analysis has been run for this case."
    return InvestigationStatus(
        case_id=case.id, state=state, graph_version=version,
        analyzed=analyzed, reason=reason,
        current_findings=len(current_rows),
        stale_findings=sum(1 for f in all_findings
                           if f.graph_version != version),
        hypotheses=len(svc._stage4_hypotheses(db, case.id)),
        insufficient=insufficient,
        timeline={
            "events_total": len(data.events),
            "events_with_timestamp": len(data.dated_events),
            "events_without_timestamp":
                len(data.events) - len(data.dated_events),
        },
        geospatial={
            "locations_total": len(data.locations),
            "locations_with_coords": sum(
                1 for l in data.locations if l.latitude is not None),
        })


@router.get("/cases/{case_id}/investigation/findings",
            response_model=InvestigationFindings,
            summary="All stage-4 findings (current + stale)")
def investigate_findings(case_id: int,
                         include_stale: bool = Query(default=True),
                         db: Session = Depends(get_db_checked),
                         current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    from ...services.case_analysis import analysis_block
    out = svc.list_findings(db, case, include_stale=include_stale)
    out["analysis"] = analysis_block(db, case)
    return out


@router.get("/cases/{case_id}/investigation/findings/{finding_id}",
            response_model=FindingDetailOut,
            summary="A single finding resolved to its full evidence chain")
def investigate_finding_detail(case_id: int, finding_id: int,
                               db: Session = Depends(get_db_checked),
                               current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    from ...services.case_analysis import analysis_block
    out = svc.finding_evidence_chain(db, case, finding_id)
    out["analysis"] = analysis_block(db, case)
    return out


@router.get("/cases/{case_id}/investigation/contradictions",
            response_model=InvestigationFindings,
            summary="Potential contradictions (confirmed records only)")
def investigate_contradictions(case_id: int,
                               include_stale: bool = Query(default=True),
                               db: Session = Depends(get_db_checked),
                               current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    from ...services.case_analysis import analysis_block
    out = svc.list_findings_by_type(db, case, "CONTRADICTION",
                                    include_stale=include_stale)
    out["analysis"] = analysis_block(db, case)
    return out


@router.get("/cases/{case_id}/investigation/gaps",
            response_model=InvestigationFindings,
            summary="Potential investigation gaps")
def investigate_gaps(case_id: int,
                     include_stale: bool = Query(default=True),
                     db: Session = Depends(get_db_checked),
                     current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    from ...services.case_analysis import analysis_block
    out = svc.list_findings_by_type(db, case, "INVESTIGATION_GAP",
                                    include_stale=include_stale)
    out["analysis"] = analysis_block(db, case)
    return out


@router.get("/cases/{case_id}/investigation/hypotheses",
            response_model=InvestigationHypotheses,
            summary="Competing hypotheses with transparent scores")
def investigate_hypotheses(case_id: int,
                           include_stale: bool = Query(default=True),
                           db: Session = Depends(get_db_checked),
                           current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    from ...services.case_analysis import analysis_block
    out = svc.list_hypotheses(db, case, include_stale=include_stale)
    out["analysis"] = analysis_block(db, case)
    return out


@router.post("/cases/{case_id}/investigation/hypotheses",
             response_model=InvestigationHypothesisOut,
             summary="Create an investigator hypothesis (scored, never deleted)")
def investigate_create_hypothesis(
        case_id: int, body: InvestigatorHypothesisIn,
        db: Session = Depends(get_db_checked),
        current: CurrentUser = Depends(
            require_roles("INVESTIGATOR", "SUPERVISOR"))):
    case = require_case_access(db, case_id, current)
    return svc.create_hypothesis(db, case, current, body.model_dump())


@router.get("/cases/{case_id}/investigation/evidence-impact",
            response_model=EvidenceImpactSummary,
            summary="Per-evidence analytical linkage + impact scores")
def investigate_evidence_impact(case_id: int,
                                db: Session = Depends(get_db_checked),
                                current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    from ...services.case_analysis import analysis_block
    data = load_stage4_data(db, case.id)
    out = evidence_impact.summary_payload(data, db)
    out["analysis"] = analysis_block(db, case)
    return out


@router.get("/cases/{case_id}/investigation/evidence/{evidence_id}/impact",
            response_model=EvidenceImpact,
            summary="Impact of one evidence record")
def investigate_evidence_impact_one(case_id: int, evidence_id: int,
                                    db: Session = Depends(get_db_checked),
                                    current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    data = load_stage4_data(db, case.id)
    if not any(v.id == evidence_id for v in data.evidence):
        from ...core.errors import not_found
        not_found("EVIDENCE_NOT_FOUND",
                  f"Evidence {evidence_id} not found in this case.")
    return evidence_impact.evidence_impact_payload(data, db, evidence_id)


@router.post("/cases/{case_id}/investigation/evidence/{evidence_id}/simulate-impact",
             response_model=EvidenceSimulation,
             summary="In-memory removal simulation (never deletes)")
def investigate_simulate_impact(case_id: int, evidence_id: int,
                                db: Session = Depends(get_db_checked),
                                current: CurrentUser = Depends(
                                    require_roles("INVESTIGATOR", "SUPERVISOR"))):
    case = require_case_access(db, case_id, current)
    data = load_stage4_data(db, case.id)
    if not any(v.id == evidence_id for v in data.evidence):
        from ...core.errors import not_found
        not_found("EVIDENCE_NOT_FOUND",
                  f"Evidence {evidence_id} not found in this case.")
    return evidence_impact.simulate_removal(db, data, evidence_id)


@router.get("/cases/{case_id}/investigation/timeline",
            response_model=TimelineAnalysis,
            summary="Timeline intelligence (overlaps, proximity, sequence, gaps)")
def investigate_timeline(case_id: int,
                         db: Session = Depends(get_db_checked),
                         current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    data = load_stage4_data(db, case.id)
    from ...services.case_analysis import analysis_block
    results, meta = timeline_engine.analyze_timeline(data)
    return TimelineAnalysis(
        case_id=case.id,
        results=[TimelineResultOut(**r.__dict__) for r in results],
        events_total=meta["events_total"],
        events_with_timestamp=meta["events_with_timestamp"],
        events_without_timestamp=meta["events_without_timestamp"],
        insufficient=meta["insufficient"],
        analysis_method=timeline_engine.METHOD,
        analysis=analysis_block(db, case))


@router.get("/cases/{case_id}/investigation/geospatial",
            response_model=GeospatialAnalysis,
            summary="Geospatial intelligence (co-location, proximity, sequence)")
def investigate_geospatial(case_id: int,
                           db: Session = Depends(get_db_checked),
                           current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    from ...services.case_analysis import analysis_block
    data = load_stage4_data(db, case.id)
    results, obs, meta = geospatial_engine.analyze_geospatial(data)
    name_of = {e.id: e.canonical_name for e in data.entities}
    return GeospatialAnalysis(
        case_id=case.id,
        results=[GeoResultOut(**r.__dict__) for r in results],
        observations=[
            GeoObservationOut(
                entity_id=o.entity_id,
                entity_name=(name_of.get(o.entity_id)
                             if o.entity_id else None),
                location_id=o.location_id, location_name=o.location_name,
                latitude=o.lat, longitude=o.lon,
                timestamp=o.timestamp.isoformat() if o.timestamp else None,
                source_event_id=o.source_event_id,
                source_relationship_id=o.source_relationship_id)
            for o in obs],
        observations_count=meta["observations"],
        location_data_insufficient=meta["location_data_insufficient"],
        analysis_method=geospatial_engine.METHOD,
        analysis=analysis_block(db, case))


@router.post("/cases/{case_id}/investigation/findings/{finding_id}/review",
             response_model=InvestigationFinding,
             summary="Review a stage-4 finding (kept auditable)")
def investigate_review_finding(case_id: int, finding_id: int,
                               body: ReviewDecision | None = None,
                               db: Session = Depends(get_db_checked),
                               current: CurrentUser = Depends(
                                   require_roles("INVESTIGATOR", "SUPERVISOR"))):
    case = require_case_access(db, case_id, current)
    return svc.review_finding(db, case, finding_id, current, "reviewed",
                              body.note if body else None)


@router.post("/cases/{case_id}/investigation/findings/{finding_id}/dismiss",
             response_model=InvestigationFinding,
             summary="Dismiss a stage-4 finding (kept auditable, never deleted)")
def investigate_dismiss_finding(case_id: int, finding_id: int,
                                body: ReviewDecision | None = None,
                                db: Session = Depends(get_db_checked),
                                current: CurrentUser = Depends(
                                    require_roles("INVESTIGATOR", "SUPERVISOR"))):
    case = require_case_access(db, case_id, current)
    return svc.review_finding(db, case, finding_id, current, "dismissed",
                              body.note if body else None)


@router.post("/cases/{case_id}/investigation/hypotheses/{hypothesis_id}/review",
             response_model=InvestigationHypothesisOut,
             summary="Review a hypothesis (kept auditable)")
def investigate_review_hypothesis(case_id: int, hypothesis_id: int,
                                  body: ReviewDecision | None = None,
                                  db: Session = Depends(get_db_checked),
                                  current: CurrentUser = Depends(
                                      require_roles("INVESTIGATOR", "SUPERVISOR"))):
    case = require_case_access(db, case_id, current)
    return svc.review_hypothesis(db, case, hypothesis_id, current, "reviewed",
                                 body.note if body else None)


@router.post("/cases/{case_id}/investigation/hypotheses/{hypothesis_id}/dismiss",
             response_model=InvestigationHypothesisOut,
             summary="Dismiss a hypothesis (kept auditable, never deleted)")
def investigate_dismiss_hypothesis(case_id: int, hypothesis_id: int,
                                   body: ReviewDecision | None = None,
                                   db: Session = Depends(get_db_checked),
                                   current: CurrentUser = Depends(
                                       require_roles("INVESTIGATOR", "SUPERVISOR"))):
    case = require_case_access(db, case_id, current)
    return svc.review_hypothesis(db, case, hypothesis_id, current, "dismissed",
                                 body.note if body else None)
