"""검증 오류가 제출된 비밀값을 되돌려주지 않는지 검사한다.

근거 출력에는 실제 자격 증명을 남기지 않는다. 아래 문자열은 테스트 전용
표식이며 어떤 계정의 비밀번호도 아니다.
"""

from __future__ import annotations

import pytest

LOGIN = "/api/v1/auth/login"
CANARY = "CANARY-do-not-echo-8f3a9c"


def _post(client, body: bytes, content_type: str = "application/json"):
    return client.post(LOGIN, content=body, headers={"content-type": content_type})


def _assert_no_echo(response) -> None:
    text = response.text
    assert response.status_code == 422, text
    assert CANARY not in text
    assert "CANARY" not in text
    # 본문 자체를 되돌려주지 않는다.
    assert '"input"' not in text
    for error in response.json()["detail"]:
        assert set(error) == {"type", "loc", "msg"}


def test_password_object_does_not_come_back_in_the_error(client):
    """루트가 보고한 재현: 숫자 email + 객체 password."""
    response = _post(
        client,
        b'{"email": 12345, "password": {"$secret": "' + CANARY.encode() + b'"}}',
    )
    _assert_no_echo(response)


def test_missing_email_with_password_present_does_not_echo_the_body(client):
    response = _post(client, b'{"password": "' + CANARY.encode() + b'"}')
    _assert_no_echo(response)


def test_missing_password_with_email_present_does_not_echo_the_body(client):
    response = _post(client, b'{"email": "someone@example.test"}')
    assert response.status_code == 422
    assert '"input"' not in response.text


def test_malformed_json_does_not_echo_the_body(client):
    response = _post(client, b'{"email": "a@b.test", "password": "' + CANARY.encode() + b'"')
    assert response.status_code == 422
    assert CANARY not in response.text
    assert '"input"' not in response.text


def test_wrong_content_type_does_not_echo_the_body(client):
    response = _post(
        client,
        b'{"email": "a@b.test", "password": "' + CANARY.encode() + b'"}',
        content_type="text/plain",
    )
    assert response.status_code == 422
    assert CANARY not in response.text


def test_array_body_does_not_echo_submitted_values(client):
    response = _post(client, b'["' + CANARY.encode() + b'"]')
    assert response.status_code == 422
    assert CANARY not in response.text


def test_empty_object_reports_both_required_fields(client):
    response = _post(client, b"{}")
    assert response.status_code == 422
    missing = {
        error["loc"][-1]
        for error in response.json()["detail"]
        if error["type"] == "missing"
    }
    assert missing == {"email", "password"}


def test_valid_credentials_are_not_echoed_in_a_success_body(client, make_user):
    user = make_user()
    response = client.post(LOGIN, json={"email": user["email"], "password": user["password"]})
    assert response.status_code == 200
    assert user["password"] not in response.text


@pytest.mark.parametrize("field", ["email", "password"])
def test_over_long_field_does_not_echo_the_value(client, field: str):
    payload = {"email": "someone@example.test", "password": "short-password"}
    payload[field] = "x" * 5000
    response = client.post(LOGIN, json=payload)
    assert response.status_code == 422
    assert "xxxxxxxxxx" not in response.text
