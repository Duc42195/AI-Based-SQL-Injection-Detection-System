"""Monitor page — drift chart, retrain trigger and logs, one tab per branch."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import api_client, ui

st.set_page_config(page_title="SQLi Detection — Monitor", page_icon="📊", layout="wide")


def render_task(task: str) -> None:
    """Render the drift chart + retrain control + logs for one task."""
    try:
        data = api_client.drift(task)
    except api_client.ApiError as exc:
        ui.show_api_error(exc)
        return

    chart_col, action_col = st.columns([4, 1])
    with action_col:
        if st.button("🔁 Retrain", key=f"retrain_{task}", width="stretch"):
            try:
                result = api_client.retrain(task)
                st.success(f"Queued: `{result['job_id']}`")
            except api_client.ApiError as exc:
                ui.show_api_error(exc)
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

    with st.expander("📜 Logs"):
        try:
            lines = api_client.logs(task)["lines"]
            st.code("\n".join(lines))
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
