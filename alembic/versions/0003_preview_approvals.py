"""MP-02 섹션 워크플로우 승인 테이블 (preview_dev 전용).

적용 범위는 `preview_dev` 스키마뿐이다. 기존 `public` 영역에는 어떤 객체도 만들지
않고, 스키마를 생략한 DDL도 쓰지 않는다.

공용 Alembic 체인으로 실행되면 실패한다. 이 스키마는
`preview_dev.schema_migrations(version, applied_at)`에 자체 이력을 남기며, 적용은
`scripts/preview_dev_migrate.py`가 담당한다. 이유는 `0002_preview_runs.py`와 같다.

승인 단위는 프리뷰 섹션을 만드는 완결된 워크플로우다. 내부 노드나 D0 같은 자료 준비
단계에는 별도 승인 행을 만들지 않는다.

승인 표는 append-only다. 이전 승인 행은 지우지 않고 `active`만 내리므로, 되돌리기가
필요한 경우도 표를 지우는 것이 아니라 감사 기록을 남기는 방식이어야 한다.
"""

from __future__ import annotations

SCHEMA = "preview_dev"
VERSION = "0003_preview_approvals"
PREVIOUS_VERSION = "0002_preview_runs"

revision = VERSION
down_revision = PREVIOUS_VERSION
branch_labels = None
depends_on = None

UPGRADE_STATEMENTS: tuple[str, ...] = (
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA}.preview_section_approvals (
        id uuid PRIMARY KEY,
        workflow_id text NOT NULL,
        workflow_version text NOT NULL,
        version_hash text NOT NULL,
        constituents jsonb NOT NULL DEFAULT '[]'::jsonb,
        reviewed_run_id uuid REFERENCES {SCHEMA}.preview_runs(id) ON DELETE SET NULL,
        section_result_id uuid,
        approved_by_actor_id bigint NOT NULL,
        approved_at timestamptz NOT NULL,
        reviewed_note text,
        active boolean NOT NULL DEFAULT true,
        supersedes_approval_id uuid
    )
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_section_approvals_workflow_id
        ON {SCHEMA}.preview_section_approvals (workflow_id)
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_section_approvals_version_hash
        ON {SCHEMA}.preview_section_approvals (version_hash)
    """,
    # 섹션당 활성 승인은 하나뿐이다. 부분 유일 인덱스로 DB에서도 강제한다.
    f"""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_preview_section_approvals_one_active
        ON {SCHEMA}.preview_section_approvals (workflow_id)
        WHERE active
    """,
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = (
    f"DROP INDEX IF EXISTS {SCHEMA}.uq_preview_section_approvals_one_active",
    f"DROP INDEX IF EXISTS {SCHEMA}.ix_preview_section_approvals_version_hash",
    f"DROP INDEX IF EXISTS {SCHEMA}.ix_preview_section_approvals_workflow_id",
    f"DROP TABLE IF EXISTS {SCHEMA}.preview_section_approvals",
)

_REFUSAL = (
    "0003_preview_approvals is applied by scripts/preview_dev_migrate.py so the "
    "preview_dev schema keeps its own migration history. Running the shared "
    "Alembic chain would create objects in the existing public schema."
)


def upgrade() -> None:
    raise RuntimeError(_REFUSAL)


def downgrade() -> None:
    raise RuntimeError(_REFUSAL)
