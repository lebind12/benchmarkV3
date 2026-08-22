"""add curated team brand colors and seed the 2026/27 EPL clubs.

Revision ID: 0015_team_color
Revises: 0014_broadcast_momentum_state
Create Date: 2026-08-22 00:00:00 +09:00
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_team_color"
down_revision: Union[str, None] = "0014_broadcast_momentum_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VERIFIED_AT = datetime(2026, 8, 22, tzinfo=timezone(timedelta(hours=9)))

TEAM_COLOR_SEEDS: list[dict[str, Any]] = [
    {
        "external_id": 42,
        "primary_color": "#EF0107",
        "secondary_color": "#063672",
        "accent_color": "#9C824A",
        "source_url": "https://teamcolorcodes.com/arsenal-color-codes/",
    },
    {
        "external_id": 66,
        "primary_color": "#670E36",
        "secondary_color": "#95BFE5",
        "accent_color": "#FEE505",
        "source_url": "https://teamcolorcodes.com/aston-villa-fc-color-codes/",
    },
    {
        "external_id": 35,
        "primary_color": "#DA291C",
        "secondary_color": "#000000",
        "accent_color": "#EFDBB2",
        "source_url": "https://teamcolorcodes.com/afc-bournemouth-color-codes/",
    },
    {
        "external_id": 55,
        "primary_color": "#C10000",
        "secondary_color": "#000000",
        "accent_color": "#FFB81C",
        "source_url": "https://www.clubcolorcodes.com/",
    },
    {
        "external_id": 51,
        "primary_color": "#0057B8",
        "secondary_color": "#FFCD00",
        "accent_color": "#FFFFFF",
        "source_url": "https://teamcolorcodes.com/brighton-hove-albion-colors/",
    },
    {
        "external_id": 49,
        "primary_color": "#034694",
        "secondary_color": "#DBA111",
        "accent_color": "#EE242C",
        "source_url": "https://teamcolorcodes.com/chelsea-color-codes/",
    },
    {
        "external_id": 1346,
        "primary_color": "#059DD9",
        "secondary_color": "#FFFFFF",
        "accent_color": None,
        "source_url": "https://teamcolorcodes.com/coventry-city-f-c-color-codes/",
    },
    {
        "external_id": 52,
        "primary_color": "#1B458F",
        "secondary_color": "#C4122E",
        "accent_color": "#A7A5A6",
        "source_url": "https://teamcolorcodes.com/crystal-palace-fc-colors/",
    },
    {
        "external_id": 45,
        "primary_color": "#003399",
        "secondary_color": "#FFFFFF",
        "accent_color": None,
        "source_url": "https://teamcolorcodes.com/everton-fc-colors/",
    },
    {
        "external_id": 36,
        "primary_color": "#000000",
        "secondary_color": "#CC0000",
        "accent_color": "#FFFFFF",
        "source_url": "https://teamcolorcodes.com/fulham-fc-color-codes/",
    },
    {
        "external_id": 64,
        "primary_color": "#F18A01",
        "secondary_color": "#000000",
        "accent_color": "#FFFFFF",
        "source_url": "https://teamcolorcodes.com/hull-city-a-f-c-color-codes/",
    },
    {
        "external_id": 57,
        "primary_color": "#123D88",
        "secondary_color": "#E40520",
        "accent_color": "#FFFFFF",
        "source_url": "https://football-logos.cc/england/ipswich/",
    },
    {
        "external_id": 63,
        "primary_color": "#1D428A",
        "secondary_color": "#FFCD00",
        "accent_color": "#FFFFFF",
        "source_url": "https://teamcolorcodes.com/leeds-united-football-club-colors/",
    },
    {
        "external_id": 40,
        "primary_color": "#C8102E",
        "secondary_color": "#F6EB61",
        "accent_color": "#00B2A9",
        "source_url": "https://teamcolorcodes.com/liverpool-fc-colors/",
    },
    {
        "external_id": 50,
        "primary_color": "#6CABDD",
        "secondary_color": "#1C2C5B",
        "accent_color": "#FFC659",
        "source_url": "https://teamcolorcodes.com/manchester-city-fc-colors/",
    },
    {
        "external_id": 33,
        "primary_color": "#DA291C",
        "secondary_color": "#FBE122",
        "accent_color": "#000000",
        "source_url": "https://teamcolorcodes.com/manchester-united-colors/",
    },
    {
        "external_id": 34,
        "primary_color": "#241F20",
        "secondary_color": "#FFFFFF",
        "accent_color": "#F1BE48",
        "source_url": "https://teamcolorcodes.com/newcastle-united-fc-colors/",
    },
    {
        "external_id": 65,
        "primary_color": "#DD0000",
        "secondary_color": "#FFFFFF",
        "accent_color": None,
        "source_url": "https://teamcolorcodes.com/nottingham-forest-f-c-color-codes/",
    },
    {
        "external_id": 746,
        "primary_color": "#EB172B",
        "secondary_color": "#211E1E",
        "accent_color": "#A68A26",
        "source_url": "https://www.clubcolorcodes.com/",
    },
    {
        "external_id": 47,
        "primary_color": "#132257",
        "secondary_color": "#FFFFFF",
        "accent_color": None,
        "source_url": "https://teamcolorcodes.com/tottenham-hotspur-colors/",
    },
]


def upgrade() -> None:
    op.create_table(
        "team_color",
        sa.Column(
            "id", sa.BigInteger(), sa.Identity(always=True), primary_key=True
        ),
        sa.Column(
            "team_id",
            sa.BigInteger(),
            sa.ForeignKey("team.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("primary_color", sa.String(length=7), nullable=False),
        sa.Column("secondary_color", sa.String(length=7)),
        sa.Column("accent_color", sa.String(length=7)),
        sa.Column("source_url", sa.Text()),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("team_id", name="team_color_team_id_key"),
        sa.CheckConstraint(
            "primary_color ~ '^#[0-9A-Fa-f]{6}$'",
            name="team_color_primary_hex_check",
        ),
        sa.CheckConstraint(
            "secondary_color IS NULL OR secondary_color ~ '^#[0-9A-Fa-f]{6}$'",
            name="team_color_secondary_hex_check",
        ),
        sa.CheckConstraint(
            "accent_color IS NULL OR accent_color ~ '^#[0-9A-Fa-f]{6}$'",
            name="team_color_accent_hex_check",
        ),
    )

    seed_rows = [{**row, "verified_at": VERIFIED_AT} for row in TEAM_COLOR_SEEDS]
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO team_color (
                team_id, primary_color, secondary_color, accent_color,
                source_url, verified_at
            )
            SELECT
                t.id, :primary_color, :secondary_color, :accent_color,
                :source_url, :verified_at
            FROM team t
            WHERE t.external_id = :external_id
            ON CONFLICT (team_id) DO UPDATE SET
                primary_color = EXCLUDED.primary_color,
                secondary_color = EXCLUDED.secondary_color,
                accent_color = EXCLUDED.accent_color,
                source_url = EXCLUDED.source_url,
                verified_at = EXCLUDED.verified_at,
                updated_at = now()
            """
        ),
        seed_rows,
    )


def downgrade() -> None:
    op.drop_table("team_color")
