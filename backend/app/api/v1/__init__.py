"""The v1 API surface.

    api_router = /api/v1/{health, auth, users, cases, documents, entities,
                 relationships, evidence, timeline, locations, hypotheses,
                 contradictions, gaps, simulations, graph-intelligence, copilot}

Mounted onto the application in `app.main` ahead of the SPA catch-all.
"""

from __future__ import annotations

from fastapi import APIRouter

from . import (auth, case_workflow, copilot, cases, documents,
               graph_intelligence, health, investigation_intelligence,
               search, users)
from .resources import build_resource_routers


def create_api_router() -> APIRouter:
    api_router = APIRouter(prefix="/api/v1")
    api_router.include_router(health.router)
    api_router.include_router(auth.router)
    api_router.include_router(users.router)
    api_router.include_router(cases.router)
    api_router.include_router(search.router)
    for resource_router in build_resource_routers():
        api_router.include_router(resource_router)
    # Stage 2 document lifecycle (upload / status / processing / review).
    # Included after the resource list routers so GET /documents (list)
    # keeps its place and the id-scoped routes resolve uniquely.
    api_router.include_router(documents.router)
    # Stage 3 graph intelligence (case-scoped analysis routes).
    api_router.include_router(graph_intelligence.router)
    # Stage 4 investigation intelligence (case-scoped analysis routes).
    api_router.include_router(investigation_intelligence.router)
    # Stage 6 case workflow (one-call analysis orchestration for the
    # case workspace — reuses the Stage 3/4 engines, adds no new logic).
    api_router.include_router(case_workflow.router)
    api_router.include_router(copilot.router)
    return api_router


api_router = create_api_router()
