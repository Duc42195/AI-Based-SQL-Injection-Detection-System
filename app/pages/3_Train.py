"""Train page — split selection, live loss curve/logs, then metrics per branch."""

from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from app import api_client, ui

st.set_page_config(page_title="SQLi Detection — Train", page_icon="🎓", layout="wide")

POLL_SECONDS = 0.7


def _render_result(task: str, job_id: str) -> None:
    """Render the confusion matrix and metrics of a finished job."""
    try:
        result = api_client.train_result(task, job_id)
    except api_client.ApiError as exc:
        ui.show_api_error(exc)
        return
    if result["status"] != "done":
        st.info(result.get("detail") or "Training still running.")
        return

    st.success(f"Training complete — saved as `{result['saved_version']}`")
    metrics = result["metrics"]

    left, right = st.columns(2)
    left.metric("F1 (macro)", f"{metrics['f1_macro']:.4f}")
    right.metric("Accuracy", f"{metrics['accuracy']:.4f}")

    st.markdown("**Confusion matrix**")
    labels = result["labels"]
    matrix = pd.DataFrame(result["confusion_matrix"], index=labels, columns=labels)
    st.dataframe(
        matrix.style.background_gradient(cmap="Blues", axis=None),
        width="stretch",
    )
    st.caption("Rows = true label, columns = predicted label.")

    st.markdown("**Per-class metrics**")
    st.dataframe(pd.DataFrame(metrics["per_class"]).T, width="stretch")


def _run_job(task: str, job_id: str) -> None:
    """Poll a running job, streaming the loss curve and logs until it finishes."""
    chart_col, log_col = st.columns(2)
    chart_col.markdown("**Loss curve**")
    chart_slot = chart_col.empty()
    log_col.markdown("**Logs**")
    log_slot = log_col.empty()
    progress = st.progress(0.0)

    while True:
        try:
            status = api_client.train_status(task, job_id)
        except api_client.ApiError as exc:
            ui.show_api_error(exc)
            return

        if status["loss_curve"]:
            curve = pd.DataFrame(status["loss_curve"]).set_index("epoch")
            chart_slot.line_chart(curve)
        log_slot.code("\n".join(status["logs"]) or "starting...")
        progress.progress(status["epoch"] / max(status["total_epochs"], 1))

        if status["status"] != "running":
            break
        time.sleep(POLL_SECONDS)

    st.divider()
    _render_result(task, job_id)


def render_task(task: str) -> None:
    """Render the split controls and training run for one task."""
    col_train, col_valid, col_test = st.columns(3)
    train_pct = col_train.number_input(
        "Train %", min_value=1, max_value=98, value=70, key=f"train_{task}"
    )
    valid_pct = col_valid.number_input(
        "Valid %", min_value=1, max_value=98, value=15, key=f"valid_{task}"
    )
    test_pct = col_test.number_input(
        "Test %", min_value=1, max_value=98, value=15, key=f"test_{task}"
    )

    total = train_pct + valid_pct + test_pct
    if total != 100:
        st.warning(f"Split must sum to 100 (currently {total}).")

    if st.button(
        "▶ Start training", type="primary", key=f"start_{task}", disabled=total != 100
    ):
        try:
            job = api_client.train_start(task, train_pct, valid_pct, test_pct)
        except api_client.ApiError as exc:
            ui.show_api_error(exc)
            return
        st.caption(f"Job `{job['job_id']}` · {job['total_epochs']} epochs")
        _run_job(task, job["job_id"])


ui.page_header("🎓 Train", "Launch training runs and inspect the resulting metrics.")
st.warning(
    "Training is **simulated** — it produces a realistic loss curve and metrics "
    "so the workflow can be demonstrated, but does not retrain the real models. "
    "Real training runs live in `train/train_branch*.py`.",
    icon="⚠️",
)

for tab, task in zip(st.tabs([ui.TASK_LABELS[t] for t in ui.TASKS]), ui.TASKS):
    with tab:
        render_task(task)
