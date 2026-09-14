"""Database setup for the platform layer (PostgreSQL via SQLAlchemy 2.0).

The analysis pipeline (backend/app/graph, pipeline, intelligence) stores
nothing in the relational database; this module exists for the application
data layer — users, cases, documents, entities, evidence and the rest of
the models in `app.models`.

Schema management (phase 1): **Alembic is the schema authority**. At
startup `init_database` runs `alembic upgrade head` in-process — a no-op
when the schema is already at head, and the real migration path when new
revisions have been deployed. The very first revision (0001) is an
idempotent bootstrap, so this works on a fresh database *and* on a
pre-existing one without destroying data. The legacy `create_all` +
`_COLUMN_MIGRATIONS` path remains only as a fallback for environments
where the alembic package is missing (it is a declared dependency).

The engine is created lazily and connection health is checked at startup
(`init_database`), so the whole application still starts when PostgreSQL
is not running: the v1 API then answers with a structured 503 instead of
crashing, and the legacy /api analysis surface is unaffected.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

logger = logging.getLogger("nexus.database")


class Base(DeclarativeBase):
    """Declarative base for all platform models."""


def _engine():
    settings = get_settings()
    url = settings.database_url
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False}, echo=False)
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": 3},
        echo=False,
    )


# Created at import time but only *used* after init_database() succeeds;
# lazy pool means no connection is opened until the first query.
engine = _engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

_db_ready = False


def db_ready() -> bool:
    return _db_ready


# (table, column, DDL type) — columns added to pre-existing tables after
# stage 1 shipped. create_all creates missing TABLES but cannot ALTER an
# existing one, so these are applied idempotently at startup. New installs
# get them from the model definitions anyway.
_COLUMN_MIGRATIONS = [
    ("document", "mime_type", "VARCHAR(128)"),
    ("document", "storage_path", "VARCHAR(512)"),
    ("document", "sha256", "VARCHAR(64)"),
    ("document", "uploaded_by", 'INTEGER REFERENCES "user"(id) ON DELETE SET NULL'),
    ("document", "processed_at", "TIMESTAMPTZ"),
    ("document", "processing_error", "TEXT"),
    # stage 5: multilingual provenance
    ("document", "language_confidence", "FLOAT"),
    ("document", "translation_status", "VARCHAR(24)"),
    ("document", "processing_method", "VARCHAR(64)"),
    ("document_extraction", "original_text", "TEXT"),
    ("document_extraction", "normalized_text", "TEXT"),
    ("document_extraction", "language", "VARCHAR(16)"),
    ("document_extraction", "language_confidence", "FLOAT"),
    ("document_extraction", "claims", "JSON"),
    # stage 7: case lifecycle + processing provenance
    ("case", "workflow_state", "VARCHAR(32) DEFAULT 'DRAFT'"),
    ("case", "last_analysis_at", "TIMESTAMPTZ"),
    ("document", "processing_started_at", "TIMESTAMPTZ"),
    ("document", "processing_seconds", "FLOAT"),
    ("document", "page_count", "INTEGER"),
]


def _ensure_columns(conn) -> list[str]:
    applied = []
    is_sqlite = conn.dialect.name == "sqlite"
    for table, column, ddl in _COLUMN_MIGRATIONS:
        if is_sqlite:
            cols = [r[1] for r in conn.execute(text(f"PRAGMA table_info('{table}')")).fetchall()]
            exists = column in cols
        else:
            exists = conn.execute(
                text("SELECT 1 FROM information_schema.columns "
                     "WHERE table_name = :t AND column_name = :c"),
                {"t": table, "c": column},
            ).first() is not None
        if not exists:
            sqlite_ddl = ddl.split("REFERENCES")[0].strip() if is_sqlite else ddl
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sqlite_ddl}'))
            applied.append(f"{table}.{column}")
    return applied


def _alembic_script_location() -> str:
    """Absolute path to the alembic/ directory (a sibling of app/)."""
    base = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    return os.path.join(base, "alembic")


def _apply_migrations() -> str:
    """Bring the schema to the Alembic head revision (idempotent).

    Returns a short description of what happened, for logging/health.
    Raises on real failure — the caller decides how to report it.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", _alembic_script_location())
    # Belt-and-braces: env.py also injects this from the app settings.
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)

    # Capture the revision we are starting from so we can report real work.
    from alembic.runtime.migration import MigrationContext
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        current = ctx.get_current_revision()

    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        head = MigrationContext.configure(conn).get_current_revision()
    return f"{current} -> {head}" if current != head else "at head"


def init_database() -> bool:
    """Verify the connection and bring the schema to the Alembic head.

    Returns True when the platform database is usable. Never raises:
    a missing database must not take down the analysis API.
    """
    global _db_ready
    try:
        from ..models import models as _models  # noqa: F401  (register tables)
        is_sqlite = engine.dialect.name == "sqlite"
        if not is_sqlite:
            with engine.begin() as conn:
                server = conn.execute(text("SELECT version()")).scalar()
        else:
            server = "SQLite 3"

        try:
            migration_summary = _apply_migrations()
        except Exception as mig_exc:  # noqa: BLE001 — reported, not raised
            # Fall back to the legacy create_all path only if alembic
            # itself failed (e.g. package missing). The legacy path is also
            # idempotent and never destroys data.
            logger.warning("Alembic migration failed (%s); using create_all "
                           "fallback.", mig_exc.__class__.__name__)
            with engine.begin() as conn:
                Base.metadata.create_all(conn)
                applied = _ensure_columns(conn)
            if applied:
                logger.info("Schema updated, added columns: %s",
                            ", ".join(applied))
            migration_summary = "create_all fallback"

        logger.info("Platform database connected: %s (schema: %s)",
                    str(server).split(",")[0], migration_summary)
        _db_ready = True
    except Exception as exc:  # noqa: BLE001 — reported, not raised
        logger.warning("Platform database unavailable at startup: %s", exc)
        _db_ready = False
    return _db_ready


def get_db():
    """FastAPI dependency yielding a session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_db(session: Session):
    """Raise a structured 503 when the platform database is down."""
    if not _db_ready:
        from ..core.errors import database_unavailable

        database_unavailable()
