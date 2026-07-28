"""Monitor page — drift chart, retrain trigger and logs, one tab per branch."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import api_client, cache, state, ui

st.set_page_config(page_title="SQLi Detection — Monitor", page_icon="📊", layout="wide")


def render_task(task: str) -> None:
    """Render the drift chart + retrain control + logs for one task."""
    try:
        data = cache.drift(task)
    except api_client.ApiError as exc:
        ui.show_api_error(exc)
        return

    chart_col, action_col = st.columns([4, 1])
    with action_col:
        if st.button(
            "🔁 Retrain", key=state.widget_key("monitor", task, "retrain"), width="stretch"
        ):
            try:
                result = api_client.retrain(task)
            except api_client.ApiError as exc:
                state.set_feedback("monitor", task, kind="error", message=str(exc))
            else:
                state.set_feedback(
                    "monitor",
                    task,
                    kind="success",
                    message=f"Retrain queued: `{result['job_id']}`",
                )
            st.rerun()
        if data["alert"]:
            st.error("⚠️ Drift above threshold")

    with chart_col:
        frame = pd.DataFrame(data["points"]).set_index("date")
        frame["threshold"] = data["threshold"]
        frame = frame.rename(columns={"value": data["metric"].upper()})
        st.line_chart(frame)
        latest = data["points"][-1]["value"] if data["points"] else 0.0
        st.caption(
            f"Metric: {data['metric'].upper()} · latest = {latest:.4f} · "
            f"threshold = {data['threshold']}"
        )

    ui.render_feedback("monitor", task)

    with st.expander("📜 Logs"):
        try:
            st.code("\n".join(cache.logs(task)["lines"]))
        except api_client.ApiError as exc:
            ui.show_api_error(exc)


ui.page_header("📊 Monitor", "Drift monitoring, retraining and logs per branch.")
st.info(
    "Drift series and logs are mock data — the shapes are final, the values get "
    "replaced once drift logging writes to `monitoring.metrics_log_path`.",
    icon="ℹ️",
)

for tab, task in zip(st.tabs([ui.TASK_LABELS[t] for t in ui.TASKS]), ui.TASKS):
    with tab:
        render_task(task)
