"""GET /api/v1/users — personnel directory (supervisor and above)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.errors import not_found
from ...models import User
from ...schemas.v1 import UserOut
from ...security.rbac import CurrentUser, require_supervisor
from ...services.auth_service import record_audit
from .deps import get_db_checked

logger = logging.getLogger("nexus.api.users")
router = APIRouter(prefix="/users", tags=["users"])


def _to_out(user) -> UserOut:
    return UserOut.model_validate(user)


@router.get("", response_model=list[UserOut], summary="List users (SUPERVISOR+)")
def list_users(db: Session = Depends(get_db_checked),
               current: CurrentUser = Depends(require_supervisor)) -> list[UserOut]:
    users = db.scalars(select(User).order_by(User.name)).all()
    record_audit(db, current, "LIST_USERS", "user", str(len(users)))
    return [_to_out(u) for u in users]


@router.get("/{user_id}", response_model=UserOut, summary="One user (SUPERVISOR+)")
def get_user(user_id: int, db: Session = Depends(get_db_checked),
             current: CurrentUser = Depends(require_supervisor)) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        not_found("USER_NOT_FOUND", "No user with this id.")
    return _to_out(user)
