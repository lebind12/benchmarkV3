"""Add immutable home preview storage after authenticated management.

Revision ID: 0018_home_preview_storage
Revises: 0017_streamer_management
"""

from pathlib import Path

from alembic import op

revision = "0018_home_preview_storage"
down_revision = "0017_streamer_management"
branch_labels = None
depends_on = None


def upgrade():
    path = (
        Path(__file__).resolve().parents[2]
        / "supabase/migrations/20261024235328_home_preview_storage.sql"
    )
    op.get_bind().exec_driver_sql(path.read_text())


def downgrade():
    for table in (
        "home_preview_attempt",
        "home_preview_publication",
        "home_preview_version",
        "home_preview_snapshot",
    ):
        op.drop_table(table)
