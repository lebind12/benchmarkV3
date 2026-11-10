"""표시 경계 이름 변환 (MP-10 통합).

무엇을 하는가:

- 실행 하나의 팀·선수 표시 이름을 DB의 한국어 값으로 바꾼 **파사드 하나**를 만든다.
- 경기 제목, 주목 선수 목록, 본문 문장을 같은 파사드로 처리한다.

무엇을 하지 않는가:

- 저장 본문·원문 응답·승인 스탬프를 다시 쓰지 않는다. 변환은 **화면에 내보내는 값**에만
  적용한다. 그래서 과거 승인이 검토한 본문은 그대로 남는다.
- 번역하지 않는다. 해석기가 DB에서 찾은 값만 쓴다. 없으면 원문 표기를 유지하고 사유를
  관리자 진단으로 넘긴다.
- 이름 때문에 실행을 실패시키지 않는다. 설정이 없거나 읽기가 실패하면 원문을 그대로 쓴다.

읽기 범위:

- 필요한 팀 2개(홈·원정)와 그 로스터만 읽는다. 필터 없는 조회는 해석기가 거부한다.
- 연결은 요청/실행 단위로 하나 만들고 끝나면 닫는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from app.preview.football_terms import rewrite_football_terms

__all__ = [
    "DisplayNameBridge",
    "open_display_names",
    "localize_section_payload",
]


@dataclass
class DisplayNameBridge:
    """한 실행의 표시 이름 파사드와 그 진단.

    `names`가 `None`이면 변환을 하지 않는다(설정 없음·읽기 실패). 화면은 원문을 쓰고
    관리자는 `note`에서 이유를 본다.
    """

    names: Any | None = None
    note: str | None = None
    fixture_label: str | None = None
    unmapped: list[dict[str, Any]] = field(default_factory=list)
    # 모델이 같은 응답에서 준 한국어 표기 반영 결과(관리자 진단 전용).
    model_labels: list[dict[str, Any]] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self.names is not None

    def label(self, *, fixture: Mapping[str, Any] | None, fallback: str) -> str:
        """경기 제목. 해석하지 못하면 저장된 원래 표기를 그대로 쓴다."""
        if self.fixture_label:
            return self.fixture_label
        if self.names is None or not isinstance(fixture, Mapping):
            return fallback
        try:
            resolved = self.names.fixture_label(
                home_team_id=_int_or_none(fixture.get("home_team_id")),
                away_team_id=_int_or_none(fixture.get("away_team_id")),
                # 저장 자료 경로의 팀 ID는 DB 내부 키다(API 팀 ID가 아니다).
                id_space="internal",
                fallback=fallback,
            )
        except Exception:  # noqa: BLE001 - 표시 실패로 실행을 깨지 않는다
            return fallback
        return str(resolved or fallback)

    def localize_players(
        self, items: Sequence[Mapping[str, Any]], *, scope_team_ids: Sequence[int]
    ) -> list[dict[str, Any]]:
        """주목 선수 목록의 표시 이름을 바꾼다. 원본 항목은 보존한다.

        해석기가 확정한 모델 표기는 자동으로 치환 표기에 등록되므로, 이 단계를 본문
        치환보다 먼저 해야 본문의 같은 선수도 같은 값으로 바뀐다.
        """
        if self.names is None or not items:
            return [dict(item) for item in items]
        try:
            result = self.names.watch_players(
                [dict(item) for item in items], scope_team_ids=list(scope_team_ids)
            )
        except Exception as exc:  # noqa: BLE001
            self.note = f"선수 표시 이름을 확인하지 못했습니다: {exc}"
            return [dict(item) for item in items]
        self.unmapped.extend(
            dict(entry.to_dict()) if hasattr(entry, "to_dict") else dict(entry)
            for entry in getattr(result, "unmapped", ()) or ()
        )
        rows = []
        for row in getattr(result, "rows", ()) or ():
            rows.append(dict(row))
        return rows or [dict(item) for item in items]

    def register_model_labels(self, labels: Any) -> None:
        """같은 생성 응답이 준 한국어 표기를 반영한다(DB 값이 있으면 DB가 이긴다).

        번역은 모델이 낸 것이며 이 코드가 만들지 않는다. 해석기가 없으면(설정 없음)
        아무것도 하지 않고, 그 사실을 진단에 남긴다.
        """
        if not labels:
            return
        if self.names is None:
            self.note = (
                "이름 해석기가 없어 모델이 준 한국어 표기를 표시에 반영하지 못했습니다."
            )
            return
        register = getattr(self.names, "register_model_labels", None)
        if not callable(register):
            return
        try:
            self.model_labels.extend(dict(item) for item in register(labels))
        except Exception as exc:  # noqa: BLE001
            self.note = f"모델 번역 표기를 반영하지 못했습니다: {exc}"

    def rewrite_body(self, text: str) -> str:
        """본문 문장을 한국어 표기로 바꾼다. URL·미확인 고유명사는 그대로 둔다.

        순서: ① 축구 용어·대회명 사전 ② 해석기가 확인한 팀·선수 표기(DB 우선).
        두 단계 모두 표기만 바꾸며 수치·사건·신원을 만들지 않는다.
        """
        if not text:
            return text
        rewritten = rewrite_football_terms(text)
        if self.names is None:
            return rewritten
        try:
            return str(self.names.rewrite_body(rewritten) or rewritten)
        except Exception as exc:  # noqa: BLE001
            self.note = f"본문 표시 이름을 바꾸지 못했습니다: {exc}"
            return rewritten


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def open_display_names(
    *,
    fixture: Mapping[str, Any] | None,
    dsn: str | None,
    fallback_label: str,
    player_ids: Iterable[int] = (),
) -> DisplayNameBridge:
    """실행 하나의 표시 이름 파사드를 연다. 실패는 원문 유지로 흡수한다.

    호출자는 반환값의 `.close()`를 부를 필요가 없다. 조회기는 여기서 만들고 여기서
    닫되, 파사드가 들고 있는 인덱스는 이미 메모리 값이라 연결 없이 동작한다.
    """
    bridge = DisplayNameBridge()
    if not dsn:
        bridge.note = (
            "이름 읽기 연결이 설정되지 않아 저장된 원래 표기를 그대로 표시합니다."
        )
        return bridge
    if not isinstance(fixture, Mapping):
        bridge.note = "경기 식별자가 없어 표시 이름을 확인하지 않았습니다."
        return bridge
    home = _int_or_none(fixture.get("home_team_id"))
    away = _int_or_none(fixture.get("away_team_id"))
    if home is None or away is None:
        bridge.note = "팀 식별자가 없어 표시 이름을 확인하지 않았습니다."
        return bridge

    try:
        from app.preview.localized_names import (
            DbNameLookup,
            DisplayNames,
            load_name_index,
        )

        lookup = DbNameLookup.from_url(dsn)
        try:
            index = load_name_index(
                lookup,
                team_ids=[home, away],
                include_rosters=True,
                player_ids=[int(item) for item in player_ids if item],
            )
        finally:
            # 인덱스는 메모리 값이다. 연결은 여기서 닫고 파사드는 계속 쓴다.
            lookup.close()
    except Exception as exc:  # noqa: BLE001 - 설정·권한·연결 실패를 숨기지 않되 막지 않는다
        bridge.note = (
            "이름 읽기를 사용할 수 없어 저장된 원래 표기를 그대로 표시합니다:"
            f" {type(exc).__name__}"
        )
        return bridge

    bridge.names = DisplayNames(index)
    bridge.fixture_label = bridge.label(fixture=fixture, fallback=fallback_label)
    return bridge


def localize_section_payload(
    payload: Mapping[str, Any],
    *,
    bridge: DisplayNameBridge,
    fixture: Mapping[str, Any] | None,
    scope_team_ids: Sequence[int] = (),
    body_text: str | None = None,
) -> dict[str, Any]:
    """저장 payload에서 **화면에 낼 값만** 한국어 표기로 바꾼 사본을 만든다.

    반환값은 새 딕셔너리다. 입력 payload(저장 행 내용)는 수정하지 않는다.
    """
    # 모델이 같은 응답에서 준 한국어 표기를 먼저 반영한다(DB 값이 있으면 DB가 이긴다).
    # 해석기가 없어도 용어 사전은 동작하므로 아래 body 처리는 계속한다.
    bridge.register_model_labels(payload.get("korean_labels"))

    if not bridge.active:
        localized = dict(payload)
        text = body_text if body_text is not None else payload.get("body")
        if isinstance(text, str) and text:
            # 해석기가 없어도 축구 용어·대회명은 한국어로 바꾼다.
            localized["body"] = bridge.rewrite_body(text)
        return localized

    localized = dict(payload)
    scope = [int(item) for item in scope_team_ids if item is not None]
    for key in ("hot_players", "players"):
        items = [item for item in payload.get(key) or () if isinstance(item, Mapping)]
        if not items:
            continue
        localized[key] = bridge.localize_players(items, scope_team_ids=scope)
    text = body_text if body_text is not None else payload.get("body")
    if isinstance(text, str) and text:
        localized["body"] = bridge.rewrite_body(text)
    return localized
