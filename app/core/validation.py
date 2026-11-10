"""검증 오류 응답에서 요청 본문을 제거한다.

FastAPI 기본 422 응답은 `detail[].input`에 제출된 값을 그대로 되돌려준다.
로그인 비밀번호처럼 민감한 값이 오류 응답에 실려 나가지 않도록, 검증 오류는
필드 위치와 이유만 남기고 제출값은 버린다.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _safe_entry(error: dict[str, Any]) -> dict[str, Any]:
    """`loc`·`type`·`msg`만 남긴다. `input`·`ctx`·`url`은 본문이나 값을 담을 수 있다."""
    loc = [str(part) for part in error.get("loc", ())]
    return {
        "type": str(error.get("type", "validation_error")),
        "loc": loc,
        "msg": str(error.get("msg", "invalid value")),
    }


def install_validation_error_scrubber(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _scrubbed(_request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        safe = [_safe_entry(error) for error in errors]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": safe}
        )
