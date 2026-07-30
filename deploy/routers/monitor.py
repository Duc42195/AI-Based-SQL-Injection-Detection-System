"""Monitor page — drift, retrain trigger and logs, one tab per task.

Branch 1 serves the **real** drift record written by a stream replay
(``POST /mlops/replay``) or by the offline experiment. Branches 2 and 3 have no
drift pipeline yet and report ``not_ready`` rather than inventing a series — a
monitor that fabricates numbers is worse than one that admits it has none.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from deploy.schemas import DriftPoint, DriftResponse, LogsResponse, RetrainResponse
from deploy.tasks import validate_task
from src.continual_learning.gate import read_decisions
from src.continual_learning.trainer import RUNS_LOG, train_and_seal
from src.utils import get_logger, load_config

logger = get_logger(__name__)

router = APIRouter(prefix="/monitor", tags=["monitor"])


def _artifacts(cfg) -> Path:
    return Path(cfg.get_path("mlops.artifacts_dir", "report/metrics/continual_learning"))


@router.get("/drift/{task}", response_model=DriftResponse)
def drift(task: str) -> DriftResponse:
    """Return the measured drift series for a task.

    Every monitored PSI signal is returned per window, so the UI can show which
    signals move and which stay flat — which is the point of the experiment.
    """
    validate_task(task)
    cfg = load_config()
    threshold = float(cfg.get_path("monitoring.psi_alert_threshold", 0.2))
    metric = str(cfg.get_path("monitoring.drift_metric", "psi"))

    record_path = _artifacts(cfg) / "drift.json"
    if task != "branch1" or not record_path.exists():
        detail = (
            "No drift pipeline for this branch yet."
            if task != "branch1"
            else "No drift record yet — run a replay (POST /api/v1/mlops/replay)."
        )
        return DriftResponse(
            task=task,
            metric=metric,
            threshold=threshold,
            alert=False,
            status="not_ready",
            detail=detail,
            points=[],
        )

    with record_path.open("r", encoding="utf-8") as handle:
        record: dict[str, Any] = json.load(handle)

    windows = record.get("windows", [])
    signals = sorted({name for w in windows for name in w.get("psi", {})})
    points = [
        DriftPoint(
            date=f"w{w['index']}",
            value=float(max(w.get("psi", {}).values(), default=0.0)),
            index=int(w["index"]),
            phase=str(w.get("phase", "")),
            is_reference=bool(w.get("is_reference", False)),
            psi=w.get("psi", {}),
            rates=w.get("rates", {}),
        )
        for w in windows
    ]
    trigger = record.get("trigger", {})
    return DriftResponse(
        task=task,
        metric=metric,
        threshold=float(record.get("threshold", threshold)),
        alert=bool(trigger.get("fired", False)),
        status="ready",
        signals=signals,
        trigger=trigger,
        reference=record.get("reference"),
        generated_at=record.get("generated_at"),
        points=points,
    )


@router.post("/retrain/{task}", response_model=RetrainResponse)
def retrain(task: str) -> RetrainResponse:
    """Trigger a real retrain for Branch 1 (others are not wired yet).

    Returns the ``run_id``, which is the same key ``/train`` reports — no
    orphan identifiers that nothing can look up.
    """
    validate_task(task)
    if task != "branch1":
        return RetrainResponse(
            ok=False,
            task=task,
            job_id="",
            status="not_ready",
            detail="Only Branch 1 supports real retraining so far.",
        )
    outcome = train_and_seal()
    return RetrainResponse(
        ok=outcome.status != "failed",
        task=task,
        job_id=outcome.run_id,
        status=outcome.status,
        detail=outcome.detail or f"model={outcome.model_version} data={outcome.data_version}",
    )


@router.get("/logs/{task}", response_model=LogsResponse)
def logs(task: str) -> LogsResponse:
    """Return real run and promotion-decision lines for a task."""
    validate_task(task)
    cfg = load_config()
    artifacts = _artifacts(cfg)
    lines: list[str] = []

    runs_path = artifacts / RUNS_LOG
    if runs_path.exists():
        with runs_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    run = json.loads(line)
                except ValueError:  # pragma: no cover
                    continue
                lines.append(
                    f"{run.get('created_at', '?')} RUN   {run.get('run_id')} "
                    f"model={run.get('model_version')} data={run.get('data_version')} "
                    f"f1_macro={run.get('metrics', {}).get('f1_macro')}"
                )

    for decision in read_decisions(artifacts / "decisions.jsonl"):
        lines.append(
            f"{decision.get('ts', '?')} GATE  {decision.get('verdict', '').upper():14s} "
            f"{decision.get('candidate')} vs {decision.get('champion')} "
            f"({decision.get('comparison')}) — {decision.get('reason', '')[:120]}"
        )

    if not lines:
        lines = ["No runs or promotion decisions recorded yet."]
    return LogsResponse(task=task, lines=sorted(lines))
