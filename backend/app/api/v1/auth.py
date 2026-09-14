"""GET /api/v1/auth/me — the authenticated NEXUS profile.

There is no ``/login`` endpoint: authentication happens against **Supabase
Auth** from the React client (email/password, session, refresh). The
frontend then calls this endpoint with the Supabase access token, and the
backend verifies it, resolves the Supabase user UUID to the NEXUS user, and
returns the NEXUS profile + role. The role always comes from the database —
never from the token or the client.

Registration is intentionally not a public endpoint. NEXUS is a controlled
investigator platform: accounts are provisioned through Supabase Auth (Admin
→ Authentication → Users) and mapped to a NEXUS user/role server-side (see
README → "Creating NEXUS users"). A new identity without a NEXUS profile is
rejected here, which is the safe default (no implicit ADMIN or any role).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.database import get_db, require_db
from ...schemas.v1 import UserOut
from ...security.rbac import CurrentUser, get_current_user
from ...services.auth_service import record_audit

logger = logging.getLogger("nexus.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserOut, summary="The authenticated user")
def me(current: CurrentUser = Depends(get_current_user),
       db: Session = Depends(get_db)) -> UserOut:
    require_db(db)
    record_audit(db, current, "AUTH_ME", "user", str(current.user.id))
    return UserOut.model_validate(current.user)
