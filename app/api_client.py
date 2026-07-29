"""HTTP client for the FastAPI backend.

The Streamlit app talks to the API over HTTP only (never imports the models
directly), so the UI can run on a different host/port from the service. The base
URL comes from ``configs/config.yaml`` (``api.host``/``api.port``) and can be
overridden with the ``SQLIDS_API_URL`` environment variable.
"""

from __future__ import annotations

import os
from typing import Any

import requests

from src.utils import load_config

DEFAULT_TIMEOUT = 30


class ApiError(RuntimeError):
    """Raised when the backend is unreachable or returns an error status."""


def base_url() -> str:
    """Return the backend base URL (env override wins over config)."""
    override = os.environ.get("SQLIDS_API_URL")
    if override:
        return override.rstrip("/")
    cfg = load_config()
    host = str(cfg.get_path("api.host", "127.0.0.1"))
    # 0.0.0.0 means "listen on all interfaces" — not a valid address to call.
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    port = int(cfg.get_path("api.port", 8000))
    return f"http://{host}:{port}"


def api_prefix() -> str:
    """Return the versioned API prefix, e.g. ``/api/v1``."""
    cfg = load_config()
    return f"/api/{cfg.get_path('api.api_version', 'v1')}"


def _request(method: str, path: str, **kwargs: Any) -> dict:
    """Send a request to the backend and return the decoded JSON body.

    Args:
        method: HTTP method (``"GET"``/``"POST"``).
        path: Path starting with ``/`` (already including any prefix).
        **kwargs: Extra arguments forwarded to ``requests.request``.

    Returns:
        The decoded JSON response body.

    Raises:
        ApiError: If the backend is unreachable or replies with an error status.
    """
    url = f"{base_url()}{path}"
    try:
        resp = requests.request(method, url, timeout=DEFAULT_TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        raise ApiError(
            f"Cannot reach the API at {url}. Is it running? "
            f"Start it with: uv run uvicorn deploy.main:app --reload\n({exc})"
        ) from exc
    if resp.status_code >= 400:
        raise ApiError(f"{method} {path} → HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def get(path: str, **params: Any) -> dict:
    """GET a versioned API path (prefix added automatically)."""
    return _request("GET", f"{api_prefix()}{path}", params=params or None)


def post(path: str, payload: dict | None = None) -> dict:
    """POST JSON to a versioned API path (prefix added automatically)."""
    return _request("POST", f"{api_prefix()}{path}", json=payload)


def health() -> dict:
    """Return backend health + per-branch readiness (unversioned path)."""
    return _request("GET", "/health")


# --------------------------------------------------------------------------- #
# Convenience wrappers (one per UI action)
# --------------------------------------------------------------------------- #
def detect(query: str) -> dict:
    """Run the full detection pipeline on one query."""
    return post("/detect", {"query": query})


def demo_database() -> dict:
    """Return the seeded demo table."""
    return get("/demo/database")


def demo_execute(inputs: list[str], protected: bool) -> dict:
    """Run inputs against the demo DB, with or without the detector."""
    return post("/demo/execute", {"inputs": inputs, "protected": protected})


def branch3_session(queries: list[str]) -> dict:
    """Classify a whole session (Branch 3)."""
    return post("/branch3/session", {"queries": queries})


def metrics(task: str) -> dict:
    """Return evaluation metrics for a task."""
    return get(f"/metrics/{task}")


def drift(task: str) -> dict:
    """Return the drift time-series + alert flag for a task."""
    return get(f"/monitor/drift/{task}")


def retrain(task: str) -> dict:
    """Trigger a retrain for a task."""
    return post(f"/monitor/retrain/{task}")


def logs(task: str) -> dict:
    """Return recent log lines for a task."""
    return get(f"/monitor/logs/{task}")


def unannotated(task: str, limit: int = 20, offset: int = 0) -> dict:
    """List samples awaiting a label."""
    return get(f"/data/{task}/unannotated", limit=limit, offset=offset)


def annotated(task: str, limit: int = 20, offset: int = 0) -> dict:
    """List already-labelled samples."""
    return get(f"/data/{task}/annotated", limit=limit, offset=offset)


def annotate(task: str, item_id: str, action: str, label: str | None = None) -> dict:
    """Review one queued item: approve, correct (with a label) or reject."""
    return post(
        f"/data/{task}/annotate", {"id": item_id, "action": action, "label": label}
    )


# --------------------------------------------------------------------------- #
# MLOps lifecycle
# --------------------------------------------------------------------------- #
def versions() -> dict:
    """Return the data-version registry with lineage."""
    return get("/mlops/versions")


def runs() -> dict:
    """Return recorded training runs."""
    return get("/mlops/runs")


def decisions() -> dict:
    """Return the promotion decision log."""
    return get("/mlops/decisions")


def replay(limit: int = 20000, max_queue: int = 200) -> dict:
    """Replay a slice of the held-out stream: writes drift, fills the queue."""
    return post("/mlops/replay", {"limit": limit, "max_queue": max_queue})


def reset_demo() -> dict:
    """Restore the protected baseline so the demo can be run again."""
    return post("/mlops/reset")


def train_start(task: str, train: int, valid: int, test: int) -> dict:
    """Start a training job with the given split."""
    return post(f"/train/{task}/start", {"train": train, "valid": valid, "test": test})


def train_status(task: str, job_id: str) -> dict:
    """Poll a training job's live status."""
    return get(f"/train/{task}/status/{job_id}")


def train_result(task: str, job_id: str) -> dict:
    """Fetch a finished training job's metrics + confusion matrix."""
    return get(f"/train/{task}/result/{job_id}")
