"""Train page — real Branch-1 training, run identity, gate and promotion.

Implements section 1.5c and 7 of ``report/plan/mlops_contract.md``.

Pressing *Train* seals the next data version from whatever has been confirmed,
computes the ``run_id`` and looks it up. An identical run that already
completed is reported rather than repeated. Training runs in a background
thread so the request returns immediately and the page can poll.

Branches 2 and 3 keep the simulator until their training paths are wired.
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock, Thread
from typing import Any

from fastapi import APIRouter, HTTPException

from deploy.registry import get_registry
from deploy.schemas import (
    LossPoint,
    TrainResultResponse,
    TrainStartRequest,
    TrainStartResponse,
    TrainStatusResponse,
)
from deploy.tasks import label_options, validate_task
from src.continual_learning.gate import (
    ModelEvaluation,
    append_decision,
    evaluate_gate,
)
from src.continual_learning.trainer import (
    evaluate_on_golden,
    promote,
    train_and_seal,
)
from src.utils import get_logger, load_config

logger = get_logger(__name__)

router = APIRouter(prefix="/train", tags=["train"])

TOTAL_EPOCHS = 5
SECONDS_PER_EPOCH = 1.2  # simulator only (branches 2 and 3)


@dataclass
class _Job:
    """A training job: real for Branch 1, simulated for the others."""

    job_id: str
    task: str
    started_at: float
    total_epochs: int = TOTAL_EPOCHS
    labels: list[str] = field(default_factory=list)
    real: bool = False
    status: str = "running"
    logs: list[str] = field(default_factory=list)
    outcome: dict[str, Any] | None = None
    decision: dict[str, Any] | None = None
    error: str | None = None


_JOBS: dict[str, _Job] = {}
_lock = Lock()


# --------------------------------------------------------------------------- #
# Real Branch-1 training
# --------------------------------------------------------------------------- #
def _champion_data_version(model_version: str, cfg) -> str:
    """Return the data version a deployed model was trained on.

    Falls back to the configured baseline for models predating versioning.
    """
    import json

    meta_path = (
        Path(cfg.get_path("paths.models_dir", "models")) / model_version / "metadata.json"
    )
    if meta_path.exists():
        try:
            recorded = json.loads(meta_path.read_text(encoding="utf-8")).get("data_version")
            if recorded:
                return str(recorded)
        except ValueError:  # pragma: no cover
            pass
    return str(cfg.get_path("mlops.baseline.data_version", "1.0"))


def _run_real_training(job: _Job) -> None:
    """Seal a version, train, run the gate, and promote if it passes."""
    try:
        job.logs.append("assembling dataset from confirmed labels…")
        outcome = train_and_seal()
        job.outcome = outcome.to_dict()

        if outcome.status == "exists":
            job.logs.append(f"run {outcome.run_id} already completed — nothing retrained")
            job.status = "done"
            return

        job.logs.append(
            f"trained {outcome.model_version} on data {outcome.data_version} "
            f"(bump={outcome.bump}) in {outcome.duration_s:.1f}s"
        )

        cfg = load_config()
        candidate = evaluate_on_golden(
            outcome.model_version or "", outcome.data_version or "1.0", cfg
        )
        champion_version = str(cfg.get_path("branch1_supervised.active_version", ""))
        champion: ModelEvaluation | None = None
        if champion_version and champion_version != outcome.model_version:
            # Take the champion's data version from its own metadata. Reading it
            # from config would attribute the *baseline* version to whatever is
            # deployed, which can invent a spurious major-version gap and make
            # the gate refuse a comparison it should have made.
            champion = evaluate_on_golden(
                champion_version, _champion_data_version(champion_version, cfg), cfg
            )

        if candidate is None:
            job.status = "failed"
            job.error = "Could not evaluate the candidate on the golden set."
            return

        job.logs.append(
            f"golden: F1-macro={candidate.f1_macro:.4f} FPR={candidate.fpr:.4f}"
        )
        decision = evaluate_gate(
            candidate,
            champion,
            max_per_class_recall_drop=float(
                cfg.get_path("mlops.gate.max_per_class_recall_drop", 0.02)
            ),
            min_new_class_recall=float(
                cfg.get_path("mlops.gate.min_new_class_recall", 0.80)
            ),
            golden_version=str(outcome.data_version or "").split(".")[0],
        )
        artifacts = Path(
            cfg.get_path("mlops.artifacts_dir", "report/metrics/continual_learning")
        )
        append_decision(decision, artifacts / "decisions.jsonl")
        job.decision = decision.to_dict()
        job.logs.append(f"gate: {decision.verdict.upper()} — {decision.reason}")

        if decision.promoted and outcome.model_version:
            promote(outcome.model_version, cfg)
            get_registry().reload()
            job.logs.append(f"promoted {outcome.model_version}; active version updated")
        else:
            job.logs.append("not promoted; the active model is unchanged")

        job.status = "done"
    except Exception as exc:  # pragma: no cover - surfaced to the UI
        logger.exception("Training job %s failed", job.job_id)
        job.status = "failed"
        job.error = str(exc)
        job.logs.append(f"FAILED: {exc}")


# --------------------------------------------------------------------------- #
# Simulator (branches 2 and 3)
# --------------------------------------------------------------------------- #
def _completed_epochs(job: _Job) -> int:
    elapsed = time.monotonic() - job.started_at
    return min(job.total_epochs, int(elapsed // SECONDS_PER_EPOCH))


def _loss_curve(job: _Job, epochs: int) -> list[LossPoint]:
    points: list[LossPoint] = []
    for e in range(1, epochs + 1):
        train_loss = round(0.9 * math.exp(-0.5 * e) + 0.05, 4)
        points.append(
            LossPoint(
                epoch=e,
                train_loss=train_loss,
                valid_loss=round(train_loss + 0.05 + 0.01 * (e % 2), 4),
            )
        )
    return points


def _simulated_logs(job: _Job, epochs: int) -> list[str]:
    lines = [f"start training {job.task} (epochs={job.total_epochs}) [SIMULATED]"]
    for point in _loss_curve(job, epochs):
        lines.append(
            f"epoch {point.epoch}/{job.total_epochs} "
            f"train_loss={point.train_loss} valid_loss={point.valid_loss}"
        )
    if epochs >= job.total_epochs:
        lines.append("training complete [SIMULATED — no model was written]")
    return lines


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.post("/{task}/start", response_model=TrainStartResponse)
def start(task: str, request: TrainStartRequest) -> TrainStartResponse:
    """Start training. Branch 1 trains for real; the others simulate."""
    validate_task(task)
    if request.train + request.valid + request.test != 100:
        raise HTTPException(
            status_code=422, detail="train + valid + test must sum to 100."
        )

    real = task == "branch1"
    token = hashlib.sha256(f"{task}:{time.time()}".encode()).hexdigest()[:6]
    job = _Job(
        job_id=f"job_{task}_{token}",
        task=task,
        started_at=time.monotonic(),
        labels=label_options(task),
        real=real,
    )
    with _lock:
        _JOBS[job.job_id] = job

    if real:
        # Background thread: training takes tens of seconds and the page polls.
        Thread(target=_run_real_training, args=(job,), daemon=True).start()

    return TrainStartResponse(
        job_id=job.job_id,
        task=task,
        total_epochs=TOTAL_EPOCHS,
        real=real,
    )


def _get_job(task: str, job_id: str) -> _Job:
    job = _JOBS.get(job_id)
    if job is None or job.task != task:
        raise HTTPException(status_code=404, detail=f"Unknown job '{job_id}'.")
    return job


@router.get("/{task}/status/{job_id}", response_model=TrainStatusResponse)
def status(task: str, job_id: str) -> TrainStatusResponse:
    """Return live status; poll while ``status == "running"``."""
    validate_task(task)
    job = _get_job(task, job_id)

    if job.real:
        return TrainStatusResponse(
            job_id=job.job_id,
            task=job.task,
            status=job.status,
            epoch=job.total_epochs if job.status != "running" else 0,
            total_epochs=job.total_epochs,
            loss_curve=[],  # a linear model has no epoch-wise curve to report
            logs=list(job.logs) or ["starting…"],
            real=True,
        )

    epochs = _completed_epochs(job)
    done = epochs >= job.total_epochs
    return TrainStatusResponse(
        job_id=job.job_id,
        task=job.task,
        status="done" if done else "running",
        epoch=epochs,
        total_epochs=job.total_epochs,
        loss_curve=_loss_curve(job, epochs),
        logs=_simulated_logs(job, epochs),
        real=False,
    )


@router.get("/{task}/result/{job_id}", response_model=TrainResultResponse)
def result(task: str, job_id: str) -> TrainResultResponse:
    """Return the finished job's metrics, gate decision and promotion outcome."""
    validate_task(task)
    job = _get_job(task, job_id)

    if job.real:
        if job.status == "running":
            return TrainResultResponse(
                job_id=job.job_id, task=job.task, status="running",
                detail="Training still in progress.",
            )
        if job.status == "failed":
            return TrainResultResponse(
                job_id=job.job_id, task=job.task, status="failed",
                detail=job.error or "Training failed.",
            )
        outcome = job.outcome or {}
        return TrainResultResponse(
            job_id=job.job_id,
            task=job.task,
            status="done",
            labels=job.labels,
            metrics=outcome.get("metrics", {}),
            saved_version=outcome.get("model_version"),
            data_version=outcome.get("data_version"),
            bump=outcome.get("bump"),
            run_id=outcome.get("run_id"),
            run_status=outcome.get("status"),
            decision=job.decision,
            detail=outcome.get("detail") or None,
            real=True,
        )

    if _completed_epochs(job) < job.total_epochs:
        return TrainResultResponse(
            job_id=job.job_id, task=job.task, status="running",
            detail="Training still in progress.",
        )
    labels = job.labels
    matrix = _mock_confusion_matrix(job, labels)
    return TrainResultResponse(
        job_id=job.job_id,
        task=job.task,
        status="done",
        labels=labels,
        confusion_matrix=matrix,
        metrics=_metrics_from_confusion(matrix, labels),
        saved_version=None,
        detail="Simulated run — no model was written.",
        real=False,
    )


def _mock_confusion_matrix(job: _Job, labels: list[str]) -> list[list[int]]:
    """A strongly-diagonal matrix sized to the labels (simulator only)."""
    n = len(labels)
    return [
        [
            900 + (hash((job.job_id, i)) % 100) if i == j else (hash((job.job_id, i, j)) % 6)
            for j in range(n)
        ]
        for i in range(n)
    ]


def _metrics_from_confusion(cm: list[list[int]], labels: list[str]) -> dict:
    """Precision/recall/F1 per class plus macro-F1 and accuracy."""
    n = len(labels)
    per_class: dict[str, dict[str, float]] = {}
    total = sum(sum(row) for row in cm)
    correct = sum(cm[i][i] for i in range(n))
    f1s = []
    for i in range(n):
        tp = cm[i][i]
        fp = sum(cm[r][i] for r in range(n)) - tp
        fn = sum(cm[i]) - tp
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        f1s.append(f1)
        per_class[labels[i]] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
    return {
        "accuracy": round(correct / total, 4) if total else 0.0,
        "f1_macro": round(sum(f1s) / n, 4) if n else 0.0,
        "per_class": per_class,
    }
