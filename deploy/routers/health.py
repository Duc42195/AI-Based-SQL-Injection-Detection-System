"""Health / readiness endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from deploy.registry import get_registry
from deploy.schemas import HealthResponse
from src.utils import load_config

router = APIRouter(tags=["ops"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report liveness and per-branch model readiness."""
    cfg = load_config()
    return HealthResponse(
        api_version=str(cfg.get_path("api.api_version", "v1")),
        branches=get_registry().status(),
    )
