"""Train page — seal a data version, train, gate, promote; and reset the demo.

Branch 1 trains for real: the version bump follows from what was confirmed, the
``run_id`` makes a repeat press a no-op, and the gate decides promotion.
Branches 2 and 3 still simulate, and say so.
"""

from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from app import api_client, cache, state, ui

st.set_page_config(page_title="SQLi Detection — Train", page_icon="🎓", layout="wide")

POLL_SECONDS = 1.0

VERDICT_STYLE = {
    "promote": ("✅", st.success),
    "direct_promote": ("✅", st.success),
    "reject": ("🚫", st.error),
}


def _render_decision(decision: dict | None) -> None:
    """Show the gate's verdict and the evidence behind it."""
    if not decision:
        return
    verdict = decision.get("verdict", "")
    icon, alert = VERDICT_STYLE.get(verdict, ("ℹ️", st.info))
    alert(f"{icon} **{verdict.replace('_', ' ').upper()}** — {decision.get('reason', '')}")

    if decision.get("comparison") == "cross_major_refused":
        st.caption(
            "The label space changed, so a champion/challenger comparison would "
            "measure the benchmark rather than the models. The candidate is "
            "promoted directly and the refusal is recorded."
        )

    criteria = decision.get("criteria") or {}
    if criteria and "f1_macro" in criteria:
        rows = [
            {"criterion": "F1-macro", "value": criteria["f1_macro"]["candidate"],
             "bound": criteria["f1_macro"]["floor"], "ok": criteria["f1_macro_ok"]},
            {"criterion": "FPR", "value": criteria["fpr"]["candidate"],
             "bound": criteria["fpr"]["ceiling"], "ok": criteria["fpr_ok"]},
        ]
        st.dataframe(pd.DataFrame(rows).set_index("criterion"), width="stretch")
        if criteria.get("regressions"):
            st.warning(
                "Per-class recall regressions: "
                + ", ".join(f"`{k}` −{v:.4f}" for k, v in criteria["regressions"].items())
            )


def _render_result(task: str, job_id: str) -> None:
    """Render a finished job: what was sealed, trained, decided and promoted."""
    try:
        result = api_client.train_result(task, job_id)
    except api_client.ApiError as exc:
        ui.show_api_error(exc)
        return

    if result["status"] == "running":
        st.info(result.get("detail") or "Training still in progress.")
        return
    if result["status"] == "failed":
        st.error(result.get("detail") or "Training failed.")
        return

    if result.get("run_status") == "exists":
        st.info(
            f"⏭️ {result.get('detail')}  \nRun `{result.get('run_id')}` produced "
            f"`{result.get('saved_version')}`.",
            icon="ℹ️",
        )
        return

    if result.get("real"):
        cols = st.columns(3)
        cols[0].metric("Model", result.get("saved_version") or "—")
        cols[1].metric(
            "Data version",
            result.get("data_version") or "—",
            delta=result.get("bump"),
            help="The bump follows from the label space: a new class is a major bump.",
        )
        metrics = result.get("metrics") or {}
        cols[2].metric(
            "F1-macro (validation)",
            f"{metrics.get('f1_macro', 0):.4f}" if metrics else "—",
        )
        st.caption(f"run_id `{result.get('run_id')}`")
        _render_decision(result.get("decision"))
        return

    # Simulated branches keep the confusion-matrix view.
    st.warning("Simulated run — no model was written.", icon="⚠️")
    metrics = result["metrics"]
    left, right = st.columns(2)
    left.metric("F1 (macro)", f"{metrics['f1_macro']:.4f}")
    right.metric("Accuracy", f"{metrics['accuracy']:.4f}")
    labels = result["labels"]
    matrix = pd.DataFrame(result["confusion_matrix"], index=labels, columns=labels)
    st.dataframe(matrix.style.background_gradient(cmap="Blues", axis=None), width="stretch")


@st.fragment(run_every=POLL_SECONDS)
def _live_job(task: str) -> None:
    """Poll a running job without blocking the rest of the app."""
    job = state.get_train_job(task)
    if job is None or job.finished:
        return
    try:
        status = api_client.train_status(task, job.job_id)
    except api_client.ApiError as exc:
        job.status = "failed"
        job.logs = [*job.logs, str(exc)]
        state.set_train_job(task, job)
        st.rerun(scope="app")
        return

    job.status = status["status"]
    job.epoch = status["epoch"]
    job.loss_curve = status["loss_curve"]
    job.logs = status["logs"]
    state.set_train_job(task, job)

    if job.loss_curve:
        st.line_chart(pd.DataFrame(job.loss_curve).set_index("epoch"))
    st.code("\n".join(job.logs) or "starting…")
    if job.total_epochs and status["epoch"]:
        st.progress(job.progress, text=f"epoch {job.epoch}/{job.total_epochs}")
    else:
        st.spinner("training…")

    if job.finished:
        cache.invalidate_lifecycle()
        st.rerun(scope="app")


def render_task(task: str) -> None:
    """Render the controls and the current/last run for one task."""
    job = state.get_train_job(task)
    running = job is not None and not job.finished

    if task == "branch1":
        st.caption(
            "Training seals a new data version from whatever has been confirmed on "
            "the Data page. A new class makes it a **major** bump (promoted "
            "directly); more of the same classes is a **minor** bump (gated)."
        )
    else:
        st.warning("This branch still simulates training.", icon="⚠️")

    cols = st.columns(3)
    train_pct = cols[0].number_input(
        "Train %", 1, 98, 70, key=state.widget_key("train", task, "train"), disabled=running
    )
    valid_pct = cols[1].number_input(
        "Valid %", 1, 98, 15, key=state.widget_key("train", task, "valid"), disabled=running
    )
    test_pct = cols[2].number_input(
        "Test %", 1, 98, 15, key=state.widget_key("train", task, "test"), disabled=running
    )
    total = train_pct + valid_pct + test_pct
    if total != 100:
        st.warning(f"Split must sum to 100 (currently {total}).")

    start_col, clear_col, _ = st.columns([1, 1, 3])
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

    if job is not None and clear_col.button(
        "Clear", key=state.widget_key("train", task, "clear"), disabled=running
    ):
        state.clear_train_job(task)
        st.rerun()

    ui.render_feedback("train", task)

    if job is None:
        return
    st.caption(f"Job `{job.job_id}` · status: {job.status}")
    if running:
        _live_job(task)
    else:
        if job.logs:
            st.code("\n".join(job.logs))
        st.divider()
        _render_result(task, job.job_id)


def render_sidebar_reset() -> None:
    """The demo reset: archive everything this round produced, restore baseline."""
    with st.sidebar:
        st.divider()
        st.markdown("### Demo")
        st.caption(
            "Restores the protected baseline. Models are archived, never deleted."
        )
        if st.button("↺ Reset demo", width="stretch", key=state.widget_key("reset")):
            try:
                result = api_client.reset_demo()
            except api_client.ApiError as exc:
                st.error(str(exc))
                return
            cache.invalidate_lifecycle()
            for task in ui.TASKS:
                state.clear_train_job(task)
            st.success(
                f"Restored `{result['baseline_model']}` (data "
                f"{result['baseline_data_version']}). Archived "
                f"{len(result['archived_models'])} model(s), purged "
                f"{result['purged_queue_rows']} queue rows."
            )


ui.page_header("🎓 Train", "Seal a data version, train, and let the gate decide.")
render_sidebar_reset()

for tab, task in zip(st.tabs([ui.TASK_LABELS[t] for t in ui.TASKS]), ui.TASKS):
    with tab:
        render_task(task)
