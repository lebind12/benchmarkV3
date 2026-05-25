"""add worker sync log origin metadata.

Revision ID: 0013_worker_sync_log_origin
Revises: 0012_worker_sync_log
Create Date: 2026-05-26 05:10:00 +09:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_worker_sync_log_origin"
down_revision: Union[str, None] = "0012_worker_sync_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "worker_sync_log",
        sa.Column("origin", postgresql.JSONB(astext_type=sa.Text())),
    )


def downgrade() -> None:
    op.drop_column("worker_sync_log", "origin")
