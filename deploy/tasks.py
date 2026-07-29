"""Shared helpers for the per-task MLOps routers (monitor/data/train).

A "task" is one of the three branches. Centralised here so validation and label
vocabularies stay consistent across routers.
"""

from __future__ import annotations

from fastapi import HTTPException

from src.preprocessing.multiclass_tagger import LABEL_NAMES

VALID_TASKS = ("branch1", "branch2")


def validate_task(task: str) -> str:
    """Return the task if valid, else raise HTTP 404."""
    if task not in VALID_TASKS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown task '{task}'. Expected one of {VALID_TASKS}.",
        )
    return task


def label_options(task: str) -> list[str]:
    """Return the label vocabulary a given task's annotator should offer."""
    if task == "branch1":
        return [LABEL_NAMES[i] for i in sorted(LABEL_NAMES)]
    if task == "branch2":
        # Branch 2 is benign-only anomaly detection: label is binary.
        return ["normal", "anomaly"]
    raise HTTPException(
        status_code=404,
        detail=f"Unknown task '{task}'. Expected one of {VALID_TASKS}.",
    )
