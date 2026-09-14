"""Stage 6 — case-level analysis orchestration (single-case workflow).

This module is the ONE service the case workspace talks to when the
investigator wants "run the intelligence" or "what is the state of this
case". It deliberately does not reimplement any engine:

* ``run_full_analysis`` wraps the existing Stage 4 ``finding_service.
  run_analysis`` orchestrator (network / bridges / communities /
  anomalies / contradictions / hypotheses / gaps / timeline / geospatial
  — all Stage 4 engines, untouched) and decorates the result with the
  fields the case workspace needs: ``analysis_id``, started/completed
  timestamps, graph node/edge counts and the post-run state.
* ``build_graph`` / ``graph_payload`` reuse the Stage 3 confirmed-graph
  builder (NetworkX, evidence-linked) — the graph is always derived from
  confirmed case data, never hardcoded.
* ``analysis_status`` / ``processing_status`` / ``summary`` /
  ``review_queue`` report ONLY real backend state. There is no progress
  percentage: document states are the discrete persisted states
  (UPLOADED / PROCESSING / PROCESSED / REVIEW_REQUIRED / FAILED) and the
  analysis state machine mirrors the documented Stage 4 status endpoint
  exactly (not-analyzed / up-to-date / stale / insufficient).

Full recomputation, structured for later incremental work: every run is
versioned by the documented Stage 4 snapshot hash. A document upload
changes the hash, so ``run_full_analysis`` recomputes and the previous
snapshot's findings become ``STALE`` (kept, never deleted), and
``analysis_status`` exposes current vs stale counts. An incremental
engine can later key off the same version without any public API change.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import networkx as nx

from ..core.errors import ApiError
from ..models import (AuditLog, Case, CaseAnalysisRun, CaseProcessingJob,
                      Document, Entity, EntityCandidate,
                      EntityMatchSuggestion, Evidence, EvidenceClaim,
                      GraphFinding, Hypothesis, InvestigationHypothesis,
                      Location, Relationship, RelationshipCandidate,
                      TimelineEvent, User)
from ..security.rbac import CurrentUser
from ..services import case_state_machine as sm
from ..services import document_service
from ..services.auth_service import record_audit
from ..repositories import document_repository as repo
from ..services.graph_intelligence.graph_builder import (build_case_graph,
                                                         compute_graph_version)
from ..services.graph_intelligence.cluster_analysis import analyze_clusters
from ..services.investigation_intelligence.data import (compute_stage4_version,
                                                        load_stage4_data)
from ..services.investigation_intelligence.finding_service import (
    _stage4_findings, _stage4_hypotheses, run_analysis)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------- state

def _stage4_state(db: Session, case: Case) -> dict:
    """Analysis state of a case (Stage 7, run-record based).

    Since Stage 7 every analysis is persisted as a versioned
    ``CaseAnalysisRun``. "Has the current confirmed-data snapshot been
    analyzed?" is therefore a property of the LATEST RUN, not of
    "do findings exist" — a clean analysis may legitimately return
    zero findings and must still read as up-to-date. Cases from before
    Stage 7 (no persisted run, e.g. seeded demo data) fall back to the
    findings-snapshot inference.
    """
    data = load_stage4_data(db, case.id)
    version = compute_stage4_version(data)
    all_findings = _stage4_findings(db, case.id)
    current_rows = [f for f in all_findings if f.graph_version == version]
    stale_rows = [f for f in all_findings if f.graph_version != version]
    insufficient = not (data.entities and data.relationships)
    latest_run = db.scalar(
        select(CaseAnalysisRun)
        .where(CaseAnalysisRun.case_id == case.id)
        .order_by(CaseAnalysisRun.version.desc(),
                  CaseAnalysisRun.created_at.desc())
        .limit(1))
    if insufficient:
        state = "insufficient"
        reason = ("No confirmed entities/relationships in this case — "
                  "analysis needs confirmed graph data.")
        analyzed = False
    elif latest_run is None:
        # Pre-Stage-7 case: no persisted run — infer from findings.
        if current_rows:
            state = "up-to-date"
            reason = (f"{len(current_rows)} finding(s) for the current "
                      f"confirmed-data snapshot {version}.")
        elif stale_rows:
            state = "stale"
            reason = (f"Confirmed data changed since the last analysis "
                      f"({len(stale_rows)} stale finding(s) kept) — "
                      "re-analyze to refresh.")
        else:
            state = "not-analyzed"
            reason = "No investigation analysis has been run for this case."
        analyzed = bool(current_rows)
    elif latest_run.graph_version == version:
        state = "up-to-date"
        analyzed = True
        reason = (f"Run #{latest_run.version} "
                  f"({latest_run.findings_count} finding(s)) covers the "
                  f"current confirmed-data snapshot {version}."
                  + (f" {len(stale_rows)} finding(s) from earlier "
                     "snapshots are kept as stale." if stale_rows else ""))
    else:
        state = "stale"
        analyzed = False
        reason = (f"Confirmed data changed after run #{latest_run.version} "
                  f"(data version {version[:12]}… vs analyzed "
                  f"{latest_run.graph_version[:12]}…) — "
                  f"{len(stale_rows)} finding(s) from the previous "
                  "snapshot are kept as stale; recalculate to rebuild.")
    return {
        "state": state,
        "graph_version": version,
        "reason": reason,
        "analyzed": analyzed,
        "insufficient": insufficient,
        "current_findings": len(current_rows),
        "stale_findings": len(stale_rows),
        "data": data,
    }


def analysis_block(db: Session, case: Case) -> dict:
    """The case's analysis freshness as a self-describing block (phase 2,
    work item E). Every intelligence surface returns this alongside its
    results so the UI can show NOT_ANALYZED / UP_TO_DATE / STALE /
    INSUFFICIENT_DATA — old analysis is never silently presented as
    current. ``graph_version`` here is the stage-4 confirmed-data hash
    (entities + relationships + evidence + events + locations + claims)."""
    st = _stage4_state(db, case)
    return {"state": st["state"],
            "graph_version": st["graph_version"],
            "reason": st["reason"],
            "analyzed": st["analyzed"],
            "insufficient": st["insufficient"]}


def analysis_status(db: Session, case: Case) -> dict:
    """Real backend state of the whole pipeline for one case (one call)."""
    st = _stage4_state(db, case)
    data = st.pop("data")
    version = st["graph_version"]

    docs = db.execute(select(Document).where(Document.case_id == case.id)
                      ).scalars().all()
    docs_by_status: dict[str, int] = {}
    for d in docs:
        docs_by_status[d.processing_status] = docs_by_status.get(
            d.processing_status, 0) + 1

    def _count(model, *where):
        q = select(func.count()).select_from(model)
        for w in where:
            q = q.where(w)
        return db.execute(q).scalar_one()

    current_findings = _stage4_findings(db, case.id)
    return {
        "case_id": case.id,
        "case_number": case.case_number,
        "workflow_state": case.workflow_state,
        "allowed_next": list(sm.allowed_next(case.workflow_state)),
        "state": st["state"],
        "reason": st["reason"],
        "graph_version": version,
        "analyzed": st["analyzed"],
        "last_analysis_at": case.last_analysis_at,
        "documents": {
            "total": len(docs),
            "by_status": docs_by_status,
            "all_processed": len(docs) > 0 and all(
                d.processing_status not in ("UPLOADED", "PROCESSING")
                for d in docs),
        },
        "pending_review": {
            "entity_candidates": _count(EntityCandidate,
                                        EntityCandidate.case_id == case.id,
                                        EntityCandidate.status == "PENDING"),
            "entity_matches": _count(EntityMatchSuggestion,
                                     EntityMatchSuggestion.case_id == case.id,
                                     EntityMatchSuggestion.status == "PENDING"),
            "relationship_candidates": _count(
                RelationshipCandidate,
                RelationshipCandidate.case_id == case.id,
                RelationshipCandidate.status == "PENDING"),
            "evidence_claims": _count(EvidenceClaim,
                                      EvidenceClaim.case_id == case.id),
            "contradiction_findings": sum(
                1 for f in current_findings
                if f.finding_type == "CONTRADICTION"
                and f.graph_version == version and f.status == "ACTIVE"),
        },
        "findings": {
            "current": st["current_findings"],
            "stale": st["stale_findings"],
        },
        "hypotheses": len(_stage4_hypotheses(db, case.id)),
        "timeline": {
            "events_total": len(data.events),
            "events_with_timestamp": len(data.dated_events),
            "events_without_timestamp":
                len(data.events) - len(data.dated_events),
        },
        "geospatial": {
            "locations_total": len(data.locations),
            "locations_with_coords": sum(
                1 for l in data.locations if l.latitude is not None),
        },
    }


def processing_status(db: Session, case: Case) -> dict:
    """Case processing state: the real job, the real per-document states,
    the real stage checklist and the real extracted counts (stage 7).

    No progress percentage anywhere: ``job.current_stage`` names the
    document in flight, and each checklist stage is proven by a persisted
    artifact (extraction row, language column, candidate counts)."""
    from . import case_processing

    docs = db.execute(select(Document).where(Document.case_id == case.id)
                      .order_by(Document.id)).scalars().all()
    counts = repo._candidate_counts(db, case.id)
    out_docs = []
    for d in docs:
        f = repo.document_out_fields(db, case, d, counts)
        # Derived display status (documented, not a stored field): a
        # PROCESSED document still carrying pending candidates is shown
        # as REVIEW_REQUIRED. The stored processing_status is untouched.
        f["effective_status"] = ("REVIEW_REQUIRED"
                                 if d.processing_status == "PROCESSED"
                                 and f["pending_review"] > 0
                                 else d.processing_status)
        out_docs.append(f)
    by_status: dict[str, int] = {}
    for d in docs:
        by_status[d.processing_status] = by_status.get(d.processing_status, 0) + 1
    job = case_processing.latest_job(db, case)
    return {
        "case_id": case.id,
        "case_number": case.case_number,
        "workflow_state": case.workflow_state,
        "job": {
            "job_id": job.job_id,
            "status": job.status,
            "current_stage": job.current_stage,
            "total_documents": job.total_documents,
            "processed_documents": job.processed_documents,
            "failed_documents": job.failed_documents,
            "extracted_counts": job.extracted_counts,
            "error": job.error,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
        } if job else None,
        "stage_checklist": case_processing.stage_checklist(db, case),
        "documents": out_docs,
        "total": len(docs),
        "processed": sum(1 for d in docs if d.processing_status == "PROCESSED"),
        "failed": sum(1 for d in docs if d.processing_status == "FAILED"),
        "by_status": by_status,
        "all_processed": len(docs) > 0 and all(
            d.processing_status not in ("UPLOADED", "PROCESSING")
            for d in docs),
        "note": ("Documents are processed by a real case job; poll this "
                 "endpoint or GET /documents/{id}/status. Every number "
                 "here is a persisted row count — no progress "
                 "percentage is faked."),
    }


def summary(db: Session, case: Case) -> dict:
    """All case-workspace counts from the database (one call)."""
    def _count(model, *where):
        q = select(func.count()).select_from(model)
        for w in where:
            q = q.where(w)
        return db.execute(q).scalar_one()

    case_id = case.id
    st = _stage4_state(db, case)
    version = st["graph_version"]
    findings = _stage4_findings(db, case_id)
    current = [f for f in findings if f.graph_version == version]
    return {
        "case_id": case_id,
        "case_number": case.case_number,
        "title": case.title,
        "is_synthetic": case.is_synthetic,
        "created_by": case.created_by_name,
        "priority": case.priority,
        "description": case.description,
        "status": case.status,
        "created_at": case.created_at,
        "counts": {
            "documents": _count(Document, Document.case_id == case_id),
            "entities": _count(Entity, Entity.case_id == case_id),
            "relationships": _count(Relationship,
                                    Relationship.case_id == case_id),
            "relationship_candidates": _count(
                RelationshipCandidate,
                RelationshipCandidate.case_id == case_id,
                RelationshipCandidate.status == "PENDING"),
            "evidence": _count(Evidence, Evidence.case_id == case_id),
            "timeline_events": _count(TimelineEvent,
                                      TimelineEvent.case_id == case_id),
            "locations": _count(Location, Location.case_id == case_id),
            "findings_current": len(current),
            "findings_stale": len(findings) - len(current),
            "contradictions": sum(
                1 for f in current if f.finding_type == "CONTRADICTION"),
            "hypotheses": _count(InvestigationHypothesis,
                                 InvestigationHypothesis.case_id == case_id,
                                 InvestigationHypothesis.status == "ACTIVE"),
            "legacy_hypotheses": _count(Hypothesis,
                                        Hypothesis.case_id == case_id,
                                        Hypothesis.status == "OPEN"),
            "claims": _count(EvidenceClaim, EvidenceClaim.case_id == case_id),
        },
        "analysis": {
            "state": st["state"],
            "reason": st["reason"],
            "graph_version": version,
            "last_analyzed": max((f.created_at for f in current),
                                 default=None),
        },
    }


# ------------------------------------------------------------- review queue

def review_queue(db: Session, case: Case) -> dict:
    """The five case-level review sections (spec: everything waiting on a
    human decision, with full context for each row)."""
    docs = {d.id: d for d in db.execute(
        select(Document).where(Document.case_id == case.id)).scalars()}
    ents = {e.id: e for e in db.execute(
        select(Entity).where(Entity.case_id == case.id)).scalars()}

    cands = db.execute(select(EntityCandidate).where(
        EntityCandidate.case_id == case.id,
        EntityCandidate.status == "PENDING").order_by(EntityCandidate.id)
    ).scalars().all()
    # all candidates (any status) — relationship endpoints that were
    # already accepted/rejected must still be nameable in the queue
    all_cands = db.execute(select(EntityCandidate).where(
        EntityCandidate.case_id == case.id).order_by(EntityCandidate.id)
    ).scalars().all()
    matches = db.execute(select(EntityMatchSuggestion).where(
        EntityMatchSuggestion.case_id == case.id,
        EntityMatchSuggestion.status == "PENDING"
    ).order_by(EntityMatchSuggestion.candidate_id,
               EntityMatchSuggestion.rank)).scalars().all()
    rel_cands = db.execute(select(RelationshipCandidate).where(
        RelationshipCandidate.case_id == case.id,
        RelationshipCandidate.status == "PENDING"
    ).order_by(RelationshipCandidate.id)).scalars().all()

    # Phase 2: a candidate may carry several ranked suggestions — each
    # PENDING row is its own review item (rank 1 first).
    matches_by_candidate: dict[int, list] = {}
    for m in matches:
        matches_by_candidate.setdefault(m.candidate_id, []).append(m)

    def _doc(cid: int | None):
        d = docs.get(cid)
        return d.filename if d else None

    new_entities, potential_duplicates = [], []
    for c in cands:
        entry = {
            "id": c.id,
            "document_id": c.document_id,
            "name": c.candidate_name,
            "entity_type": c.entity_type,
            "confidence": c.confidence,
            "aliases": c.aliases,
            "source_document": _doc(c.document_id),
            "source_snippet": c.source_snippet,
            "source_location": c.source_location,
            "extraction_method": c.extraction_method,
        }
        ms = matches_by_candidate.get(c.id, [])
        usable = [m for m in ms if m.existing_entity_id in ents]
        if usable:
            for m in usable:
                existing = ents[m.existing_entity_id]
                potential_duplicates.append({
                    **entry,
                    "match_id": m.id,
                    "rank": m.rank,
                    "suggestions_total": len(usable),
                    "existing_entity_id": existing.id,
                    "existing_entity_name": existing.canonical_name,
                    "similarity": m.similarity,
                    "match_reasons": m.reasons,
                })
        else:
            new_entities.append(entry)

    def _endpoint_name(cand_id: int) -> str:
        """Name a relationship endpoint: the accepted candidate's canonical
        entity when it has been confirmed, otherwise the candidate name —
        never a silent '?' for a row that still exists."""
        cand = next((c for c in all_cands if c.id == cand_id), None)
        if cand is None:
            return "?"
        if cand.status == "ACCEPTED" and cand.accepted_entity_id is not None:
            ent = ents.get(cand.accepted_entity_id)
            if ent is not None:
                return ent.canonical_name
        return cand.candidate_name

    candidate_relationships = []
    for r in rel_cands:
        candidate_relationships.append({
            "id": r.id,
            "document_id": r.document_id,
            "source_name": _endpoint_name(r.source_candidate_id),
            "target_name": _endpoint_name(r.target_candidate_id),
            "relationship_type": r.relationship_type,
            "confidence": r.confidence,
            "source_document": _doc(r.document_id),
            "source_snippet": r.source_snippet,
            "source_location": r.source_location,
        })

    claims = db.execute(select(EvidenceClaim).where(
        EvidenceClaim.case_id == case.id).order_by(EvidenceClaim.id)
    ).scalars().all()
    evs = {e.id: e for e in db.execute(select(Evidence).where(
        Evidence.case_id == case.id)).scalars()}
    evidence_claims = []
    for c in claims:
        subj = ents.get(c.subject_entity_id)
        obj = ents.get(c.object_entity_id)
        ev = evs.get(c.evidence_id)
        evidence_claims.append({
            "id": c.id,
            "subject": subj.canonical_name if subj else str(c.subject_entity_id),
            "predicate": c.predicate,
            "object": obj.canonical_name if obj else c.object_value,
            "event_time": c.event_time,
            "location": c.location_id,
            "evidence_type": ev.evidence_type if ev else None,
            "source_document": _doc(ev.document_id) if ev else None,
        })

    version = compute_stage4_version(load_stage4_data(db, case.id))
    contradiction_findings = [
        {
            "id": f.id,
            "title": f.title,
            "severity": (f.details or {}).get("severity"),
            "contradiction_type": (f.details or {}).get("contradiction_type"),
            "status": f.status,
            "graph_version": f.graph_version,
            "is_current": f.graph_version == version,
            "explanation": f.explanation,
        }
        for f in _stage4_findings(db, case.id)
        if f.finding_type == "CONTRADICTION"
    ]

    queue = {
        "new_entities": new_entities,
        "potential_duplicates": potential_duplicates,
        "candidate_relationships": candidate_relationships,
        "evidence_claims": evidence_claims,
        "potential_contradictions": contradiction_findings,
    }
    # Claims are confirmed structured data (materialized on acceptance),
    # not decisions — they are listed for review but not "pending".
    queue["total_pending"] = (len(new_entities) + len(potential_duplicates)
                              + len(candidate_relationships))
    return queue


# ----------------------------------------------------------- bulk review

def bulk_review(db: Session, case: Case, current: CurrentUser,
                category: str, action: str, item_ids: list[int]) -> dict:
    """Explicit bulk decision (stage 7): confirm or reject the SELECTED
    items only. There is no automatic bulk-confirm of low-confidence
    candidates — the investigator chooses every id, and the API applies
    exactly the same single-item service calls (same validation, same
    effects, same audit rows) item by item, reporting each result.
    """
    if action not in ("confirm", "reject"):
        raise ApiError("BAD_ACTION", "action must be 'confirm' or 'reject'.", 422)
    if not item_ids:
        raise ApiError("NO_ITEMS", "Select at least one item.", 422)
    if len(set(item_ids)) != len(item_ids):
        raise ApiError("DUPLICATE_IDS", "item_ids contains duplicates.", 422)

    results: list[dict] = []
    applied = 0
    for cid in item_ids:
        try:
            if category == "entity":
                cand = db.get(EntityCandidate, cid)
                if cand is None or cand.case_id != case.id:
                    raise ApiError("ITEM_NOT_FOUND",
                                   f"No entity candidate {cid} in this case.", 404)
                if action == "confirm":
                    document_service.accept_entity_candidate(
                        db, cand.document, cand, current)
                else:
                    document_service.reject_entity_candidate(
                        db, cand.document, cand, current)
            elif category == "relationship":
                rel = db.get(RelationshipCandidate, cid)
                if rel is None or rel.case_id != case.id:
                    raise ApiError("ITEM_NOT_FOUND",
                                   f"No relationship candidate {cid} in this case.", 404)
                if action == "confirm":
                    document_service.accept_relationship_candidate(
                        db, rel.document, rel, current)
                else:
                    document_service.reject_relationship_candidate(
                        db, rel.document, rel, current)
            elif category == "match":
                m = db.get(EntityMatchSuggestion, cid)
                if m is None or m.case_id != case.id:
                    raise ApiError("ITEM_NOT_FOUND",
                                   f"No match suggestion {cid} in this case.", 404)
                if action == "confirm":
                    document_service.accept_match(db, m.candidate.document,
                                                  m, current)
                else:
                    document_service.reject_match(db, m.candidate.document,
                                                  m, current)
            else:
                raise ApiError("BAD_CATEGORY",
                               "category must be entity, relationship or match.", 422)
            results.append({"id": cid, "ok": True})
            applied += 1
        except ApiError as err:
            db.rollback()
            results.append({"id": cid, "ok": False,
                            "error": f"{err.code}: {err.message}"})
    record_audit(db, current, "REVIEW_BULK", "case", str(case.id),
                 {"category": category, "action": action,
                  "requested": len(item_ids), "applied": applied})
    db.commit()
    return {
        "case_id": case.id,
        "category": category,
        "action": action,
        "requested": len(item_ids),
        "applied": applied,
        "results": results,
    }


# ------------------------------------------------------------------- audit

def audit_trail(db: Session, case: Case, limit: int = 200) -> dict:
    """Case-scoped audit trail (read-only view of the platform audit log).

    Every case operation already records its `case_id` in the audit
    metadata; this endpoint filters on that so the trail is strictly
    scoped to the case (no cross-case leakage).
    """
    # The metadata column is JSON (not JSONB), so filter with the `->`
    # operator (works on both) instead of a JSONB containment operator.
    rows = db.execute(
        select(AuditLog).where(
            (AuditLog.resource_type == "case") &
            (AuditLog.resource_id == str(case.id)) |
            (AuditLog.meta["case_id"].as_integer() == case.id)
        ).order_by(AuditLog.id.desc()).limit(limit)
    ).scalars().all()
    user_names = {u.id: u.name for u in db.execute(
        select(User).where(User.id.in_({r.user_id for r in rows
                                        if r.user_id}))).scalars()}
    return {
        "case_id": case.id,
        "count": len(rows),
        "entries": [
            {
                "id": r.id,
                "action": r.action,
                "resource_type": r.resource_type,
                "resource_id": r.resource_id,
                "timestamp": r.timestamp,
                "user": user_names.get(r.user_id),
                "metadata": r.meta,
            }
            for r in rows
        ],
    }


# ------------------------------------------------------------- graph build

def _graph_stats(graph) -> dict:
    """Real structural statistics (stage 7): connected components and
    modularity communities from the confirmed graph itself."""
    g = graph.graph
    components = (len(list(nx.connected_components(g)))
                  if g.number_of_nodes() else 0)
    clusters = analyze_clusters(graph)
    communities = sum(len(c.subgroups) for c in clusters if c.subgroups)
    return {
        "nodes": graph.node_count,
        "edges": graph.edge_count,
        "components": components,
        "clusters": len(clusters),
        "communities": communities,
    }


def build_graph(db: Session, case: Case, current: User) -> dict:
    """Build (recompute) the confirmed NetworkX graph for this case.

    The graph is always derived from confirmed data in the database —
    never hardcoded. Returns node/edge counts + structural stats and the
    graph version so the UI can prove the build came from real case data.
    """
    data = load_stage4_data(db, case.id)
    graph = build_case_graph(data.entities, data.relationships,
                             data.evidence_index, data.accepted_candidates)
    version = compute_graph_version(data.entities, data.relationships)
    stats = _graph_stats(graph)
    record_audit(db, current, "GRAPH_BUILD", "case", str(case.id),
                 metadata={"graph_version": version,
                           "nodes": graph.node_count,
                           "edges": graph.edge_count,
                           "components": stats["components"],
                           "communities": stats["communities"]})
    db.commit()
    return {
        "case_id": case.id,
        "graph_version": version,
        "nodes": graph.node_count,
        "edges": graph.edge_count,
        "stats": stats,
        "insufficient": graph.is_insufficient(),
        "built_at": _now().isoformat(),
        "backend": "networkx (built from confirmed case data)",
    }


def graph_payload(db: Session, case: Case,
                  entity_type: str | None = None,
                  relationship_type: str | None = None,
                  min_confidence: float | None = None,
                  limit: int | None = None) -> dict:
    """Nodes + edges for the graph view; every edge carries its provenance
    (source document, snippet, candidate id) so the graph is never
    detached from evidence.

    Stage 7 filters (server-side, case-scoped): ``entity_type``,
    ``relationship_type``, ``min_confidence`` (0..1) and ``limit`` (max
    nodes, ordered by first entity id — deterministic). The reported
    ``stats`` always describe the FULL confirmed graph; the node/edge
    lists reflect the filters.
    """
    data = load_stage4_data(db, case.id)
    graph = build_case_graph(data.entities, data.relationships,
                             data.evidence_index, data.accepted_candidates)
    version = compute_graph_version(data.entities, data.relationships)
    stats = _graph_stats(graph)

    rel_rows = {r.id: r for r in db.execute(
        select(Relationship).where(
            Relationship.case_id == case.id)).scalars()}
    docs = {d.id: d for d in db.execute(
        select(Document).where(Document.case_id == case.id)).scalars()}

    nodes = []
    for nid, info in graph.nodes.items():
        nodes.append({
            "id": nid,
            "name": info.display_name,
            "type": info.entity_type,
            "entity_ids": info.entity_ids,
            "evidence_count": info.evidence_count,
        })
    edges = []
    for key, info in graph.edges.items():
        meta = {}
        row = rel_rows.get(info.relationship_id)
        if row and row.meta:
            meta = row.meta
        src_doc = docs.get(meta.get("source_document_id")) if meta else None
        edges.append({
            "id": f"r{info.relationship_id}",
            "source": key[0],
            "target": key[1],
            "type": info.relationship_type,
            "confidence": (rel_rows[info.relationship_id].confidence
                           if info.relationship_id in rel_rows else None),
            "verification_status": info.verification_status,
            "evidence_count": info.evidence_count,
            "source_document_id": meta.get("source_document_id"),
            "source_document_name": src_doc.filename if src_doc else None,
            "source_snippet": meta.get("source_snippet"),
            "source_location": meta.get("source_location"),
            "candidate_id": meta.get("candidate_id"),
            "source_evidence_id": meta.get("source_evidence_id"),
            "extraction_method": meta.get("extraction_method"),
        })

    # ---- stage 7 server-side filters ------------------------------------
    if relationship_type:
        edges = [e for e in edges if e["type"] == relationship_type]
    if min_confidence is not None:
        edges = [e for e in edges
                 if e["confidence"] is not None and e["confidence"] >= min_confidence]
    if entity_type:
        nodes = [n for n in nodes if n["type"] == entity_type]
    nodes.sort(key=lambda n: min(n["entity_ids"]))
    if limit and limit > 0:
        nodes = nodes[:limit]
    kept = {n["id"] for n in nodes}
    # edges must stay inside the visible node set (otherwise the client
    # would render dangling edges)
    edges = [e for e in edges if e["source"] in kept and e["target"] in kept]

    return {
        "case_id": case.id,
        "graph_version": version,
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "stats": stats,
        "filters": {
            "entity_type": entity_type,
            "relationship_type": relationship_type,
            "min_confidence": min_confidence,
            "limit": limit,
        },
        "insufficient": graph.is_insufficient(),
    }


# --------------------------------------------------------- run + status

def run_full_analysis(db: Session, case: Case, current: User,
                      audit_action: str = "ANALYSIS_RUN") -> dict:
    """ONE call the case workspace uses to run all intelligence.

    Delegates to the Stage 4 orchestrator (all existing engines — no
    rewrites) and adds analysis_id / timing / graph-count fields. An
    insufficient case returns status "insufficient" (honest 200 with a
    reason) instead of raising, so the workflow UI can show a reason
    banner; the legacy POST /investigation/analyze keeps its 409.

    Stage 7: every run is PERSISTED as a ``CaseAnalysisRun`` — the
    data-version record (analysis_id, per-case version, created_by,
    created_at, input document versions, status, graph version) — and the
    case lifecycle moves ANALYZING -> ANALYSIS_COMPLETE (guarded by the
    state machine; a recalculation may come from STALE instead).
    """
    started = _now()
    t0 = time.monotonic()
    data = load_stage4_data(db, case.id)
    graph = build_case_graph(data.entities, data.relationships,
                             data.evidence_index, data.accepted_candidates)
    nodes, edges = graph.node_count, graph.edge_count

    # lifecycle: READY_FOR_ANALYSIS | STALE -> ANALYZING
    if case.workflow_state in (sm.READY_FOR_ANALYSIS, sm.STALE):
        sm.transition(db, case, sm.ANALYZING)

    result: dict = {}
    status = "completed"
    reason = None
    try:
        result = run_analysis(db, case, current)
        if result and result.get("recomputed") is False and status == "completed":
            status = "no_changes"
    except ApiError as err:
        if err.code == "INSUFFICIENT_CONFIRMED_DATA":
            status = "insufficient"
            reason = err.message
        else:
            run_row = _analysis_run_row(db, case, current, started,
                                        "FAILED", None, nodes, edges, 0,
                                        int((time.monotonic() - t0) * 1000))
            record_audit(db, current, audit_action, "case", str(case.id),
                         metadata={"analysis_id": run_row.analysis_id,
                                   "status": "FAILED",
                                   "error": str(err)[:500]})
            db.commit()
            raise

    completed = _now()
    findings = _stage4_findings(db, case.id)
    hypotheses = _stage4_hypotheses(db, case.id)
    version = compute_stage4_version(data)
    # Staleness is version-based (the documented Stage 4 rule): findings
    # for the current snapshot are current; everything else is stale.
    current_findings = [f for f in findings if f.graph_version == version]
    stale_findings = [f for f in findings if f.graph_version != version]
    input_versions = {str(d.id): d.sha256 for d in db.scalars(
        select(Document).where(Document.case_id == case.id)).all()
        if d.sha256}

    analysis_id = str(uuid.uuid4())
    run_row = _analysis_run_row(db, case, current, started, status, version,
                                nodes, edges, len(current_findings),
                                int((time.monotonic() - t0) * 1000),
                                input_versions, analysis_id)
    case.last_analysis_at = completed
    record_audit(db, current, audit_action, "case", str(case.id),
                 metadata={"analysis_id": analysis_id,
                           "run_version": run_row.version,
                           "status": status,
                           "graph_version": version, "nodes": nodes,
                           "edges": edges, "findings": len(findings),
                           "hypotheses": len(hypotheses)})
    if status in ("completed", "no_changes"):
        sm.transition(db, case, sm.ANALYSIS_COMPLETE)
    db.commit()
    return {
        "analysis_id": analysis_id,
        "version": run_row.version,
        "created_by": current.user.email,
        "input_document_versions": input_versions,
        "case_id": case.id,
        "case_number": case.case_number,
        "status": status,
        "reason": reason,
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "duration_ms": int((time.monotonic() - t0) * 1000),
        "graph_version": version,
        "graph_nodes": nodes,
        "graph_edges": edges,
        "findings_count": len(current_findings),
        "stale_findings": len(stale_findings),
        "hypotheses_count": len(hypotheses),
        "recomputed": result.get("recomputed") if result else None,
        "findings": result.get("findings") if result else None,
        "hypotheses": result.get("hypotheses") if result else None,
    }


def _analysis_run_row(db: Session, case: Case, current: User, started: datetime,
                      status: str, graph_version: str | None,
                      nodes: int, edges: int, findings_count: int,
                      duration_ms: int,
                      input_versions: dict | None = None,
                      analysis_id: str | None = None) -> CaseAnalysisRun:
    """Persist the versioned run record (one row per analysis run)."""
    last = db.execute(
        select(CaseAnalysisRun.version).where(
            CaseAnalysisRun.case_id == case.id).order_by(
            CaseAnalysisRun.version.desc()).limit(1)).scalar()
    row = CaseAnalysisRun(
        analysis_id=analysis_id or str(uuid.uuid4()), case_id=case.id,
        version=(last or 0) + 1, status=status.upper(),
        graph_version=graph_version,
        input_document_versions=input_versions,
        findings_count=findings_count, duration_ms=duration_ms,
        created_by=current.user.id, created_at=started)
    db.add(row)
    db.flush()
    return row


def recalculate(db: Session, case: Case, current: User) -> dict:
    """[RECALCULATE] — re-run the intelligence after the case went STALE.

    Only valid while the analysis is actually stale (confirmed data moved
    since the last run); anything else gets 409 NOT_STALE so the UI never
    shows a recalculation that would be a no-op.
    """
    st = _stage4_state(db, case)
    if st["state"] not in ("stale", "not-analyzed"):
        raise ApiError("NOT_STALE",
                       "Nothing to recalculate — the analysis is "
                       f"{st['state']}.", 409)
    return run_full_analysis(db, case, current, audit_action="RECALCULATE")


def lifecycle(db: Session, case: Case) -> dict:
    """The case's position in the documented lifecycle (dashboard strip)."""
    return {
        "case_id": case.id,
        "workflow_state": case.workflow_state,
        "allowed_next": sm.allowed_next(case.workflow_state),
        "happy_path": list(sm.HAPPY_PATH),
        "last_analysis_at": case.last_analysis_at,
        "administrative_status": case.status,
    }
