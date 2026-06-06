from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import db
from app.api.v1.auth import router
from app.core.security import hash_password, verify_password

pytestmark = pytest.mark.unit


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE app_user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'USER'
                    CHECK (role IN ('USER', 'STREAMER', 'ADMIN')),
                nickname TEXT,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                email_verified BOOLEAN NOT NULL DEFAULT 0,
                last_login_at DATETIME,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_session():
        with SessionLocal() as session:
            yield session

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[db.get_db_session] = override_session
    app.state.SessionLocal = SessionLocal
    return TestClient(app)


def test_password_hash_roundtrip():
    password_hash = hash_password("Bench1234")

    assert password_hash != "Bench1234"
    assert verify_password("Bench1234", password_hash)
    assert not verify_password("wrong-password", password_hash)


def test_signup_creates_user_with_default_role(client: TestClient):
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "email": " NewUser@Example.COM ",
            "password": "Bench1234",
            "nickname": "  New User  ",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user"] == {
        "id": 1,
        "email": "newuser@example.com",
        "role": "USER",
        "nickname": "New User",
        "is_active": True,
    }


def test_signup_rejects_duplicate_email(client: TestClient):
    payload = {
        "email": "dup@example.com",
        "password": "Bench1234",
    }
    assert client.post("/api/v1/auth/signup", json=payload).status_code == 201

    response = client.post(
        "/api/v1/auth/signup",
        json={**payload, "email": "DUP@example.com"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "email_already_registered"


def test_signup_rejects_weak_password(client: TestClient):
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "email": "weak@example.com",
            "password": "abcdefgh",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "weak_password"


def test_login_returns_user_for_valid_credentials(client: TestClient):
    signup_response = client.post(
        "/api/v1/auth/signup",
        json={
            "email": "login@example.com",
            "password": "Bench1234",
            "nickname": "Login User",
        },
    )
    assert signup_response.status_code == 201

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": " LOGIN@example.com ",
            "password": "Bench1234",
        },
    )

    assert response.status_code == 200
    assert response.json()["user"] == {
        "id": 1,
        "email": "login@example.com",
        "role": "USER",
        "nickname": "Login User",
        "is_active": True,
    }
    with client.app.state.SessionLocal() as session:
        last_login_at = session.execute(
            text("SELECT last_login_at FROM app_user WHERE email='login@example.com'")
        ).scalar_one()
    assert last_login_at is not None


def test_login_rejects_invalid_credentials(client: TestClient):
    assert client.post(
        "/api/v1/auth/signup",
        json={
            "email": "wrong@example.com",
            "password": "Bench1234",
        },
    ).status_code == 201

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "wrong@example.com",
            "password": "Wrong1234",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_credentials"


def test_login_rejects_inactive_user(client: TestClient):
    assert client.post(
        "/api/v1/auth/signup",
        json={
            "email": "inactive@example.com",
            "password": "Bench1234",
        },
    ).status_code == 201
    with client.app.state.SessionLocal() as session:
        session.execute(
            text("UPDATE app_user SET is_active=0 WHERE email='inactive@example.com'")
        )
        session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "inactive@example.com",
            "password": "Bench1234",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "inactive_user"
