"""Copilot API (stage 5).

Routes (JWT-authenticated, case-scoped, audited):

    GET  /copilot                                   platform capability statement
    GET  /cases/{case_id}/copilot/status            provider status (honest)
    GET  /cases/{case_id}/copilot/suggestions       data-driven follow-ups
    POST /cases/{case_id}/copilot/ask               answer a question (INVESTIGATOR+)
    POST /cases/{case_id}/copilot/impact            simulate evidence removal (INVESTIGATOR+)
    POST /cases/{case_id}/copilot/nlq/search        multilingual search w/ interpretation
    GET  /cases/{case_id}/search                    multilingual search (confirmed data)

Authorization: ``ask`` and ``impact`` require INVESTIGATOR or higher —
``ask`` can trigger the impact simulator, and ``impact`` runs a what-if, so
the write/analysis floor applies. ``status``/``suggestions``/``search``
work for any authenticated user (the case-read floor, same as entities).

The copilot answers only from CONFIRMED case records, cites every record it
mentions, computes confidence from retrieved data, and — when an LLM
provider is configured — only lets the model write prose that is validated
against the deterministic answer (see ``docs/COPILOT.md``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...schemas.v1 import (CopilotAnswerOut, CopilotImpactIn,
                           CopilotQuestionIn, CopilotSearchIn,
                           CopilotSearchOut, CopilotStatus,
                           CopilotStatusOut, CopilotSuggestionsOut)
from ...security.rbac import CurrentUser, get_current_user, require_roles
from ...services import copilot
from ...services.copilot.intents import CopilotQuestionParser
from ...services.copilot.search import search_case
from ...services.case_access import require_case_access
from .deps import get_db_checked

router = APIRouter(tags=["copilot"])


# ------------------------------------------------------------------ platform
@router.get("/copilot", response_model=CopilotStatus,
            summary="Copilot capability status")
def copilot_status() -> CopilotStatus:
    return CopilotStatus(
        capability="investigator copilot",
        stage="stage-5",
        message=("The case-scoped investigator copilot is live: "
                 "natural-language questions over a case's CONFIRMED records "
                 "(entities, relationships, evidence, timeline, findings, "
                 "hypotheses, structured claims), with citations, computed "
                 "confidence and multilingual search. An optional Gemini "
                 "provider can write answer prose — only validated prose; "
                 "data, citations and confidence are always deterministic. "
                 "Operation Meridian corpus questions remain served by the "
                 "analysis engine's NLQ (POST /api/query)."),
        available=[
            "case-scoped natural-language questions (12 intents)",
            "citations to the exact confirmed records behind every answer",
            "computed confidence with a documented basis",
            "multilingual search over confirmed data (EN/HI/MR/UR)",
            "impact simulation (in-memory, simulation_only)",
            "optional validated Gemini prose provider (env-configured)",
        ],
        planned=[
            "multi-turn investigation planning",
            "hypothesis rebuttal dialogue",
        ],
    )


# ------------------------------------------------------------------ case-scoped
@router.get("/cases/{case_id}/copilot/status",
            response_model=CopilotStatusOut,
            summary="Provider status (which providers are active, honestly)")
def copilot_case_status(case_id: int,
                        db: Session = Depends(get_db_checked),
                        current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    return copilot.provider_status(case)


@router.get("/cases/{case_id}/copilot/suggestions",
            response_model=CopilotSuggestionsOut,
            summary="Data-driven suggested questions for this case")
def copilot_case_suggestions(case_id: int,
                             db: Session = Depends(get_db_checked),
                             current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    ctx = copilot.load_case_context(db, case)
    from ...services.case_analysis import analysis_block
    return CopilotSuggestionsOut(
        suggestions=copilot.suggest_questions(ctx),
        analysis=analysis_block(db, case))


@router.post("/cases/{case_id}/copilot/ask",
             response_model=CopilotAnswerOut,
             summary="Ask a natural-language question about the case "
                     "(INVESTIGATOR+)")
def copilot_ask(case_id: int,
                body: CopilotQuestionIn,
                db: Session = Depends(get_db_checked),
                current: CurrentUser = Depends(
                    require_roles("INVESTIGATOR", "SUPERVISOR", "ADMIN"))):
    case = require_case_access(db, case_id, current)
    answer = copilot.ask_case(db, case, body.question, current)
    out = answer.to_dict()
    from ...services.case_analysis import analysis_block
    out["graph_version"] = out.get("data", {}).get("graph_version")
    out["analysis"] = analysis_block(db, case)
    return CopilotAnswerOut(**out)


@router.post("/cases/{case_id}/copilot/impact",
             response_model=CopilotAnswerOut,
             summary="Simulate removing an evidence record (INVESTIGATOR+; "
                     "simulation only, no stored data is modified)")
def copilot_impact(case_id: int,
                   body: CopilotImpactIn,
                   db: Session = Depends(get_db_checked),
                   current: CurrentUser = Depends(
                       require_roles("INVESTIGATOR", "SUPERVISOR", "ADMIN"))):
    case = require_case_access(db, case_id, current)
    ctx = copilot.load_case_context(db, case)
    from ...services.copilot.intents import Intent
    from ...services.copilot.providers.deterministic import (
        DeterministicProvider)
    from ...services.auth_service import record_audit
    intent = Intent(
        "impact_simulation",
        f"Simulate removing evidence {body.evidence_id} from the confirmed "
        "graph (simulation only — nothing is changed)",
        {"evidence_id": body.evidence_id}, 0.9)
    answer = DeterministicProvider().answer(ctx, intent)
    answer.data["question"] = f"what happens if we remove E{body.evidence_id}"
    from ...services.case_analysis import analysis_block
    from ...services.investigation_intelligence.data import compute_stage4_version
    answer.data["graph_version"] = compute_stage4_version(ctx.data)
    record_audit(db, current, "copilot.impact", resource_type="case",
                 resource_id=str(case.id),
                 metadata={"evidence_id": body.evidence_id,
                           "simulation_only": True,
                           "status": answer.status,
                           "citation_count": len(answer.citations)})
    out = answer.to_dict()
    out["graph_version"] = out.get("data", {}).get("graph_version")
    out["analysis"] = analysis_block(db, case)
    return CopilotAnswerOut(**out)


@router.post("/cases/{case_id}/copilot/nlq/search",
             response_model=CopilotSearchOut,
             summary="Multilingual search over confirmed records "
                     "(case-scoped)")
def copilot_nlq_search(case_id: int,
                       body: CopilotSearchIn,
                       db: Session = Depends(get_db_checked),
                       current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    ctx = copilot.load_case_context(db, case)
    # keep the NLQ-layer contract: the question is interpreted first
    CopilotQuestionParser(ctx).parse(f"search for {body.query}")
    from ...services.case_analysis import analysis_block
    out = search_case(ctx, body.query, k=body.k)
    out["analysis"] = analysis_block(db, case)
    return out


# ------------------------------------------------------- platform search
@router.get("/cases/{case_id}/search",
            response_model=CopilotSearchOut,
            summary="Multilingual search over a case's confirmed records")
def case_search(case_id: int,
                q: str = Query(min_length=1, max_length=200),
                k: int = Query(default=20, ge=1, le=50),
                db: Session = Depends(get_db_checked),
                current: CurrentUser = Depends(get_current_user)):
    case = require_case_access(db, case_id, current)
    ctx = copilot.load_case_context(db, case)
    from ...services.case_analysis import analysis_block
    out = search_case(ctx, q, k=k)
    out["analysis"] = analysis_block(db, case)
    return out
