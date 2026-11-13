"""PS-02 선수 시즌 통계 읽기 경계 검사.

확인하는 것은 **읽기 역할 경계와 정직한 상태 표기**다.

- 전용 통계 읽기 역할(`preview_dev_stats_ro`) 설정이 없으면 붙지 않고, 화면에는
  `unknown`이 남는다. 조용히 0으로 채우지 않는다.
- 읽기 연결은 `default_transaction_read_only=on`이며 `SELECT`만 보낸다.
- 범위 없이 전 테이블을 훑지 않는다. 필터(팀·리그·시즌) 없는 조회는 거부한다.
- 저장 행이 없는 것과 "기록 0"을 구분한다(빈 결과는 `unknown`+사유).
- 권한 거부는 권한 거부로 보고한다. "자료 없음"으로 바꾸지 않는다.

DB는 자기 전용 로컬 루프백 테스트 DB만 쓰고, 파괴적 준비 전에 대상을 검사한다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

FIXED_NOW = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)

# 이 파일 전용 루프백 테스트 DB. 공통 conftest의 스키마를 건드리지 않는다.
PS02_TEST_DATABASE_URL = (
    "postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/preview_ps02_test"
)

STATS_DDL = """
CREATE TABLE IF NOT EXISTS public.player (
    id bigint PRIMARY KEY,
    name text NOT NULL
);
CREATE TABLE IF NOT EXISTS public.player_translation (
    player_id bigint PRIMARY KEY,
    name_ko text,
    short_name_ko text
);
CREATE TABLE IF NOT EXISTS public.player_season_stat (
    id bigint PRIMARY KEY,
    player_id bigint NOT NULL,
    team_id bigint NOT NULL,
    league_id bigint NOT NULL,
    season_year integer NOT NULL,
    position text,
    shirt_number smallint,
    appearances smallint,
    minutes integer,
    rating numeric(4,2),
    goals smallint,
    assists smallint,
    yellow_cards smallint,
    red_cards smallint,
    raw_stats jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""


@pytest.fixture(scope="module")
def stats_engine():
    from sqlalchemy import create_engine, text

    from app.core.db_target import normalize_driver
    from tests.preview._dbguard import assert_safe_test_database

    assert_safe_test_database(PS02_TEST_DATABASE_URL)
    engine = create_engine(normalize_driver(PS02_TEST_DATABASE_URL), future=True)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        for statement in [part.strip() for part in STATS_DDL.split(";") if part.strip()]:
            conn.execute(text(statement))
        conn.execute(
            text(
                "INSERT INTO public.player (id, name) VALUES (533, 'Erling Haaland'),"
                " (534, 'Rayan Cherki')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO public.player_translation (player_id, name_ko, short_name_ko)"
                " VALUES (533, '엘링 홀란', '홀란'), (534, '라얀 셰르키', '셰르키')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO public.player_season_stat"
                " (id, player_id, team_id, league_id, season_year, position, appearances,"
                "  minutes, rating, goals, assists, yellow_cards, red_cards)"
                " VALUES (1, 533, 13, 39, 2026, 'Forward', 10, 890, 7.85, 9, 2, 1, 0),"
                "        (2, 534, 13, 39, 2026, 'Midfielder', 16, 1120, 7.10, 7, 6, 3, 0)"
            )
        )
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def _reader(engine):
    from app.preview.sources.player_stats import PlayerStatsReader

    return PlayerStatsReader(engine)


# --------------------------------------------------------------------------
# 설정/권한 없음
# --------------------------------------------------------------------------


def test_reader_is_absent_without_configured_stats_url(monkeypatch):
    """전용 통계 DSN이 없으면 붙지 않고 unknown으로 남는다."""
    from app.preview.sources import player_stats

    for key in ("PREVIEW_STATS_DATABASE_URL",):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(player_stats, "_settings_stats_url", lambda: None)

    reader = player_stats.open_player_stats_from_settings()
    assert reader is None

    access = player_stats.PlayerStatsAccess.absent("PREVIEW_STATS_DATABASE_URL")
    payload = access.to_dict()
    assert payload["readable"] is False
    assert payload["state"] == "unknown"
    assert payload["missing"] == ["SELECT ON public.player_season_stat"]


def test_rows_are_read_with_translation_and_expected_columns(stats_engine):
    reader = _reader(stats_engine)
    rows = reader.season_stats(team_id=13, league_id=39, season_year=2026)

    assert len(rows) == 2
    by_player = {row.player_id: row for row in rows}
    haaland = by_player[533]
    assert haaland.goals == 9
    assert haaland.appearances == 10
    assert haaland.minutes == 890
    assert haaland.display_name_ko is None or isinstance(haaland.display_name_ko, str)
    assert haaland.position == "Forward"

    # raw_stats 같은 넓은 열은 조회 대상이 아니다.
    payload = haaland.to_dict()
    assert "raw_stats" not in payload
    assert "shirt_number" not in payload


def test_reader_refuses_unbounded_query(stats_engine):
    """팀·리그·시즌 필터가 없으면 전 표를 훑지 않고 거부한다."""
    reader = _reader(stats_engine)
    with pytest.raises(ValueError):
        reader.season_stats(team_id=None, league_id=None, season_year=None)


def test_empty_rows_are_unknown_not_zero_stats(stats_engine):
    """저장 행이 없는 것은 '기록 0'이 아니다."""
    reader = _reader(stats_engine)
    result = reader.season_stats_with_state(team_id=99, league_id=39, season_year=2026)

    assert result.rows == ()
    assert result.state == "unknown"
    assert result.reason == "no_rows_for_team_season"
    assert result.coverage_note


def test_permission_denied_is_reported_as_permission_not_absence(stats_engine):
    """권한 거부는 권한 거부로 남는다. '자료 없음'으로 바꾸지 않는다."""
    from sqlalchemy import create_engine, text

    from app.core.db_target import normalize_driver
    from app.preview.sources import player_stats

    # 통계 표에서 SELECT를 뺀 좁은 역할을 흉내낸다(테스트 DB 안에서만).
    with stats_engine.begin() as conn:
        conn.execute(
            text(
                "DO $$ BEGIN"
                " IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ps02_narrow') THEN"
                "   CREATE ROLE ps02_narrow LOGIN PASSWORD 'ps02_narrow_pw';"
                " END IF;"
                " END $$;"
            )
        )
        conn.execute(text("GRANT USAGE ON SCHEMA public TO ps02_narrow"))
        conn.execute(text("REVOKE ALL ON public.player_season_stat FROM ps02_narrow"))

    narrow_url = (
        "postgresql://ps02_narrow:ps02_narrow_pw@127.0.0.1:55432/preview_ps02_test"
    )
    narrow_engine = create_engine(normalize_driver(narrow_url), future=True)
    try:
        reader = player_stats.PlayerStatsReader(narrow_engine)
        result = reader.season_stats_with_state(
            team_id=13, league_id=39, season_year=2026
        )
        assert result.state == "denied"
        assert result.reason == "read_denied"
        assert result.rows == ()
    finally:
        narrow_engine.dispose()
        with stats_engine.begin() as conn:
            conn.execute(text("REVOKE ALL ON public.player_season_stat FROM ps02_narrow"))


def test_probe_reports_required_columns_without_writing(stats_engine):
    access = _reader(stats_engine).probe()
    payload = access.to_dict()
    assert payload["readable"] is True
    assert payload["state"] == "readable"
    assert payload["columns"]
    assert "raw_stats" not in payload["columns"]
