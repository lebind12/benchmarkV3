"""Add shared management persistence and human translation protection.

Revision ID: 0017_streamer_management
Revises: 0016_team_color_scoreboard_mode
"""

from pathlib import Path
from alembic import op

revision = "0017_streamer_management"
down_revision = "0016_team_color_scoreboard_mode"
branch_labels = None
depends_on = None


def upgrade():
    path = (
        Path(__file__).resolve().parents[2]
        / "supabase/migrations/20261024212510_streamer_management.sql"
    )
    op.get_bind().exec_driver_sql(path.read_text())


def downgrade():
    # Explicit rollback only: removes the newly introduced data and protection.
    for entity in ("league", "team", "player", "coach"):
        op.execute(f"DROP TRIGGER IF EXISTS {entity}_translation_protect ON {entity}_translation")
        for column in ("editor_id", "human_modified", "version"):
            op.drop_column(f"{entity}_translation", column)
    op.execute("DROP FUNCTION IF EXISTS protect_human_translation()")
    op.drop_table("translation_audit")
    op.drop_table("management_run")
    op.drop_column("league_sync_target", "last_sync")
    op.drop_column("league_sync_target", "initial_status")
