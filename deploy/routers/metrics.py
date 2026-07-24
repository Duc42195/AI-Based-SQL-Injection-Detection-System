"""Metrics endpoint — serves evaluation reports for the dashboard/metrics page."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

from deploy.registry import get_registry
from deploy.schemas import MetricsResponse
from src.utils import get_logger, load_config

logger = get_logger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/nhanh1", response_model=MetricsResponse)
def nhanh1_metrics() -> MetricsResponse:
    """Return Branch-1 evaluation metrics.

    Prefers ``reports/nhanh1_eval.json``; falls back to the model's
    ``metadata.json`` (which carries F1-macro and training stats). Returns a
    structured ``not_ready`` if neither exists yet.
    """
    cfg = load_config()
    reports_dir = Path(cfg.get_path("paths.reports_dir", "report/metrics"))
    eval_path = reports_dir / "nhanh1_eval.json"

    if eval_path.exists():
        try:
            with eval_path.open("r", encoding="utf-8") as handle:
                return MetricsResponse(source=str(eval_path), metrics=json.load(handle))
        except (OSError, ValueError):
            logger.warning("Could not parse %s", eval_path)

    # Fall back to the model metadata (always small, gitignored-except-metadata).
    model = get_registry().nhanh1()
    if model is not None and model.metadata:
        return MetricsResponse(source="model metadata.json", metrics=model.metadata)

    return MetricsResponse(
        status="not_ready",
        detail="No Branch-1 evaluation report or model metadata found.",
    )
