"""FastAPI application entrypoint.

Phase 0 scaffold: only exposes `/health` for liveness verification. Real
endpoints arrive in later phases per `Plans.md`.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.fixture_detail import router as fixture_detail_router
from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.broadcast import router as broadcast_router
from app.api.v1.fixture_detail_analytics import router as fixture_detail_analytics_router
from app.api.v1.general import router as general_router
from app.api.v1.home import router as home_router
from app.core.config import get_settings
from app.core.worker_scheduler import shutdown_worker_scheduler, start_worker_scheduler


def _cors_origins() -> list[str]:
    raw = get_settings().cors_allow_origins
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or ["*"]


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
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe used by Koyeb / load balancer health checks."""
    return {"status": "ok"}


app.include_router(home_router, prefix="/api/v1/home")
app.include_router(auth_router)
app.include_router(broadcast_router)
app.include_router(admin_router)
app.include_router(general_router)
app.include_router(fixture_detail_router)
app.include_router(fixture_detail_analytics_router)
