"""테스트 DB 가드 자체의 동작 검사.

이 파일은 DB에 연결하지 않는다. 문자열 판정만 검사하므로, 잘못된 URL을 넣어도
의도하지 않은 DB에 붙지 않는다. 픽스처의 파괴적 준비 단계보다 먼저 실행되도록
`engine`·`client` 픽스처를 쓰지 않는다.
"""

from __future__ import annotations

import pytest

from tests.preview._dbguard import UnsafeTestDatabase, assert_safe_test_database

DEV_URL = "postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/preview_mp01_dev"
PROD_URL = "postgresql+psycopg://preview:secret@127.0.0.1:55432/preview_production"
BASE_NAME_URL = "postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/postgres"
TEMPLATE_URL = "postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/template1"
REMOTE_URL = "postgresql+psycopg://preview:secret@db.example.com:5432/preview_mp01_test"
SQLITE_URL = "sqlite:///./preview_test.db"
TEST_URL = "postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/preview_mp01_test"


def test_dedicated_local_test_database_is_accepted():
    target = assert_safe_test_database(TEST_URL)
    assert target.host == "127.0.0.1"
    assert target.port == 55432
    assert target.name == "preview_mp01_test"


@pytest.mark.parametrize(
    ("label", "url"),
    [
        ("development database", DEV_URL),
        ("production database", PROD_URL),
        ("shared default database", BASE_NAME_URL),
        ("postgres template database", TEMPLATE_URL),
        ("sqlite substitute", SQLITE_URL),
    ],
)
def test_non_test_databases_are_rejected(label: str, url: str):
    with pytest.raises(UnsafeTestDatabase) as raised:
        assert_safe_test_database(url)
    assert "dedicated test database" in str(raised.value) or "PostgreSQL" in str(raised.value)


def test_non_loopback_test_database_is_rejected():
    with pytest.raises(UnsafeTestDatabase) as raised:
        assert_safe_test_database(REMOTE_URL)
    assert "non-loopback" in str(raised.value)


def test_nonlocal_override_does_not_apply_to_tests(monkeypatch):
    """애플리케이션 설정의 우회 플래그가 테스트 가드를 열지 못한다."""
    monkeypatch.setenv("PREVIEW_ALLOW_NONLOCAL_DB", "1")
    with pytest.raises(UnsafeTestDatabase) as raised:
        assert_safe_test_database(REMOTE_URL)
    assert "PREVIEW_ALLOW_NONLOCAL_DB does not apply to tests" in str(raised.value)


def test_local_override_still_cannot_pick_a_dev_database(monkeypatch):
    monkeypatch.setenv("PREVIEW_ALLOW_NONLOCAL_DB", "1")
    with pytest.raises(UnsafeTestDatabase):
        assert_safe_test_database(DEV_URL)


def test_dev_name_is_rejected_even_though_the_host_is_local():
    """루프백이라는 이유만으로 개발 DB를 지우게 두지 않는다."""
    with pytest.raises(UnsafeTestDatabase) as raised:
        assert_safe_test_database(DEV_URL)
    assert "preview_mp01_dev" in str(raised.value)


def test_rejection_happens_before_any_connection(monkeypatch):
    """가드가 연결 생성 코드에 닿기 전에 실패하는지 호출 순서로 확인한다."""
    import app.db as db_module

    def _explode(*_args, **_kwargs):
        raise AssertionError("a connection was attempted for an unsafe test database")

    monkeypatch.setattr(db_module, "create_engine", _explode)
    with pytest.raises(UnsafeTestDatabase):
        assert_safe_test_database(DEV_URL)
