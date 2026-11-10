"""MP-02 실행 기록·검사 테이블 (preview_dev 전용).

적용 범위는 `preview_dev` 스키마뿐이다. 기존 `public` 영역(경기·계정)은 이
마이그레이션이 만드는 대상이 아니고, `public`에는 어떤 객체도 만들지 않는다.
스키마를 생략한 DDL을 쓰지 않으므로 전역 `search_path`에 의존하지 않는다.

이 스키마는 공용 Alembic 체인을 쓰지 않는다. 공용 체인은 `public.alembic_version`
같은 기존 영역 객체를 만든다(과거 앱의 0001~0018 head가 그렇다). 그래서 이 파일은
DDL 문장의 단일 출처이고, 실제 적용은 `scripts/preview_dev_migrate.py`가
`preview_dev.schema_migrations(version, applied_at)`에 이력을 남기며 수행한다.
`upgrade()`는 공용 Alembic으로 실행되면 명시적으로 실패한다. 조용히 "적용됨"으로
기록되면서 테이블이 없거나, 반대로 기존 영역에 객체를 만드는 일을 막기 위해서다.

되돌리기는 이 마이그레이션이 만든 테이블만 순서대로 삭제한다. 기존 개발 기록이
있으면 먼저 확인해야 한다.
"""

from __future__ import annotations

SCHEMA = "preview_dev"
VERSION = "0002_preview_runs"
PREVIOUS_VERSION = "0001_preview_access"

revision = VERSION
down_revision = PREVIOUS_VERSION
branch_labels = None
depends_on = None

# 적용 순서를 고정한다. 참조 관계가 있는 테이블이 뒤에 온다.
UPGRADE_STATEMENTS: tuple[str, ...] = (
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA}.preview_runs (
        id uuid PRIMARY KEY,
        operation_kind text NOT NULL,
        environment text NOT NULL,
        mode text NOT NULL,
        status text NOT NULL,
        quality text NOT NULL,
        actor_id bigint NOT NULL,
        config_version text NOT NULL,
        limits jsonb NOT NULL DEFAULT '{{}}'::jsonb,
        contract_versions jsonb NOT NULL DEFAULT '{{}}'::jsonb,
        fixture_id bigint,
        league_id bigint,
        season integer,
        home_team_id bigint,
        away_team_id bigint,
        kickoff_at timestamptz,
        fixture_label text,
        write_scope text NOT NULL DEFAULT 'preview_dev',
        label text,
        requested_at timestamptz NOT NULL DEFAULT now(),
        started_at timestamptz,
        finished_at timestamptz,
        failure_code text,
        failure_detail text,
        cancelled_at timestamptz,
        cancelled_by_actor_id bigint,
        cancellation_reason text
    )
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_runs_requested_at
        ON {SCHEMA}.preview_runs (requested_at)
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_runs_actor_id
        ON {SCHEMA}.preview_runs (actor_id)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA}.preview_module_executions (
        id uuid PRIMARY KEY,
        run_id uuid NOT NULL REFERENCES {SCHEMA}.preview_runs(id) ON DELETE CASCADE,
        module_id text NOT NULL,
        ordinal integer NOT NULL DEFAULT 0,
        status text NOT NULL,
        quality text NOT NULL,
        failure_code text,
        input_payload jsonb NOT NULL DEFAULT '{{}}'::jsonb,
        input_hash text NOT NULL DEFAULT '',
        delivered_next_input jsonb NOT NULL DEFAULT '{{}}'::jsonb,
        attempt_count integer NOT NULL DEFAULT 0,
        retry_count integer NOT NULL DEFAULT 0,
        started_at timestamptz,
        finished_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_module_execution_ordinal UNIQUE (run_id, module_id, ordinal)
    )
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_module_executions_run_id
        ON {SCHEMA}.preview_module_executions (run_id)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA}.preview_attempts (
        id uuid PRIMARY KEY,
        run_id uuid NOT NULL REFERENCES {SCHEMA}.preview_runs(id) ON DELETE CASCADE,
        module_execution_id uuid REFERENCES {SCHEMA}.preview_module_executions(id)
            ON DELETE CASCADE,
        module_id text,
        logical_call_id text NOT NULL,
        attempt_ordinal integer NOT NULL,
        provider text NOT NULL,
        model text,
        mode text NOT NULL,
        operation text NOT NULL DEFAULT '',
        outcome text NOT NULL,
        http_status integer,
        error_class text,
        error_message text,
        request_spec jsonb NOT NULL DEFAULT '{{}}'::jsonb,
        request_artifact_id uuid,
        response_artifact_id uuid,
        usage jsonb,
        wait_ms integer,
        started_at timestamptz,
        finished_at timestamptz,
        CONSTRAINT uq_attempt_ordinal UNIQUE (run_id, logical_call_id, attempt_ordinal)
    )
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_attempts_run_id
        ON {SCHEMA}.preview_attempts (run_id)
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_attempts_module_execution_id
        ON {SCHEMA}.preview_attempts (module_execution_id)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA}.preview_source_snapshots (
        id uuid PRIMARY KEY,
        run_id uuid NOT NULL REFERENCES {SCHEMA}.preview_runs(id) ON DELETE CASCADE,
        attempt_id uuid REFERENCES {SCHEMA}.preview_attempts(id) ON DELETE CASCADE,
        source_kind text NOT NULL,
        provider text NOT NULL,
        collected_at timestamptz NOT NULL,
        provider_updated_at timestamptz,
        fixture jsonb,
        catalog_query jsonb,
        artifact_id uuid,
        validation_status text NOT NULL,
        note text
    )
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_source_snapshots_run_id
        ON {SCHEMA}.preview_source_snapshots (run_id)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA}.preview_results (
        id uuid PRIMARY KEY,
        run_id uuid NOT NULL REFERENCES {SCHEMA}.preview_runs(id) ON DELETE CASCADE,
        module_execution_id uuid NOT NULL REFERENCES {SCHEMA}.preview_module_executions(id)
            ON DELETE CASCADE,
        module_id text NOT NULL,
        version integer NOT NULL,
        input_hash text NOT NULL,
        status text NOT NULL,
        quality text NOT NULL,
        failure_code text,
        payload jsonb NOT NULL DEFAULT '{{}}'::jsonb,
        implementation_version text NOT NULL DEFAULT '',
        prompt_version text NOT NULL DEFAULT '',
        contract_version text NOT NULL DEFAULT '',
        created_at timestamptz NOT NULL DEFAULT now(),
        supersedes_result_id uuid,
        CONSTRAINT uq_result_version UNIQUE (module_execution_id, version)
    )
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_results_run_id
        ON {SCHEMA}.preview_results (run_id)
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_results_module_execution_id
        ON {SCHEMA}.preview_results (module_execution_id)
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_results_module_id
        ON {SCHEMA}.preview_results (module_id)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA}.preview_artifacts (
        id uuid PRIMARY KEY,
        run_id uuid REFERENCES {SCHEMA}.preview_runs(id) ON DELETE CASCADE,
        attempt_id uuid REFERENCES {SCHEMA}.preview_attempts(id) ON DELETE CASCADE,
        kind text NOT NULL,
        media_type text NOT NULL,
        byte_size integer NOT NULL,
        sha256 text NOT NULL,
        redacted boolean NOT NULL DEFAULT false,
        body text,
        summary jsonb NOT NULL DEFAULT '{{}}'::jsonb,
        created_at timestamptz NOT NULL,
        expires_at timestamptz NOT NULL,
        expired_at timestamptz
    )
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_artifacts_run_id
        ON {SCHEMA}.preview_artifacts (run_id)
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_artifacts_expires_at
        ON {SCHEMA}.preview_artifacts (expires_at)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA}.preview_write_audit (
        id uuid PRIMARY KEY,
        run_id uuid NOT NULL,
        actor_id bigint NOT NULL,
        action text NOT NULL,
        target_table text NOT NULL,
        target_id text,
        detail jsonb NOT NULL DEFAULT '{{}}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_write_audit_run_id
        ON {SCHEMA}.preview_write_audit (run_id)
    """,
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = (
    f"DROP TABLE IF EXISTS {SCHEMA}.preview_write_audit",
    f"DROP TABLE IF EXISTS {SCHEMA}.preview_artifacts",
    f"DROP TABLE IF EXISTS {SCHEMA}.preview_results",
    f"DROP TABLE IF EXISTS {SCHEMA}.preview_source_snapshots",
    f"DROP TABLE IF EXISTS {SCHEMA}.preview_attempts",
    f"DROP TABLE IF EXISTS {SCHEMA}.preview_module_executions",
    f"DROP TABLE IF EXISTS {SCHEMA}.preview_runs",
)

_REFUSAL = (
    "0002_preview_runs is applied by scripts/preview_dev_migrate.py so the "
    "preview_dev schema keeps its own migration history. Running the shared "
    "Alembic chain would create objects in the existing public schema."
)


def upgrade() -> None:
    raise RuntimeError(_REFUSAL)


def downgrade() -> None:
    raise RuntimeError(_REFUSAL)
