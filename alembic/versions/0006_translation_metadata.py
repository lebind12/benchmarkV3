"""translation provenance metadata.

Revision ID: 0006_translation_metadata
Revises: 0005_fixture_detail_players
Create Date: 2026-05-19 17:00:00 +09:00

Adds source/verified metadata columns to translation tables. Backfill
curation can mark researched Korean names as verified while operational
translation-filler rows can remain unverified.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_translation_metadata"
down_revision: Union[str, None] = "0005_fixture_detail_players"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table_name in ("league_translation", "team_translation", "player_translation"):
        op.add_column(table_name, sa.Column("source", sa.Text()))
        op.add_column(
            table_name,
            sa.Column(
                "verified",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    for table_name in ("player_translation", "team_translation", "league_translation"):
        op.drop_column(table_name, "verified")
        op.drop_column(table_name, "source")
