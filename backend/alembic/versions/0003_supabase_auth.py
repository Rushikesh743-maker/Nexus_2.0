"""0003 - Supabase Auth identity mapping.

Changes:

* ``user.supabase_id`` — new column (UUID, unique, nullable, indexed)
  mapping the Supabase Auth user (``auth.users.id``) to the NEXUS record.
  This is the stable identity used to resolve a verified Supabase token to
  a NEXUS user. NULL marks a row that is not a Supabase-backed login
  identity (e.g. the synthetic-data seed owner), which therefore can never
  authenticate.
* ``user.password_hash`` — **dropped**. NEXUS no longer performs
  password-based authentication (Supabase Auth owns credentials) and must
  not store passwords. This is the one non-additive step in the migration;
  any pre-existing demo password hashes are removed with it.

Idempotency: every step checks current state first, so re-running this
revision on an already-migrated database is a no-op.

Downgrade: re-adds ``password_hash`` (nullable — the original hashes are
gone) and drops ``supabase_id``.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_USER_TABLE = "user"
_SUPABASE_ID = "supabase_id"
_PASSWORD_HASH = "password_hash"
_SUPABASE_ID_INDEX = "ix_user_supabase_id"
_SUPABASE_ID_UNIQUE = "uq_user_supabase_id"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_column(column: str) -> bool:
    return any(c["name"] == column
               for c in _inspector().get_columns(_USER_TABLE))


def _index_names() -> set:
    return {ix["name"] for ix in _inspector().get_indexes(_USER_TABLE)}


def upgrade() -> None:
    # ---- add user.supabase_id -------------------------------------------
    if not _has_column(_SUPABASE_ID):
        op.add_column(
            _USER_TABLE,
            sa.Column(_SUPABASE_ID, sa.Uuid(as_uuid=True), nullable=True),
        )
    if _SUPABASE_ID_UNIQUE not in _index_names():
        op.create_index(_SUPABASE_ID_UNIQUE, _USER_TABLE, [_SUPABASE_ID],
                        unique=True)
    if _SUPABASE_ID_INDEX not in _index_names():
        op.create_index(_SUPABASE_ID_INDEX, _USER_TABLE, [_SUPABASE_ID])

    # ---- drop user.password_hash ----------------------------------------
    if _has_column(_PASSWORD_HASH):
        op.drop_column(_USER_TABLE, _PASSWORD_HASH)


def downgrade() -> None:
    if _has_column(_PASSWORD_HASH):
        pass
    else:
        op.add_column(
            _USER_TABLE,
            sa.Column(_PASSWORD_HASH, sa.String(length=255), nullable=True),
        )
    if _SUPABASE_ID_INDEX in _index_names():
        op.drop_index(_SUPABASE_ID_INDEX, table_name=_USER_TABLE)
    if _SUPABASE_ID_UNIQUE in _index_names():
        op.drop_index(_SUPABASE_ID_UNIQUE, table_name=_USER_TABLE)
    if _has_column(_SUPABASE_ID):
        op.drop_column(_USER_TABLE, _SUPABASE_ID)
