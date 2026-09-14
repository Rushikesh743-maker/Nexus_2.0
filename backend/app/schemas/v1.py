"""Pydantic request/response schemas for the v1 API.

One module keeps the API contract visible in one place. `from_attributes`
means the serializers read straight off the ORM objects — the repositories
stay free of hand-mapped dicts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ------------------------------------------------------------------- shared

class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel):
    """Plain list responses: { items, total } for stable pagination later."""
    items: list[dict[str, Any]]
    total: int


# --------------------------------------------------------------------- auth

# There is no login request/response schema: authentication is Supabase Auth
# (the client exchanges credentials with Supabase, not with NEXUS). The only
# auth surface NEXUS exposes is GET /auth/me (UserOut), which returns the
# NEXUS profile + role for the verified Supabase identity.

class UserOut(ORMModel):
    id: int
    officer_id: str | None
    name: str
    email: str
    role: str
    created_at: datetime


# -------------------------------------------------------------------- cases

class CaseOut(ORMModel):
    id: int
    case_number: str
    title: str
    description: str | None
    status: str
    priority: str
    is_synthetic: bool
    created_by: int | None
    created_by_name: str | None = None
    created_at: datetime
    updated_at: datetime
    # stage 7: lifecycle state machine (DRAFT … ANALYSIS_COMPLETE, STALE,
    # CLOSED) — separate from the administrative `status`
    workflow_state: str = "DRAFT"
    last_analysis_at: datetime | None = None


class CaseCounts(BaseModel):
    documents: int
    entities: int
    relationships: int
    evidence: int
    timeline_events: int
    locations: int
    hypotheses: int
    contradictions: int
    gaps: int
    simulations: int


class CaseListItem(CaseOut):
    counts: CaseCounts
    latest_event_at: datetime | None = None


class CrossCaseLink(BaseModel):
    case_id: int
    case_number: str
    title: str
    status: str
    shared_entities: list[str]
    shared_count: int = 0


class CaseDetail(CaseOut):
    counts: CaseCounts
    key_entities: list[dict[str, Any]]
    cross_case_links: list[CrossCaseLink]
    latest_events: list[dict[str, Any]]


class CaseCreate(BaseModel):
    case_number: str = Field(pattern=r"^[A-Z]{2,8}-\d{4}-\d{3,}$",
                             description="e.g. CASE-2026-004")
    title: str = Field(min_length=3, max_length=255)
    description: str | None = None
    status: str = "OPEN"
    priority: str = "MEDIUM"

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        allowed = {"OPEN", "ACTIVE", "ON_HOLD", "CLOSED", "ARCHIVED"}
        v = v.upper()
        if v not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        return v

    @field_validator("priority")
    @classmethod
    def _priority(cls, v: str) -> str:
        allowed = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        v = v.upper()
        if v not in allowed:
            raise ValueError(f"priority must be one of {sorted(allowed)}")
        return v


# -------------------------------------------------------------- sub-resources

class ProcessingJobOut(ORMModel):
    """Phase 1: the background processing job for a document.

    The real queue state — the front end can show "queued / processing /
    completed / failed" exactly as the database says, with attempt count
    and the user-safe error. Never internal details.
    """
    id: int
    status: str
    attempts: int
    error: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class DocumentOut(ORMModel):
    id: int
    case_id: int
    filename: str
    file_type: str
    language: str | None
    file_size: int | None
    uploaded_at: datetime
    processing_status: str
    # Stage 2: storage + processing state (seeded Stage-1 documents keep
    # their defaults; the storage path itself is never exposed).
    mime_type: str | None = None
    file_hash: str | None = Field(default=None, validation_alias="sha256")
    uploaded_by_name: str | None = None
    processed_at: datetime | None = None
    processing_error: str | None = None
    extracted_entities: int = 0
    extracted_relationships: int = 0
    pending_review: int = 0
    # Stage 5: multilingual provenance (never the storage path).
    language_confidence: float | None = None
    translation_status: str | None = None
    processing_method: str | None = None
    # Stage 7: real processing provenance (no fake progress).
    processing_started_at: datetime | None = None
    processing_seconds: float | None = None
    page_count: int | None = None
    # Phase 1: the background processing job (null for pre-phase rows).
    processing_job: ProcessingJobOut | None = None


class EntityOut(ORMModel):
    id: int
    case_id: int
    entity_type: str
    canonical_name: str
    metadata: dict | None = Field(default=None, validation_alias="meta")
    created_at: datetime


class RelationshipOut(ORMModel):
    id: int
    case_id: int
    source_entity_id: int
    target_entity_id: int
    relationship_type: str
    confidence: float | None
    metadata: dict | None = Field(default=None, validation_alias="meta")
    created_at: datetime
    # Joined labels, added by the repository so the UI can render edges
    # without a second round trip per endpoint.
    source_label: str = ""
    target_label: str = ""


class EvidenceOut(ORMModel):
    id: int
    case_id: int
    document_id: int | None
    document_filename: str | None = None
    evidence_type: str
    description: str | None
    source_reference: str | None
    confidence: float | None
    created_at: datetime


class LocationOut(ORMModel):
    id: int
    case_id: int
    name: str
    latitude: float | None
    longitude: float | None
    metadata: dict | None = Field(default=None, validation_alias="meta")


class TimelineEventOut(ORMModel):
    id: int
    case_id: int
    entity_id: int | None
    event_type: str
    timestamp: datetime | None
    location_id: int | None
    description: str | None
    evidence_id: int | None


class HypothesisOut(ORMModel):
    id: int
    case_id: int
    title: str
    description: str | None
    score: float | None
    status: str
    created_at: datetime


class ContradictionOut(ORMModel):
    id: int
    case_id: int
    title: str
    description: str | None
    severity: str
    status: str
    created_at: datetime


class GapOut(ORMModel):
    id: int
    case_id: int
    title: str
    description: str | None
    priority: str
    status: str
    created_at: datetime


class SimulationOut(ORMModel):
    id: int
    case_id: int
    name: str
    description: str | None
    created_by: int | None
    created_at: datetime


class SimulationCreate(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    description: str | None = None


# -------------------------------------------------------------------- system

class HealthOut(BaseModel):
    status: str
    version: str
    environment: str
    time: datetime
    database: dict[str, Any]
    synthetic_data_only: bool = True
    # Phase 1 observability: per-dependency status (storage + worker/queue)
    storage: dict[str, Any] = {}
    worker: dict[str, Any] = {}


# (CopilotStatus lives with the other stage-5 copilot schemas at the end
# of this module.)

# ------------------------------------------------------------ stage 2: documents & extraction

class SourceRefOut(BaseModel):
    document_id: int | str | None = None
    page: int | None = None
    row: int | None = None
    column: str | None = None
    value: str | None = None
    line: int | None = None
    snippet: str | None = None
    available: bool = True


class MatchSuggestionOut(ORMModel):
    id: int
    candidate_id: int
    candidate_name: str | None = None
    existing_entity_id: int
    existing_entity_name: str | None = None
    similarity: float
    reasons: list[str] | None = None
    status: str
    # Phase 2: position in the candidate's ranked suggestion list (1 = best)
    rank: int = 1

    @field_validator("reasons", mode="before")
    @classmethod
    def _list(cls, v):
        return v or []


class EntityCandidateOut(ORMModel):
    id: int
    case_id: int
    document_id: int
    entity_type: str
    candidate_name: str
    aliases: list[str] | None = None
    confidence: float | None
    source_location: dict | None
    source_snippet: str | None
    extraction_method: str
    status: str
    accepted_entity_id: int | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None
    match: MatchSuggestionOut | None = None

    @field_validator("aliases", mode="before")
    @classmethod
    def _aliases(cls, v):
        return v or []


class RelationshipCandidateOut(ORMModel):
    id: int
    case_id: int
    document_id: int
    source_candidate_id: int
    target_candidate_id: int
    relationship_type: str
    confidence: float | None
    source_location: dict | None
    source_snippet: str | None
    extraction_method: str
    status: str
    decided_at: datetime | None = None
    decision_note: str | None = None
    source_name: str | None = None
    target_name: str | None = None
    endpoints_confirmed: bool = False


class ExtractionSummaryOut(BaseModel):
    source_type: str | None = None
    stats: dict | None = None
    entities: int = 0
    relationships: int = 0
    matches: int = 0
    pending: int = 0
    accepted: int = 0
    rejected: int = 0
    evidence_generated: int = 0
    # Stage 5: the preserved source text (display-capped) + language.
    # `original_text` is the untouched source; `normalized_text` is the
    # transliterated representation. Both are None for latin/empty docs.
    language: str | None = None
    language_confidence: float | None = None
    original_text: str | None = None
    normalized_text: str | None = None


class DocumentStatusOut(BaseModel):
    id: int
    case_id: int
    filename: str
    processing_status: str
    processed_at: datetime | None = None
    processing_error: str | None = None
    processing_job: ProcessingJobOut | None = None
    summary: ExtractionSummaryOut | None = None


class DocumentDetailOut(BaseModel):
    document: DocumentOut
    summary: ExtractionSummaryOut


class ExtractionOut(BaseModel):
    summary: ExtractionSummaryOut
    entities: list[EntityCandidateOut]
    relationships: list[RelationshipCandidateOut]
    matches: list[MatchSuggestionOut]


class ReviewDecision(BaseModel):
    note: str | None = Field(default=None, max_length=255)


# ---------------------------------------------------- stage 3: graph intel

class GraphFindingOut(BaseModel):
    id: int
    case_id: int
    finding_type: str
    title: str
    summary: str | None
    explanation: list[str]
    details: dict[str, Any]
    involved_entity_ids: list[int]
    supporting_relationship_ids: list[int]
    supporting_evidence_ids: list[int]
    related_case_ids: list[int]
    analysis_method: str
    graph_version: str
    stale: bool = False
    status: str
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    created_at: str


class AnalysisStateOut(BaseModel):
    """Analysis freshness (phase 2, work item E): not-analyzed |
    up-to-date | stale | insufficient. Every intelligence surface returns
    this block so stale results are never silently presented as current.
    ``graph_version`` is the stage-4 confirmed-data hash the state was
    computed against."""
    state: str
    graph_version: str
    reason: str
    analyzed: bool
    insufficient: bool


class GraphAnalysisOut(BaseModel):
    recomputed: bool
    graph_version: str
    graph: dict[str, Any] | None = None
    findings: list[GraphFindingOut]
    analysis: AnalysisStateOut | None = None


class GraphFindingsOut(BaseModel):
    graph_version: str
    analyzed: bool
    current_findings: list[GraphFindingOut]
    stale_findings: list[GraphFindingOut]
    analysis: AnalysisStateOut | None = None


class EntityMetricsOut(BaseModel):
    entity_id: int
    name: str
    entity_type: str
    degree: int
    weighted_degree: int
    betweenness: float
    component_size: int
    cross_case_reach: int
    is_articulation_point: bool
    neighbor_types: dict[str, int]


class GraphMetricsOut(BaseModel):
    graph_version: str
    nodes: int
    edges: int
    metrics: list[EntityMetricsOut]
    analysis: AnalysisStateOut | None = None


class BridgeOut(BaseModel):
    entity_id: int
    name: str
    entity_type: str
    degree: int
    is_articulation_point: bool
    betweenness: float
    connectivity_impact: int
    cross_case_reach: int
    bridge_score: float
    reasons: list[str]


class GraphBridgesOut(BaseModel):
    graph_version: str
    nodes: int
    edges: int
    insufficient: bool
    bridges: list[BridgeOut]
    analysis: AnalysisStateOut | None = None


class ClusterOut(BaseModel):
    index: int
    node_ids: list[str]
    members: list[str]
    entity_ids: list[int]
    entity_count: int
    relationship_count: int
    type_breakdown: dict[str, int]
    case_ids: list[int]
    cross_case: bool
    key_bridge: dict[str, Any] | None
    subgroups: list[list[str]] | None
    description: str


class GraphClustersOut(BaseModel):
    graph_version: str
    clusters: list[ClusterOut]
    analysis: AnalysisStateOut | None = None


class CrossCaseConnectionOut(BaseModel):
    case_id: int
    case_number: str
    connection_kind: str
    shared_entities: list[dict[str, Any]]
    example_path: list[dict[str, Any]]
    example_path_relationships: list[str]
    evidence_count: int
    explanation: str


class GraphCrossCaseOut(BaseModel):
    graph_version: str
    connections: list[CrossCaseConnectionOut]
    analysis: AnalysisStateOut | None = None


class PathOut(BaseModel):
    path_length: int
    nodes: list[dict[str, Any]]
    relationship_types: list[str]
    relationship_ids: list[int]
    evidence_count: int
    explanation: str


class GraphPathsOut(BaseModel):
    graph_version: str
    source: dict[str, Any]
    target: dict[str, Any]
    max_depth: int
    paths: list[PathOut]
    analysis: AnalysisStateOut | None = None

# ------------------------------------------------- stage 4: investigation
#
# Investigation Reasoning & Evidence Intelligence (stage 4). Findings reuse
# the stage-3 graph_finding table with the four stage-4 finding types;
# hypotheses live in their own table. All payloads mirror the engine
# outputs 1:1 (details carry the rule-specific fields).


class InvestigationFinding(GraphFindingOut):
    """A stage-4 finding (CONTRADICTION / TIMELINE_INSIGHT / GEO_INSIGHT /
    INVESTIGATION_GAP). Same shape as stage-3 findings."""


class InvestigationAnalysis(BaseModel):
    recomputed: bool
    graph_version: str
    findings: list[InvestigationFinding]
    stale_findings: list[InvestigationFinding]
    hypotheses: list["InvestigationHypothesisOut"]
    analyzed: bool
    states: dict[str, Any] | None = None
    analysis: AnalysisStateOut | None = None


class InvestigationStatus(BaseModel):
    case_id: int
    # not-analyzed | analyzing | up-to-date | stale | insufficient | error
    state: str
    graph_version: str
    analyzed: bool
    reason: str
    current_findings: int
    stale_findings: int
    hypotheses: int
    insufficient: bool
    timeline: dict[str, Any]
    geospatial: dict[str, Any]


class InvestigationFindings(BaseModel):
    graph_version: str
    analyzed: bool
    current_findings: list[InvestigationFinding]
    stale_findings: list[InvestigationFinding]
    analysis: AnalysisStateOut | None = None


# ------------------------------------------------- finding evidence chain

class ChainEntityRef(BaseModel):
    id: int
    entity_type: str
    canonical_name: str


class ChainRelationshipProvenance(BaseModel):
    document_id: int | None = None
    document: str | None = None
    location: dict[str, Any] | None = None
    snippet: str | None = None
    extraction_method: str | None = None
    evidence_id: int | None = None


class ChainRelationshipRef(BaseModel):
    id: int
    relationship_type: str
    confidence: float | None = None
    source: ChainEntityRef | None = None
    target: ChainEntityRef | None = None
    provenance: ChainRelationshipProvenance


class ChainClaimRef(BaseModel):
    id: int
    predicate: str
    object_value: str | None = None
    object_entity: ChainEntityRef | None = None
    event_time: str | None = None
    original_text: str | None = None
    language: str | None = None
    location: str | None = None


class ChainEvidenceRef(BaseModel):
    id: int
    evidence_type: str
    description: str | None = None
    confidence: float | None = None
    document_id: int | None = None
    document: str | None = None
    claims: list[ChainClaimRef] = []


class FindingEvidenceChain(BaseModel):
    """A finding's resolved evidence chain (phase 2).

    `missing` is never silently empty-of-meaning: every referenced id that
    could not be resolved is listed here, and when a finding carries no
    linked evidence at all the chain says so explicitly (the UI must show
    'no evidence' rather than an empty box).
    """
    complete: bool
    entities: list[ChainEntityRef] = []
    relationships: list[ChainRelationshipRef] = []
    evidence: list[ChainEvidenceRef] = []
    missing: list[str] = []


class FindingDetailOut(BaseModel):
    finding: InvestigationFinding
    current_graph_version: str
    evidence_chain: FindingEvidenceChain
    analysis: AnalysisStateOut | None = None


# --------------------------------------------------------- entity profile

class EntityProfileConnection(BaseModel):
    relationship_id: int
    relationship_type: str
    direction: str  # outgoing | incoming
    confidence: float | None = None
    peer: ChainEntityRef | None = None
    provenance: ChainRelationshipProvenance


class EntityProfileMetrics(BaseModel):
    degree: int
    documents: int
    first_seen: str | None = None
    last_seen: str | None = None
    time_span_hours: float | None = None


class EntityProfileAnalysis(BaseModel):
    state: str
    graph_version: str
    reason: str
    analyzed: bool


class EntityProfileEvent(BaseModel):
    id: int
    event_type: str
    timestamp: str | None = None
    location: str | None = None
    description: str | None = None
    evidence_id: int | None = None


class EntityProfileLocation(BaseModel):
    name: str
    latitude: float | None = None
    longitude: float | None = None


class EntityProfileFinding(BaseModel):
    id: int
    finding_type: str
    title: str
    graph_version: str
    stale: bool
    status: str


class EntityProfileOut(BaseModel):
    entity: EntityOut
    connections: list[EntityProfileConnection] = []
    evidence: list[ChainEvidenceRef] = []
    claims: list[ChainClaimRef] = []
    events: list[EntityProfileEvent] = []
    locations: list[EntityProfileLocation] = []
    findings: list[EntityProfileFinding] = []
    metrics: EntityProfileMetrics
    analysis: EntityProfileAnalysis


# ------------------------------------------------------ case snapshots

class SnapshotCreateIn(BaseModel):
    label: str | None = Field(default=None, max_length=255)


class SnapshotSummary(BaseModel):
    id: int
    sequence: int
    label: str | None = None
    graph_version: str
    entity_count: int
    relationship_count: int
    evidence_count: int
    created_by_name: str | None = None
    created_at: datetime


class SnapshotOut(BaseModel):
    id: int
    case_id: int
    sequence: int
    label: str | None = None
    graph_version: str
    payload: dict[str, Any]
    entity_count: int
    relationship_count: int
    evidence_count: int
    created_by_name: str | None = None
    created_at: datetime


class SnapshotListOut(BaseModel):
    case_id: int
    current_graph_version: str
    snapshots: list[SnapshotSummary]
    analysis: AnalysisStateOut | None = None


class InvestigationHypothesisOut(BaseModel):
    id: int
    case_id: int
    title: str
    description: str | None
    hypothesis_type: str
    involved_entity_ids: list[int]
    supporting_relationship_ids: list[int]
    supporting_evidence_ids: list[int]
    contradicting_evidence_ids: list[int]
    supporting_finding_ids: list[int]
    contradiction_ids: list[int]
    analytical_score: float
    confidence_band: str
    score_components: dict[str, Any]
    explanation: list[str]
    analysis_method: str
    graph_version: str | None
    stale: bool
    status: str
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    created_at: str
    updated_at: str


class InvestigationHypotheses(BaseModel):
    graph_version: str
    hypotheses: list[InvestigationHypothesisOut]
    analysis: AnalysisStateOut | None = None


class InvestigatorHypothesisIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    involved_entity_ids: list[int] = Field(default_factory=list)
    supporting_relationship_ids: list[int] = Field(default_factory=list)
    supporting_evidence_ids: list[int] = Field(default_factory=list)
    contradicting_evidence_ids: list[int] = Field(default_factory=list)
    supporting_finding_ids: list[int] = Field(default_factory=list)


class EvidenceImpact(BaseModel):
    evidence_id: int
    linked_entities: list[dict[str, Any]]
    linked_relationships: list[int]
    linked_timeline_events: list[int]
    referenced_by_findings: list[int]
    referenced_by_hypotheses: list[int]
    impact_score: float
    impact_band: str
    impact_role: str
    score_components: dict[str, Any]
    explanation: list[str]


class EvidenceImpactSummary(BaseModel):
    evidence_count: int
    distribution: dict[str, int]
    top_evidence: EvidenceImpact | None
    evidence_impacts: list[EvidenceImpact]
    analysis_method: str
    analysis: AnalysisStateOut | None = None


class EvidenceSimulation(BaseModel):
    evidence_id: int
    simulation_only: bool
    message: str
    edges_removed: list[dict[str, Any]]
    newly_isolated_entities: list[dict[str, Any]]
    metrics_before: dict[str, Any]
    metrics_after: dict[str, Any]
    diff: dict[str, Any]
    affected_findings: list[int]
    analysis_method: str


class TimelineResultOut(BaseModel):
    timeline_type: str
    title: str
    summary: str
    explanation: list[str]
    event_ids: list[int]
    entity_ids: list[int]
    interval_minutes: float | None
    details: dict[str, Any]


class TimelineAnalysis(BaseModel):
    case_id: int
    results: list[TimelineResultOut]
    events_total: int
    events_with_timestamp: int
    events_without_timestamp: int
    insufficient: bool
    analysis_method: str
    analysis: AnalysisStateOut | None = None


class GeoObservationOut(BaseModel):
    entity_id: int | None
    entity_name: str | None
    location_id: int
    location_name: str
    latitude: float
    longitude: float
    timestamp: str | None
    source_event_id: int | None
    source_relationship_id: int | None


class GeoResultOut(BaseModel):
    geo_type: str
    title: str
    summary: str
    explanation: list[str]
    entity_ids: list[int]
    event_ids: list[int]
    relationship_ids: list[int]
    location_ids: list[int]
    distance_km: float | None
    time_difference_minutes: float | None
    threshold: str
    details: dict[str, Any]


class GeospatialAnalysis(BaseModel):
    case_id: int
    results: list[GeoResultOut]
    observations: list[GeoObservationOut]
    observations_count: int
    location_data_insufficient: bool
    analysis_method: str
    analysis: AnalysisStateOut | None = None


# ================================================================ stage 5:
# multilingual search + investigator copilot
class CopilotCitationOut(BaseModel):
    kind: str
    id: int
    label: str
    record: dict | None = None


class CopilotAnswerOut(BaseModel):
    intent: str
    interpretation: str
    status: str
    answer_text: str | None = None
    confidence: float
    confidence_basis: str
    citations: list[CopilotCitationOut]
    data: dict
    provider: str
    fallback: bool
    suggestions: list[str] = []
    # phase 2 (work item F): every answer is bound to the confirmed-data
    # snapshot it was computed over, plus the case's analysis freshness,
    # so a stale answer is never silently presented as current.
    graph_version: str | None = None
    analysis: AnalysisStateOut | None = None


class CopilotQuestionIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class CopilotImpactIn(BaseModel):
    evidence_id: int


class CopilotSearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    k: int = Field(default=20, ge=1, le=50)


class CopilotSearchHitOut(BaseModel):
    kind: str
    id: int
    label: str
    field: str
    snippet: str | None = None


class CopilotSearchOut(BaseModel):
    query: str
    hits: list[CopilotSearchHitOut]
    counts: dict[str, int]
    total: int
    analysis: AnalysisStateOut | None = None


class CopilotProviderOut(BaseModel):
    id: str
    name: str
    active: bool
    reason: str
    model: str | None = None


class CopilotStatusOut(BaseModel):
    providers: list[CopilotProviderOut]
    active: str
    case_id: int


class CopilotSuggestionsOut(BaseModel):
    suggestions: list[str]
    analysis: AnalysisStateOut | None = None


# The platform /copilot capability statement is upgraded to report the
# stage-5 capabilities that are actually live (kept additive: the original
# fields remain so any older client keeps working).
class CopilotStatus(BaseModel):
    capability: str
    stage: str
    message: str
    available: list[str]
    planned: list[str]
