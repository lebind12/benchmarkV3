"""0002 마이그레이션 DDL과 모델 메타데이터가 같은 모양인지 확인한다.

이 검사는 로컬 전용 테스트 DB에서만 돈다(conftest의 대상 검사가 먼저 실패한다).
실제 `preview_dev`에는 적용하지 않는다. DDL과 모델이 어긋나면 운영 개발 환경에서
테이블은 있는데 앱은 쓰지 못하는 상태가 되므로, 그 차이를 여기서 잡는다.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from app.preview import models as preview_models
from app.preview.contracts import RAW_ARTIFACT_RETENTION_DAYS

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0002_preview_runs.py"
)
SCHEMA = "preview_dev"

# 마이그레이션이 만드는 테이블. 모델 메타데이터와 이 목록이 같아야 한다.
MIGRATED_TABLES = (
    "preview_runs",
    "preview_module_executions",
    "preview_attempts",
    "preview_source_snapshots",
    "preview_results",
    "preview_artifacts",
    "preview_write_audit",
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mp02_migration_ddl", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_migration_file_declares_the_expected_version():
    migration = _load_migration()
    assert migration.VERSION == "0002_preview_runs"
    assert migration.revision == migration.VERSION
    assert migration.down_revision == "0001_preview_access"
    assert migration.SCHEMA == SCHEMA


def test_migration_refuses_to_run_through_the_shared_alembic_chain():
    """공용 Alembic으로 실행되면 조용히 통과하지 않고 실패한다.

    공용 체인은 `public` 영역에 마이그레이션 이력 객체를 만든다. 그 경로로 이
    마이그레이션이 실행되면 기존 영역을 건드리거나, 이력만 남고 테이블이 없는
    상태가 될 수 있다.
    """
    migration = _load_migration()
    with pytest.raises(RuntimeError) as raised:
        migration.upgrade()
    assert "preview_dev_migrate.py" in str(raised.value)
    with pytest.raises(RuntimeError):
        migration.downgrade()


def test_migration_creates_the_tables_the_models_use(engine, schema):
    """DDL을 실제로 적용해 모델이 기대하는 테이블·열이 만들어지는지 본다."""
    migration = _load_migration()
    # conftest가 만든 스키마를 지우고 마이그레이션 DDL만으로 다시 만든다.
    with engine.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        for statement in migration.UPGRADE_STATEMENTS:
            conn.execute(text(statement))

    with engine.connect() as conn:
        found = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = :schema"
                ),
                {"schema": SCHEMA},
            )
        }
    assert set(MIGRATED_TABLES) <= found

    engine_from_models = engine
    from sqlalchemy import inspect

    inspector = inspect(engine_from_models)
    for table_name in MIGRATED_TABLES:
        model_table = preview_models.Base.metadata.tables[f"{SCHEMA}.{table_name}"]
        ddl_columns = {
            column["name"] for column in inspector.get_columns(table_name, schema=SCHEMA)
        }
        model_columns = {column.name for column in model_table.columns}
        assert model_columns == ddl_columns, f"{table_name} column mismatch"


def test_migration_is_repeatable(engine, schema):
    """이미 적용된 상태에서 다시 실행해도 실패하지 않는다(멱등)."""
    migration = _load_migration()
    with engine.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        for _ in range(2):
            for statement in migration.UPGRADE_STATEMENTS:
                conn.execute(text(statement))


def test_retention_days_are_declared_in_one_place():
    """계약의 보관 기간 값이 마이그레이션 기본값과 어긋나지 않게 한다."""
    assert RAW_ARTIFACT_RETENTION_DAYS == 30


# --------------------------------------------------------------------------
# MP-04: 섹션 결과 표 (0004)
# --------------------------------------------------------------------------

SECTION_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0004_section_results.py"
)


def _load_section_migration():
    spec = importlib.util.spec_from_file_location(
        "mp04_section_migration_ddl", SECTION_MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_section_result_migration_refuses_the_shared_alembic_chain():
    """공용 Alembic으로 0004를 실행하면 조용히 통과하지 않는다."""
    migration = _load_section_migration()
    with pytest.raises(RuntimeError) as raised:
        migration.upgrade()
    assert "preview_dev_migrate.py" in str(raised.value)
    assert migration.down_revision == "0003_preview_approvals"


def test_section_result_ddl_matches_the_model(engine, schema):
    """0004 DDL로 만든 표가 모델이 기대하는 열과 같은지 본다.

    이 표가 없으면 섹션 본문 결과를 저장할 곳이 없어 승인 경로가 영원히 닫히거나,
    반대로 근거 없는 승인이 만들어질 수 있다.
    """
    from sqlalchemy import inspect

    migration = _load_section_migration()
    with engine.begin() as conn:
        for statement in migration.UPGRADE_STATEMENTS:
            conn.execute(text(statement))
        # 멱등성도 함께 확인한다.
        for statement in migration.UPGRADE_STATEMENTS:
            conn.execute(text(statement))

    inspector = inspect(engine)
    ddl_columns = {
        column["name"]
        for column in inspector.get_columns(
            "preview_section_results", schema=SCHEMA
        )
    }
    model_table = preview_models.Base.metadata.tables[
        f"{SCHEMA}.preview_section_results"
    ]
    assert {column.name for column in model_table.columns} == ddl_columns


# --------------------------------------------------------------------------
# NS-01: 선수 섹션 고정 슬롯·한글명 후보 표 (0006)
# --------------------------------------------------------------------------

PLAYER_SECTION_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0006_player_section_storage.py"
)

PLAYER_SECTION_MIGRATED_TABLES = (
    "preview_player_name_candidates",
    "preview_watch_player_sections",
    "preview_injury_player_sections",
)


def _load_player_section_migration():
    spec = importlib.util.spec_from_file_location(
        "ns01_player_section_migration_ddl", PLAYER_SECTION_MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_player_section_migration_refuses_shared_alembic_and_registers_explicit_runner():
    """공용 Alembic으로 0006을 실행하면 실패하고, 명시적 preview_dev_migrate 목록에 등록되어 있어야 한다."""
    import scripts.preview_dev_migrate as migrate_runner

    migration = _load_player_section_migration()
    assert migration.VERSION == "0006_player_section_storage"
    assert migration.down_revision == "0005_pipeline_runs"
    assert migration.SCHEMA == SCHEMA
    assert PLAYER_SECTION_MIGRATION_PATH in migrate_runner.MIGRATION_PATHS

    with pytest.raises(RuntimeError) as raised:
        migration.upgrade()
    assert "preview_dev_migrate.py" in str(raised.value)
    with pytest.raises(RuntimeError):
        migration.downgrade()


def test_player_section_ddl_matches_models_and_is_repeatable(engine, schema):
    """0006 DDL이 ORM 모델과 일치하고 반복 실행해도 안전해야 두 섹션 저장이 어긋나지 않는다."""
    from sqlalchemy import inspect

    migration = _load_player_section_migration()
    with engine.begin() as conn:
        for statement in migration.UPGRADE_STATEMENTS:
            conn.execute(text(statement))
        for statement in migration.UPGRADE_STATEMENTS:
            conn.execute(text(statement))

    inspector = inspect(engine)
    for table_name in PLAYER_SECTION_MIGRATED_TABLES:
        ddl_columns = {
            column["name"]
            for column in inspector.get_columns(table_name, schema=SCHEMA)
        }
        model_table = preview_models.Base.metadata.tables[f"{SCHEMA}.{table_name}"]
        assert {column.name for column in model_table.columns} == ddl_columns

    watch_cols = {
        column["name"]
        for column in inspector.get_columns("preview_watch_player_sections", schema=SCHEMA)
    }
    injury_cols = {
        column["name"]
        for column in inspector.get_columns("preview_injury_player_sections", schema=SCHEMA)
    }
    assert {"home_etc", "away_etc"} <= watch_cols
    assert "home_etc" not in injury_cols
    assert "away_etc" not in injury_cols

    cand_uniques = inspector.get_unique_constraints(
        "preview_player_name_candidates", schema=SCHEMA
    )
    assert any(
        set(uc["column_names"]) == {"section_result_id", "slot_key"}
        for uc in cand_uniques
    )
