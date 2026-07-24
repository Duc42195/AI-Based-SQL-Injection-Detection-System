"""FastAPI application: wires config, CORS, routers and startup model loading.

Run locally:
    uv run uvicorn deploy.main:app --reload --port 8000
Interactive docs at http://localhost:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from deploy.registry import get_registry
from deploy.routers import (
    admin,
    data,
    demo,
    detect,
    health,
    metrics,
    monitor,
    nhanh1,
    nhanh2,
    nhanh3,
    train,
)
from src.utils import get_logger, load_config

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm the model registry at startup so the first request isn't slow."""
    status = get_registry().status()
    logger.info("API startup — branch readiness: %s", status)
    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI application from config."""
    cfg = load_config()
    api_version = str(cfg.get_path("api.api_version", "v1"))
    prefix = f"/api/{api_version}"
    cors_origins = cfg.get_path("api.cors_origins", ["*"])

    app = FastAPI(
        title=str(cfg.get_path("api.title", "SQLi Detection API")),
        version=api_version,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health lives at the root; everything else under the versioned prefix.
    app.include_router(health.router)
    app.include_router(detect.router, prefix=prefix)
    app.include_router(nhanh1.router, prefix=prefix)
    app.include_router(nhanh2.router, prefix=prefix)
    app.include_router(nhanh3.router, prefix=prefix)
    app.include_router(metrics.router, prefix=prefix)
    app.include_router(admin.router, prefix=prefix)
    # MLOps + Test-page routers.
    app.include_router(demo.router, prefix=prefix)
    app.include_router(monitor.router, prefix=prefix)
    app.include_router(data.router, prefix=prefix)
    app.include_router(train.router, prefix=prefix)
    return app


app = create_app()
