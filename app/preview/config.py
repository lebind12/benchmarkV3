"""프리뷰 설정 (원래 benchmark 연결 그대로 사용).

**접속 자격 증명의 기준은 하나다.** 원래 benchmark의 `DATABASE_URL`과 그 계정의
기존 전체 읽기·쓰기 권한을 그대로 쓴다. 프리뷰의 경기·이름·통계·계정 조회·생성
결과 저장 caller도 같은 값에서 연결을 얻는다. 새 계정·전용 읽기 역할·신규 GRANT·
별도 DSN 다섯 개를 만들지 않는다. 사용자가 관리할 DSN도 하나다.

이 클래스는 원래 `app.core.config`와 **singleton을 공유하지 않는다**(프리뷰 전용
설정 축: 저장 스키마 `preview_dev`, 세션 수명, 모델 제공자). 다만 DB 주소는 예외
없이 원래 `DATABASE_URL` 하나에서 온다.

호환 필드(`database_url`, `identity_database_url`, `fixtures_database_url`,
`names_database_url`, `stats_database_url`)는 남겨 두되 **모두 같은 기준값**을
돌려주는 읽기 전용 property다. 옛 환경 키(`PREVIEW_DATABASE_URL`,
`PREVIEW_IDENTITY_DATABASE_URL`, `PREVIEW_FIXTURES_DATABASE_URL`,
`PREVIEW_NAMES_DATABASE_URL`, `PREVIEW_STATS_DATABASE_URL`)는 더 이상 읽지 않으므로
다른 계정으로 분기시키지 못한다.

스킴(SQLite 등)과 목적지 확정은 `parse_database_target`이 연결 전에 거부한다.
비루프백 대상은 `PREVIEW_ALLOW_NONLOCAL_DB`가 있어야만 허용한다.

계약: `app.preview.config.get_settings() -> PreviewSettings`. 이관 전 이름
(`Settings`)을 같은 클래스의 별칭으로 둔다. 저장 schema(`preview_dev`)도 유지한다.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import configured_database_url, resolved_database_url
from app.core.db_target import AmbiguousDatabaseTarget, parse_database_target

Environment = Literal["dev", "test", "prod"]

# 로컬 합성 계정용 예시 DSN. 실제 연결은 원래 `DATABASE_URL`만 쓴다.
# 이 값은 `scripts/preview_ui_fixture.py` 같은 로컬 검사 도구가 명시적으로
# `DATABASE_URL`을 세울 때 참고하는 이름으로만 남는다.
LOCAL_DEV_DATABASE_URL = (
    "postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/preview_mp01_dev"
)

__all__ = [
    "Environment",
    "PreviewSettings",
    "Settings",
    "get_settings",
    "LOCAL_DEV_DATABASE_URL",
]


class PreviewSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PREVIEW_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 저장소(`preview_dev`)·세션·모델 설정만 이 이름공간이 소유한다. DB 주소는
    # 아래 property가 원래 `DATABASE_URL`에서 가져온다(필드로 복제하지 않는다).
    env: Environment = "dev"
    session_ttl_seconds: int = Field(default=8 * 60 * 60, gt=0, le=7 * 24 * 60 * 60)
    cookie_secure: bool = False
    allow_nonlocal_db: bool = False
    # 이전 이름을 그대로 받아 둔다(자격 증명 파일·기존 문서 호환). 새 역할이나 별도
    # DSN을 뜻하지 않으며, 같은 단일 연결의 비루프백 동의로만 쓰인다.
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

    # --- 원래 benchmark 연결 (단일 기준) ----------------------------------
    @property
    def database_url(self) -> str:
        """원래 `DATABASE_URL`. 미설정이면 `MissingDatabaseUrl`로 멈춘다."""
        return resolved_database_url()

    @property
    def connection_url(self) -> str | None:
        """원래 `DATABASE_URL` 원문 또는 `None`(미설정). 값은 출력하지 않는다."""
        return configured_database_url()

    @property
    def is_connection_configured(self) -> bool:
        return configured_database_url() is not None

    # --- 호환 필드 (모두 같은 기준값) --------------------------------------
    # 기존 caller가 이름만 다르게 부르던 다섯 DSN을 하나로 합친다. 각 property는
    # 같은 원래 URL을 돌려주므로, 어떤 caller도 다른 계정으로 분기하지 않는다.
    @property
    def identity_database_url(self) -> str | None:
        return configured_database_url()

    @property
    def resolved_identity_database_url(self) -> str:
        return resolved_database_url()

    @property
    def fixtures_database_url(self) -> str | None:
        return configured_database_url()

    @property
    def names_database_url(self) -> str | None:
        return configured_database_url()

    @property
    def stats_database_url(self) -> str | None:
        return configured_database_url()

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
        """단일 연결 대상 검사(개발 저장·경기·이름·통계 공통).

        `PREVIEW_ALLOW_NONLOCAL_DB`가 비루프백 대상의 명시 동의다. 이 플래그만
        켜는 것으로 운영 접속 준비가 끝났다고 간주하지 않는다.
        """
        self._assert_usable(
            resolved_database_url(),
            allow_nonlocal=self.allow_nonlocal_db,
            label="the shared benchmark connection",
        )

    def assert_identity_database(self) -> None:
        """계정 조회 연결 대상 검사.

        같은 기준값을 쓰지만 동의 규칙은 기존 identity 경로 그대로 둔다
        (`PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB` 또는 기존 `..._DB` 플래그).
        """
        self._assert_usable(
            resolved_database_url(),
            allow_nonlocal=self.allow_nonlocal_identity_db or self.allow_nonlocal_db,
            label="the shared benchmark connection",
        )

    def assert_stats_database(self) -> None:
        """선수 통계 조회 연결 대상 검사."""
        self.assert_local_database()

    @property
    def database_host(self) -> str:
        return self.database_target.host

    @property
    def database_target(self):
        """연결 전에 확정한 목적지. 확정할 수 없으면 그 자체로 거부한다."""
        return parse_database_target(resolved_database_url())

    @property
    def is_loopback_database(self) -> bool:
        return self.database_target.is_loopback


# 이관 전 이름. 같은 클래스이며 별도 singleton을 만들지 않는다.
Settings = PreviewSettings


@lru_cache
def get_settings() -> PreviewSettings:
    return PreviewSettings()
