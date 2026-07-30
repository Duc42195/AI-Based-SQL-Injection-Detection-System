"""Monitor page — measured drift, replay control, retrain trigger and logs."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import api_client, cache, state, ui

st.set_page_config(page_title="SQLi Detection — Monitor", page_icon="📊", layout="wide")

# Each option must exceed the drift baseline (mlops.drift.baseline_windows x
# window_size, 10k by default), or every window is reference and the chart
# compares the baseline against itself.
REPLAY_SIZES = {
    "20k queries (fast)": 20000,
    "40k queries": 40000,
    "Full stream (~81k)": 200000,
}


def _render_chart(data: dict) -> None:
    """Plot every monitored PSI signal against the alert threshold."""
    frame = pd.DataFrame(
        [{"window": p["index"], **p["psi"]} for p in data["points"]]
    ).set_index("window")
    frame["threshold"] = data["threshold"]
    st.line_chart(frame)

    reference = [p for p in data["points"] if p["is_reference"]]
    phase_b = [p for p in data["points"] if p["phase"] == "B"]
    st.caption(
        f"{len(data['points'])} windows · reference = first {len(reference)} "
        f"({data.get('reference', '')}) · phase B from window "
        f"{phase_b[0]['index'] if phase_b else '—'} · threshold {data['threshold']}"
    )


def _render_signal_table(data: dict) -> None:
    """Per-signal summary: does any of them actually breach the threshold?"""
    points = [p for p in data["points"] if not p["is_reference"]]
    if not points:
        st.warning(
            "Every replayed window is part of the drift **reference**, so the chart "
            "is comparing the baseline against itself and means nothing yet. "
            "Replay a longer slice to get windows beyond the baseline.",
            icon="⚠️",
        )
        return
    rows = []
    for signal in data["signals"]:
        values = [p["psi"].get(signal, 0.0) for p in points]
        phase_b = [p["psi"].get(signal, 0.0) for p in points if p["phase"] == "B"]
        rows.append(
            {
                "signal": signal,
                "mean": round(sum(values) / len(values), 4),
                "max": round(max(values), 4),
                "phase B max": round(max(phase_b), 4) if phase_b else None,
                "breached": max(values) >= data["threshold"],
            }
        )
    st.dataframe(pd.DataFrame(rows).set_index("signal"), width="stretch")


def render_task(task: str) -> None:
    """Render drift, controls and logs for one task."""
    try:
        data = cache.drift(task)
    except api_client.ApiError as exc:
        ui.show_api_error(exc)
        return

    chart_col, action_col = st.columns([4, 1])

    with action_col:
        if task == "branch1":
            size = st.selectbox(
                "Replay size", list(REPLAY_SIZES), key=state.widget_key("monitor", "size")
            )
            if st.button("▶ Replay stream", width="stretch", key=state.widget_key("monitor", "replay")):
                with st.spinner("Replaying through the live model…"):
                    try:
                        result = api_client.replay(limit=REPLAY_SIZES[size], max_queue=200)
                    except api_client.ApiError as exc:
                        state.set_feedback("monitor", task, kind="error", message=str(exc))
                    else:
                        cache.invalidate_lifecycle()
                        state.set_feedback(
                            "monitor",
                            task,
                            kind="success",
                            message=(
                                f"Replayed {result['replayed']:,} queries over "
                                f"{result['windows']} windows; {result['queued']} "
                                "items queued for review."
                            ),
                        )
                st.rerun()

        if st.button("🔁 Retrain", key=state.widget_key("monitor", task, "retrain"), width="stretch"):
            with st.spinner("Training…"):
                try:
                    result = api_client.retrain(task)
                except api_client.ApiError as exc:
                    state.set_feedback("monitor", task, kind="error", message=str(exc))
                else:
                    cache.invalidate_lifecycle()
                    state.set_feedback(
                        "monitor",
                        task,
                        kind="success" if result["ok"] else "warning",
                        message=f"{result['status']}: {result.get('detail') or result['job_id']}",
                    )
            st.rerun()

        if data.get("alert"):
            st.error("⚠️ Drift alert")

    with chart_col:
        if data["status"] != "ready":
            st.info(data.get("detail") or "No drift data yet.")
        else:
            _render_chart(data)

    ui.render_feedback("monitor", task)

    if data["status"] == "ready":
        trigger = data.get("trigger") or {}
        if trigger.get("fired"):
            st.warning(
                f"Trigger fired on **{trigger['signal']}** at window "
                f"{trigger['window_index']} after {trigger['sustained_windows']} "
                "sustained windows."
            )
        else:
            st.info(
                "No signal sustained a breach. At a ~5 % attack rate a new class is "
                "~1 % of traffic, which aggregate distribution statistics do not "
                "register — uncertainty routing catches it instead (see the Data page).",
                icon="ℹ️",
            )
        _render_signal_table(data)

    with st.expander("📜 Runs and gate decisions"):
        try:
            st.code("\n".join(cache.logs(task)["lines"]))
        except api_client.ApiError as exc:
            ui.show_api_error(exc)


ui.page_header("📊 Monitor", "Measured drift, replay control and the run log.")

for tab, task in zip(st.tabs([ui.TASK_LABELS[t] for t in ui.TASKS]), ui.TASKS):
    with tab:
        render_task(task)
