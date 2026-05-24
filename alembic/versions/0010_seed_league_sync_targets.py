"""seed sync targets from active leagues.

Revision ID: 0010_seed_league_sync_targets
Revises: 0009_league_sync_target
Create Date: 2026-05-20 06:55:00 +09:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0010_seed_league_sync_targets"
down_revision: Union[str, None] = "0009_league_sync_target"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO league_sync_target (league_id, season_year)
        SELECT id, current_season
        FROM league
        WHERE is_active = true
          AND current_season IS NOT NULL
        ON CONFLICT (league_id, season_year) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO league_sync_target (league_id, season_year)
        SELECT id, current_season - 1
        FROM league
        WHERE is_active = true
          AND external_id <> 1
          AND current_season IS NOT NULL
          AND current_season > 1900
        ON CONFLICT (league_id, season_year) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM league_sync_target st
        USING league l
        WHERE st.league_id = l.id
          AND (
            st.season_year = l.current_season
            OR (l.external_id <> 1 AND st.season_year = l.current_season - 1)
          )
        """
    )
