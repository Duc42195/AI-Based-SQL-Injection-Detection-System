"""Metrics page — real evaluation results for the trained models."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import api_client, ui

st.set_page_config(page_title="SQLi Detection — Metrics", page_icon="📈", layout="wide")

# Keys worth surfacing as headline numbers when present in a report.
_HEADLINE_KEYS = ("f1_macro", "accuracy", "roc_auc", "auc", "fpr", "train_rows")


def render_task(task: str) -> None:
    """Render the evaluation report for one task."""
    try:
        report = api_client.metrics(task)
    except api_client.ApiError as exc:
        ui.show_api_error(exc)
        return

    if report["status"] != "ready":
        st.info(report.get("detail") or "No evaluation report available yet.")
        return

    st.caption(f"Source: `{report['source']}`")
    metrics = report["metrics"] or {}

    headline = {k: metrics[k] for k in _HEADLINE_KEYS if isinstance(metrics.get(k), (int, float))}
    if headline:
        for col, (key, value) in zip(st.columns(len(headline)), headline.items()):
            col.metric(key, f"{value:,.4f}" if isinstance(value, float) else f"{value:,}")

    per_class = metrics.get("per_class") or metrics.get("classification_report")
    if isinstance(per_class, dict):
        st.markdown("**Per-class metrics**")
        st.dataframe(pd.DataFrame(per_class).T, width="stretch")

    with st.expander("Raw report JSON"):
        st.json(metrics)


ui.page_header("📈 Metrics", "Evaluation results for the trained models.")

for tab, task in zip(st.tabs([ui.TASK_LABELS[t] for t in ui.TASKS]), ui.TASKS):
    with tab:
        render_task(task)
