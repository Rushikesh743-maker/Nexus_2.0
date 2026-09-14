"""0002 - phase 2 investigation intelligence.

Changes (all additive or compatibility-preserving; nothing is dropped):

* ``case_snapshot`` — new table for immutable investigation snapshots
  (case versions) with per-case ``sequence``.
* ``entity_match_suggestion`` — a candidate may now carry several RANKED
  match suggestions: the unique index on ``candidate_id`` becomes a plain
  index and a ``rank`` column (1 = best) is added. Existing rows keep
  their meaning (they become rank 1).

Idempotency: every step checks current state first, so re-running this
revision on an already-migrated database is a no-op.

Downgrade: drops the snapshot table and the rank column and restores the
unique index (only safe while at most one suggestion per candidate exists).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_SNAPSHOT_TABLE = "case_snapshot"
_SUGGESTION_TABLE = "entity_match_suggestion"
_OLD_UNIQUE_INDEX = "ix_entity_match_suggestion_candidate_id"
_NEW_INDEX = "ix_entity_match_suggestion_candidate_id_rank"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column
               for c in _inspector().get_columns(table))


def _index_names(table: str) -> set:
    return {ix["name"] for ix in _inspector().get_indexes(table)}


def upgrade() -> None:
    # ---- case_snapshot ----------------------------------------------------
    if not _has_table(_SNAPSHOT_TABLE):
        op.create_table(
            _SNAPSHOT_TABLE,
            sa.Column("id", sa.Integer(), autoincrement=True,
                      nullable=False),
            sa.Column("case_id", sa.Integer(), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("label", sa.String(length=255), nullable=True),
            sa.Column("graph_version", sa.String(length=32), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("entity_count", sa.Integer(),
                      server_default="0", nullable=False),
            sa.Column("relationship_count", sa.Integer(),
                      server_default="0", nullable=False),
            sa.Column("evidence_count", sa.Integer(),
                      server_default="0", nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["case_id"], ["case.id"],
                                    ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["user.id"],
                                    ondelete="SET NULL"),
            sa.UniqueConstraint("case_id", "sequence",
                                name="uq_case_snapshot_case_sequence"),
        )
        op.create_index(op.f("ix_case_snapshot_case_id"), _SNAPSHOT_TABLE,
                        ["case_id"])
        op.create_index(op.f("ix_case_snapshot_graph_version"),
                        _SNAPSHOT_TABLE, ["graph_version"])

    # ---- entity_match_suggestion: ranked multi-suggestions ----------------
    if _has_table(_SUGGESTION_TABLE):
        if not _has_column(_SUGGESTION_TABLE, "rank"):
            op.add_column(_SUGGESTION_TABLE,
                          sa.Column("rank", sa.Integer(), nullable=False,
                                    server_default="1"))
        # unique index -> plain index (several ranked rows per candidate)
        if _OLD_UNIQUE_INDEX in _index_names(_SUGGESTION_TABLE):
            op.drop_index(_OLD_UNIQUE_INDEX, table_name=_SUGGESTION_TABLE)
        if _NEW_INDEX not in _index_names(_SUGGESTION_TABLE):
            op.create_index(_NEW_INDEX, _SUGGESTION_TABLE,
                            ["candidate_id", "rank"], unique=True)


def downgrade() -> None:
    # Restore the single-suggestion shape (safe only with <=1 row/candidate).
    if _has_table(_SUGGESTION_TABLE):
        if _NEW_INDEX in _index_names(_SUGGESTION_TABLE):
            op.drop_index(_NEW_INDEX, table_name=_SUGGESTION_TABLE)
        if _OLD_UNIQUE_INDEX not in _index_names(_SUGGESTION_TABLE):
            op.create_index(_OLD_UNIQUE_INDEX, _SUGGESTION_TABLE,
                            ["candidate_id"], unique=True)
        if _has_column(_SUGGESTION_TABLE, "rank"):
            op.drop_column(_SUGGESTION_TABLE, "rank")
    if _has_table(_SNAPSHOT_TABLE):
        op.drop_index(op.f("ix_case_snapshot_graph_version"),
                      table_name=_SNAPSHOT_TABLE)
        op.drop_index(op.f("ix_case_snapshot_case_id"),
                      table_name=_SNAPSHOT_TABLE)
        op.drop_table(_SNAPSHOT_TABLE)
