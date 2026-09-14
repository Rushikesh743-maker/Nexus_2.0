"""Shared pagination for list endpoints (phase 1 performance work).

Contract (deliberately backward compatible):

* Without query parameters the endpoint returns the full list — exactly
  the stage-6/7 contract the front end and tests rely on.
* With ``limit`` (and optional ``offset``) the endpoint returns that
  slice of the list.
* ``X-Total-Count`` is always sent, so a client knows how many items
  exist beyond the page it received; ``X-Offset`` / ``X-Limit`` echo the
  applied window when one was requested.

The body shape is always a plain JSON array — pagination is opt-in, so no
existing consumer changes.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Response

MAX_LIMIT = 1000

# Reusable Query defaults (FastAPI inspects the signature values).
LIMIT_QUERY = Query(default=None, ge=1, le=MAX_LIMIT)
OFFSET_QUERY = Query(default=None, ge=0)


def apply_pagination(items: list[Any], limit: int | None,
                     offset: int | None, response: Response) -> list[Any]:
    """Set the pagination headers and return the (possibly sliced) list."""
    response.headers["X-Total-Count"] = str(len(items))
    if limit is None:
        return items
    lo = max(offset or 0, 0)
    response.headers["X-Offset"] = str(lo)
    response.headers["X-Limit"] = str(limit)
    return items[lo:lo + limit]
