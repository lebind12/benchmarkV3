"""coach translation tables.

Revision ID: 0008_coach_translation
Revises: 0007_remove_translation_metadata
Create Date: 2026-05-19 19:00:00 +09:00

Stores coaches as first-class entities so lineup/club pages can display
Korean coach names without mixing staff rows into player tables.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_coach_translation"
down_revision: Union[str, None] = "0007_remove_translation_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coach",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("external_id", sa.Integer(), unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("photo_url", sa.Text()),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("coach_slug_idx", "coach", ["slug"], unique=True)

    op.create_table(
        "coach_translation",
        sa.Column(
            "coach_id",
            sa.BigInteger(),
            sa.ForeignKey("coach.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("name_ko", sa.Text()),
        sa.Column("short_name_ko", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "team_coach",
        sa.Column(
            "team_id",
            sa.BigInteger(),
            sa.ForeignKey("team.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "coach_id",
            sa.BigInteger(),
            sa.ForeignKey("coach.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("league_id", sa.BigInteger(), sa.ForeignKey("league.id", ondelete="SET NULL")),
        sa.Column("season_year", sa.Integer()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("team_id", "coach_id"),
    )
    op.create_index("team_coach_team_last_seen_idx", "team_coach", ["team_id", "last_seen_at"])
    op.create_index("team_coach_league_season_idx", "team_coach", ["league_id", "season_year"])


def downgrade() -> None:
    op.drop_index("team_coach_league_season_idx", table_name="team_coach")
    op.drop_index("team_coach_team_last_seen_idx", table_name="team_coach")
    op.drop_table("team_coach")
    op.drop_table("coach_translation")
    op.drop_index("coach_slug_idx", table_name="coach")
    op.drop_table("coach")
