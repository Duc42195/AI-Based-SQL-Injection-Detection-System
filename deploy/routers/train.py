"""Train page — start a (simulated) training job and poll live loss/logs.

MOCK TRAINER: a job advances one epoch per ``SECONDS_PER_EPOCH`` of wall-clock
time, producing a decaying loss curve and log lines, then a confusion matrix +
metrics. This lets the frontend build the live-training UX now; replace
``_simulate`` with a real trainer (scripts/train_*.py, backgrounded) later — the
status/result shapes are the stable contract.
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from threading import Lock

from fastapi import APIRouter, HTTPException

from deploy.schemas import (
    LossPoint,
    TrainResultResponse,
    TrainStartRequest,
    TrainStartResponse,
    TrainStatusResponse,
)
from deploy.tasks import label_options, validate_task

router = APIRouter(prefix="/train", tags=["train"])

TOTAL_EPOCHS = 5
SECONDS_PER_EPOCH = 1.2  # simulated wall-clock per epoch


@dataclass
class _Job:
    job_id: str
    task: str
    started_at: float
    total_epochs: int = TOTAL_EPOCHS
    labels: list[str] = field(default_factory=list)


_JOBS: dict[str, _Job] = {}
_lock = Lock()


def _completed_epochs(job: _Job) -> int:
    elapsed = time.monotonic() - job.started_at
    return min(job.total_epochs, int(elapsed // SECONDS_PER_EPOCH))


def _loss_curve(job: _Job, epochs: int) -> list[LossPoint]:
    """Deterministic decaying train/valid loss for the completed epochs."""
    points: list[LossPoint] = []
    for e in range(1, epochs + 1):
        train_loss = round(0.9 * math.exp(-0.5 * e) + 0.05, 4)
        valid_loss = round(train_loss + 0.05 + 0.01 * (e % 2), 4)
        points.append(LossPoint(epoch=e, train_loss=train_loss, valid_loss=valid_loss))
    return points


def _logs(job: _Job, epochs: int) -> list[str]:
    lines = [f"start training {job.task} (epochs={job.total_epochs})"]
    for point in _loss_curve(job, epochs):
        lines.append(
            f"epoch {point.epoch}/{job.total_epochs} "
            f"train_loss={point.train_loss} valid_loss={point.valid_loss}"
        )
    if epochs >= job.total_epochs:
        lines.append("training complete — saved new model version")
    return lines


@router.post("/{task}/start", response_model=TrainStartResponse)
def start(task: str, request: TrainStartRequest) -> TrainStartResponse:
    """Start a simulated training job for a task with the given split."""
    validate_task(task)
    if request.train + request.valid + request.test != 100:
        raise HTTPException(
            status_code=422, detail="train + valid + test must sum to 100."
        )
    token = hashlib.sha256(f"{task}:{time.time()}".encode()).hexdigest()[:6]
    job_id = f"job_{task}_{token}"
    with _lock:
        _JOBS[job_id] = _Job(
            job_id=job_id,
            task=task,
            started_at=time.monotonic(),
            labels=label_options(task),
        )
    return TrainStartResponse(job_id=job_id, task=task, total_epochs=TOTAL_EPOCHS)


def _get_job(task: str, job_id: str) -> _Job:
    job = _JOBS.get(job_id)
    if job is None or job.task != task:
        raise HTTPException(status_code=404, detail=f"Unknown job '{job_id}'.")
    return job


@router.get("/{task}/status/{job_id}", response_model=TrainStatusResponse)
def status(task: str, job_id: str) -> TrainStatusResponse:
    """Return live epoch/loss/logs; poll while status == 'running'."""
    validate_task(task)
    job = _get_job(task, job_id)
    epochs = _completed_epochs(job)
    done = epochs >= job.total_epochs
    return TrainStatusResponse(
        job_id=job.job_id,
        task=job.task,
        status="done" if done else "running",
        epoch=epochs,
        total_epochs=job.total_epochs,
        loss_curve=_loss_curve(job, epochs),
        logs=_logs(job, epochs),
    )


@router.get("/{task}/result/{job_id}", response_model=TrainResultResponse)
def result(task: str, job_id: str) -> TrainResultResponse:
    """Return the confusion matrix + metrics once the job is done."""
    validate_task(task)
    job = _get_job(task, job_id)
    if _completed_epochs(job) < job.total_epochs:
        return TrainResultResponse(
            job_id=job.job_id,
            task=job.task,
            status="running",
            detail="Training still in progress.",
        )

    labels = job.labels
    cm = _mock_confusion_matrix(job, labels)
    metrics = _metrics_from_confusion(cm, labels)
    version = f"{job.task}_v2"
    return TrainResultResponse(
        job_id=job.job_id,
        task=job.task,
        status="done",
        labels=labels,
        confusion_matrix=cm,
        metrics=metrics,
        saved_version=version,
    )


def _mock_confusion_matrix(job: _Job, labels: list[str]) -> list[list[int]]:
    """A strongly-diagonal confusion matrix (good model) sized to the labels."""
    n = len(labels)
    matrix: list[list[int]] = []
    for i in range(n):
        row = []
        for j in range(n):
            if i == j:
                row.append(900 + (hash((job.job_id, i)) % 100))
            else:
                row.append((hash((job.job_id, i, j)) % 6))
        matrix.append(row)
    return matrix


def _metrics_from_confusion(cm: list[list[int]], labels: list[str]) -> dict:
    """Compute precision/recall/f1 per class + macro-F1 + accuracy from a CM."""
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
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall)
            else 0.0
        )
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
