"""Monitor page — drift chart + retrain trigger + logs, one tab per task.

MOCK DATA: drift points and logs are synthesised deterministically so the
frontend can be built now. Replace ``_drift_points`` with reads from
``monitoring.metrics_log_path`` and ``retrain`` with a real job trigger
(src/monitoring, src/continual_learning) when those land — the response shapes
are the stable contract.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta

from fastapi import APIRouter

from deploy.schemas import DriftPoint, DriftResponse, LogsResponse, RetrainResponse
from deploy.tasks import validate_task
from src.utils import load_config

router = APIRouter(prefix="/monitor", tags=["monitor"])

_NUM_POINTS = 14


def _seeded_series(task: str, n: int) -> list[float]:
    """Deterministic pseudo-random drift series in ~[0.02, 0.30] for a task."""
    values: list[float] = []
    for i in range(n):
        h = hashlib.sha256(f"{task}:{i}".encode()).digest()
        # Trend upward slightly so the latest point can cross the threshold.
        base = (h[0] / 255.0) * 0.18
        values.append(round(base + i * 0.006, 4))
    return values


@router.get("/drift/{task}", response_model=DriftResponse)
def drift(task: str) -> DriftResponse:
    """Return the drift (PSI) time-series and alert flag for a task."""
    validate_task(task)
    cfg = load_config()
    metric = str(cfg.get_path("monitoring.drift_metric", "psi"))
    threshold = float(cfg.get_path("monitoring.psi_alert_threshold", 0.2))

    series = _seeded_series(task, _NUM_POINTS)
    today = date.today()
    points = [
        DriftPoint(
            date=(today - timedelta(days=_NUM_POINTS - 1 - i)).isoformat(),
            value=value,
        )
        for i, value in enumerate(series)
    ]
    alert = bool(series and series[-1] > threshold)
    return DriftResponse(
        task=task, metric=metric, threshold=threshold, alert=alert, points=points
    )


@router.post("/retrain/{task}", response_model=RetrainResponse)
def retrain(task: str) -> RetrainResponse:
    """Trigger a retrain for a task (stub: queues a job id, no real run yet)."""
    validate_task(task)
    job_id = f"retrain_{task}_{_short_token(task)}"
    return RetrainResponse(ok=True, task=task, job_id=job_id)


@router.get("/logs/{task}", response_model=LogsResponse)
def logs(task: str) -> LogsResponse:
    """Return recent log lines for a task (mock)."""
    validate_task(task)
    lines = [
        f"2026-07-16 09:00:01 INFO  [{task}] loaded active model version",
        f"2026-07-16 09:00:02 INFO  [{task}] drift monitor started (metric=psi)",
        f"2026-07-16 12:30:11 INFO  [{task}] evaluated 1,024 queries — FPR=0.9%",
        f"2026-07-16 15:45:03 WARN  [{task}] PSI rising on feature 'length'",
    ]
    return LogsResponse(task=task, lines=lines)


def _short_token(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()[:6]
