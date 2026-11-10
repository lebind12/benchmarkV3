"""기존 운영 계정 인증 호환성과 기존 행 무변경 경계.

합성 입력만 쓴다. 운영 계정을 만들거나 조회하지 않고, 운영 DB에 이 테스트를
실행하지 않는다(`tests/preview/_dbguard.py`가 전용 로컬 테스트 DB만 허용).

검사 이유: 기존 계정은 `pbkdf2_sha256` 해시와 대문자 역할을 쓴다. 현재 앱이
그 형식을 검증하지 못하면 사용자는 실제 계정으로 로그인할 수 없고, 로그인 과정이
기존 행을 갱신하면 "기존 자료 읽기 전용" 기준을 위반한다.
"""

from __future__ import annotations

from sqlalchemy import text

from app.auth.passwords import hash_pbkdf2_sha256, verify_pbkdf2_sha256

LOGIN = "/api/v1/auth/login"
PROTECTED = "/api/v1/admin/preview/runs"


def test_pbkdf2_roundtrip_matches_the_stored_format():
    """저장 형식(`scheme$iterations$salt$digest`)과 검증이 서로 맞는지 확인한다."""
    stored = hash_pbkdf2_sha256("synthetic-password-1")
    scheme, iterations, salt, digest = stored.split("$")
    assert scheme == "pbkdf2_sha256"
    assert int(iterations) == 260_000
    assert salt and digest
    assert verify_pbkdf2_sha256("synthetic-password-1", stored) is True
    assert verify_pbkdf2_sha256("wrong-password", stored) is False


def test_unsupported_hash_formats_are_refused_rather_than_accepted():
    """argon2·bcrypt 등 다른 형식이나 손상된 값은 통과시키지 않는다."""
    argon2_like = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
    bcrypt_like = "$2b$12$" + "a" * 53
    for value in (argon2_like, bcrypt_like, "", "not-a-hash", "pbkdf2_sha256$x$y$z"):
        assert verify_pbkdf2_sha256("any-password", value) is False


def test_stored_iteration_count_is_honoured():
    """행마다 다른 반복 횟수를 그대로 따라 계산하는지 확인한다(대표 사례)."""
    stored = hash_pbkdf2_sha256("synthetic-password-2", iterations=210_000)
    assert stored.split("$")[1] == "210000"
    assert verify_pbkdf2_sha256("synthetic-password-2", stored) is True


def test_admin_login_succeeds_with_a_production_shaped_account(client, make_user):
    """기존 계정 형태(대문자 ADMIN, pbkdf2)로 로그인해 보호 경로까지 간다."""
    user = make_user(role="ADMIN")
    response = client.post(
        LOGIN, json={"email": user["email"], "password": user["password"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "ADMIN"
    assert client.get(PROTECTED).status_code == 200


def test_login_does_not_touch_the_existing_account_row(client, make_user, session_factory):
    """로그인·조회가 기존 계정 행을 갱신하지 않는지 확인한다.

    과거 구현은 로그인 성공 시 `last_login_at`을 갱신했다. 지금 기준은 기존 행
    무변경이므로, 로그인 전후 행 스냅샷이 같아야 한다.
    """
    user = make_user(role="ADMIN")
    with session_factory() as session:
        before = session.execute(
            text(
                "SELECT password_hash, role, is_active, last_login_at, updated_at "
                "FROM public.app_user WHERE id = :id"
            ),
            {"id": user["id"]},
        ).one()

    assert client.post(
        LOGIN, json={"email": user["email"], "password": user["password"]}
    ).status_code == 200
    assert client.get(PROTECTED).status_code == 200

    with session_factory() as session:
        after = session.execute(
            text(
                "SELECT password_hash, role, is_active, last_login_at, updated_at "
                "FROM public.app_user WHERE id = :id"
            ),
            {"id": user["id"]},
        ).one()

    assert tuple(before) == tuple(after)


def test_session_rows_are_written_only_to_the_development_schema(
    client, make_user, session_factory
):
    """로그인 쓰기가 `preview_dev`로만 가고 공용 스키마에는 남지 않는지 확인한다."""
    user = make_user(role="ADMIN")
    assert client.post(
        LOGIN, json={"email": user["email"], "password": user["password"]}
    ).status_code == 200

    with session_factory() as session:
        dev_rows = session.execute(
            text("SELECT count(*) FROM preview_dev.preview_admin_sessions")
        ).scalar_one()
        public_sessions = session.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name LIKE '%session%'"
            )
        ).scalar_one()
    assert dev_rows == 1
    assert public_sessions == 0


def test_non_admin_production_account_is_refused(client, make_user):
    """기존 계정이라도 ADMIN이 아니면 403이다. STREAMER도 대체 권한이 아니다."""
    for role in ("USER", "STREAMER"):
        user = make_user(role=role)
        response = client.post(
            LOGIN, json={"email": user["email"], "password": user["password"]}
        )
        assert response.status_code == 403, response.text
        assert response.json()["detail"] == "admin role required"
