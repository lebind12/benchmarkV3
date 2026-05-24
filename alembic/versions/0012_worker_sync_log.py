"""worker sync log retention table.

Revision ID: 0012_worker_sync_log
Revises: 0011_api_football_league_catalog
Create Date: 2026-05-24 21:05:00 +09:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_worker_sync_log"
down_revision: Union[str, None] = "0011_api_football_league_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "worker_sync_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("run_id", sa.Text(), nullable=False, unique=True),
        sa.Column("worker_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("total_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_percent", sa.Float(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("duration_seconds", sa.Float()),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("error", sa.Text()),
        sa.Column("logs", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="worker_sync_log_status_check",
        ),
    )
    op.create_index("worker_sync_log_worker_created_idx", "worker_sync_log", ["worker_name", "created_at"])
    op.create_index("worker_sync_log_status_idx", "worker_sync_log", ["status"])


def downgrade() -> None:
    op.drop_index("worker_sync_log_status_idx", table_name="worker_sync_log")
    op.drop_index("worker_sync_log_worker_created_idx", table_name="worker_sync_log")
    op.drop_table("worker_sync_log")
