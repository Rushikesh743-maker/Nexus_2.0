"""Audit helper for the platform.

Authentication itself no longer lives here: identity is provided by Supabase
Auth and verified per-request in ``security.supabase_auth`` /
``security.rbac.get_current_user``. NEXUS stores no passwords and issues no
login tokens. What remains is the audit write used across the API.
"""

from __future__ import annotations

import logging

from ..models import AuditLog
from ..security.rbac import CurrentUser

logger = logging.getLogger("nexus.auth")


def record_audit(db, current: CurrentUser | None, action: str,
                 resource_type: str | None = None,
                 resource_id: str | None = None,
                 metadata: dict | None = None) -> None:
    """Append a row to the platform audit table (best effort).

    The actor is the real authenticated NEXUS user resolved from the verified
    Supabase identity — never a value supplied by the client.
    """
    try:
        db.add(AuditLog(
            user_id=current.user.id if current else None,
            action=action, resource_type=resource_type, resource_id=resource_id,
            meta=metadata,   # attribute is `meta` (column name "metadata")
        ))
        db.commit()
    except Exception as exc:  # noqa: BLE001 — audit must not break the request
        db.rollback()
        logger.warning("Audit write failed for %s: %s", action, exc)
