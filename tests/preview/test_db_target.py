"""연결 목적지 확정과 애플리케이션 로컬 검사의 동작.

`urlparse`의 호스트·경로만 보면 쿼리 인자·인코딩·다중 호스트로 목적지를 바꾼
URL을 통과시킨다. 여기서는 그런 URL이 연결 전에 거부되는지, 그리고 앱의
`PREVIEW_ALLOW_NONLOCAL_DB`가 테스트 가드를 열지 못하는지 확인한다.

거부 검사는 실제로 어디에도 접속하지 않는다. 소켓과 드라이버를 막아 두고
호출되면 실패하게 만든다.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.db_target import (
    AmbiguousDatabaseTarget,
    DatabaseTarget,
    parse_database_target,
)
from tests.preview._dbguard import UnsafeTestDatabase, assert_safe_test_database

BASE = "postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/preview_mp01_test"
DEV_BASE = "postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/preview_mp01_dev"

# 목적지를 URL 밖에서 바꾸는 형태들. 실제 psycopg·SQLAlchemy 파싱 결과로 확인했다.
AMBIGUOUS_URLS = [
    ("query dbname", BASE + "?dbname=preview_mp01_dev"),
    ("percent-encoded query key", BASE + "?%64bname=preview_mp01_dev"),
    ("repeated dbname", BASE + "?dbname=preview_mp01_test&dbname=preview_mp01_dev"),
    ("query host", BASE + "?host=10.9.9.9"),
    ("query hostaddr", BASE + "?hostaddr=10.9.9.9"),
    ("query port", BASE + "?port=5432"),
    ("query service", BASE + "?service=prod"),
    (
        "multihost netloc",
        "postgresql+psycopg://preview:pw@127.0.0.1,10.9.9.9:55432/preview_mp01_test",
    ),
    (
        "percent-encoded multihost netloc",
        "postgresql+psycopg://preview:pw@127.0.0.1%2C10.9.9.9:55432/preview_mp01_test",
    ),
    (
        "percent-encoded database path",
        "postgresql+psycopg://preview:pw@127.0.0.1:55432/preview%5Fmp01_dev",
    ),
    ("path with semicolon", BASE + ";host=10.9.9.9"),
    ("no host", "postgresql+psycopg:///preview_mp01_test"),
    ("no database", "postgresql+psycopg://preview:pw@127.0.0.1:55432"),
    ("sqlite", "sqlite:///./preview_test.db"),
]


@pytest.fixture()
def no_connections(monkeypatch):
    """연결을 여는 모든 경로를 막는다. 거부가 접속 없이 끝나는지 확인하는 데 쓴다."""
    import psycopg
    import socket

    import app.db as db_module

    def _explode(*_args, **_kwargs):
        raise AssertionError("a connection was attempted for a rejected target")

    monkeypatch.setattr(socket, "getaddrinfo", _explode)
    monkeypatch.setattr(socket, "create_connection", _explode)
    monkeypatch.setattr(psycopg, "connect", _explode)
    monkeypatch.setattr(db_module, "create_engine", _explode)


def test_explicit_single_target_is_accepted():
    target = parse_database_target(BASE, environ={})
    assert target == DatabaseTarget(host="127.0.0.1", port=55432, database="preview_mp01_test")
    assert target.is_loopback


def test_connection_only_query_parameters_stay_accepted():
    """목적지를 바꾸지 않는 libpq 키워드는 막지 않는다."""
    target = parse_database_target(
        BASE + "?sslmode=require&connect_timeout=3&application_name=preview-tests",
        environ={},
    )
    assert target.database == "preview_mp01_test"


@pytest.mark.parametrize(("label", "url"), AMBIGUOUS_URLS, ids=[c[0] for c in AMBIGUOUS_URLS])
def test_ambiguous_target_is_rejected_before_any_connection(label, url, no_connections):
    with pytest.raises(AmbiguousDatabaseTarget) as raised:
        parse_database_target(url, environ={})
    assert "ambiguous database target" in str(raised.value)


@pytest.mark.parametrize(("label", "url"), AMBIGUOUS_URLS, ids=[c[0] for c in AMBIGUOUS_URLS])
def test_destructive_guard_rejects_ambiguous_target_without_connecting(label, url, no_connections):
    with pytest.raises(UnsafeTestDatabase) as raised:
        assert_safe_test_database(url, environ={})
    assert "tests refuse" in str(raised.value)


@pytest.mark.parametrize(("label", "url"), AMBIGUOUS_URLS, ids=[c[0] for c in AMBIGUOUS_URLS])
def test_application_local_check_rejects_ambiguous_target(label, url, no_connections):
    with pytest.raises(RuntimeError) as raised:
        Settings(database_url=url).assert_local_database()
    assert "Refusing to connect" in str(raised.value)


def test_rejection_never_reaches_the_driver(monkeypatch):
    """거부된 URL은 엔진 생성에도 닿지 않는다."""
    calls: list[str] = []

    import app.db as db_module

    monkeypatch.setattr(db_module, "create_engine", lambda *a, **k: calls.append("engine"))

    with pytest.raises(RuntimeError):
        Settings(database_url=BASE + "?host=10.9.9.9").assert_local_database()
    with pytest.raises(UnsafeTestDatabase):
        assert_safe_test_database(BASE + "?dbname=preview_mp01_dev", environ={})

    assert calls == []


def test_libpq_hostaddr_environment_cannot_retarget_a_valid_url():
    """PGHOSTADDR는 URL의 host를 연결 시점에 바꾸므로 확정 불가로 본다."""
    with pytest.raises(AmbiguousDatabaseTarget):
        parse_database_target(BASE, environ={"PGHOSTADDR": "10.9.9.9"})


def test_nonlocal_opt_in_never_opens_the_test_guard(monkeypatch):
    """애플리케이션 우회 플래그는 테스트 격리를 풀지 못한다."""
    monkeypatch.setenv("PREVIEW_ALLOW_NONLOCAL_DB", "1")
    remote = "postgresql+psycopg://preview:secret@db.example.com:5432/preview_mp01_test"

    with pytest.raises(UnsafeTestDatabase):
        assert_safe_test_database(remote, environ={})
    with pytest.raises(UnsafeTestDatabase):
        assert_safe_test_database(BASE + "?host=db.example.com", environ={})


def test_nonlocal_opt_in_still_rejects_an_ambiguous_target():
    settings = Settings(database_url=BASE + "?host=db.example.com", allow_nonlocal_db=True)
    with pytest.raises(RuntimeError):
        settings.assert_local_database()


def test_nonlocal_opt_in_only_applies_to_a_confirmed_single_target():
    settings = Settings(
        database_url="postgresql+psycopg://preview:secret@db.example.com:5432/preview_mp01_dev",
        allow_nonlocal_db=True,
    )
    settings.assert_local_database()
    assert settings.database_host == "db.example.com"


def test_guard_and_application_agree_on_the_same_url():
    """두 계층이 같은 판정을 쓰는지 고정한다."""
    for _label, url in AMBIGUOUS_URLS:
        with pytest.raises(UnsafeTestDatabase):
            assert_safe_test_database(url, environ={})
        with pytest.raises(RuntimeError):
            Settings(database_url=url).assert_local_database()


def test_error_messages_do_not_echo_the_password():
    secret = "sup3r-secret-value"
    url = f"postgresql+psycopg://preview:{secret}@127.0.0.1:55432/preview_mp01_test?dbname=preview_mp01_dev"
    with pytest.raises(UnsafeTestDatabase) as raised:
        assert_safe_test_database(url, environ={})
    assert secret not in str(raised.value)
