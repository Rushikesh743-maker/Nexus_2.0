"""Stage 7 — per-case access control.

The platform's documented role matrix (stage 1) is:

    ANALYST       read everything, no writes
    INVESTIGATOR  read + create cases / simulations
    SUPERVISOR    investigator rights + manage users
    ADMIN         everything

Stage 7 makes the case *ownership* part of that matrix explicit:

* **SUPERVISOR / ADMIN** — every case.
* **ANALYST** — read access to every case (the documented read-only
  platform access); every write is still role-forbidden (403) exactly as
  before.
* **INVESTIGATOR** — the cases they created, and nothing else.

Platform/seeded cases (``created_by IS NULL`` — the reproducible
demonstration data, seeded on behalf of the platform) are accessible to
every authenticated user.

Denied investigators get **404 CASE_NOT_FOUND** (the case's existence,
title and counts are never leaked — not via read, upload, review, graph,
analysis, copilot or audit). Case lists are filtered the same way, so
``GET /cases`` does not leak other people's cases either.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.errors import not_found
from ..models import Case, User
from ..security.rbac import CurrentUser

_FULL_ACCESS = ("SUPERVISOR", "ADMIN")


def can_access_case(case: Case, user: User) -> bool:
    if user.role in _FULL_ACCESS:
        return True
    if user.role == "ANALYST":
        return True  # documented read-only platform access
    if case.created_by is None:
        return True  # platform/seeded case — shared demonstration data
    return case.created_by == user.id


def require_case_access(db: Session, case_id: int,
                        current: CurrentUser) -> Case:
    """Fetch a case and enforce case access — 404 (not 403) when the
    caller has no access, so existence is not leaked."""
    case = db.get(Case, case_id)
    if case is None:
        not_found("CASE_NOT_FOUND", f"Case {case_id} does not exist.")
    if not can_access_case(case, current.user):
        not_found("CASE_NOT_FOUND", f"Case {case_id} does not exist.")
    return case


def accessible_case_ids(db: Session, user: User) -> list[int] | None:
    """None = no restriction (supervisor/admin/analyst); otherwise the
    user's own cases plus the platform cases (created_by IS NULL)."""
    if user.role in _FULL_ACCESS or user.role == "ANALYST":
        return None
    return [c.id for c in db.scalars(
        select(Case).where((Case.created_by == user.id)
                           | (Case.created_by.is_(None)))).all()]
