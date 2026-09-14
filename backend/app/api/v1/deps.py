"""Shared dependencies for the v1 API."""

from __future__ import annotations

from typing import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from ...core.database import get_db, require_db


def get_db_checked(db: Session = Depends(get_db)) -> Iterator[Session]:
    """Session dependency that fails with a structured 503 when the
    platform database is down — instead of leaking a connection error."""
    require_db(db)
    yield db
