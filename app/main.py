"""FastAPI 앱 팩토리.

MP-01 범위는 ADMIN 로그인과 빈 실행 목록까지다. 실행 추적 저장소·조사 모듈·
지표·배포는 이 앱에 아직 없다.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1 import auth, preview_admin
from app.core.config import get_settings
from app.db import get_session_factory

logger = logging.getLogger("match_preview")

LOCAL_DEV_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Match Preview", version="0.1.0")

    if settings.env in ("dev", "test"):
        # 세션 쿠키를 주고받으려면 자격 증명 허용과 정확한 오리진이 필요하다.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=LOCAL_DEV_ORIGINS,
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["content-type"],
        )

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        """DB까지 실제로 확인한다. 연결 실패를 ok로 꾸미지 않는다."""
        try:
            with get_session_factory()() as session:
                session.execute(text("SELECT 1"))
        except (SQLAlchemyError, RuntimeError):
            logger.exception("database health check failed")
            return {"status": "degraded", "database": "unavailable"}
        return {"status": "ok", "database": "ok"}

    app.include_router(auth.router)
    app.include_router(preview_admin.router)
    return app


app = create_app()
