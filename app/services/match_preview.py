"""경기 프리뷰 생성의 **단일 진입점**.

이 모듈이 책임지는 것:

- 외부 경기 번호(API-Football `fixture_id`)를 **저장된 경기 자료에서 해석**한다.
- 해석한 경기로 기존 LangGraph(`run_bundle_pipeline`)를 **한 번** 호출한다.
- 그 실행의 결과(`BundlePipelineOutcome`)를 그대로 돌려준다.

이 모듈이 책임지지 않는 것:

- 생성 엔진·프롬프트·모듈 재작성. 여기서 새 파이프라인을 만들지 않는다.
- 다른 서버로의 HTTP 프록시. 같은 앱 안에서 함수로 부른다.
- 품질 판정·자동 재생성·콘텐츠 성공 판단. **성공 판단은 사용자 몫**이다.

호출자:

- 관리자 명시 실행(`POST /api/v1/admin/preview/bundle-runs`) → `trigger='admin'`.
- 기존 수집 완료 hook → `trigger='collection'`(후속 단계에서 연결).

actor 경계:

- 관리자 경로는 인증된 관리자의 실제 `user_id`를 넘긴다.
- 수집 경로는 시스템 호출이며 **가짜 ADMIN ID를 만들지 않는다.** 관리자 ID로
  위장하면 감사 기록이 사실과 달라진다. 그래서 `actor_id=None`을 허용하고, 실행
  기록에는 "관리자 계정 아님"을 표시하는 별도 값을 쓴다.

재시도 의미(사용자 확정 2026-11-12):

한 번의 생성 실행에서 **각 논리 AI 모듈의 최초 포함 최대 3회**다. 전체 8회·다른
경기·이전 시험 집합 누적 차감은 쓰지 않는다. 이 정책은 `app/preview/retry.py`의
`RunBudget.for_generation()`이 소유하며, 이 모듈은 그 경로를 쓰기만 한다.

DB 경계:

- 저장 경기·부상·순위·이름·통계 자료는 **읽기 전용** 조회기로 읽는다.
- 쓰기는 `preview_dev` 스키마의 preview 실행·섹션 행뿐이다.
- 시작 시 마이그레이션·수집·자동 실행을 하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping, Protocol

from sqlalchemy.orm import Session

from app.preview import bundle_pipeline
from app.preview.bundle_pipeline import BundlePipelineOutcome
from app.preview.config import PreviewSettings, get_settings

__all__ = [
    "COLLECTION_ACTOR_ID",
    "FixtureResolution",
    "FixtureResolutionError",
    "FixtureResolver",
    "generate_match_preview",
    "resolve_stored_fixture",
]

Trigger = Literal["admin", "collection"]

# 수집(시스템) 경로가 실행 기록에 쓰는 actor 값. **실제 관리자 ID가 아니다.**
# preview 실행 행의 `actor_id`는 NOT NULL 정수이므로 0을 쓰고, 라벨에 시스템
# 호출임을 남긴다. 관리자 계정처럼 보이는 값을 지어내지 않는다.
COLLECTION_ACTOR_ID = 0

# 수집 경로 실행 라벨에 붙이는 표기. 관리자 실행과 구분해 화면·감사에서 확인한다.
_COLLECTION_LABEL = "수집 완료 후 자동 생성(시스템 호출)"


class FixtureResolutionError(RuntimeError):
    """외부 경기 번호를 저장된 경기로 해석할 수 없다.

    호출자는 이 예외를 **모델 전송 전 중단**으로 다룬다. 숫자를 0으로 채우거나
    다른 경기로 대체하지 않는다.
    """

    def __init__(self, message: str, *, reason: str, status_hint: int | None = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.status_hint = status_hint


@dataclass(frozen=True)
class FixtureResolution:
    """저장된 경기에서 해석한 실행 입력."""

    fixture: Mapping[str, Any]
    record: Any
    label: str

    @property
    def fixture_id(self) -> int:
        return int(self.fixture["fixture_id"])


class FixtureResolver(Protocol):
    """외부 번호 → 저장 경기 조회기 계약(읽기 전용).

    기존 `StoredFixtureReader`가 이 계약을 만족한다. 테스트는 같은 메서드를 가진
    가짜 객체를 넘겨 실제 DB 없이 해석 경계만 확인한다.
    """

    def access(self) -> Any: ...

    def get_fixture(self, *, fixture_id: int) -> Any: ...

    def close(self) -> None: ...


def _resolver_from_settings(settings: PreviewSettings) -> FixtureResolver | None:
    """설정에서 저장 경기 조회기를 만든다. 설정이 없으면 `None`(추측하지 않는다)."""
    url = getattr(settings, "fixtures_database_url", None)
    if not url:
        return None
    from app.preview.sources.fixtures import StoredFixtureReader

    return StoredFixtureReader.from_url(url)


def resolve_stored_fixture(
    fixture_id: int,
    *,
    reader: FixtureResolver | None = None,
    settings: PreviewSettings | None = None,
) -> FixtureResolution:
    """외부 경기 번호 하나를 저장된 경기로 해석한다.

    반환은 `run_bundle_pipeline`이 그대로 받는 fixture dict다. 읽기 권한이 없거나
    저장 자료에 없는 번호는 `FixtureResolutionError`로 멈춘다(모델 전송 0회).
    """
    if int(fixture_id) <= 0:
        raise FixtureResolutionError(
            f"경기 번호 {fixture_id}는 외부 경기 번호가 아닙니다.",
            reason="invalid_fixture_id",
            status_hint=422,
        )

    borrowed = reader is None
    opener = reader or _resolver_from_settings(settings or get_settings())
    if opener is None:
        raise FixtureResolutionError(
            "저장된 경기 자료 조회기가 설정되지 않아 경기 번호를 해석할 수 없습니다."
            " 모델을 보내지 않았습니다.",
            reason="reader_unconfigured",
            status_hint=503,
        )
    try:
        access = opener.access()
        if not getattr(access, "readable", False):
            detail = getattr(access, "detail", None) or "읽기 권한을 확인하지 못했습니다."
            raise FixtureResolutionError(
                f"저장된 경기 자료를 읽을 수 없습니다: {detail}",
                reason="reader_denied",
                status_hint=503,
            )
        try:
            record = opener.get_fixture(fixture_id=int(fixture_id))
        except FixtureResolutionError:
            raise
        except Exception as exc:  # noqa: BLE001 - 연결 실패를 빈 결과로 감추지 않는다
            raise FixtureResolutionError(
                f"저장된 경기 자료를 읽지 못했습니다: {type(exc).__name__}: {exc}",
                reason="reader_failed",
                status_hint=503,
            ) from None
    finally:
        if borrowed:
            close = getattr(opener, "close", None)
            if callable(close):
                close()

    if record is None:
        raise FixtureResolutionError(
            f"저장된 경기 번호 {fixture_id}를 찾지 못했습니다.",
            reason="fixture_not_found",
            status_hint=404,
        )
    if getattr(record, "home_team_id", None) is None or (
        getattr(record, "away_team_id", None) is None
    ):
        raise FixtureResolutionError(
            "이 경기는 홈·원정 팀이 확정되지 않아 프리뷰 대상이 아닙니다."
            " 팀 ID를 0으로 채우지 않고 모델을 보내지 않았습니다.",
            reason="fixture_incomplete",
            status_hint=422,
        )
    fixture = {
        "fixture_id": int(record.fixture_id),
        "league_id": int(record.league_id),
        "season": int(record.season),
        "home_team_id": int(record.home_team_id),
        "away_team_id": int(record.away_team_id),
        "kickoff_at": record.kickoff_at.isoformat(),
    }
    return FixtureResolution(fixture=fixture, record=record, label=record.label)


def generate_match_preview(
    *,
    fixture_id: int,
    actor_id: int | None,
    trigger: Trigger,
    session: Session,
    transport: Any,
    reader: FixtureResolver | None = None,
    http: Any = None,
    label: str | None = None,
    settings: PreviewSettings | None = None,
    target_checker: Any = None,
    checkpointer: Any | None = None,
    now: Any = None,
    mode: Any = None,
    limits: Any = None,
) -> BundlePipelineOutcome:
    """경기 한 건의 프리뷰를 **기존 LangGraph로 한 번** 생성한다.

    인자:

    - `fixture_id`: API-Football 외부 경기 번호. 내부 DB 기본키가 아니다.
    - `actor_id`: 인증된 관리자의 실제 ID. 수집(시스템) 호출이면 `None`.
    - `trigger`: `'admin'`(관리자 명시 실행) 또는 `'collection'`(수집 완료 hook).
    - `session`: preview 쓰기 세션(`app.preview.db.get_db()`).
    - `transport`: 모델 전송 어댑터. live 여부는 이 객체의 mode가 정한다.

    반환은 기존 `BundlePipelineOutcome` 그대로다. 저장된 본문·섹션 결과 ID·묶음
    ID·예산 스냅샷이 모두 들어 있다. 이 함수는 결과를 **판정하지 않는다**.
    """
    if trigger not in ("admin", "collection"):
        raise ValueError(f"unknown trigger: {trigger!r}")

    # 조회기 수명: 한 번 열어 **해석과 생성 단계가 같은 조회기**를 쓴다.
    #
    # 이전에는 해석 단계가 설정으로 조회기를 열고 곧바로 닫은 뒤, 파이프라인에는 원래
    # `reader`(=None)를 넘겼다. 그래서 경기 식별·부상·순위 같은 본문 자료 준비가
    # "저장 경기 자료 읽기 연결이 설정되지 않았습니다"(readable=false, not_run)로 비었다.
    # 자료가 없거나 DB가 고장 난 것이 아니라 조회기를 넘기지 않은 연결 결함이다.
    #
    # 소유권: 호출자가 조회기를 주입하면 그대로 쓰고 **닫지 않는다**(호출자 소유).
    # 주입이 없으면 이 서비스가 설정에서 열고, 성공·해석 오류·생성 오류 모두에서 닫는다.
    owned_reader = None
    effective_reader = reader
    if effective_reader is None:
        owned_reader = _resolver_from_settings(settings or get_settings())
        effective_reader = owned_reader
    try:
        resolution = resolve_stored_fixture(
            fixture_id, reader=effective_reader, settings=settings
        )

        if actor_id is not None and int(actor_id) <= 0:
            # 인증된 actor가 아닌 값을 실제 관리자처럼 넘기지 않는다.
            raise ValueError(
                "actor_id는 인증된 관리자의 양의 정수 ID이거나 None이어야 합니다."
            )
        if trigger == "collection" and actor_id is not None:
            raise ValueError(
                "수집(시스템) 호출은 관리자 ID로 위장하지 않습니다. actor_id=None을 쓰세요."
            )
        if trigger == "admin" and actor_id is None:
            raise ValueError("관리자 실행에는 인증된 actor_id가 필요합니다.")

        run_actor_id = COLLECTION_ACTOR_ID if actor_id is None else int(actor_id)
        if trigger == "collection":
            run_label = f"{label or _COLLECTION_LABEL}"
        else:
            run_label = label

        kwargs: dict[str, Any] = {
            "fixture": dict(resolution.fixture),
            "actor_id": run_actor_id,
            "transport": transport,
            "reader": effective_reader,
            "http": http,
            "label": run_label,
            # 모듈별 3회 상한은 run_bundle_pipeline이 `RunBudget.for_generation`으로
            # 세운다. 여기서 전체 8회·trial prior를 다시 주입하지 않는다.
            "module_send_cap": bundle_pipeline.MODULE_SEND_CAP,
        }
        if target_checker is not None:
            kwargs["target_checker"] = target_checker
        if checkpointer is not None:
            kwargs["checkpointer"] = checkpointer
        if now is not None:
            kwargs["now"] = now
        if mode is not None:
            kwargs["mode"] = mode
        if limits is not None:
            kwargs["limits"] = limits

        return bundle_pipeline.run_bundle_pipeline(session, **kwargs)
    finally:
        # 이 서비스가 연 조회기만 닫는다. 호출자가 주입한 조회기는 호출자 소유이므로
        # 건드리지 않는다. 해석 오류·생성 오류에서도 같은 지점에서 정리된다.
        if owned_reader is not None:
            close = getattr(owned_reader, "close", None)
            if callable(close):
                close()
