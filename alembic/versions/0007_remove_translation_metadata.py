"""remove translation provenance metadata.

Revision ID: 0007_remove_translation_metadata
Revises: 0006_translation_metadata
Create Date: 2026-05-19 17:30:00 +09:00

Removes source/verified from translation tables. Backfill translation curation
is tracked in seed CSV files, while DB translation tables store only Korean
display names.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_remove_translation_metadata"
down_revision: Union[str, None] = "0006_translation_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table_name in ("player_translation", "team_translation", "league_translation"):
        op.drop_column(table_name, "verified")
        op.drop_column(table_name, "source")


def downgrade() -> None:
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
