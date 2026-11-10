"""MP-10 전체 프리뷰 실행 작업 상태 테이블 (preview_dev 전용).

적용 범위는 `preview_dev` 스키마뿐이다. 기존 `public` 영역에는 어떤 객체도 만들지
않고, 스키마를 생략한 DDL도 쓰지 않는다.

공용 Alembic 체인으로 실행되면 실패한다. 이 스키마는
`preview_dev.schema_migrations(version, applied_at)`에 자체 이력을 남기며, 적용은
`scripts/preview_dev_migrate.py`가 담당한다. 이유는 `0002_preview_runs.py`와 같다.

이 표가 생기는 이유: 전체 프리뷰는 여러 단계를 넘기며 진행되고, 프로세스가 멈추면
그 지점부터 다시 이어야 한다. "누가 지금 이 실행을 소유하는가"와 "어디까지
끝났는가"를 결과 기록(`preview_runs`·`preview_module_executions`·`preview_results`)에
섞으면, 결과 행의 의미가 작업 상태에 따라 흔들린다. 그래서 작업 상태를 따로 둔다.

되돌리기는 이 마이그레이션이 만든 표만 지운다. 다른 표의 기록은 건드리지 않는다.
"""

from __future__ import annotations

SCHEMA = "preview_dev"
VERSION = "0005_pipeline_runs"
PREVIOUS_VERSION = "0004_section_results"

revision = VERSION
down_revision = PREVIOUS_VERSION
branch_labels = None
depends_on = None

UPGRADE_STATEMENTS: tuple[str, ...] = (
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA}.preview_pipeline_runs (
        id uuid PRIMARY KEY REFERENCES {SCHEMA}.preview_runs(id) ON DELETE CASCADE,
        dedup_key text NOT NULL,
        active boolean NOT NULL DEFAULT true,
        resume_of_run_id uuid,
        rerun_of_run_id uuid,
        admission text NOT NULL,
        workflow_versions jsonb NOT NULL DEFAULT '{{}}'::jsonb,
        selected_result_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
        stage text NOT NULL DEFAULT 'created',
        pending_nodes jsonb NOT NULL DEFAULT '[]'::jsonb,
        completed_nodes jsonb NOT NULL DEFAULT '[]'::jsonb,
        owner_id text,
        lease_expires_at timestamptz,
        fencing_token integer NOT NULL DEFAULT 0,
        budget_state jsonb NOT NULL DEFAULT '{{}}'::jsonb,
        deadline_at timestamptz,
        waiting_reason text,
        failure_code text,
        failure_detail text,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_pipeline_runs_dedup_key
        ON {SCHEMA}.preview_pipeline_runs (dedup_key)
    """,
    # 진행 중인 실행만 중복 방지 대상이다. 끝난 실행은 키에서 빠져 재실행이 가능하다.
    f"""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_pipeline_active_dedup
        ON {SCHEMA}.preview_pipeline_runs (dedup_key)
        WHERE active
    """,
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = (
    f"DROP INDEX IF EXISTS {SCHEMA}.uq_pipeline_active_dedup",
    f"DROP INDEX IF EXISTS {SCHEMA}.ix_preview_pipeline_runs_dedup_key",
    f"DROP TABLE IF EXISTS {SCHEMA}.preview_pipeline_runs",
)

_REFUSAL = (
    "0005_pipeline_runs is applied by scripts/preview_dev_migrate.py so the "
    "preview_dev schema keeps its own migration history. Running the shared "
    "Alembic chain would create objects in the existing public schema."
)


def upgrade() -> None:
    raise RuntimeError(_REFUSAL)


def downgrade() -> None:
    raise RuntimeError(_REFUSAL)
