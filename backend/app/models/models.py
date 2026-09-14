"""SQLAlchemy models for the platform data layer.

Stage 1: thirteen tables mapped 1:1 from the data model spec
(docs/DATABASE.md). Stage 2 adds the document-processing tables:
`document_extraction`, `entity_candidate`, `relationship_candidate`,
`entity_match_suggestion`, and storage/provenance columns on `document`.

Deliberately plain — string statuses, JSON metadata, no inheritance, no
mixins — so later stages (hypothesis engine, simulations, copilot) can add
columns and tables without churning this file.

All rows seeded by `app.seed` are synthetic demonstration data; the seed
labels each case accordingly and the docs state the same.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer,
                        String, Text, Uuid)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ people

class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    officer_id: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # Stable identity: the Supabase Auth user UUID (auth.users.id). This is
    # how a verified Supabase token maps to this NEXUS record. NULL means the
    # row is not a Supabase-backed login identity (e.g. the synthetic-data
    # seed owner) and can therefore never authenticate. NEXUS stores NO
    # passwords — authentication is Supabase Auth.
    supabase_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), unique=True, nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(32), default="INVESTIGATOR", nullable=False)
    # INVESTIGATOR | ANALYST | SUPERVISOR | ADMIN
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    created_cases: Mapped[list["Case"]] = relationship(back_populates="creator")
    simulations: Mapped[list["Simulation"]] = relationship(back_populates="creator")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")


# -------------------------------------------------------------------- cases

class Case(Base):
    __tablename__ = "case"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_number: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="OPEN", index=True, nullable=False)
    # OPEN | ACTIVE | ON_HOLD | CLOSED | ARCHIVED
    priority: Mapped[str] = mapped_column(String(16), default="MEDIUM", nullable=False)
    # LOW | MEDIUM | HIGH | CRITICAL
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # -- Stage 7: case lifecycle state machine -----------------------------
    # DRAFT -> UPLOADING -> PROCESSING -> REVIEW_REQUIRED ->
    # READY_FOR_ANALYSIS -> ANALYZING -> ANALYSIS_COMPLETE
    # upload after completion -> STALE -> PROCESSING -> ...
    # CLOSED is the terminal administrative state. Transitions are guarded
    # (services/case_state_machine.py); invalid ones are rejected, never
    # silently allowed.
    workflow_state: Mapped[str] = mapped_column(
        String(32), default="DRAFT", index=True, nullable=False)
    last_analysis_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)

    creator: Mapped["User | None"] = relationship(back_populates="created_cases")
    documents: Mapped[list["Document"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    entities: Mapped[list["Entity"]] = relationship(back_populates="case", cascade="all, delete-orphan")

    @property
    def created_by_name(self) -> str | None:
        """Display name of the opening user (lazy-loads the creator)."""
        return self.creator.name if self.creator else None
    relationships_: Mapped[list["Relationship"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    timeline_events: Mapped[list["TimelineEvent"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    locations: Mapped[list["Location"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    hypotheses: Mapped[list["Hypothesis"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    contradictions: Mapped[list["Contradiction"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    gaps: Mapped[list["InvestigationGap"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    simulations: Mapped[list["Simulation"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    graph_findings: Mapped[list["GraphFinding"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    investigation_hypotheses: Mapped[list["InvestigationHypothesis"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    evidence_claims: Mapped[list["EvidenceClaim"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    snapshots: Mapped[list["CaseSnapshot"]] = relationship(back_populates="case", cascade="all, delete-orphan")


# ----------------------------------------------------------------- documents

class Document(Base):
    __tablename__ = "document"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), default="text", nullable=False)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processing_status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)
    # PENDING | UPLOADED | PROCESSING | PROCESSED | FAILED
    # (seeded Stage-1 documents stay PENDING/PROCESSED; uploaded documents
    #  walk UPLOADED -> PROCESSING -> PROCESSED | FAILED)

    # -- Stage 2: storage + processing provenance --------------------------
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # relative to the storage root; never exposed to the front end
    sha256: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    # real processing duration in seconds (started_at -> processed_at)
    processing_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # page count reported by the real extractor (PDFs only; None when the
    # document type has no pages — never guessed)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # -- Stage 5: multilingual provenance ----------------------------------
    # `language` (above) holds the detected code (en|hi|mr|ur|None).
    language_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # NOT_REQUIRED | NORMALIZED | PENDING — documents the state of the
    # language-specific processing, never a claim about the content.
    translation_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # Which pipeline processed it (e.g. "rules", "rules+multilingual:hi").
    processing_method: Mapped[str | None] = mapped_column(String(64), nullable=True)

    case: Mapped["Case"] = relationship(back_populates="documents")
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="document")
    uploader: Mapped["User | None"] = relationship()
    extraction: Mapped["DocumentExtraction | None"] = relationship(
        back_populates="document", uselist=False, cascade="all, delete-orphan")


# ------------------------------------------------------------------- entities

class Entity(Base):
    __tablename__ = "entity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # person | vehicle | location | organization | phone | account | ...
    canonical_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    meta: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped["Case"] = relationship(back_populates="entities")

    source_relationships: Mapped[list["Relationship"]] = relationship(
        foreign_keys="Relationship.source_entity_id", back_populates="source")
    target_relationships: Mapped[list["Relationship"]] = relationship(
        foreign_keys="Relationship.target_entity_id", back_populates="target")


class Relationship(Base):
    __tablename__ = "relationship"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    source_entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id", ondelete="CASCADE"), index=True, nullable=False)
    target_entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id", ondelete="CASCADE"), index=True, nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    # OWNS | CALLED | LOCATED_AT | ASSOCIATED_WITH | TRANSFERRED_TO | ...
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped["Case"] = relationship(back_populates="relationships_")
    source: Mapped["Entity"] = relationship(foreign_keys=[source_entity_id], back_populates="source_relationships")
    target: Mapped["Entity"] = relationship(foreign_keys=[target_entity_id], back_populates="target_relationships")


# -------------------------------------------------------------------- evidence

class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("document.id", ondelete="SET NULL"), nullable=True)
    evidence_type: Mapped[str] = mapped_column(String(48), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped["Case"] = relationship(back_populates="evidence")
    document: Mapped["Document | None"] = relationship(back_populates="evidence")
    claims: Mapped[list["EvidenceClaim"]] = relationship(back_populates="evidence")


# --------------------------------------------------------------------- events

class Location(Base):
    __tablename__ = "location"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    case: Mapped["Case"] = relationship(back_populates="locations")


class TimelineEvent(Base):
    __tablename__ = "timeline_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    entity_id: Mapped[int | None] = mapped_column(ForeignKey("entity.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("location.id", ondelete="SET NULL"), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_id: Mapped[int | None] = mapped_column(ForeignKey("evidence.id", ondelete="SET NULL"), nullable=True)

    case: Mapped["Case"] = relationship(back_populates="timeline_events")
    location: Mapped["Location | None"] = relationship()
    evidence: Mapped["Evidence | None"] = relationship()


# -------------------------------------------------------- analytical records

class Hypothesis(Base):
    __tablename__ = "hypothesis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="OPEN", nullable=False)
    # OPEN | SUPPORTED | REFUTED | ARCHIVED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped["Case"] = relationship(back_populates="hypotheses")


class Contradiction(Base):
    __tablename__ = "contradiction"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(16), default="MEDIUM", nullable=False)
    # LOW | MEDIUM | HIGH
    status: Mapped[str] = mapped_column(String(32), default="OPEN", nullable=False)
    # OPEN | RESOLVED | DISMISSED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped["Case"] = relationship(back_populates="contradictions")


class InvestigationGap(Base):
    __tablename__ = "investigation_gap"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(16), default="MEDIUM", nullable=False)
    # LOW | MEDIUM | HIGH
    status: Mapped[str] = mapped_column(String(32), default="OPEN", nullable=False)
    # OPEN | ADDRESSED | ACCEPTED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped["Case"] = relationship(back_populates="gaps")


class Simulation(Base):
    __tablename__ = "simulation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped["Case"] = relationship(back_populates="simulations")
    creator: Mapped["User | None"] = relationship(back_populates="simulations")


# --------------------------------------------------------------------- audit

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id", ondelete="SET NULL"), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    meta: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    user: Mapped["User | None"] = relationship(back_populates="audit_logs")


# ------------------------------------------------ Stage 2: document processing

class DocumentExtraction(Base):
    """Normalized content of a processed document (one row per document).

    This is the raw extraction record — it is preserved for auditability
    even after candidates are accepted or rejected. Large fields are capped
    so a pathological file cannot bloat the database.
    """

    __tablename__ = "document_extraction"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)  # pdf | txt | csv
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    pages: Mapped[list | None] = mapped_column(JSON, nullable=True)   # pdf: [{page, chars, text_head}]
    rows: Mapped[dict | None] = mapped_column(JSON, nullable=True)    # csv: {columns: [...], rows: [[...]]}
    stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # {pages|lines|rows, chars, warnings[]}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # -- Stage 5: multilingual text preservation ---------------------------
    # The untouched original source text (full, uncapped by display limits).
    # `raw_text` remains the processing-cap copy; this column is the audit
    # copy that is never overwritten by review or re-processing edits.
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Language-specific normalized (transliterated to Latin) representation,
    # used for search and matching. The original text is always preserved.
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)  # en|hi|mr|ur|None
    language_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Extraction-time structured claims (materialized to evidence_claim
    # rows only when their subject candidate is accepted — confirmed-only).
    claims: Mapped[list | None] = mapped_column(JSON, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="extraction")


class EntityCandidate(Base):
    """An entity detected by the extraction pipeline, awaiting review.

    A candidate is NOT a confirmed analytical entity. It becomes one only
    when an investigator accepts it (creating or linking an `Entity` row,
    plus an `Evidence` row with provenance). Rejected candidates stay in the
    table — the original extraction result is never destroyed.
    """

    __tablename__ = "entity_candidate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id", ondelete="CASCADE"), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # person | phone | vehicle | location | account | organization | case | event
    candidate_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    aliases: Mapped[list | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # extraction confidence, 0..1
    source_location: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # {"page": n, "snippet": "..."} | {"row": n, "column": "...", "value": "..."} | {"line": n, "snippet": "..."}
    source_snippet: Mapped[str | None] = mapped_column(String(512), nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(64), default="rule", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True, nullable=False)
    # PENDING | DEFERRED | ACCEPTED | REJECTED
    accepted_entity_id: Mapped[int | None] = mapped_column(ForeignKey("entity.id", ondelete="SET NULL"), nullable=True)
    decision_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # set when the row was rejected automatically (e.g. endpoint entity rejected)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped["Document"] = relationship()
    accepted_entity: Mapped["Entity | None"] = relationship()
    matches: Mapped[list["EntityMatchSuggestion"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan")


class RelationshipCandidate(Base):
    """A relationship detected between two entity candidates, awaiting review.

    Only created when the source text or structured data explicitly supports
    the link (column pairs / connective phrases) — co-occurrence alone never
    creates a candidate.
    """

    __tablename__ = "relationship_candidate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id", ondelete="CASCADE"), index=True, nullable=False)
    source_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("entity_candidate.id", ondelete="CASCADE"), index=True, nullable=False)
    target_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("entity_candidate.id", ondelete="CASCADE"), index=True, nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    # CALLED | OWNS | USED | LOCATED_AT | ASSOCIATED_WITH | TRANSFERRED_TO | ...
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_location: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_snippet: Mapped[str | None] = mapped_column(String(512), nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(64), default="rule", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True, nullable=False)
    # PENDING | ACCEPTED | REJECTED
    decision_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped["Document"] = relationship()
    source_candidate: Mapped["EntityCandidate"] = relationship(
        foreign_keys=[source_candidate_id])
    target_candidate: Mapped["EntityCandidate"] = relationship(
        foreign_keys=[target_candidate_id])


class EntityMatchSuggestion(Base):
    """A suggested match between a new candidate and an existing entity.

    Never auto-merged: the suggestion is PENDING until an investigator
    accepts it (candidate folds into the existing entity, which gains the
    candidate name as an alias) or rejects it (the candidate may then be
    accepted as a new entity). Reasons must be data-supported — the field
    holds the exact checks that fired.

    Phase 2: a candidate may have SEVERAL ranked suggestions (best first,
    ``rank`` 1..N) so the investigator sees alternatives, each with its
    own reasons — including contextual signals (shared phone/vehicle/
    account/location), not just name similarity.
    """

    __tablename__ = "entity_match_suggestion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    # Phase 2: indexed but no longer unique — several ranked suggestions
    # per candidate are allowed (migration 0002).
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("entity_candidate.id", ondelete="CASCADE"), index=True, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    existing_entity_id: Mapped[int] = mapped_column(
        ForeignKey("entity.id", ondelete="CASCADE"), index=True, nullable=False)
    similarity: Mapped[float] = mapped_column(Float, nullable=False)
    reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True, nullable=False)
    # PENDING | ACCEPTED | REJECTED
    decision_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    candidate: Mapped["EntityCandidate"] = relationship(back_populates="matches")
    existing_entity: Mapped["Entity"] = relationship()


# ---------------------------------------------- Stage 3: graph intelligence

class GraphFinding(Base):
    """A computed, explainable result of the graph intelligence engine.

    A finding is an ANALYTICAL result, not a confirmed fact: it is produced
    from confirmed entities/relationships only, carries the exact computed
    evidence (entities, relationships, evidence ids) behind it, and is
    associated with a graph version (a snapshot hash of the confirmed data)
    so the UI can tell when the underlying data has moved on. Findings are
    never deleted on re-analysis — the history stays for auditability and
    reviewers can mark findings REVIEWED or DISMISSED.
    """

    __tablename__ = "graph_finding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    finding_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # HIDDEN_CONNECTION | BRIDGE_ENTITY | CROSS_CASE_CONNECTION | NETWORK_CLUSTER | HIGH_CONNECTIVITY
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # why this was found — every bullet is generated from computed data
    explanation: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # structured payload (paths, metrics, cluster members, …)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    involved_entity_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    supporting_relationship_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    supporting_evidence_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    related_case_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)  # cross-case findings
    analysis_method: Mapped[str] = mapped_column(String(255), nullable=False)
    graph_version: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True, nullable=False)
    # ACTIVE | REVIEWED | DISMISSED
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    case: Mapped["Case"] = relationship(back_populates="graph_findings")
    reviewer: Mapped["User | None"] = relationship()


# -------------------------------------------- Stage 4: investigation intel

class InvestigationHypothesis(Base):
    """A competing explanation of the confirmed data (stage 4).

    Hypotheses are ANALYTICAL constructs, never conclusions: each carries a
    transparent deterministic score with visible components, the records
    behind every supporting/contradicting signal, and a neutral
    explanation. Generated rows are versioned against the confirmed data;
    investigator-created rows persist across re-analyses. Status lifecycle
    mirrors findings: ACTIVE -> REVIEWED | DISMISSED, never deleted.
    """

    __tablename__ = "investigation_hypothesis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # GENERATED_CONTRADICTION | GENERATED_STRUCTURE | INVESTIGATOR
    hypothesis_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    involved_entity_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    supporting_relationship_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    supporting_evidence_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    contradicting_evidence_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    supporting_finding_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    contradiction_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    analytical_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_band: Mapped[str] = mapped_column(String(16), nullable=False)  # LOW | MEDIUM | HIGH
    score_components: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # visible factor values
    explanation: Mapped[list | None] = mapped_column(JSON, nullable=True)  # supporting/contradicting signals
    analysis_method: Mapped[str] = mapped_column(String(255), nullable=False)
    graph_version: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True, nullable=False)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    case: Mapped["Case"] = relationship(back_populates="investigation_hypotheses")
    reviewer: Mapped["User | None"] = relationship()


# --------------------------------------------- Stage 5: structured claims

# ------------------------------------------- Stage 7: case orchestration

class CaseAnalysisRun(Base):
    """A persisted, versioned intelligence run for a case (stage 7).

    Every ``POST /cases/{id}/analysis/run`` (and recalculation) writes one
    row: who ran it, when, over which document versions (sha256 per
    document), with the resulting graph version and status. This is the
    data-version record the spec requires — analysis results are always
    explainable against an exact input snapshot, and stale findings can be
    traced to the run that produced them.
    """

    __tablename__ = "case_analysis_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    # per-case monotonically increasing version (1, 2, 3, ...)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # COMPLETED | NO_CHANGES | INSUFFICIENT | FAILED
    status: Mapped[str] = mapped_column(String(24), default="COMPLETED", nullable=False)
    graph_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # {document_id: sha256} — the exact document inputs this run saw
    input_document_versions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    findings_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped["Case"] = relationship()
    creator: Mapped["User | None"] = relationship()


class CaseProcessingJob(Base):
    """A case-level processing job (stage 7).

    ``POST /cases/{id}/process`` creates one QUEUED job and returns its
    ``job_id`` immediately; the worker then walks the case's documents
    through the EXISTING per-document pipeline (ingest -> text -> OCR ->
    language -> normalize -> extract -> resolve -> review candidates) and
    updates this row's real stage + aggregate counts as it goes. No fake
    percentages: ``current_stage`` is one of the actual pipeline stages
    and the counts are row counts from the database.
    """

    __tablename__ = "case_processing_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    # QUEUED | RUNNING | COMPLETED | FAILED
    status: Mapped[str] = mapped_column(String(16), default="QUEUED", index=True, nullable=False)
    # real pipeline stage of the document currently being processed
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_documents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_documents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_documents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # extracted counts for this run: {entities, matches, relationships, claims}
    extracted_counts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    case: Mapped["Case"] = relationship()
    creator: Mapped["User | None"] = relationship()


class DocumentProcessingJob(Base):
    """A per-document processing job (production foundation, phase 1).

    Document processing moved off the API request lifecycle: an upload
    (or a retry) creates exactly one QUEUED row and the HTTP response
    returns immediately. A worker — in-process with the API in
    development, or a separate ``python -m app.workers.document_worker``
    process in production — claims rows with
    ``SELECT ... FOR UPDATE SKIP LOCKED`` and runs the existing pipeline
    (``document_service.process_document``). Multiple workers can run
    concurrently without double-processing.

    Idempotency is enforced by the unique ``document_id``: a document
    that already has a live (QUEUED/PROCESSING) job is never re-queued,
    and a completed document is never reprocessed (the retry action
    reuses the same row, incrementing ``attempts``).
    """

    __tablename__ = "document_processing_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), unique=True,
        index=True, nullable=False)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    # QUEUED | PROCESSING | COMPLETED | FAILED
    status: Mapped[str] = mapped_column(String(16), default="QUEUED",
                                        index=True, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # user-safe error message (mirrors document.processing_error)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)

    document: Mapped["Document"] = relationship()
    case: Mapped["Case"] = relationship()


class EvidenceClaim(Base):
    """A structured claim extracted from evidence (stage 5).

    Claims are the only legitimate input to the EVIDENCE_CONTRADICTION rule:
    two comparable structured facts (subject, predicate, object, time,
    location) can be compared honestly; free text cannot. A claim row is
    created **only** when the subject candidate has been accepted —
    confirmed entities only, by construction. The original snippet and its
    language are preserved so the investigator can always open the source.
    """

    __tablename__ = "evidence_claim"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id", ondelete="CASCADE"), index=True, nullable=False)
    # subject (who/what the claim is about) — a confirmed entity
    subject_entity_id: Mapped[int | None] = mapped_column(ForeignKey("entity.id", ondelete="SET NULL"), index=True, nullable=True)
    # predicate — a documented verb: was_at | present_at | called | owns | ...
    predicate: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # object — a confirmed entity, or a plain value (object_value) when the
    # object is not (yet) a confirmed entity
    object_entity_id: Mapped[int | None] = mapped_column(ForeignKey("entity.id", ondelete="SET NULL"), index=True, nullable=True)
    object_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("location.id", ondelete="SET NULL"), index=True, nullable=True)
    normalized_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # e.g. "candidate:123" — the accepted candidate the claim was materialized from
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # preserved original-language snippet the claim was extracted from
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)  # en|hi|mr|ur
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped["Case"] = relationship(back_populates="evidence_claims")
    evidence: Mapped["Evidence"] = relationship(back_populates="claims")
    subject: Mapped["Entity | None"] = relationship(foreign_keys=[subject_entity_id])
    object_entity: Mapped["Entity | None"] = relationship(foreign_keys=[object_entity_id])
    location: Mapped["Location | None"] = relationship()


# ------------------------------------------------------------------ snapshots

class CaseSnapshot(Base):
    """An immutable investigation snapshot (case version, phase 2).

    A snapshot is a point-in-time capture of the case's CONFIRMED
    intelligence state: confirmed entities and relationships, evidence
    counts, findings, hypotheses, gaps and locations, plus the
    ``graph_version`` (the confirmed-data snapshot hash) it was taken
    against.

    Snapshots are IMMUTABLE: the API exposes create / list / compare only
    — no update or delete. ``payload`` is a compact JSON document (ids,
    names, types, counts — not raw document text) so comparing two
    versions answers "what changed" without re-deriving anything.

    ``sequence`` is a per-case monotonic number (CASE VERSION N) so the
    investigator can say "version 6 -> version 7".
    """

    __tablename__ = "case_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("case.id", ondelete="CASCADE"), index=True, nullable=False)
    # Monotonic per-case version number (1, 2, 3, ...). Unique per case.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # The confirmed-data snapshot hash the state was captured at.
    graph_version: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # Immutable capture: entities / relationships / evidence / findings /
    # hypotheses / gaps / locations (ids + names + types + counts).
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    # Entity/relationship counts at capture time (for fast diff summary).
    entity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relationship_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped["Case"] = relationship(back_populates="snapshots")
    creator: Mapped["User | None"] = relationship()
