"""Single source of truth for every piece of Streamlit session state.

Streamlit re-runs the whole script on each interaction, so anything that must
survive a re-run — a detection result, an in-flight training job, a feedback
message — has to live in ``st.session_state``. Spreading raw string keys across
pages makes that impossible to audit, so **every** key in the app is declared
here with a typed accessor and an explicit default.

Two kinds of state exist in this app:

1. **Widget state** — owned by Streamlit itself via a widget's ``key=``. Declare
   the key with :func:`widget_key` so it is namespaced and greppable, but read
   the value from the widget's return, not from here.
2. **Application state** — everything below: results and jobs that outlive the
   run that produced them. Always go through the accessors in this module.

Server-side data that is merely *fetched* (drift series, metric reports) is not
state — it is cached in :mod:`app.cache` instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import streamlit as st

# All keys share this prefix so app state is distinguishable from widget keys
# belonging to third-party components in the same session_state dict.
_PREFIX = "sqli"

Task = str  # "branch1" | "branch2"


# --------------------------------------------------------------------------- #
# Stored value types
# --------------------------------------------------------------------------- #
@dataclass
class DemoRun:
    """One completed run of the Test page (with or without the detector).

    Persisted so the verdict and charts stay on screen after an unrelated
    widget interaction triggers a re-run.
    """

    protected: bool
    inputs: list[str]
    response: dict[str, Any]


@dataclass
class TrainJob:
    """A training job and the latest status snapshot polled for it."""

    job_id: str
    task: Task
    total_epochs: int
    status: Literal["running", "done", "failed"] = "running"
    epoch: int = 0
    loss_curve: list[dict[str, Any]] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None

    @property
    def finished(self) -> bool:
        """True once the job is no longer running."""
        return self.status != "running"

    @property
    def progress(self) -> float:
        """Completion ratio in ``[0, 1]`` for a progress bar."""
        return min(self.epoch / max(self.total_epochs, 1), 1.0)


@dataclass
class Feedback:
    """A transient message shown after an action (annotation, retrain)."""

    kind: Literal["success", "info", "warning", "error"]
    message: str


# --------------------------------------------------------------------------- #
# Key construction
# --------------------------------------------------------------------------- #
def _key(*parts: str) -> str:
    """Build a namespaced session-state key from its parts."""
    return ".".join((_PREFIX, *parts))


def widget_key(*parts: str) -> str:
    """Return a namespaced key for a Streamlit widget's ``key=`` argument.

    Widget values are owned by Streamlit; this only guarantees the key is
    unique across pages and easy to grep for.
    """
    return _key("w", *parts)


def _get(key: str, default: Any = None) -> Any:
    return st.session_state.get(key, default)


def _set(key: str, value: Any) -> None:
    st.session_state[key] = value


def _clear(key: str) -> None:
    st.session_state.pop(key, None)


# --------------------------------------------------------------------------- #
# Test page — last run per mode ("single" or "session")
# --------------------------------------------------------------------------- #
def get_demo_run(mode: str) -> DemoRun | None:
    """Return the last Test-page run for ``mode``, if any."""
    return _get(_key("test", mode, "run"))


def set_demo_run(mode: str, run: DemoRun) -> None:
    """Persist the latest Test-page run for ``mode``."""
    _set(_key("test", mode, "run"), run)


def clear_demo_run(mode: str) -> None:
    """Drop the stored Test-page run for ``mode``."""
    _clear(_key("test", mode, "run"))


# --------------------------------------------------------------------------- #
# Train page — one job per task
# --------------------------------------------------------------------------- #
def get_train_job(task: Task) -> TrainJob | None:
    """Return the current/last training job for a task, if any."""
    return _get(_key("train", task, "job"))


def set_train_job(task: Task, job: TrainJob) -> None:
    """Store (or replace) the training job for a task."""
    _set(_key("train", task, "job"), job)


def clear_train_job(task: Task) -> None:
    """Forget the training job for a task."""
    _clear(_key("train", task, "job"))


# --------------------------------------------------------------------------- #
# Feedback messages — keyed by an arbitrary scope (page/task/item)
# --------------------------------------------------------------------------- #
def get_feedback(*scope: str) -> Feedback | None:
    """Return the pending feedback message for a scope, if any."""
    return _get(_key("feedback", *scope))


def set_feedback(*scope: str, kind: str, message: str) -> None:
    """Store a feedback message to render on the next run."""
    _set(_key("feedback", *scope), Feedback(kind=kind, message=message))  # type: ignore[arg-type]


def pop_feedback(*scope: str) -> Feedback | None:
    """Return and clear the feedback message for a scope (show-once)."""
    key = _key("feedback", *scope)
    value = _get(key)
    _clear(key)
    return value


# --------------------------------------------------------------------------- #
# Data page — pagination offset per task
# --------------------------------------------------------------------------- #
def get_offset(task: Task) -> int:
    """Return the annotated-list pagination offset for a task."""
    return int(_get(_key("data", task, "offset"), 0))


def set_offset(task: Task, offset: int) -> None:
    """Set the annotated-list pagination offset for a task."""
    _set(_key("data", task, "offset"), max(0, offset))


# --------------------------------------------------------------------------- #
# Introspection (used by tests and the debug expander)
# --------------------------------------------------------------------------- #
def app_state() -> dict[str, Any]:
    """Return every app-owned session-state entry (excluding widget keys)."""
    widget_prefix = _key("w") + "."
    return {
        key: value
        for key, value in st.session_state.items()
        if isinstance(key, str)
        and key.startswith(_PREFIX + ".")
        and not key.startswith(widget_prefix)
    }


def reset() -> None:
    """Clear all app-owned state (widget state is left untouched)."""
    for key in list(app_state()):
        _clear(key)
