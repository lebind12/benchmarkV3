"""MP-10 LangGraph 체크포인트 저장소 어댑터 (preview_dev 한정).

무엇을 하는가:

- LangGraph 공식 `PostgresSaver`를 **preview_dev 스키마로 한정해** 연결한다.
  공식 saver의 DDL은 스키마를 생략한 `CREATE TABLE`이므로, 연결의 `search_path`를
  `preview_dev`로 고정하지 않으면 기존 `public` 영역에 표가 생길 수 있다.
- 표 생성(`setup`)은 **명시적 1회 준비**다. 앱 시작 시 자동 DDL을 돌리지 않는다.

무엇을 하지 않는가:

- 그래프 실행·상태 병합을 다시 구현하지 않는다(공식 런타임을 그대로 쓴다).
- 여러 저장 백엔드를 섞지 않는다. 개발 영역 DB 하나만 쓴다.
- 체크포인트는 **재개의 진행 위치**를 남기는 값이고, 사용자용 결과·원문 기록
  (`preview_results`·`preview_attempts`·`preview_section_results`)과 다른 축이다.
  체크포인트가 있다고 사용자 승인 근거나 결과 본문이 생기지는 않는다.

정직성:

- 체크포인트는 "외부 호출의 정확히 한 번 실행"을 보장하지 않는다. 전송 뒤 응답
  보존 전에 멈춘 시도는 `unknown`으로 남는다(기존 기록 계약).
- 저장된 체크포인트를 읽지 못하면 재개하지 않고 그 사실을 알린다.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Any, Iterator
from urllib.parse import quote

__all__ = [
    "CHECKPOINT_SCHEMA",
    "checkpointer_available",
    "ensure_checkpoint_tables",
    "checkpoint_conninfo",
    "open_checkpointer",
]

CHECKPOINT_SCHEMA = "preview_dev"


def checkpointer_available() -> tuple[bool, str | None]:
    """공식 Postgres saver를 쓸 수 있는지. 없으면 사유를 그대로 돌려준다."""
    try:
        from langgraph.checkpoint.postgres import PostgresSaver  # noqa: F401
    except Exception as exc:  # noqa: BLE001 - 설치돼 있지 않은 환경을 숨기지 않는다
        return False, f"langgraph-checkpoint-postgres를 불러오지 못했습니다: {exc}"
    try:
        import psycopg  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return False, f"psycopg를 불러오지 못했습니다: {exc}"
    return True, None


def checkpoint_conninfo(database_url: str, *, schema: str = CHECKPOINT_SCHEMA) -> str:
    """SQLAlchemy URL을 libpq conninfo로 바꾸고 `search_path`를 개발 스키마로 고정한다.

    공식 saver는 psycopg 연결 문자열을 받는다. 스키마를 여기서 고정하지 않으면
    `CREATE TABLE checkpoints`가 `public`에 떨어진다. 그래서 옵션으로 못 박는다.
    """
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise ValueError(f"refusing unsafe schema name: {schema!r}")
    plain = database_url
    for prefix in (
        "postgresql+psycopg://",
        "postgresql+psycopg2://",
        "postgresql://",
        "postgres://",
    ):
        if plain.startswith(prefix):
            plain = "postgresql://" + plain[len(prefix) :]
            break
    joiner = "&" if "?" in plain else "?"
    options = quote(f"-c search_path={schema}", safe="")
    return f"{plain}{joiner}options={options}"


def ensure_checkpoint_tables(database_url: str) -> None:
    """체크포인트 표를 한 번 준비한다. 앱 시작 시 자동으로 부르지 않는다.

    `scripts/preview_dev_migrate.py`가 명시적으로 호출하는 경로다.
    """
    from langgraph.checkpoint.postgres import PostgresSaver

    conninfo = checkpoint_conninfo(database_url)
    with PostgresSaver.from_conn_string(conninfo) as saver:
        saver.setup()


@contextmanager
def open_checkpointer(database_url: str) -> Iterator[Any]:
    """열린 체크포인터 하나. 호출자가 with 블록 안에서만 쓴다."""
    from langgraph.checkpoint.postgres import PostgresSaver

    conninfo = checkpoint_conninfo(database_url)
    with PostgresSaver.from_conn_string(conninfo) as saver:
        yield saver
