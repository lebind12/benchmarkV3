"""MP-01 개발 세션 저장소.

`preview_dev` 스키마에만 적용한다. 기존 운영 계정 원장(`public.app_user`)은
읽기 전용이며 이 마이그레이션이 만드는 대상이 아니다. 운영 DB에는
`scripts/preview_dev_provision.py`가 같은 이름의 객체를 만든다.

`user_id`는 기존 `public.app_user.id`(bigint)를 가리키지만 FK 제약을 걸지 않는다.
기존 테이블에 제약을 추가하지 않는 경계를 지키기 위해서다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_preview_access"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "preview_dev"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.create_table(
        "preview_admin_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_preview_admin_sessions_user_id",
        "preview_admin_sessions",
        ["user_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_preview_admin_sessions_user_id",
        table_name="preview_admin_sessions",
        schema=SCHEMA,
    )
    op.drop_table("preview_admin_sessions", schema=SCHEMA)
