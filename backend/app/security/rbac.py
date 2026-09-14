"""Role-based authorization for the v1 API.

Four roles, least privilege by default:

    ANALYST       read everything, no writes
    INVESTIGATOR  read + create cases / simulations
    SUPERVISOR    investigator rights + manage users
    ADMIN         everything

Identity is provided by **Supabase Auth**. The dependency `get_current_user`
verifies the Supabase access token on every request, resolves the Supabase
user UUID to the NEXUS user, and reads the NEXUS role **from the database**
(the token alone is not trusted to carry authority, and a client can never
grant itself a role). The `require_roles` factory enforces the role matrix
per route.
"""

from __future__ import annotations

import logging
import uuid as _uuid
from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db, require_db
from ..core.errors import forbidden, unauthenticated
from ..models import User
from .supabase_auth import verify_supabase_bearer

logger = logging.getLogger("nexus.rbac")
_ROLES = {"ANALYST", "INVESTIGATOR", "SUPERVISOR", "ADMIN"}

# Privilege ladder: a role can do what every lower role can do.
_LADDER = ["ANALYST", "INVESTIGATOR", "SUPERVISOR", "ADMIN"]


@dataclass
class CurrentUser:
    user: User
    payload: dict    # the verified Supabase JWT claims


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> CurrentUser:
    require_db(db)
    # Verify token and extract claims
    claims = verify_supabase_bearer(authorization)
    # Extract sub (Supabase user UUID) from claims
    sub_val = claims.get('sub')
    logger.debug('JWT sub claim: %s', sub_val)
    try:
        sub_uuid = _uuid.UUID(str(sub_val)) if sub_val else None
    except (ValueError, TypeError):
        sub_uuid = None
    logger.debug('Parsed sub UUID: %s', sub_uuid)
    if sub_uuid is None:
        unauthenticated()
    # DB lookup
    user = db.scalars(select(User).where(User.supabase_id == sub_uuid)).first()
    if user is None and claims.get("email"):
        email = claims.get("email")
        user = db.scalars(select(User).where(User.email == email)).first()
        if user is not None:
            user.supabase_id = sub_uuid
            db.commit()
            db.refresh(user)
            logger.info("Linked existing user profile (%s) to Supabase UUID %s", email, sub_uuid)

    if user is None and claims.get("email"):
        email = claims.get("email")
        user_meta = claims.get("user_metadata") or {}
        name = user_meta.get("full_name") or user_meta.get("name") or (email.split("@")[0] if email else "Investigator")
        user = User(
            supabase_id=sub_uuid,
            email=email,
            name=name,
            role="INVESTIGATOR",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("Auto-provisioned NEXUS profile for Supabase UUID %s (%s)", sub_uuid, email)

    logger.debug('User lookup result: %s', 'found' if user else 'none')
    if user is None or not user.is_active:
        unauthenticated()
    return CurrentUser(user=user, payload=claims)


def _meets(user_role: str, required: set[str]) -> bool:
    if not required:
        return True
    try:
        floor = _LADDER.index(user_role)
    except ValueError:
        return False
    return any(r in _ROLES and _LADDER.index(r) <= floor for r in required)


def require_roles(*roles: str):
    """Route dependency: allow if the caller's role is in `roles` (or higher)."""

    def _check(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not _meets(current.user.role, set(roles)):
            forbidden(", ".join(sorted(roles)))
        return current

    return _check


def require_admin(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return require_roles("ADMIN")(current)


def require_supervisor(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return require_roles("SUPERVISOR")(current)
