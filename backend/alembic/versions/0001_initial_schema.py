"""0001 - initial schema (bootstrap).

This is the FIRST migration, adopting a schema that already existed (it was
previously created with ``Base.metadata.create_all`` plus a set of startup
column migrations). To make it work on BOTH a fresh database and an existing
one — without ever destroying data — it is deliberately idempotent:

* ``Base.metadata.create_all`` creates any missing tables and is a no-op for
  tables that already exist (it never alters or drops).
* ``_ensure_columns`` adds any legacy columns a pre-existing table may be
  missing (again, no-op when the columns are already present).

Running it twice, on a fresh DB, or on a data-filled DB, all converge to the
same schema with no data loss. All schema changes FROM HERE ON are ordinary
Alembic migrations (use ``alembic revision --autogenerate``).

Downgrade is intentionally a safe no-op: undoing the *initial* migration
would mean dropping the entire schema, which conflicts with the
never-destroy-data rule.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _bootstrap(conn: sa.engine.Connection) -> None:
    # Import the models so every table is registered on Base.metadata, then
    # import the shared column-migration helpers from the application.
    from app.core.database import Base, _ensure_columns
    from app.models import models  # noqa: F401  (register tables)

    # Idempotent: creates missing tables, leaves existing ones untouched.
    Base.metadata.create_all(conn)
    applied = _ensure_columns(conn)
    if applied:
        op.logger.info(
            "0001 bootstrap: ensured legacy columns %s", ", ".join(applied))


def upgrade() -> None:
    bind = op.get_bind()
    _bootstrap(bind)


def downgrade() -> None:
    # Safe no-op on purpose — see module docstring. Undoing the initial
    # migration would drop the whole schema, which we never do automatically.
    op.logger.warning(
        "0001 downgrade is a no-op: the initial schema is not rolled back "
        "to protect existing data.")
