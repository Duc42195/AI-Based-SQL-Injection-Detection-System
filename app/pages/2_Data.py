"""Data page — annotation queues (annotated / unannotated) per branch."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import api_client, ui

st.set_page_config(page_title="SQLi Detection — Data", page_icon="🏷️", layout="wide")


def render_task(task: str) -> None:
    """Render annotated/unannotated counts and the labelling form for a task."""
    try:
        pending = api_client.unannotated(task)
        done = api_client.annotated(task)
    except api_client.ApiError as exc:
        ui.show_api_error(exc)
        return

    left, right = st.columns(2)
    left.metric("Annotated", f"{done['count']:,}")
    right.metric("Awaiting label", f"{pending['count']:,}")

    unannotated_tab, annotated_tab = st.tabs(["Unannotated", "Annotated"])

    with unannotated_tab:
        if not pending["items"]:
            st.success("Nothing left to label.")
        for item in pending["items"]:
            with st.container(border=True):
                st.code(item["query"], language="sql")
                st.caption(f"id: `{item['id']}` · source: {item['source']}")
                label = st.radio(
                    "Label",
                    pending["label_options"],
                    horizontal=True,
                    key=f"label_{task}_{item['id']}",
                )
                if st.button("Save label", key=f"save_{task}_{item['id']}"):
                    try:
                        result = api_client.annotate(task, item["id"], label)
                        if result.get("persisted"):
                            st.success(f"Saved `{label}`.")
                        else:
                            st.info(
                                f"Accepted `{label}` — not persisted yet "
                                "(continual-learning store pending)."
                            )
                    except api_client.ApiError as exc:
                        ui.show_api_error(exc)

    with annotated_tab:
        if done["items"]:
            st.dataframe(pd.DataFrame(done["items"]), width="stretch")
            st.caption(f"Showing {len(done['items'])} of {done['count']:,}")
        else:
            st.info("No annotated samples yet.")


ui.page_header("🏷️ Data", "Review and label samples feeding continual learning.")
st.info(
    "Sample pools are mock data. The real queue comes from the Overkill review "
    "queue and the continual-learning store.",
    icon="ℹ️",
)

for tab, task in zip(st.tabs([ui.TASK_LABELS[t] for t in ui.TASKS]), ui.TASKS):
    with tab:
        render_task(task)
