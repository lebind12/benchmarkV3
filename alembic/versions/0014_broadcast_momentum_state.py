"""persist broadcast momentum redis state.

Revision ID: 0014_broadcast_momentum_state
Revises: 0013_worker_sync_log_origin
Create Date: 2026-06-14 09:35:00 +09:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_broadcast_momentum_state"
down_revision: Union[str, None] = "0013_worker_sync_log_origin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "broadcast_momentum_state",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("fixture_external_id", sa.Integer(), nullable=False),
        sa.Column("redis_key_prefix", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_state", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("samples", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("latest", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latest_updated_at", sa.DateTime(timezone=True)),
        sa.Column("last_captured_at", sa.DateTime(timezone=True)),
        sa.Column("persisted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "fixture_external_id",
            "redis_key_prefix",
            name="broadcast_momentum_state_fixture_prefix_key",
        ),
    )
    op.create_index(
        "broadcast_momentum_state_fixture_idx",
        "broadcast_momentum_state",
        ["fixture_external_id"],
    )
    op.create_index(
        "broadcast_momentum_state_persisted_idx",
        "broadcast_momentum_state",
        ["persisted_at"],
    )


def downgrade() -> None:
    op.drop_index("broadcast_momentum_state_persisted_idx", table_name="broadcast_momentum_state")
    op.drop_index("broadcast_momentum_state_fixture_idx", table_name="broadcast_momentum_state")
    op.drop_table("broadcast_momentum_state")
