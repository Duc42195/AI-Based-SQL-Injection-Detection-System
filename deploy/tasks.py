"""Shared helpers for the per-task MLOps routers (monitor/data/train).

A "task" is one of the three branches. Centralised here so validation and label
vocabularies stay consistent across routers.
"""

from __future__ import annotations

from fastapi import HTTPException

from src.preprocessing.multiclass_tagger import LABEL_NAMES
from src.utils import load_config

VALID_TASKS = ("nhanh1", "nhanh2", "nhanh3")


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
    if task == "nhanh1":
        return [LABEL_NAMES[i] for i in sorted(LABEL_NAMES)]
    if task == "nhanh2":
        # Branch 2 is benign-only anomaly detection: label is binary.
        return ["normal", "anomaly"]
    # Branch 3 session labels come from config (fallback to a sensible default).
    cfg = load_config()
    session_classes = cfg.get_path("branch3_session.session_classes") or {
        "benign": 0,
        "boolean_blind": 1,
        "time_blind": 2,
        "query_splitting": 3,
    }
    return list(session_classes.keys())
