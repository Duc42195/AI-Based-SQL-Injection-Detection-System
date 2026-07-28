"""Shared Streamlit rendering helpers used across pages."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from app import api_client, cache, state

TASKS = ("branch1", "branch2", "branch3")
TASK_LABELS = {
    "branch1": "Branch 1 — Supervised",
    "branch2": "Branch 2 — Anomaly",
    "branch3": "Branch 3 — Session",
}

# Decision action → (emoji, Streamlit alert function).
_ACTION_STYLE = {
    "BLOCK": ("🔴", st.error),
    "OVERKILL": ("🟡", st.warning),
    "ALLOW": ("🟢", st.success),
    "UNKNOWN": ("⚪", st.info),
}


def page_header(title: str, subtitle: str) -> None:
    """Render a page title + caption and the sidebar backend status."""
    st.title(title)
    st.caption(subtitle)
    sidebar_status()


def sidebar_status() -> None:
    """Show backend reachability, per-branch readiness and a refresh control."""
    with st.sidebar:
        st.markdown("### Backend")
        st.caption(api_client.base_url())
        try:
            branches = cache.health()["branches"]
        except api_client.ApiError as exc:
            st.error("API unreachable")
            st.caption(str(exc).split("\n")[0])
            if st.button("Retry", key=state.widget_key("sidebar", "retry")):
                cache.invalidate_all()
                st.rerun()
            return
        for task, status in branches.items():
            icon = "🟢" if status == "ready" else "⚪"
            st.write(f"{icon} {task}: `{status}`")
        if st.button("↻ Refresh data", key=state.widget_key("sidebar", "refresh")):
            cache.invalidate_all()
            st.rerun()


def render_feedback(*scope: str) -> None:
    """Render and consume a pending feedback message for a scope, if any."""
    feedback = state.pop_feedback(*scope)
    if feedback is None:
        return
    {"success": st.success, "info": st.info, "warning": st.warning, "error": st.error}[
        feedback.kind
    ](feedback.message)


def render_decision(decision: dict[str, Any] | None) -> None:
    """Render the fused verdict (BLOCK / OVERKILL / ALLOW / UNKNOWN)."""
    if not decision:
        return
    action = decision.get("action", "UNKNOWN")
    icon, alert = _ACTION_STYLE.get(action, _ACTION_STYLE["UNKNOWN"])
    alert(f"{icon} **{action}** — {decision.get('reason', '')}")


def render_branch1(result: dict[str, Any] | None) -> None:
    """Render Branch-1 output, or a placeholder when it isn't ready."""
    st.markdown("**Branch 1 — Supervised multiclass**")
    if not result or result.get("status") != "ready":
        st.info(_not_ready_text(result, "Branch 1"))
        return

    left, right = st.columns(2)
    left.metric("Class", result["label_name"])
    left.metric("Is SQLi", "YES" if result["is_sqli"] else "NO")
    right.metric("Attack probability", f"{result['attack_probability']:.1%}")
    right.caption(
        f"threshold = {result['threshold']:.2f} · "
        f"top-class confidence = {result['confidence']:.1%}"
    )
    probs = result.get("probabilities") or {}
    if probs:
        st.bar_chart(pd.DataFrame({"probability": probs}))


def render_branch2(result: dict[str, Any] | None) -> None:
    """Render Branch-2 output, or a placeholder when it isn't ready."""
    st.markdown("**Branch 2 — Anomaly detection**")
    if not result or result.get("status") != "ready":
        st.info(_not_ready_text(result, "Branch 2"))
        return
    left, right = st.columns(2)
    left.metric("Anomalous", "YES" if result["is_anomaly"] else "NO")
    right.metric("Anomaly score", f"{result['anomaly_score']:+.4f}")
    st.caption(
        "Higher = more anomalous. Branch 2 sees only structural shape "
        "(length, entropy, special chars), not attack content — it targets "
        "zero-days, not known payloads."
    )


def render_branch3(result: dict[str, Any] | None) -> None:
    """Render Branch-3 output, or a placeholder when it isn't ready."""
    st.markdown("**Branch 3 — Session-level**")
    if not result or result.get("status") != "ready":
        st.info(_not_ready_text(result, "Branch 3"))
        return
    left, right = st.columns(2)
    left.metric("Session label", result.get("session_label") or "—")
    right.metric("Is attack", "YES" if result.get("is_attack") else "NO")


def _not_ready_text(result: dict[str, Any] | None, name: str) -> str:
    detail = (result or {}).get("detail")
    return detail or f"{name} is not available yet."


def show_api_error(exc: Exception) -> None:
    """Render an API failure with the hint on how to start the backend."""
    st.error(str(exc))
