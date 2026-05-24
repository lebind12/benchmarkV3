"""fixture_detail.players JSONB for fixture player statistics.

Revision ID: 0005_fixture_detail_players
Revises: 0004_h2h_fixture
Create Date: 2026-05-18 22:00:00 +09:00

Stores API-Football ``GET /fixtures/players?fixture={id}`` raw payload for
match-player ratings, minutes, cards, substitutions, and other per-fixture
player statistics. This complements ``events``, ``statistics``, and
``lineups`` already stored on ``fixture_detail``.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_fixture_detail_players"
down_revision: Union[str, None] = "0004_h2h_fixture"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "fixture_detail",
        sa.Column("players", postgresql.JSONB(astext_type=sa.Text())),
    )


def downgrade() -> None:
    op.drop_column("fixture_detail", "players")
