"""Stage 7 — the case lifecycle state machine.

Nine states, one deterministic transition table:

    DRAFT -> UPLOADING -> PROCESSING -> REVIEW_REQUIRED
          -> READY_FOR_ANALYSIS -> ANALYZING -> ANALYSIS_COMPLETE

After the case has been analyzed, a new upload takes it

    ANALYSIS_COMPLETE -> STALE -> PROCESSING -> ... -> ANALYSIS_COMPLETE

and any state can be moved to the terminal administrative state
``CLOSED`` (supervisor action). ``OPEN`` is NOT a workflow state — it is
the pre-existing administrative ``Case.status`` (OPEN/ACTIVE/ON_HOLD/…)
and the two fields stay independent on purpose.

Rules:

* The machine is **event-driven and guarded**: ``transition()`` checks
  the transition table and raises ``INVALID_STATE_TRANSITION`` (409) on
  anything not allowed — invalid states are never stored.
* Transitions are **idempotent**: re-applying the current state is a no-op
  (processing finishes twice, a queue empties twice — no error).
* The services that observe the real events (upload, processing
  completion, review decisions, analysis run) call ``transition`` —
  the state always mirrors what actually happened in the database.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..core.errors import ApiError
from ..models import Case

# ------------------------------------------------------------------- states

DRAFT = "DRAFT"
UPLOADING = "UPLOADING"
PROCESSING = "PROCESSING"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
READY_FOR_ANALYSIS = "READY_FOR_ANALYSIS"
ANALYZING = "ANALYZING"
ANALYSIS_COMPLETE = "ANALYSIS_COMPLETE"
STALE = "STALE"
CLOSED = "CLOSED"

ALL_STATES = (
    DRAFT, UPLOADING, PROCESSING, REVIEW_REQUIRED, READY_FOR_ANALYSIS,
    ANALYZING, ANALYSIS_COMPLETE, STALE, CLOSED,
)

# the documented happy path, for display + tests
HAPPY_PATH = (
    DRAFT, UPLOADING, PROCESSING, REVIEW_REQUIRED, READY_FOR_ANALYSIS,
    ANALYZING, ANALYSIS_COMPLETE,
)

# allowed transitions (from -> set of to). CLOSED is reachable from
# anywhere; everything else is strictly the documented flow.
_TRANSITIONS: dict[str, frozenset[str]] = {
    DRAFT: frozenset({UPLOADING, CLOSED}),
    UPLOADING: frozenset({PROCESSING, DRAFT, CLOSED}),
    PROCESSING: frozenset({REVIEW_REQUIRED, READY_FOR_ANALYSIS, DRAFT, CLOSED}),
    # a new upload while candidates are pending (or the case is ready)
    # sends the case back through processing for the new document
    REVIEW_REQUIRED: frozenset({REVIEW_REQUIRED, READY_FOR_ANALYSIS,
                                PROCESSING, CLOSED}),
    READY_FOR_ANALYSIS: frozenset({ANALYZING, STALE, PROCESSING, CLOSED}),
    ANALYZING: frozenset({ANALYSIS_COMPLETE, READY_FOR_ANALYSIS, CLOSED}),
    ANALYSIS_COMPLETE: frozenset({STALE, CLOSED}),
    # stale by a new upload -> process it; stale by new confirmations
    # (data moved on) -> recalculate directly
    STALE: frozenset({PROCESSING, ANALYZING, CLOSED}),
    CLOSED: frozenset(),
}


def allowed_next(state: str) -> tuple[str, ...]:
    """The states ``state`` may legally move to (stable tuple)."""
    return tuple(sorted(_TRANSITIONS.get(state, frozenset())))


def is_valid_transition(src: str, dst: str) -> bool:
    if src == dst:
        return True  # idempotent re-application
    return dst in _TRANSITIONS.get(src, frozenset())


def transition(db: Session, case: Case, dst: str,
               audit: bool = True) -> str:
    """Move ``case.workflow_state`` to ``dst`` if the transition is legal.

    Raises ``ApiError(INVALID_STATE_TRANSITION, 409)`` for anything the
    table does not allow. An idempotent re-application (dst == current)
    commits nothing and returns the state.
    """
    if dst not in ALL_STATES:
        raise ApiError("UNKNOWN_STATE", f"Unknown workflow state: {dst!r}", 409)
    # Re-read the current state from the database. Callers may hold a
    # stale in-memory Case (long-lived sessions run with
    # ``expire_on_commit=False``) and another worker may have moved the
    # case concurrently — the database row is the only trustworthy
    # source for the guard.
    from sqlalchemy import select
    fresh = db.execute(
        select(Case.workflow_state).where(Case.id == case.id)
    ).scalar_one_or_none()
    src = (fresh if fresh is not None else case.workflow_state) or DRAFT
    if src == dst:
        return src
    if not is_valid_transition(src, dst):
        raise ApiError(
            "INVALID_STATE_TRANSITION",
            f"Case is in state {src}; transition to {dst} is not allowed "
            f"(allowed: {', '.join(allowed_next(src)) or 'none — closed'})", 409)
    case.workflow_state = dst
    if audit:
        from .auth_service import record_audit
        record_audit(db, None, "CASE_STATE_TRANSITION", "case", str(case.id),
                     metadata={"from": src, "to": dst})
        db.commit()
    return dst


def require_state(case: Case, *states: str) -> None:
    """409 unless the case is in one of ``states``."""
    if case.workflow_state not in states:
        raise ApiError(
            "WRONG_WORKFLOW_STATE",
            f"Case is in state {case.workflow_state}; this action needs one "
            f"of {', '.join(states)}", 409)
