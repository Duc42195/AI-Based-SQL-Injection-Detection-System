"""Metrics endpoint — serves evaluation reports for the dashboard/metrics page."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

from deploy.registry import get_registry
from deploy.schemas import MetricsResponse
from deploy.tasks import validate_task
from src.utils import get_logger, load_config

logger = get_logger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/{task}", response_model=MetricsResponse)
def task_metrics(task: str) -> MetricsResponse:
    """Return evaluation metrics for a branch.

    Prefers ``<reports_dir>/<task>_eval.json``; for Branch 1 falls back to the
    loaded model's ``metadata.json`` (which carries F1-macro and training
    stats). Returns a structured ``not_ready`` if neither exists yet.
    """
    validate_task(task)
    cfg = load_config()
    reports_dir = Path(cfg.get_path("paths.reports_dir", "report/metrics"))
    eval_path = reports_dir / f"{task}_eval.json"

    if eval_path.exists():
        try:
            with eval_path.open("r", encoding="utf-8") as handle:
                return MetricsResponse(source=str(eval_path), metrics=json.load(handle))
        except (OSError, ValueError):
            logger.warning("Could not parse %s", eval_path)

    # Fall back to the model metadata (always small, gitignored-except-metadata).
    if task == "branch1":
        model = get_registry().branch1()
        if model is not None and model.metadata:
            return MetricsResponse(source="model metadata.json", metrics=model.metadata)

    return MetricsResponse(
        status="not_ready",
        detail=f"No evaluation report found for {task}.",
    )
