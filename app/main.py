"""FastAPI application entrypoint.

원래 benchmark 앱(인증·관리·홈·수집 조회)과 프리뷰 기능이 **같은 앱**에 있다.
앱은 하나이고, 설정/저장 연결만 목적별로 분리한다.

- 원래 벤치마크 라우터: `/health`, `/api/v1/auth/*`, `/api/v1/home/*`,
  `/api/v1/admin*`, `/api/v1/fixtures*`, `/api/v1/broadcast*`, `/api/v1/*`(general).
  이 라우터들은 원래 `app.core.config.get_settings()`와 원래 `app.db`(public 모델)
  연결을 그대로 쓴다.
- 프리뷰 라우터: `/api/v1/admin/preview/*`. 인증은 같은 앱의 원래 JWT를 재사용하고
  (`app.preview.access.require_preview_admin`), 저장 연결만 `app.preview.db`
  (`preview_dev` 스키마)로 분리한다.

경계:

- 라우터를 두 벌 만들지 않는다. `/api/v1/auth`는 원래 라우터 하나뿐이다.
- 원래 세션 의존성(`app.db.get_db_session`)을 전역 dependency override로 프리뷰
  세션으로 바꾸지 않는다. 그렇게 하면 원래 public 모델 쿼리가 개발 스키마로 간다.
- scheduler는 기본적으로 꺼져 있다(`WORKER_SCHEDULER_ENABLED=false`). 로컬 시험에서
  자동 수집·자동 마이그레이션을 시작하지 않는다.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.fixture_detail import router as fixture_detail_router
from app.api.v1 import preview_admin as preview_admin_module
from app.api.v1 import preview_metrics as preview_metrics_module
from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.broadcast import router as broadcast_router
from app.api.v1.fixture_detail_analytics import router as fixture_detail_analytics_router
from app.api.v1.general import router as general_router
from app.api.v1.home import router as home_router
from app.api.v1.home_preview import router as home_preview_router
from app.api.v1.management import router as management_router
from app.core.config import allowed_web_origins
from app.core.validation import install_validation_error_scrubber
from app.core.worker_scheduler import shutdown_worker_scheduler, start_worker_scheduler


def _cors_origins() -> list[str]:
    return allowed_web_origins()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = start_worker_scheduler()
    app.state.worker_scheduler = scheduler
    try:
        yield
    finally:
        shutdown_worker_scheduler(scheduler)


app = FastAPI(
    title="benchmark API",
    description="축구 정보 사이트 백엔드 (방송용 페이지 포함).",
    version="0.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 검증 오류 응답에서 제출 본문을 제거한다(로그인 비밀번호 등). 원래 인증 경로와
# 프리뷰 경로가 같은 앱이므로 한 번만 설치한다.
install_validation_error_scrubber(app)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe used by Koyeb / load balancer health checks."""
    return {"status": "ok"}


app.include_router(home_router, prefix="/api/v1/home")
app.include_router(auth_router)
app.include_router(broadcast_router)
app.include_router(admin_router)
app.include_router(management_router)
app.include_router(general_router)
app.include_router(fixture_detail_router)
app.include_router(fixture_detail_analytics_router)

app.include_router(home_preview_router)

# 프리뷰 기능. 원래 앱과 같은 프로세스에서 돈다. 접두어는 `/api/v1/admin/preview`다.
app.include_router(preview_admin_module.router)
app.include_router(preview_metrics_module.router)


def create_app() -> FastAPI:
    """검사·기동 편의를 위한 팩토리. 모듈 수준 `app`과 같은 라우터 구성을 돌려준다."""
    from app.main import app as _app

    return _app
