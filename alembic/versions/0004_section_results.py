"""MP-04 섹션 워크플로우 결과 테이블 (preview_dev 전용).

적용 범위는 `preview_dev` 스키마뿐이다. 기존 `public` 영역에는 어떤 객체도 만들지
않고, 스키마를 생략한 DDL도 쓰지 않는다.

공용 Alembic 체인으로 실행되면 실패한다. 이 스키마는
`preview_dev.schema_migrations(version, applied_at)`에 자체 이력을 남기며, 적용은
`scripts/preview_dev_migrate.py`가 담당한다. 이유는 `0002_preview_runs.py`와 같다.

이 표가 생기는 이유: 승인 근거는 개별 노드·모듈 결과가 아니라 **섹션 본문 결과**다.
그 결과를 저장할 곳이 없으면 승인은 영원히 거부되고, 반대로 아무 결과나 승인 근거로
쓰면 실제 확인 없이 승인된 것처럼 보인다. 그래서 본문·근거·버전·실행 방식을 한
행에 담는 최소 표를 만든다.

되돌리기는 이 마이그레이션이 만든 표만 지운다. 다른 표의 기록은 건드리지 않는다.
"""

from __future__ import annotations

SCHEMA = "preview_dev"
VERSION = "0004_section_results"
PREVIOUS_VERSION = "0003_preview_approvals"

revision = VERSION
down_revision = PREVIOUS_VERSION
branch_labels = None
depends_on = None

UPGRADE_STATEMENTS: tuple[str, ...] = (
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA}.preview_section_results (
        id uuid PRIMARY KEY,
        run_id uuid NOT NULL REFERENCES {SCHEMA}.preview_runs(id) ON DELETE CASCADE,
        workflow_id text NOT NULL,
        workflow_version text NOT NULL,
        version integer NOT NULL,
        title text NOT NULL,
        body text NOT NULL,
        sources jsonb NOT NULL DEFAULT '[]'::jsonb,
        mode text NOT NULL,
        environment text NOT NULL,
        quality text NOT NULL,
        module_execution_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
        result_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
        diagnostics jsonb NOT NULL DEFAULT '[]'::jsonb,
        unavailable_reason text,
        output_contract_version text NOT NULL,
        contract_version text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        supersedes_section_result_id uuid,
        CONSTRAINT uq_section_result_version UNIQUE (run_id, workflow_id, version)
    )
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_section_results_run_id
        ON {SCHEMA}.preview_section_results (run_id)
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_section_results_workflow_id
        ON {SCHEMA}.preview_section_results (workflow_id)
    """,
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = (
    f"DROP INDEX IF EXISTS {SCHEMA}.ix_preview_section_results_workflow_id",
    f"DROP INDEX IF EXISTS {SCHEMA}.ix_preview_section_results_run_id",
    f"DROP TABLE IF EXISTS {SCHEMA}.preview_section_results",
)

_REFUSAL = (
    "0004_section_results is applied by scripts/preview_dev_migrate.py so the "
    "preview_dev schema keeps its own migration history. Running the shared "
    "Alembic chain would create objects in the existing public schema."
)


def upgrade() -> None:
    raise RuntimeError(_REFUSAL)


def downgrade() -> None:
    raise RuntimeError(_REFUSAL)
