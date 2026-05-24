"""league sync target table.

Revision ID: 0009_league_sync_target
Revises: 0008_coach_translation
Create Date: 2026-05-20 06:40:00 +09:00

Stores the ADMIN-selected API-Football league/season combinations that the
daily-sync worker should crawl.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_league_sync_target"
down_revision: Union[str, None] = "0008_coach_translation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "league_sync_target",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "league_id",
            sa.BigInteger(),
            sa.ForeignKey("league.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("season_year", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("include_details", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("include_players", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("include_standings", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("fixture_limit", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("season_year >= 1900", name="league_sync_target_season_year_check"),
        sa.CheckConstraint(
            "fixture_limit IS NULL OR fixture_limit > 0",
            name="league_sync_target_fixture_limit_check",
        ),
        sa.UniqueConstraint("league_id", "season_year", name="league_sync_target_league_season_uq"),
    )
    op.create_index(
        "league_sync_target_active_idx",
        "league_sync_target",
        ["is_active", "league_id", "season_year"],
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("league_sync_target_active_idx", table_name="league_sync_target")
    op.drop_table("league_sync_target")
