"""api football league catalog.

Revision ID: 0011_api_football_league_catalog
Revises: 0010_seed_league_sync_targets
Create Date: 2026-05-20 09:15:00 +09:00

Stores the API-Football league/season catalog so ADMIN search can read DB data
and refresh it manually instead of calling API-Football on every search.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_api_football_league_catalog"
down_revision: Union[str, None] = "0010_seed_league_sync_targets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_football_league_catalog",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("external_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("logo_url", sa.Text()),
        sa.Column("country_name", sa.Text()),
        sa.Column("country_code", sa.Text()),
        sa.Column("country_flag", sa.Text()),
        sa.Column("current_season", sa.Integer()),
        sa.Column(
            "seasons",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("type IN ('League', 'Cup')", name="api_football_league_catalog_type_check"),
    )
    op.create_index(
        "api_football_league_catalog_country_idx",
        "api_football_league_catalog",
        ["country_name"],
    )
    op.create_index(
        "api_football_league_catalog_current_season_idx",
        "api_football_league_catalog",
        ["current_season"],
    )


def downgrade() -> None:
    op.drop_index("api_football_league_catalog_current_season_idx", table_name="api_football_league_catalog")
    op.drop_index("api_football_league_catalog_country_idx", table_name="api_football_league_catalog")
    op.drop_table("api_football_league_catalog")
