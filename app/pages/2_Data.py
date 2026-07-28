"""Data page — annotation queues (annotated / unannotated) per branch."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import api_client, cache, state, ui

st.set_page_config(page_title="SQLi Detection — Data", page_icon="🏷️", layout="wide")

PAGE_SIZE = 20


def _save_label(task: str, item_id: str, label: str) -> None:
    """Persist a label and refresh the cached pools."""
    try:
        result = api_client.annotate(task, item_id, label)
    except api_client.ApiError as exc:
        state.set_feedback("data", task, kind="error", message=str(exc))
        return
    if result.get("persisted"):
        message = f"Saved `{label}` for `{item_id}`."
        kind = "success"
    else:
        message = (
            f"Accepted `{label}` for `{item_id}` — not persisted yet "
            "(continual-learning store pending)."
        )
        kind = "info"
    state.set_feedback("data", task, kind=kind, message=message)
    cache.invalidate_annotations()


def _render_unannotated(task: str, pending: dict) -> None:
    """Render the labelling form for each pending sample."""
    if not pending["items"]:
        st.success("Nothing left to label.")
        return
    for item in pending["items"]:
        with st.container(border=True):
            st.code(item["query"], language="sql")
            st.caption(f"id: `{item['id']}` · source: {item['source']}")
            label = st.radio(
                "Label",
                pending["label_options"],
                horizontal=True,
                key=state.widget_key("data", task, "label", item["id"]),
            )
            if st.button(
                "Save label", key=state.widget_key("data", task, "save", item["id"])
            ):
                _save_label(task, item["id"], label)
                st.rerun()


def _render_annotated(task: str, done: dict) -> None:
    """Render a page of already-labelled samples with pagination."""
    if not done["items"]:
        st.info("No annotated samples yet.")
        return
    st.dataframe(pd.DataFrame(done["items"]), width="stretch")

    offset = state.get_offset(task)
    shown_from = offset + 1
    shown_to = offset + len(done["items"])
    st.caption(f"Showing {shown_from:,}–{shown_to:,} of {done['count']:,}")

    prev_col, next_col, _ = st.columns([1, 1, 6])
    if prev_col.button(
        "‹ Prev", key=state.widget_key("data", task, "prev"), disabled=offset == 0
    ):
        state.set_offset(task, offset - PAGE_SIZE)
        st.rerun()
    if next_col.button(
        "Next ›",
        key=state.widget_key("data", task, "next"),
        disabled=shown_to >= done["count"],
    ):
        state.set_offset(task, offset + PAGE_SIZE)
        st.rerun()


def render_task(task: str) -> None:
    """Render annotated/unannotated counts and the labelling form for a task."""
    offset = state.get_offset(task)
    try:
        pending = cache.unannotated(task, limit=PAGE_SIZE)
        done = cache.annotated(task, limit=PAGE_SIZE, offset=offset)
    except api_client.ApiError as exc:
        ui.show_api_error(exc)
        return

    left, right = st.columns(2)
    left.metric("Annotated", f"{done['count']:,}")
    right.metric("Awaiting label", f"{pending['count']:,}")

    ui.render_feedback("data", task)

    unannotated_tab, annotated_tab = st.tabs(["Unannotated", "Annotated"])
    with unannotated_tab:
        _render_unannotated(task, pending)
    with annotated_tab:
        _render_annotated(task, done)


ui.page_header("🏷️ Data", "Review and label samples feeding continual learning.")
st.info(
    "Sample pools are mock data. The real queue comes from the Overkill review "
    "queue and the continual-learning store.",
    icon="ℹ️",
)

for tab, task in zip(st.tabs([ui.TASK_LABELS[t] for t in ui.TASKS]), ui.TASKS):
    with tab:
        render_task(task)
