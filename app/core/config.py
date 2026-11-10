"""애플리케이션 설정.

두 연결을 분리한다.

1. `PREVIEW_DATABASE_URL` — 개발 쓰기 연결. 세션 행만 `preview_dev` 스키마에 쓴다.
   기존 `public` 영역에 대한 쓰기 권한은 DB 역할에서 제거돼 있다.
2. `PREVIEW_IDENTITY_DATABASE_URL` — 기존 운영 계정 `public.app_user` 읽기 전용
   연결. 설정하지 않으면 개발 DB를 그대로 쓴다(로컬 합성 계정 검사용).

스킴(SQLite 등)과 목적지 확정은 `parse_database_target`이 연결 전에 거부한다.
비루프백 대상은 각각의 명시 플래그가 있어야만 허용한다. 플래그만 켜는 것으로
운영 접속 준비가 끝났다고 간주하지 않는다. 실제 대상 확인과 권한 분리는
`scripts/preview_dev_provision.py`와 검증 절차가 담당한다.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.db_target import AmbiguousDatabaseTarget, parse_database_target

Environment = Literal["dev", "test", "prod"]

LOCAL_DEV_DATABASE_URL = (
    "postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/preview_mp01_dev"
)

__all__ = ["Environment", "Settings", "get_settings", "LOCAL_DEV_DATABASE_URL"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PREVIEW_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(default=LOCAL_DEV_DATABASE_URL)
    identity_database_url: str | None = None
    # 저장된 경기·부상·순위 자료 읽기 전용 연결(별도 좁은 역할).
    # 설정이 없으면 조회기는 붙지 않고 화면에 `stored_access.readable=false`가 남는다.
    fixtures_database_url: str | None = None
    # 팀·선수 표시 이름(한국어) 읽기 전용 연결. 이름 열만 SELECT하는 별도 역할이라
    # fixture/identity DSN을 재사용하지 않는다. 설정이 없으면 표시 이름 변환을
    # 건너뛰고 원문 표기를 그대로 쓴다(번역을 지어내지 않는다).
    names_database_url: str | None = None
    env: Environment = "dev"
    session_ttl_seconds: int = Field(default=8 * 60 * 60, gt=0, le=7 * 24 * 60 * 60)
    cookie_secure: bool = False
    allow_nonlocal_db: bool = False
    allow_nonlocal_identity_db: bool = False

    # --- MP-04 모델 제공자 설정 -------------------------------------------
    # 비밀값은 이름만 두고 값은 환경에서만 읽는다. 조회·보고서에 값을 출력하지
    # 않는다. `model_credentials_json`은 서비스 계정 JSON 원문이며 로그에 남기지
    # 않는다(저장소 계약 `__repr__`에서도 가린다).
    model_provider: str = "vertex"
    model_project: str | None = None
    model_location: str = "global"
    model_name: str | None = None
    model_credentials_json: str | None = Field(default=None, repr=False)
    model_timeout_seconds: int = Field(default=300, gt=0)
    # 실제 유료 호출은 명시적 플래그가 있을 때만 열린다. 기본은 닫힘이다.
    model_live_enabled: bool = False

    @model_validator(mode="after")
    def _identity_defaults_to_dev(self) -> "Settings":
        if not self.identity_database_url:
            self.identity_database_url = self.database_url
        return self

    @property
    def resolved_identity_database_url(self) -> str:
        return self.identity_database_url or self.database_url

    def _assert_usable(self, url: str, *, allow_nonlocal: bool, label: str) -> None:
        try:
            target = parse_database_target(url)
        except AmbiguousDatabaseTarget as exc:
            raise RuntimeError(
                f"Refusing to connect: {exc}. {label} requires a single explicit target."
            ) from None
        if target.is_loopback or allow_nonlocal:
            return
        raise RuntimeError(
            f"Refusing to connect {label} to a non-loopback database ({target.host}). "
            "Set the matching allow-nonlocal flag only if the target is deliberate."
        )

    def assert_local_database(self) -> None:
        """개발 쓰기 연결 대상 검사.

        `PREVIEW_ALLOW_NONLOCAL_DB`는 기존 이름을 유지한다. 이 플래그가 개발 쓰기
        연결에 적용되며, 신원 읽기 연결에는 별도 플래그를 쓴다.
        """
        self._assert_usable(
            self.database_url,
            allow_nonlocal=self.allow_nonlocal_db,
            label="the development session store",
        )

    def assert_identity_database(self) -> None:
        """기존 계정 읽기 연결 대상 검사."""
        same_as_dev = self.resolved_identity_database_url == self.database_url
        self._assert_usable(
            self.resolved_identity_database_url,
            allow_nonlocal=self.allow_nonlocal_identity_db
            or (self.allow_nonlocal_db and same_as_dev),
            label="the identity reader",
        )

    @property
    def database_host(self) -> str:
        return self.database_target.host

    @property
    def database_target(self):
        """연결 전에 확정한 목적지. 확정할 수 없으면 그 자체로 거부한다."""
        return parse_database_target(self.database_url)

    @property
    def is_loopback_database(self) -> bool:
        return self.database_target.is_loopback


@lru_cache
def get_settings() -> Settings:
    return Settings()
