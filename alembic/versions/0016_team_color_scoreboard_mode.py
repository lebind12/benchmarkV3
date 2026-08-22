"""add curated scoreboard color mode to team palettes.

Revision ID: 0016_team_color_scoreboard_mode
Revises: 0015_team_color
Create Date: 2026-08-22 00:00:00 +09:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_team_color_scoreboard_mode"
down_revision: Union[str, None] = "0015_team_color"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Confirmed from the supplied Premier League scoreboard reference. All other
# clubs use the PRIMARY_LIGHT default, including promoted clubs absent from it.
SECONDARY_SCOREBOARD_TEAM_EXTERNAL_IDS = (
    66,   # Aston Villa
    35,   # AFC Bournemouth
    55,   # Brentford
    52,   # Crystal Palace
    63,   # Leeds United
    50,   # Manchester City
    746,  # Sunderland
    47,   # Tottenham Hotspur
)


def upgrade() -> None:
    op.add_column(
        "team_color",
        sa.Column(
            "scoreboard_color_mode",
            sa.String(length=24),
            nullable=False,
            server_default="PRIMARY_LIGHT",
        ),
    )
    op.create_check_constraint(
        "team_color_scoreboard_color_mode_check",
        "team_color",
        "scoreboard_color_mode IN ('PRIMARY_LIGHT', 'SECONDARY')",
    )

    team = sa.table(
        "team",
        sa.column("id", sa.BigInteger()),
        sa.column("external_id", sa.BigInteger()),
    )
    team_color = sa.table(
        "team_color",
        sa.column("team_id", sa.BigInteger()),
        sa.column("scoreboard_color_mode", sa.String(length=24)),
    )
    op.execute(
        sa.update(team_color)
        .where(
            team_color.c.team_id.in_(
                sa.select(team.c.id).where(
                    team.c.external_id.in_(SECONDARY_SCOREBOARD_TEAM_EXTERNAL_IDS)
                )
            )
        )
        .values(scoreboard_color_mode="SECONDARY")
    )


def downgrade() -> None:
    op.drop_constraint(
        "team_color_scoreboard_color_mode_check",
        "team_color",
        type_="check",
    )
    op.drop_column("team_color", "scoreboard_color_mode")
