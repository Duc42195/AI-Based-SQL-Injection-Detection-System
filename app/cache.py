"""Cached read-through wrappers around the API client.

``st.tabs`` renders *every* tab on each run (the browser only hides the inactive
ones), so an uncached read in a three-tab page fires three requests per
interaction — for tabs nobody opened. Every read-only endpoint is wrapped here
with a TTL suited to how fast that data actually changes.

Only **reads** belong here. Writes (annotate, retrain, train start) go straight
through :mod:`app.api_client` and then invalidate whatever they affected.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from app import api_client

# TTLs in seconds, tuned to how volatile each resource is.
_TTL_HEALTH = 10  # readiness can flip when the backend restarts
_TTL_DRIFT = 60  # a drift series gains a point per day
_TTL_LOGS = 30
_TTL_METRICS = 300  # evaluation reports only change on retrain
_TTL_DEMO_DB = 600  # seeded fixture, effectively static
_TTL_ANNOTATION = 15  # invalidated explicitly after each label is saved


@st.cache_data(ttl=_TTL_HEALTH, show_spinner=False)
def health() -> dict[str, Any]:
    """Backend health + per-branch readiness."""
    return api_client.health()


@st.cache_data(ttl=_TTL_DEMO_DB, show_spinner=False)
def demo_database() -> dict[str, Any]:
    """The seeded demo table."""
    return api_client.demo_database()


@st.cache_data(ttl=_TTL_DRIFT, show_spinner=False)
def drift(task: str) -> dict[str, Any]:
    """Drift time-series + alert flag for a task."""
    return api_client.drift(task)


@st.cache_data(ttl=_TTL_LOGS, show_spinner=False)
def logs(task: str) -> dict[str, Any]:
    """Recent log lines for a task."""
    return api_client.logs(task)


@st.cache_data(ttl=_TTL_METRICS, show_spinner=False)
def metrics(task: str) -> dict[str, Any]:
    """Evaluation report for a task."""
    return api_client.metrics(task)


@st.cache_data(ttl=_TTL_ANNOTATION, show_spinner=False)
def unannotated(task: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """Samples awaiting a label."""
    return api_client.unannotated(task, limit=limit, offset=offset)


@st.cache_data(ttl=_TTL_ANNOTATION, show_spinner=False)
def annotated(task: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """Samples that already have a label."""
    return api_client.annotated(task, limit=limit, offset=offset)


def invalidate_annotations() -> None:
    """Drop cached annotation pools after a label is saved."""
    unannotated.clear()
    annotated.clear()


def invalidate_all() -> None:
    """Drop every cached read (used by the sidebar refresh control)."""
    for cached in (
        health,
        demo_database,
        drift,
        logs,
        metrics,
        unannotated,
        annotated,
    ):
        cached.clear()
