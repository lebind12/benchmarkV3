"""Exercise the real Alembic chain and rollback without touching public schemas."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect, text


def test_home_migration_after_management_and_safe_downgrade(isolated_db, test_database_url):
    engine, schema = isolated_db
    env = dict(
        os.environ,
        DATABASE_URL=test_database_url,
        SQLALCHEMY_DATABASE_URL=test_database_url,
        PGOPTIONS=f"-c search_path={schema}",
    )

    def migrate(revision):
        direction = "downgrade" if revision == "0017_streamer_management" else "upgrade"
        result = subprocess.run(
            [sys.executable, "-m", "alembic", direction, revision],
            cwd=Path(__file__).parents[2],
            env=env,
            capture_output=True,
            check=False,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    migrate("head")
    with engine.connect() as conn:
        assert (
            conn.scalar(text("select version_num from alembic_version"))
            == "0018_home_preview_storage"
        )
        tables = set(inspect(conn).get_table_names())
        assert {
            "management_run",
            "translation_audit",
            "home_preview_snapshot",
            "home_preview_version",
            "home_preview_publication",
            "home_preview_attempt",
        } <= tables
        assert (
            conn.scalar(
                text(
                    "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname=:schema and c.relname like 'home_preview_%' and c.relkind='r' and c.relrowsecurity"
                ),
                {"schema": schema},
            )
            == 4
        )
    migrate("0017_streamer_management")
    with engine.connect() as conn:
        conn.execute(text(f'SET search_path TO "{schema}"'))
        tables = inspect(conn).get_table_names()
        assert "management_run" in tables
        assert not any(name.startswith("home_preview_") for name in tables)
    migrate("head")
