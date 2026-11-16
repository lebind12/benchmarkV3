"""NS-01 선수 섹션 고정 슬롯·한글명 후보 테이블 (preview_dev 전용).

적용 범위는 `preview_dev` 스키마뿐이다. 기존 `public` 영역에는 어떤 객체도 만들지
않고, 스키마를 생략한 DDL도 쓰지 않는다.

공용 Alembic 체인으로 실행되면 실패한다. 이 스키마는
`preview_dev.schema_migrations(version, applied_at)`에 자체 이력을 남기며, 적용은
`scripts/preview_dev_migrate.py`가 담당한다.

되돌리기는 이 마이그레이션이 만든 세 테이블과 인덱스만 지운다. 다른 표의 기록은
건드리지 않는다.
"""

from __future__ import annotations

SCHEMA = "preview_dev"
VERSION = "0006_player_section_storage"
PREVIOUS_VERSION = "0005_pipeline_runs"

revision = VERSION
down_revision = PREVIOUS_VERSION
branch_labels = None
depends_on = None

_SLOT_PREFIXES = ("home1", "home2", "away1", "away2")


def _slot_columns_ddl(*, include_injury: bool) -> str:
    lines: list[str] = []
    for prefix in _SLOT_PREFIXES:
        lines.extend(
            [
                f"        {prefix}_player_id bigint,",
                f"        {prefix}_original_name text,",
                f"        {prefix}_name_ko text,",
                f"        {prefix}_body text,",
                f"        {prefix}_name_source text,",
                f"        {prefix}_unresolved_reason text,",
                f"        {prefix}_translation_candidate_id uuid REFERENCES {SCHEMA}.preview_player_name_candidates(id),",
                f"        {prefix}_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,",
            ]
        )
        if include_injury:
            lines.extend(
                [
                    f"        {prefix}_status text,",
                    f"        {prefix}_injury text,",
                    f"        {prefix}_importance text,",
                ]
            )
    return "\n".join(lines)


UPGRADE_STATEMENTS: tuple[str, ...] = (
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA}.preview_player_name_candidates (
        id uuid PRIMARY KEY,
        run_id uuid NOT NULL REFERENCES {SCHEMA}.preview_runs(id) ON DELETE CASCADE,
        section_result_id uuid NOT NULL REFERENCES {SCHEMA}.preview_section_results(id) ON DELETE CASCADE,
        workflow_id text NOT NULL,
        slot_key text NOT NULL,
        fixture_id bigint NOT NULL,
        team_id bigint,
        player_id bigint,
        original_name text NOT NULL,
        candidate_name_ko text NOT NULL,
        source text NOT NULL DEFAULT 'ai_translation',
        review_status text NOT NULL DEFAULT 'pending',
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_player_name_candidate_slot UNIQUE (section_result_id, slot_key)
    )
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_player_name_candidates_run_id
        ON {SCHEMA}.preview_player_name_candidates (run_id)
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_player_name_candidates_section_result_id
        ON {SCHEMA}.preview_player_name_candidates (section_result_id)
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_player_name_candidates_fixture_id
        ON {SCHEMA}.preview_player_name_candidates (fixture_id)
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_player_name_candidates_review_status
        ON {SCHEMA}.preview_player_name_candidates (review_status)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA}.preview_watch_player_sections (
        section_result_id uuid PRIMARY KEY REFERENCES {SCHEMA}.preview_section_results(id) ON DELETE CASCADE,
        run_id uuid NOT NULL REFERENCES {SCHEMA}.preview_runs(id) ON DELETE CASCADE,
        fixture_id bigint NOT NULL,
        home_team_id bigint,
        away_team_id bigint,
        output_contract_version text NOT NULL,
{_slot_columns_ddl(include_injury=False)}
        home_etc text,
        away_etc text,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_watch_player_sections_run_id
        ON {SCHEMA}.preview_watch_player_sections (run_id)
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_watch_player_sections_fixture_id
        ON {SCHEMA}.preview_watch_player_sections (fixture_id)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA}.preview_injury_player_sections (
        section_result_id uuid PRIMARY KEY REFERENCES {SCHEMA}.preview_section_results(id) ON DELETE CASCADE,
        run_id uuid NOT NULL REFERENCES {SCHEMA}.preview_runs(id) ON DELETE CASCADE,
        fixture_id bigint NOT NULL,
        home_team_id bigint,
        away_team_id bigint,
        output_contract_version text NOT NULL,
{_slot_columns_ddl(include_injury=True)}
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_injury_player_sections_run_id
        ON {SCHEMA}.preview_injury_player_sections (run_id)
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_injury_player_sections_fixture_id
        ON {SCHEMA}.preview_injury_player_sections (fixture_id)
    """,
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = (
    f"DROP INDEX IF EXISTS {SCHEMA}.ix_preview_injury_player_sections_fixture_id",
    f"DROP INDEX IF EXISTS {SCHEMA}.ix_preview_injury_player_sections_run_id",
    f"DROP TABLE IF EXISTS {SCHEMA}.preview_injury_player_sections",
    f"DROP INDEX IF EXISTS {SCHEMA}.ix_preview_watch_player_sections_fixture_id",
    f"DROP INDEX IF EXISTS {SCHEMA}.ix_preview_watch_player_sections_run_id",
    f"DROP TABLE IF EXISTS {SCHEMA}.preview_watch_player_sections",
    f"DROP INDEX IF EXISTS {SCHEMA}.ix_preview_player_name_candidates_review_status",
    f"DROP INDEX IF EXISTS {SCHEMA}.ix_preview_player_name_candidates_fixture_id",
    f"DROP INDEX IF EXISTS {SCHEMA}.ix_preview_player_name_candidates_section_result_id",
    f"DROP INDEX IF EXISTS {SCHEMA}.ix_preview_player_name_candidates_run_id",
    f"DROP TABLE IF EXISTS {SCHEMA}.preview_player_name_candidates",
)

_REFUSAL = (
    "0006_player_section_storage is applied by scripts/preview_dev_migrate.py so the "
    "preview_dev schema keeps its own migration history. Running the shared "
    "Alembic chain would create objects in the existing public schema."
)


def upgrade() -> None:
    raise RuntimeError(_REFUSAL)


def downgrade() -> None:
    raise RuntimeError(_REFUSAL)
