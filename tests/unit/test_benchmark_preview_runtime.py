"""BI-01 직접 경계 검사 — 한 앱의 라우터·세션 bind·스키마.

검사 대상은 "같은 FastAPI 앱"이 실제로 원래 benchmark 라우터와 프리뷰 라우터를
함께 들고 있는지, 그리고 그 두 영역이 서로 다른 DB 연결/스키마를 쓰는지다.
실제 DB 연결은 열지 않는다. 세션 bind·metadta는 설정과 모델 선언으로만 판정한다.

검사 이유(실패 시 사용자 영향):

- 라우터가 빠지면 사용자는 로컬에서 원래 관리 화면이나 프리뷰 탭 중 하나를 아예
  쓸 수 없다.
- auth 라우터가 두 벌이 되면 같은 경로가 중복 등록돼 로그인 응답이 어느 쪽으로
  갈지 불확실해진다. 그건 기존 계정 로그인 계약을 깨는 회귀다.
- 두 Base가 섞이거나 preview 모델이 `public`을 가리키면 기존 계정·경기 테이블을
  개발 검증이 건드릴 수 있다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _route_map(app) -> dict[str, set[str]]:
    routes: dict[str, set[str]] = {}
    for route in app.routes:
        path = getattr(route, "path", None)
        if not path:
            continue
        routes.setdefault(path, set()).update(getattr(route, "methods", None) or set())
    return routes


def test_one_app_serves_health_benchmark_admin_home_and_preview():
    from app.main import app

    routes = _route_map(app)

    # 원래 benchmark 앱의 활성 경로
    assert "GET" in routes["/health"]
    assert "GET" in routes["/api/v1/home/recommendations"]
    assert "GET" in routes["/api/v1/admin/management/catalog"]
    assert "GET" in routes["/api/v1/home/fixtures"]
    # 원래 JWT 인증 계약
    assert "POST" in routes["/api/v1/auth/login"]
    assert "GET" in routes["/api/v1/auth/me"]
    assert "POST" in routes["/api/v1/auth/refresh"]
    # 같은 앱 안의 프리뷰 라우터
    assert "GET" in routes["/api/v1/admin/preview/runs"]
    assert "POST" in routes["/api/v1/admin/preview/bundle-runs"]


def test_auth_routes_are_registered_exactly_once():
    """인증 경로가 두 벌 등록되면 어느 라우터가 응답할지 불확실해진다."""
    from app.main import app

    paths = [getattr(route, "path", None) for route in app.routes]
    for path in (
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/auth/refresh",
    ):
        assert paths.count(path) == 1, f"{path} is registered {paths.count(path)} times"


def test_benchmark_and_preview_use_different_bases_and_engines():
    """public 모델과 preview 모델의 Base/metadata를 합치지 않는다."""
    from app import db as benchmark_db
    from app.preview import db as preview_db

    assert benchmark_db.engine is not preview_db.get_engine()
    assert benchmark_db.SessionLocal.kw["bind"] is benchmark_db.engine


def test_preview_models_are_declared_in_the_preview_schema_only():
    """preview 모델은 `preview_dev`에만 있고 public 테이블을 만들지 않는다."""
    from app.preview import db as preview_db
    from app.preview import models as preview_models  # noqa: F401  (모델 등록)

    assert preview_db.SCHEMA == "preview_dev"

    tables = set(preview_db.Base.metadata.tables)
    assert tables, "preview models did not register on the preview Base"

    for qualified in tables:
        schema, _, _name = qualified.partition(".")
        assert schema == preview_db.SCHEMA, f"{qualified} is not in {preview_db.SCHEMA}"


def test_public_models_stay_on_the_benchmark_base():
    """기존 경기·계정 모델은 원래 Base에 남고 스키마를 새로 만들지 않는다."""
    from app.models import Base as benchmark_base
    from app.preview.db import Base as preview_base

    assert benchmark_base is not preview_base
    public_tables = set(benchmark_base.metadata.tables)
    assert "app_user" in public_tables
    assert "fixture" in public_tables
    # preview 테이블이 원래 Base에 섞이지 않았는지 확인한다.
    assert not any(name.startswith("preview_") for name in public_tables)


def test_preview_settings_do_not_share_the_benchmark_singleton():
    """설정 singleton을 공유하면 두 DSN이 어느 쪽으로 가는지 알 수 없게 된다."""
    from app.core.config import get_settings as benchmark_settings
    from app.preview.config import PreviewSettings, get_settings as preview_settings
    from app.preview.config import Settings as AliasSettings

    assert AliasSettings is PreviewSettings
    assert preview_settings is not benchmark_settings
    assert preview_settings.cache_info() is not benchmark_settings.cache_info()

    preview = preview_settings()
    assert isinstance(preview, PreviewSettings)
    # 서로 다른 필드 집합: preview는 저장 스키마 관련 DSN을, benchmark는 수집/모델
    # 설정을 소유한다. 같은 클래스가 아니다.
    assert type(preview).__name__ != type(benchmark_settings()).__name__


def test_account_reader_always_uses_the_original_connection(monkeypatch):
    """계정 조회는 프로필과 무관하게 원래 `DATABASE_URL`의 세션을 그대로 쓴다.

    계정 전용 읽기 역할·강제 읽기 전용 옵션이 다시 들어오면 로그인·ADMIN 판정이
    다른 계정 집합을 보게 되어 사용자는 로그인할 수 없다.
    """
    from app import db as benchmark_db
    from app.core.config import get_settings as benchmark_settings

    for profile in ("false", "true"):
        monkeypatch.setenv("LOCAL_DEV_AUTH_ENABLED", profile)
        benchmark_settings.cache_clear()
        benchmark_db.reset_auth_engine()
        benchmark_db.reset_engine()
        try:
            if profile == "false":
                assert benchmark_settings().local_dev_auth_enabled is False
            else:
                assert benchmark_settings().local_dev_auth_enabled is True

            # 같은 요청이 만든 base 세션을 그대로 넘긴다 → 같은 세션 객체를 받는다.
            base_dependency = benchmark_db.get_db_session()
            try:
                base_session = next(base_dependency)
                auth_dependency = benchmark_db.get_auth_db_session(base_session)
                try:
                    auth_session = next(auth_dependency)
                    assert auth_session is base_session
                    assert auth_session.get_bind() is benchmark_db.engine
                finally:
                    auth_dependency.close()
            finally:
                base_dependency.close()

            # describe_target은 같은 연결임을 값 없이 요약한다(읽기 전용 아님).
            described = benchmark_db.describe_target()
            assert described["auth_connection"] == "database_url"
            assert described["shared_connection"] is True
            assert described["read_only"] is False
            assert "auth_read_only" not in described
            assert "://" not in str(described)

            # 강제 읽기 전용/계정 전용 연결 옵션을 다시 만들지 않았다.
            assert not hasattr(benchmark_db, "AUTH_CONNECT_ARGS")
            assert not hasattr(benchmark_db, "READ_ONLY_CONNECT_ARGS")
        finally:
            benchmark_settings.cache_clear()
            benchmark_db.reset_auth_engine()
            benchmark_db.reset_engine()


def test_preview_access_requires_the_original_jwt_and_admin_role():
    """preview 경계는 원본 current_user를 재사용하고 ADMIN만 통과시킨다."""
    import inspect

    from app.preview import access
    from app.core.sessions import current_user

    source = inspect.getsource(access.require_preview_admin)
    assert "current_user" in source

    # principal은 preview API가 실제로 쓰는 세 값만 담는다.
    assert set(access.PreviewPrincipal.__dataclass_fields__) == {"user_id", "email", "role"}

    from app.models.app_user import AppUser

    admin = AppUser(id=7, email="admin@example.test", role="ADMIN", is_active=True)
    principal = access.require_preview_admin(user=admin)
    assert (principal.user_id, principal.email, principal.role) == (7, "admin@example.test", "ADMIN")

    streamer = AppUser(id=8, email="streamer@example.test", role="STREAMER", is_active=True)
    with pytest.raises(Exception) as excinfo:
        access.require_preview_admin(user=streamer)
    assert getattr(excinfo.value, "status_code", None) == 403
    assert current_user is not None


def test_every_preview_caller_resolves_the_one_original_database_url(monkeypatch):
    """경기·이름·통계·계정 조회·저장 caller가 **같은 한 값**을 쓴다.

    사용자 지시(2026-11-12): 원래 benchmark `DATABASE_URL`과 그 계정의 기존 전체
    읽기·쓰기 권한을 그대로 쓴다. 새 역할/GRANT/별도 읽기 계정을 만들지 않는다.
    옛 프리뷰 DSN이 남아 있어도 caller가 다른 계정으로 분기하면, 사용자는 DSN 다섯
    개를 관리해야 하고 권한도 원래와 달라진다.
    """
    from app.core.config import get_settings as benchmark_settings
    from app.preview.config import get_settings as preview_settings

    original = "postgresql+psycopg://u:p@127.0.0.1:55432/preview_mp01_test"
    legacy = "postgresql+psycopg://legacy:legacy@127.0.0.1:55433/other_db"
    monkeypatch.setenv("DATABASE_URL", original)
    for key in (
        "PREVIEW_DATABASE_URL",
        "PREVIEW_DEV_DATABASE_URL",
        "PREVIEW_IDENTITY_DATABASE_URL",
        "PREVIEW_FIXTURES_DATABASE_URL",
        "PREVIEW_NAMES_DATABASE_URL",
        "PREVIEW_STATS_DATABASE_URL",
    ):
        monkeypatch.setenv(key, legacy)
    benchmark_settings.cache_clear()
    preview_settings.cache_clear()
    try:
        preview = preview_settings()
        # 다섯 호환 필드가 모두 원래 값이다(옛 키로 분기하지 않는다).
        for name in (
            "database_url",
            "resolved_identity_database_url",
            "fixtures_database_url",
            "names_database_url",
            "stats_database_url",
        ):
            assert getattr(preview, name) == original, name
        assert preview.is_connection_configured is True

        # 원래 앱 설정도 같은 값이다(별도 복제 없음).
        assert benchmark_settings().database_url == original

        # 통계 reader는 옛 전용 키가 아니라 원래 연결을 쓴다.
        from app.preview.sources import player_stats

        assert player_stats._settings_stats_url() == original
    finally:
        benchmark_settings.cache_clear()
        preview_settings.cache_clear()


def test_missing_original_url_is_reported_not_replaced(monkeypatch):
    """원래 `DATABASE_URL`이 없으면 대체 DSN 없이 명확히 실패한다."""
    from app.core.config import (
        PLACEHOLDER_DATABASE_URL,
        MissingDatabaseUrl,
        configured_database_url,
        resolved_database_url,
        get_settings,
    )

    monkeypatch.setenv("DATABASE_URL", PLACEHOLDER_DATABASE_URL)
    monkeypatch.setenv("PREVIEW_DATABASE_URL", "postgresql+psycopg://x:y@127.0.0.1:55432/other")
    get_settings.cache_clear()
    try:
        assert configured_database_url() is None
        with pytest.raises(MissingDatabaseUrl):
            resolved_database_url()
    finally:
        get_settings.cache_clear()


def test_launcher_does_not_overwrite_database_url_from_a_fixture_dsn():
    """런처는 원래 `DATABASE_URL`을 다른 DSN으로 덮어쓰지 않는다.

    이전 런처는 `BENCHMARK_READ_DATABASE_URL`/`PREVIEW_FIXTURES_DATABASE_URL`로
    덮어써 홈 조회가 fixture 읽기 역할로 붙었다. 그 경로가 돌아오면 사용자는 원래
    계정 권한을 잃고 홈 조회가 42501로 실패한다.
    """
    from pathlib import Path

    launcher = Path(__file__).resolve().parents[2] / "scripts" / "run_benchmark_dev.sh"
    source = launcher.read_text(encoding="utf-8")

    # 이름은 방어적 `unset` 줄에만 나올 수 있다. 연결 값으로 쓰이지 않는다.
    for line in source.splitlines():
        if "BENCHMARK_READ_DATABASE_URL" in line:
            assert line.lstrip().startswith("unset "), line
    # 대입 형태로 다른 DSN을 끼워 넣지 않는다(`DATABASE_URL="..."`).
    assert 'DATABASE_URL="${BENCHMARK' not in source
    assert 'DATABASE_URL="${PREVIEW_FIXTURES' not in source
    # 원래 값이 없으면 기동하지 않는다.
    assert 'DATABASE_URL="${DATABASE_URL:?' in source


class _PgError(Exception):
    """psycopg 오류 대역. 판정에 쓰는 sqlstate/diag만 흉내 낸다."""

    def __init__(self, sqlstate: str, table: str | None = None) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate
        self.diag = type("Diag", (), {"table_name": table, "schema_name": None})()


class _FakeSession:
    """저장점 동작만 흉내 내는 세션. 표 부재 뒤 세션 재사용 여부를 검사한다."""

    def __init__(self, errors: list[Exception], row=None) -> None:
        from contextlib import contextmanager

        self.info: dict = {}
        self.calls: list[int] = []
        self.rollbacks = 0
        self._errors = errors
        self._live = True
        self._row = row
        outer = self

        @contextmanager
        def begin_nested():
            # 실제 PostgreSQL/SQLAlchemy처럼, 문장 실패는 저장점 롤백으로만 풀린다.
            # 저장점이 없으면 세션은 중단 상태(25P02)로 남는다.
            try:
                yield
            except BaseException:
                outer.rollbacks += 1
                outer._live = True
                raise

        self.begin_nested = begin_nested

    def get(self, model, identifier):
        from sqlalchemy.exc import ProgrammingError

        self.calls.append(identifier)
        if self._live and self._errors:
            error = self._errors.pop(0)
            self._live = False
            raise error
        if not self._live:
            # 저장점이 되돌려지지 않았다면 실제 DB는 25P02(중단된 트랜잭션)로 실패한다.
            raise ProgrammingError("SELECT 1", {}, _PgError("25P02"))
        return self._row


def _undefined_table(statement: str, table: str | None = None):
    from sqlalchemy.exc import ProgrammingError

    return ProgrammingError(statement, {}, _PgError("42P01", table))


def test_preview_storage_absence_does_not_fail_the_public_home_boundary():
    """프리뷰 저장소 표가 없어도 경기 목록은 살아 있어야 한다.

    사용자 영향: 운영 DB에 `home_preview_publication`/`home_preview_version`이 아직
    없을 때 추천 조회가 503이 되면 방문자는 로그인 없이 볼 수 있는 경기 목록 자체를
    못 본다. 그래서 이 두 표의 부재만 미제공(`None`)으로 내려가고, 같은 세션의 후속
    조회가 계속 동작하며(저장점 롤백), 그 밖의 SQL 오류는 그대로 드러나야 한다.
    """
    from sqlalchemy.exc import ProgrammingError

    from app.models.home_preview import HomePreviewPublication
    from app.services import home_preview

    # 1) 표 부재는 미제공으로 흡수되고, 저장점이 되돌아가 같은 세션이 살아 있다.
    session = _FakeSession(
        [_undefined_table("SELECT ... FROM home_preview_publication WHERE fixture_id = %(p)s")]
    )
    assert home_preview.preview_row(session, HomePreviewPublication, 7) is None
    assert session.rollbacks == 1, "저장점 롤백 없이는 같은 세션 후속 조회가 25P02로 실패한다"
    assert home_preview.preview_storage_absent(session) is True

    # 2) 부재를 한 번 확인한 뒤에는 다시 조회하지 않는다(경기마다 반복 실패 방지).
    assert home_preview.preview_row(session, HomePreviewPublication, 8) is None
    assert session.calls == [7], session.calls

    # 3) 다른 표 부재·권한 오류·일반 SQL 오류는 빈 성공으로 감추지 않는다.
    #    (경기·번역 조회 실패가 "프리뷰 없음"이 되면 빈 경기 목록이 정상 응답이 된다.)
    for error in (
        _undefined_table("SELECT ... FROM league_translation", "league_translation"),
        ProgrammingError("SELECT ... FROM fixture", {}, _PgError("42501")),
        ProgrammingError("SELECT ... FROM fixture", {}, _PgError("42703")),
    ):
        failing = _FakeSession([error])
        with pytest.raises(type(error)):
            home_preview.preview_row(failing, HomePreviewPublication, 7)
        assert home_preview.preview_storage_absent(failing) is False

    # 문장에 표 이름이 있어도 위 두 표가 아니면 그대로 올린다.
    assert not home_preview.missing_preview_storage(
        _undefined_table("SELECT ... FROM league_sync_target")
    )
    assert home_preview.missing_preview_storage(
        _undefined_table("SELECT ... FROM home_preview_version")
    )

    # 4) 표가 있을 때 저장된 발행 행은 그대로 돌려준다(정상 제공 경로 보존).
    stored = object()
    healthy = _FakeSession([], row=stored)
    assert home_preview.preview_row(healthy, HomePreviewPublication, 9) is stored
    assert home_preview.preview_storage_absent(healthy) is False
