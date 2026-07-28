"""Train page — split selection, live loss curve/logs, then metrics per branch.

Polling runs inside an ``st.fragment`` so only that fragment re-runs on each
tick. A blocking ``while True: time.sleep(...)`` loop would hold the single
script thread for the whole run, freezing every other page and tab until
training finished.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import api_client, state, ui

st.set_page_config(page_title="SQLi Detection — Train", page_icon="🎓", layout="wide")

POLL_SECONDS = 0.7


def _render_progress(job: state.TrainJob) -> None:
    """Render the loss curve, logs and progress bar for a job."""
    chart_col, log_col = st.columns(2)
    with chart_col:
        st.markdown("**Loss curve**")
        if job.loss_curve:
            st.line_chart(pd.DataFrame(job.loss_curve).set_index("epoch"))
        else:
            st.caption("waiting for the first epoch…")
    with log_col:
        st.markdown("**Logs**")
        st.code("\n".join(job.logs) or "starting…")
    st.progress(job.progress, text=f"epoch {job.epoch}/{job.total_epochs}")


def _render_result(job: state.TrainJob) -> None:
    """Render the confusion matrix and metrics of a finished job."""
    if job.status == "failed":
        st.error("Training failed — see the logs above.")
        return
    if not job.result:
        st.info("No result available for this job.")
        return

    st.success(f"Training complete — saved as `{job.result['saved_version']}`")
    metrics = job.result["metrics"]

    left, right = st.columns(2)
    left.metric("F1 (macro)", f"{metrics['f1_macro']:.4f}")
    right.metric("Accuracy", f"{metrics['accuracy']:.4f}")

    st.markdown("**Confusion matrix**")
    labels = job.result["labels"]
    matrix = pd.DataFrame(job.result["confusion_matrix"], index=labels, columns=labels)
    st.dataframe(
        matrix.style.background_gradient(cmap="Blues", axis=None), width="stretch"
    )
    st.caption("Rows = true label, columns = predicted label.")

    st.markdown("**Per-class metrics**")
    st.dataframe(pd.DataFrame(metrics["per_class"]).T, width="stretch")


def _poll(task: str, job: state.TrainJob) -> state.TrainJob:
    """Fetch the latest status (and result once finished) into the job."""
    try:
        status = api_client.train_status(task, job.job_id)
    except api_client.ApiError as exc:
        job.status = "failed"
        job.logs = [*job.logs, f"polling failed: {exc}"]
        return job

    job.status = status["status"]
    job.epoch = status["epoch"]
    job.loss_curve = status["loss_curve"]
    job.logs = status["logs"]

    if job.finished and job.result is None:
        try:
            job.result = api_client.train_result(task, job.job_id)
        except api_client.ApiError as exc:
            job.status = "failed"
            job.logs = [*job.logs, f"fetching result failed: {exc}"]
    return job


@st.fragment(run_every=POLL_SECONDS)
def _live_job(task: str) -> None:
    """Poll a running job on a timer, re-running only this fragment."""
    job = state.get_train_job(task)
    if job is None or job.finished:
        return
    job = _poll(task, job)
    state.set_train_job(task, job)
    _render_progress(job)
    if job.finished:
        # Leave the auto-rerun loop: a full-app run renders the static result.
        st.rerun(scope="app")


def render_task(task: str) -> None:
    """Render the split controls and training run for one task."""
    job = state.get_train_job(task)
    running = job is not None and not job.finished

    col_train, col_valid, col_test = st.columns(3)
    train_pct = col_train.number_input(
        "Train %", 1, 98, 70, key=state.widget_key("train", task, "train"), disabled=running
    )
    valid_pct = col_valid.number_input(
        "Valid %", 1, 98, 15, key=state.widget_key("train", task, "valid"), disabled=running
    )
    test_pct = col_test.number_input(
        "Test %", 1, 98, 15, key=state.widget_key("train", task, "test"), disabled=running
    )
    total = train_pct + valid_pct + test_pct
    if total != 100:
        st.warning(f"Split must sum to 100 (currently {total}).")

    start_col, reset_col = st.columns([1, 1])
    if start_col.button(
        "▶ Start training",
        type="primary",
        key=state.widget_key("train", task, "start"),
        disabled=running or total != 100,
    ):
        try:
            started = api_client.train_start(task, train_pct, valid_pct, test_pct)
        except api_client.ApiError as exc:
            state.set_feedback("train", task, kind="error", message=str(exc))
        else:
            state.set_train_job(
                task,
                state.TrainJob(
                    job_id=started["job_id"],
                    task=task,
                    total_epochs=started["total_epochs"],
                ),
            )
            st.rerun()

    if job is not None and reset_col.button(
        "Clear", key=state.widget_key("train", task, "clear"), disabled=running
    ):
        state.clear_train_job(task)
        st.rerun()

    ui.render_feedback("train", task)

    if job is None:
        return

    st.caption(f"Job `{job.job_id}` · {job.total_epochs} epochs · status: {job.status}")
    if running:
        _live_job(task)  # fragment renders progress and polls
    else:
        _render_progress(job)
        st.divider()
        _render_result(job)


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
