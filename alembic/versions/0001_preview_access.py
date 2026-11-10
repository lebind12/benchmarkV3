"""MP-01 관리자 계정과 세션.

로컬 개발 DB에만 적용한다. 운영 DB 초기화는 이 마이그레이션의 책임이 아니다.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_preview_access"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "preview_users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "preview_admin_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("preview_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_preview_admin_sessions_user_id", "preview_admin_sessions", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_preview_admin_sessions_user_id", table_name="preview_admin_sessions"
    )
    op.drop_table("preview_admin_sessions")
    op.drop_table("preview_users")
