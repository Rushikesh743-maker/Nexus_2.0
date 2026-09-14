"""Stage 4 orchestration: analysis run, findings, hypotheses, reviews.

Reuses the Stage 3 ``graph_finding`` table for all Stage 4 finding types
(CONTRADICTION, TIMELINE_INSIGHT, GEO_INSIGHT, INVESTIGATION_GAP); the
only new table is ``investigation_hypothesis``. Nothing is ever deleted:
re-analyses add/refresh versioned rows and mark old ones stale; reviews
and dismissals are audit-logged investigator actions.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth_service import record_audit
from ...core.errors import ApiError, not_found
from ...models import (Case, Document, Entity, Evidence, EvidenceClaim,
                       GraphFinding, InvestigationHypothesis, Location,
                       Relationship, User)
from .claim_contradictions import detect_claim_contradictions
from .contradiction_engine import detect_contradictions
from .data import compute_stage4_version, load_stage4_data
from .gap_engine import detect_gaps, METHOD as GAP_METHOD
from .geospatial_engine import (METHOD as GEO_METHOD, analyze_geospatial)
from .hypothesis_engine import (METHOD as HYPO_METHOD, score_spec,
                                generate_hypotheses)
from .timeline_engine import METHOD as TIMELINE_METHOD, analyze_timeline

CONTRADICTION_METHOD = ("contradiction-engine v2 (R1 min-travel-time at "
                        "100 km/h; R2 identical-timestamp overlap; "
                        "R3 mutual OWNS; R4 EVIDENCE_CONTRADICTION on "
                        "structured claims [stage 5]; confirmed records "
                        "only)")
STAGE4_FINDING_TYPES = ("CONTRADICTION", "TIMELINE_INSIGHT", "GEO_INSIGHT",
                        "INVESTIGATION_GAP")
STAGE3_FINDING_TYPES = ("HIDDEN_CONNECTION", "BRIDGE_ENTITY",
                        "CROSS_CASE_CONNECTION", "NETWORK_CLUSTER",
                        "HIGH_CONNECTIVITY")
FINDING_TYPE_METHOD = {
    "CONTRADICTION": CONTRADICTION_METHOD,
    "TIMELINE_INSIGHT": TIMELINE_METHOD,
    "GEO_INSIGHT": GEO_METHOD,
    "INVESTIGATION_GAP": GAP_METHOD,
}


# ------------------------------------------------------------------ helpers
def _finding_payload(f: GraphFinding, version: str) -> dict:
    return {
        "id": f.id,
        "case_id": f.case_id,
        "finding_type": f.finding_type,
        "title": f.title,
        "summary": f.summary,
        "explanation": f.explanation or [],
        "details": f.details or {},
        "involved_entity_ids": f.involved_entity_ids or [],
        "supporting_relationship_ids": f.supporting_relationship_ids or [],
        "supporting_evidence_ids": f.supporting_evidence_ids or [],
        "related_case_ids": f.related_case_ids or [],
        "analysis_method": f.analysis_method,
        "graph_version": f.graph_version,
        "stale": f.graph_version != version,
        "status": f.status,
        "reviewed_by_name": f.reviewer.name if f.reviewer else None,
        "reviewed_at": f.reviewed_at.isoformat() if f.reviewed_at else None,
        "review_note": f.review_note,
        "created_at": f.created_at.isoformat(),
    }


def _hypothesis_payload(h: InvestigationHypothesis, version: str) -> dict:
    return {
        "id": h.id,
        "case_id": h.case_id,
        "title": h.title,
        "description": h.description,
        "hypothesis_type": h.hypothesis_type,
        "involved_entity_ids": h.involved_entity_ids or [],
        "supporting_relationship_ids": h.supporting_relationship_ids or [],
        "supporting_evidence_ids": h.supporting_evidence_ids or [],
        "contradicting_evidence_ids": h.contradicting_evidence_ids or [],
        "supporting_finding_ids": h.supporting_finding_ids or [],
        "contradiction_ids": h.contradiction_ids or [],
        "analytical_score": h.analytical_score,
        "confidence_band": h.confidence_band,
        "score_components": h.score_components or {},
        "explanation": h.explanation or [],
        "analysis_method": h.analysis_method,
        "graph_version": h.graph_version,
        "stale": bool(h.graph_version) and h.graph_version != version,
        "status": h.status,
        "reviewed_by_name": h.reviewer.name if h.reviewer else None,
        "reviewed_at": h.reviewed_at.isoformat() if h.reviewed_at else None,
        "review_note": h.review_note,
        "created_at": h.created_at.isoformat(),
        "updated_at": h.updated_at.isoformat(),
    }


def _require_case(db: Session, case_id: int) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        not_found("CASE_NOT_FOUND", f"Case {case_id} not found.")
    return case


def _stage4_findings(db: Session, case_id: int) -> list[GraphFinding]:
    return db.execute(
        select(GraphFinding).where(
            GraphFinding.case_id == case_id,
            GraphFinding.finding_type.in_(STAGE4_FINDING_TYPES))
        .order_by(GraphFinding.id)
    ).scalars().all()


def _stage4_hypotheses(db: Session, case_id: int) -> list[InvestigationHypothesis]:
    return db.execute(
        select(InvestigationHypothesis)
        .where(InvestigationHypothesis.case_id == case_id)
        .order_by(InvestigationHypothesis.id)
    ).scalars().all()


# ------------------------------------------------------------------ analysis
def run_analysis(db: Session, case: Case, current_user: User) -> dict:
    data = load_stage4_data(db, case.id)
    version = compute_stage4_version(data)

    if not data.entities or not data.relationships:
        record_audit(db, current_user, "INVESTIGATION_ANALYSIS_STARTED",
                     "case", str(case.id),
                     metadata={"reason": "insufficient_confirmed_data"})
        record_audit(db, current_user, "INVESTIGATION_ANALYSIS_FAILED",
                     "case", str(case.id),
                     metadata={"reason": "insufficient_confirmed_data",
                               "entities": len(data.entities),
                               "relationships": len(data.relationships)})
        db.commit()
        raise ApiError(
            "INSUFFICIENT_CONFIRMED_DATA",
            f"Case {case.case_number} has no confirmed graph data to "
            f"analyze ({len(data.entities)} entities, "
            f"{len(data.relationships)} relationships).", 409)

    # idempotent: a run exists for this exact snapshot -> nothing to do
    existing = [f for f in _stage4_findings(db, case.id)
                if f.graph_version == version]
    if existing:
        record_audit(db, current_user, "INVESTIGATION_ANALYSIS_COMPLETED",
                     "case", str(case.id),
                     metadata={"recomputed": False, "graph_version": version,
                               "findings": len(existing),
                               "hypotheses": len(_stage4_hypotheses(db, case.id))})
        db.commit()
        payload = _current_results(db, case, version)
        payload["recomputed"] = False
        return payload

    record_audit(db, current_user, "INVESTIGATION_ANALYSIS_STARTED",
                 "case", str(case.id),
                 metadata={"stage4_version": version,
                           "entities": len(data.entities),
                           "relationships": len(data.relationships),
                           "evidence": len(data.evidence),
                           "events": len(data.events),
                           "locations": len(data.locations)})

    try:
        # --- engines (pure, confirmed data only)
        contradictions, contradiction_insufficient = detect_contradictions(data)
        # stage 5: R4 evidence contradiction on structured claims (same
        # Confirmed-only guarantee — claims exist only post-acceptance)
        claim_contradictions, claim_insufficient = detect_claim_contradictions(data)
        contradiction_insufficient.update(claim_insufficient)
        contradictions.extend(claim_contradictions)
        timeline_results, timeline_meta = analyze_timeline(data)
        geo_results, _obs, geo_meta = analyze_geospatial(data)
        timeline_gap_results = [r for r in timeline_results
                                if r.timeline_type == "TIMELINE_GAP"]
        gaps = detect_gaps(data, timeline_gap_results)

        # --- persist findings (additive, versioned)
        new_findings: list[GraphFinding] = []
        for c in contradictions:
            row = GraphFinding(
                case_id=case.id, graph_version=version,
                finding_type="CONTRADICTION", title=c.title,
                summary=c.summary, explanation=c.explanation,
                details={"contradiction_type": c.contradiction_type,
                         "severity": c.severity, **c.details},
                involved_entity_ids=c.involved_entity_ids,
                supporting_relationship_ids=c.involved_relationship_ids,
                supporting_evidence_ids=c.supporting_evidence_ids,
                analysis_method=CONTRADICTION_METHOD)
            new_findings.append(row)
        for r in timeline_results:
            new_findings.append(GraphFinding(
                case_id=case.id, graph_version=version,
                finding_type="TIMELINE_INSIGHT", title=r.title,
                summary=r.summary, explanation=r.explanation,
                details={"timeline_type": r.timeline_type,
                         "interval_minutes": r.interval_minutes,
                         **r.details},
                involved_entity_ids=r.entity_ids,
                analysis_method=TIMELINE_METHOD))
        for r in geo_results:
            new_findings.append(GraphFinding(
                case_id=case.id, graph_version=version,
                finding_type="GEO_INSIGHT", title=r.title,
                summary=r.summary, explanation=r.explanation,
                details={"geo_type": r.geo_type,
                         "distance_km": r.distance_km,
                         "time_difference_minutes": r.time_difference_minutes,
                         "threshold": r.threshold, **r.details},
                involved_entity_ids=r.entity_ids,
                supporting_relationship_ids=r.relationship_ids,
                analysis_method=GEO_METHOD))
        for g in gaps:
            new_findings.append(GraphFinding(
                case_id=case.id, graph_version=version,
                finding_type="INVESTIGATION_GAP", title=g.title,
                summary=g.summary, explanation=g.explanation,
                details={"gap_type": g.gap_type, **g.details},
                involved_entity_ids=g.involved_entity_ids,
                supporting_relationship_ids=g.supporting_relationship_ids,
                analysis_method=GAP_METHOD))
        for row in new_findings:
            db.add(row)
        db.flush()  # ids for the hypothesis linkage

        # --- hypotheses (deterministic, bounded, versioned)
        contradiction_ids_by_title = {f.title: f.id for f in new_findings
                                       if f.finding_type == "CONTRADICTION"}
        specs = generate_hypotheses(data, contradictions)
        # link each generated-contradiction hypothesis to its finding
        # (the engine sets explanation_prefix "Detected contradiction:
        # <title>"; recover the title for a stable id link)
        for spec in specs:
            if spec.hypothesis_type != "GENERATED_CONTRADICTION":
                continue
            prefix = spec.explanation_prefix.removeprefix(
                "Detected contradiction: ").strip()
            if prefix in contradiction_ids_by_title:
                spec.contradiction_ids = [contradiction_ids_by_title[prefix]]

        new_hyps: list[InvestigationHypothesis] = []
        existing_titles = {(h.title, h.hypothesis_type)
                           for h in _stage4_hypotheses(db, case.id)}
        for spec in specs:
            if (spec.title, spec.hypothesis_type) in existing_titles:
                continue  # idempotent: generated once per case
            scored = score_spec(data, spec)
            new_hyps.append(InvestigationHypothesis(
                case_id=case.id, title=spec.title,
                description=spec.description,
                hypothesis_type=spec.hypothesis_type,
                involved_entity_ids=spec.involved_entity_ids,
                supporting_relationship_ids=spec.supporting_relationship_ids,
                supporting_evidence_ids=spec.supporting_evidence_ids,
                contradicting_evidence_ids=spec.contradicting_evidence_ids,
                supporting_finding_ids=spec.supporting_finding_ids,
                contradiction_ids=spec.contradiction_ids,
                analytical_score=scored.analytical_score,
                confidence_band=scored.confidence_band,
                score_components=scored.score_components,
                explanation=scored.explanation,
                analysis_method=HYPO_METHOD, graph_version=version,
                status="ACTIVE"))
            db.add(new_hyps[-1])
        db.commit()
    except Exception as exc:
        db.rollback()
        record_audit(db, current_user, "INVESTIGATION_ANALYSIS_FAILED",
                     "case", str(case.id),
                     metadata={"error": str(exc)[:300],
                               "stage4_version": version})
        db.commit()
        raise ApiError("INVESTIGATION_ANALYSIS_FAILED",
                       "Investigation analysis failed. Check the server "
                       "logs.", 500,
                       details={"reason": str(exc)[:300]}) from exc

    # --- detection audits (per-finding, as documented)
    for f in new_findings:
        if f.finding_type == "CONTRADICTION":
            record_audit(db, current_user, "CONTRADICTION_DETECTED",
                         "graph_finding", str(f.id),
                         metadata={"case_id": case.id,
                                   "contradiction_type":
                                       (f.details or {}).get("contradiction_type"),
                                   "title": f.title})
        elif f.finding_type == "INVESTIGATION_GAP":
            record_audit(db, current_user, "INVESTIGATION_GAP_DETECTED",
                         "graph_finding", str(f.id),
                         metadata={"case_id": case.id,
                                   "gap_type": (f.details or {}).get("gap_type"),
                                   "title": f.title})
    record_audit(db, current_user, "TIMELINE_ANALYSIS_COMPLETED",
                 "case", str(case.id),
                 metadata={"case_id": case.id,
                           "findings": sum(1 for f in new_findings
                                           if f.finding_type == "TIMELINE_INSIGHT"),
                           "events_total": timeline_meta["events_total"],
                           "events_with_timestamp":
                               timeline_meta["events_with_timestamp"]})
    record_audit(db, current_user, "GEO_ANALYSIS_COMPLETED",
                 "case", str(case.id),
                 metadata={"case_id": case.id,
                           "findings": sum(1 for f in new_findings
                                           if f.finding_type == "GEO_INSIGHT"),
                           "observations": geo_meta["observations"],
                           "location_data_insufficient":
                               geo_meta["location_data_insufficient"]})
    for h in new_hyps:
        record_audit(db, current_user, "HYPOTHESIS_GENERATED",
                     "investigation_hypothesis", str(h.id),
                     metadata={"case_id": case.id, "title": h.title,
                               "analytical_score": h.analytical_score,
                               "confidence_band": h.confidence_band})
    from .evidence_impact import summary_payload as _impact
    impact_summary = _impact(data, db)
    record_audit(db, current_user, "EVIDENCE_IMPACT_ANALYZED",
                 "case", str(case.id),
                 metadata={"case_id": case.id,
                           "evidence_count": impact_summary["evidence_count"],
                           "distribution": impact_summary["distribution"]})

    record_audit(db, current_user, "INVESTIGATION_ANALYSIS_COMPLETED",
                 "case", str(case.id),
                 metadata={"recomputed": True, "stage4_version": version,
                           "findings": len(new_findings),
                           "by_type": {t: sum(1 for f in new_findings
                                               if f.finding_type == t)
                                       for t in STAGE4_FINDING_TYPES},
                           "hypotheses_new": len(new_hyps),
                           "hypotheses_total":
                               len(_stage4_hypotheses(db, case.id))})
    db.commit()

    payload = _current_results(db, case, version)
    payload["recomputed"] = True
    payload["states"] = {
        "timeline": timeline_meta,
        "geospatial": geo_meta,
        "contradictions": {"insufficient_pairs": contradiction_insufficient},
    }
    return payload


def _current_results(db: Session, case: Case, version: str) -> dict:
    findings = _stage4_findings(db, case.id)
    hyps = _stage4_hypotheses(db, case.id)
    current = [f for f in findings if f.graph_version == version]
    return {
        "graph_version": version,
        "findings": [_finding_payload(f, version) for f in current],
        "stale_findings": [_finding_payload(f, version) for f in findings
                           if f.graph_version != version],
        "hypotheses": [_hypothesis_payload(h, version) for h in hyps],
        "analyzed": bool(current),
    }


# ------------------------------------------------------------------ listings
def list_findings(db: Session, case: Case, include_stale: bool = True) -> dict:
    version = compute_stage4_version(load_stage4_data(db, case.id))
    rows = _stage4_findings(db, case.id)
    order = {t: i for i, t in enumerate(STAGE4_FINDING_TYPES)}
    rows.sort(key=lambda f: (0 if f.graph_version == version else 1,
                             order.get(f.finding_type, 9), f.id))
    current = [_finding_payload(f, version) for f in rows
               if f.graph_version == version]
    stale = [_finding_payload(f, version) for f in rows
             if f.graph_version != version]
    return {"graph_version": version,
            "current_findings": current,
            "stale_findings": stale if include_stale else [],
            "analyzed": bool(current)}


def list_findings_by_type(db: Session, case: Case, finding_type: str,
                          include_stale: bool = True) -> dict:
    if finding_type not in STAGE4_FINDING_TYPES:
        raise ApiError("INVALID_FINDING_TYPE",
                       f"finding_type must be one of {STAGE4_FINDING_TYPES}.",
                       400)
    all_ = list_findings(db, case, include_stale=include_stale)
    return {**all_,
            "current_findings": [f for f in all_["current_findings"]
                                 if f["finding_type"] == finding_type],
            "stale_findings": [f for f in all_["stale_findings"]
                               if f["finding_type"] == finding_type]}


# ------------------------------------------------------------------ P2-B

def _entity_ref(e: Entity) -> dict:
    return {"id": e.id, "entity_type": e.entity_type,
            "canonical_name": e.canonical_name}


def _document_names(db: Session, doc_ids: list[int]) -> dict[int, str]:
    if not doc_ids:
        return {}
    rows = db.scalars(select(Document).where(Document.id.in_(doc_ids))).all()
    return {d.id: d.filename for d in rows}


def finding_evidence_chain(db: Session, case: Case, finding_id: int) -> dict:
    """Phase 2 (work item B): resolve a finding to its full evidence chain.

    A finding is never shown without its chain when the chain exists: the
    referenced entity / relationship / evidence ids are resolved to their
    confirmed rows plus provenance (source document, page/line/row/column
    location, snippet). When nothing can be linked the response says so
    explicitly (``complete=False`` + a message in ``missing``) instead of
    presenting an empty box. Referenced ids that no longer resolve are
    listed in ``missing`` — a chain is never silently incomplete.
    """
    f = db.get(GraphFinding, finding_id)
    if f is None or f.case_id != case.id:
        not_found("FINDING_NOT_FOUND",
                  f"Finding {finding_id} not found in case {case.id}.")
    version = compute_stage4_version(load_stage4_data(db, case.id))

    entity_ids = list(dict.fromkeys(f.involved_entity_ids or []))
    rel_ids = list(dict.fromkeys(f.supporting_relationship_ids or []))
    ev_ids = list(dict.fromkeys(f.supporting_evidence_ids or []))

    entities = {}
    if entity_ids:
        entities = {e.id: e for e in
                    db.scalars(select(Entity).where(
                        Entity.id.in_(entity_ids))).all()}
    rels = {}
    if rel_ids:
        rels = {r.id: r for r in
                db.scalars(select(Relationship).where(
                    Relationship.id.in_(rel_ids))).all()}
    evids = {}
    if ev_ids:
        evids = {e.id: e for e in
                 db.scalars(select(Evidence).where(
                     Evidence.id.in_(ev_ids))).all()}

    missing: list[str] = []
    for i in entity_ids:
        if i not in entities:
            missing.append(f"entity {i} is referenced but no longer exists")
    for i in rel_ids:
        if i not in rels:
            missing.append(f"relationship {i} is referenced but no longer exists")
    for i in ev_ids:
        if i not in evids:
            missing.append(f"evidence {i} is referenced but no longer exists")

    # claims under the finding's evidence rows
    claims: dict[int, list[EvidenceClaim]] = {}
    if evids:
        crows = db.scalars(select(EvidenceClaim).where(
            EvidenceClaim.evidence_id.in_(list(evids)))).all()
        for c in crows:
            claims.setdefault(c.evidence_id, []).append(c)

    # every entity id the chain must name: involved + relationship
    # endpoints + claim subjects/objects
    ent_ids = set(entity_ids)
    for r in rels.values():
        ent_ids.add(r.source_entity_id)
        ent_ids.add(r.target_entity_id)
    for c in (c for cs in claims.values() for c in cs):
        if c.subject_entity_id:
            ent_ids.add(c.subject_entity_id)
        if c.object_entity_id:
            ent_ids.add(c.object_entity_id)
    ent_map = ({e.id: e for e in
                db.scalars(select(Entity).where(
                    Entity.id.in_(sorted(ent_ids)))).all()}
               if ent_ids else {})

    doc_ids = {e.document_id for e in evids.values() if e.document_id}
    doc_ids |= {m for m in
                ((r.meta or {}).get("source_document_id")
                 for r in rels.values()) if m}
    doc_names = _document_names(db, sorted(doc_ids))

    loc_ids = {c.location_id for c in
               (c for cs in claims.values() for c in cs)
               if c.location_id}
    loc_names = ({l.id: l.name for l in
                  db.scalars(select(Location).where(
                      Location.id.in_(sorted(loc_ids)))).all()}
                 if loc_ids else {})

    chain_entities = [_entity_ref(entities[i]) for i in entity_ids
                      if i in entities]
    chain_rels = []
    for i in rel_ids:
        r = rels.get(i)
        if not r:
            continue
        meta = r.meta or {}
        prov_doc = meta.get("source_document_id")
        chain_rels.append({
            "id": r.id,
            "relationship_type": r.relationship_type,
            "confidence": r.confidence,
            "source": (_entity_ref(ent_map[r.source_entity_id])
                       if r.source_entity_id in ent_map else None),
            "target": (_entity_ref(ent_map[r.target_entity_id])
                       if r.target_entity_id in ent_map else None),
            "provenance": {
                "document_id": prov_doc,
                "document": doc_names.get(prov_doc),
                "location": meta.get("source_location"),
                "snippet": meta.get("source_snippet"),
                "extraction_method": meta.get("extraction_method"),
                "evidence_id": meta.get("source_evidence_id"),
            },
        })

    chain_evidence = []
    for i in ev_ids:
        ev = evids.get(i)
        if not ev:
            continue
        ev_claims = []
        for c in claims.get(i, []):
            subj = ent_map.get(c.subject_entity_id)
            obj = ent_map.get(c.object_entity_id)
            ev_claims.append({
                "id": c.id,
                "predicate": c.predicate,
                "object_value": c.object_value,
                "object_entity": (_entity_ref(obj) if obj else None),
                "event_time": (c.event_time.isoformat()
                               if c.event_time else None),
                "original_text": c.original_text,
                "language": c.language,
                "location": loc_names.get(c.location_id),
            })
        chain_evidence.append({
            "id": ev.id,
            "evidence_type": ev.evidence_type,
            "description": ev.description,
            "confidence": ev.confidence,
            "document_id": ev.document_id,
            "document": doc_names.get(ev.document_id) if ev.document_id else None,
            "claims": ev_claims,
        })

    complete = bool(chain_entities or chain_rels or chain_evidence)
    if not complete and not missing:
        missing.append(
            "this finding links no entities, relationships, or evidence "
            "rows — it is an analytical result without a direct evidence "
            "chain in the current data")

    return {
        "finding": _finding_payload(f, version),
        "current_graph_version": version,
        "evidence_chain": {
            "complete": complete,
            "entities": chain_entities,
            "relationships": chain_rels,
            "evidence": chain_evidence,
            "missing": missing,
        },
    }


def list_hypotheses(db: Session, case: Case,
                    include_stale: bool = True) -> dict:
    version = compute_stage4_version(load_stage4_data(db, case.id))
    hyps = _stage4_hypotheses(db, case.id)
    hyps.sort(key=lambda h: (0 if not h.graph_version
                             or h.graph_version == version else 1,
                             -h.analytical_score, h.id))
    if not include_stale:
        hyps = [h for h in hyps
                if not h.graph_version or h.graph_version == version]
    return {"graph_version": version,
            "hypotheses": [_hypothesis_payload(h, version) for h in hyps]}


# ------------------------------------------------------------------ reviews
def review_finding(db: Session, case: Case, finding_id: int,
                   current_user: User, action: str, note: str | None) -> dict:
    from ..graph_intelligence.finding_service import (apply_review,
                                                      require_finding)
    finding = require_finding(db, case.id, finding_id)
    if finding.finding_type not in STAGE4_FINDING_TYPES:
        raise ApiError("INVALID_FINDING_TYPE",
                       "This finding is not an investigation-intelligence "
                       "finding.", 400)
    return apply_review(db, case, finding, current_user, action, note)


def review_hypothesis(db: Session, case: Case, hypothesis_id: int,
                      current_user: User, action: str,
                      note: str | None) -> dict:
    if action not in ("reviewed", "dismissed"):
        raise ApiError("INVALID_REVIEW_ACTION",
                       "action must be 'reviewed' or 'dismissed'.", 400)
    h = db.get(InvestigationHypothesis, hypothesis_id)
    if h is None or h.case_id != case.id:
        not_found("HYPOTHESIS_NOT_FOUND",
                  f"Hypothesis {hypothesis_id} not found in this case.")
    if h.status != "ACTIVE":
        raise ApiError("HYPOTHESIS_REVIEW_NOT_ALLOWED",
                       f"This hypothesis is already {h.status}; it cannot "
                       f"be re-reviewed.", 409)
    h.status = "REVIEWED" if action == "reviewed" else "DISMISSED"
    h.reviewed_by = current_user.user.id
    h.reviewed_at = datetime.now(timezone.utc)
    h.review_note = (note or "")[:255] or None
    db.commit()
    record_audit(db, current_user,
                 "HYPOTHESIS_REVIEWED" if action == "reviewed"
                 else "HYPOTHESIS_DISMISSED",
                 "investigation_hypothesis", str(h.id),
                 metadata={"case_id": case.id, "title": h.title,
                           "status": h.status, "note": h.review_note})
    version = compute_stage4_version(load_stage4_data(db, case.id))
    return _hypothesis_payload(h, version)


# ------------------------------------------------- investigator hypothesis
def create_hypothesis(db: Session, case: Case, current_user: User,
                      payload: dict) -> dict:
    data = load_stage4_data(db, case.id)
    version = compute_stage4_version(data)

    title = (payload.get("title") or "").strip()
    if not title or len(title) > 255:
        raise ApiError("INVALID_HYPOTHESIS",
                       "title is required (max 255 chars).", 400)

    valid_entities = {e.id for e in data.entities}
    valid_rels = {r.id for r in data.relationships}
    valid_ev = {v.id for v in data.evidence}

    entities = payload.get("involved_entity_ids") or []
    rels = payload.get("supporting_relationship_ids") or []
    evs = payload.get("supporting_evidence_ids") or []
    con_evs = payload.get("contradicting_evidence_ids") or []
    findings_ids = payload.get("supporting_finding_ids") or []
    if any(i not in valid_entities for i in entities):
        raise ApiError("ENTITY_NOT_CONFIRMED",
                       "involved_entity_ids must be confirmed entities "
                       "of this case.", 400)
    if any(i not in valid_rels for i in rels):
        raise ApiError("RELATIONSHIP_NOT_FOUND",
                       "supporting_relationship_ids must be confirmed "
                       "relationships of this case.", 400)
    if any(i not in valid_ev for i in evs + con_evs):
        raise ApiError("EVIDENCE_NOT_FOUND",
                       "evidence ids must exist in this case.", 400)
    if any(i not in {f.id for f in _stage4_findings(db, case.id)}
           for i in findings_ids):
        raise ApiError("FINDING_NOT_FOUND",
                       "supporting_finding_ids must be investigation "
                       "findings of this case.", 400)

    # data-backed extension of the cited records (documented): the
    # hypotheses score also counts evidence directly linked to the
    # involved entities and relationships touching them
    extra_ev: set[int] = set(evs)
    for ent_id in entities:
        for cid in data.accepted_candidates.get(ent_id, []):
            extra_ev.update(data.evidence_index.get(f"candidate:{cid}", []))
    extra_rels: set[int] = set(rels)
    for r in data.relationships:
        if r.source_entity_id in set(entities) or \
                r.target_entity_id in set(entities):
            extra_rels.add(r.id)

    from .hypothesis_engine import HypothesisSpec
    spec = HypothesisSpec(
        title=title[:255],
        description=(payload.get("description") or "")[:2000] or None,
        hypothesis_type="INVESTIGATOR",
        involved_entity_ids=sorted(set(entities)),
        supporting_relationship_ids=sorted(extra_rels),
        supporting_evidence_ids=sorted(extra_ev),
        contradicting_evidence_ids=sorted(set(con_evs)),
        supporting_finding_ids=sorted(set(findings_ids)))
    scored = score_spec(data, spec)
    h = InvestigationHypothesis(
        case_id=case.id, title=spec.title,
        description=spec.description,
        hypothesis_type=spec.hypothesis_type,
        involved_entity_ids=spec.involved_entity_ids,
        supporting_relationship_ids=spec.supporting_relationship_ids,
        supporting_evidence_ids=spec.supporting_evidence_ids,
        contradicting_evidence_ids=spec.contradicting_evidence_ids,
        supporting_finding_ids=spec.supporting_finding_ids,
        contradiction_ids=spec.contradiction_ids,
        analytical_score=scored.analytical_score,
        confidence_band=scored.confidence_band,
        score_components=scored.score_components,
        explanation=scored.explanation,
        analysis_method=HYPO_METHOD, graph_version=version,
        status="ACTIVE")
    db.add(h)
    db.commit()
    db.refresh(h)
    record_audit(db, current_user, "HYPOTHESIS_CREATED",
                 "investigation_hypothesis", str(h.id),
                 metadata={"case_id": case.id, "title": h.title,
                           "analytical_score": h.analytical_score,
                           "confidence_band": h.confidence_band})
    return _hypothesis_payload(h, version)
