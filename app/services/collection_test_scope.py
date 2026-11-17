"""기간 지정 프리뷰 시험의 요청 범위 값(불변).

이 모듈은 **값만** 정의한다. 실행 엔진·수집기·생성기를 만들지 않는다. 라우터(경계)가
검증한 범위를 수집 계획과 종료 훅에 전달하는 공통 표현이며, 안쪽 코드는 이 값을 다시
검증하지 않는다(Boundary Discipline: 경계에서 파싱·검증, 내부는 신뢰).

경계 원칙:

- 시험 범위는 **요청별 값**이다. 전역 설정·OS 시계·경기 킥오프를 바꾸지 않는다.
- 6시간 조건 예외는 이 값이 지목한 경기 ID에만 적용한다. 일반 수집·정기 실행에는 이
  값이 없으므로 예외가 존재하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "PREVIEW_TEST_MAX_FIXTURES",
    "PreviewTestScope",
]


# 이번 계약이 지원하는 지정 경기 수. 두 경기 시험이 최소 계약이며 범용 기능이 아니다.
PREVIEW_TEST_MAX_FIXTURES = 2


@dataclass(frozen=True)
class PreviewTestScope:
    """한 시험 요청의 수집 기간과 프리뷰 대상 경기.

    `fixture_from`/`fixture_to`는 시간대를 가진 값이며 **양 끝을 포함**한다. 두 경기
    (`preview_fixture_ids`)만 시간창 조건 예외를 받는다.
    """

    fixture_from: datetime
    fixture_to: datetime
    preview_fixture_ids: tuple[int, int]
    # 이 시험이 붙을 수집 실행 ID. 같은 시험의 중복 생성을 막는 키의 일부다.
    run_id: str = ""
    # 수집이 끝난 뒤 프리뷰 생성을 시작할지. 기본값은 기존 동작(생성함)이다.
    #
    # `False`는 **수집만** 실행하는 요청이다. 종료 훅이 정상·부분 실패·상위 예외 어느
    # 경로로 끝나도 생성 호출 0회여야 하며, 생성 결과 키(`home_preview`)도 만들지 않는다
    # (없는 결과를 "생성 실패"로 읽히게 하지 않기 위해서다).
    generate_after_collection: bool = True

    def in_window(self, kickoff_at: Any) -> bool:
        """이 시각이 수집 기간 안인지(양 끝 포함). 시간대 없는 값은 포함하지 않는다."""
        if not isinstance(kickoff_at, datetime):
            return False
        moment = kickoff_at if kickoff_at.tzinfo else None
        if moment is None:
            return False
        return self.fixture_from <= moment <= self.fixture_to

    def is_preview_fixture(self, fixture_id: Any) -> bool:
        """이 외부 경기 ID가 시험의 프리뷰 대상인지."""
        try:
            return int(fixture_id) in self.preview_fixture_ids
        except (TypeError, ValueError):
            return False

    def to_dict(self) -> dict[str, Any]:
        """실행 기록에 저장할 표현. 시간대를 보존한다."""
        return {
            "fixture_from": self.fixture_from.isoformat(),
            "fixture_to": self.fixture_to.isoformat(),
            "preview_fixture_ids": list(self.preview_fixture_ids),
            "run_id": self.run_id,
            "generate_after_collection": self.generate_after_collection,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "PreviewTestScope | None":
        """저장된 값을 복원한다. 형식이 아니면 `None`(시험 범위 없음으로 본다)."""
        if not isinstance(value, Mapping):
            return None
        try:
            start = datetime.fromisoformat(str(value["fixture_from"]))
            end = datetime.fromisoformat(str(value["fixture_to"]))
            ids = tuple(int(item) for item in value["preview_fixture_ids"])
        except (KeyError, TypeError, ValueError):
            return None
        if len(ids) != 2 or start.tzinfo is None or end.tzinfo is None:
            return None
        if start > end:
            return None
        # 저장된 키가 없는 옛 기록은 **기존 동작(생성함)** 으로 복원한다. 이 키가 없다고
        # 자동 생성을 끄면, 이미 접수된 실행의 의미가 복원 과정에서 바뀐다.
        generate = value.get("generate_after_collection", True)
        if not isinstance(generate, bool):
            return None
        return cls(
            fixture_from=start,
            fixture_to=end,
            preview_fixture_ids=(ids[0], ids[1]),  # type: ignore[arg-type]
            run_id=str(value.get("run_id") or ""),
            generate_after_collection=generate,
        )

    def with_run_id(self, run_id: str) -> "PreviewTestScope":
        """수집 실행 ID를 붙인 사본. 실행 생성 뒤에 확정된다."""
        return PreviewTestScope(
            fixture_from=self.fixture_from,
            fixture_to=self.fixture_to,
            preview_fixture_ids=self.preview_fixture_ids,
            run_id=str(run_id),
            generate_after_collection=self.generate_after_collection,
        )
