"""Data page — review AI pre-labels: approve, correct or reject."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import api_client, cache, state, ui

st.set_page_config(page_title="SQLi Detection — Data", page_icon="🏷️", layout="wide")

PAGE_SIZE = 20


def _decide(task: str, item_id: str, action: str, label: str | None = None) -> None:
    """Send a review decision and refresh the cached pools."""
    try:
        result = api_client.annotate(task, item_id, action, label)
    except api_client.ApiError as exc:
        state.set_feedback("data", task, kind="error", message=str(exc))
        return
    cache.invalidate_annotations()
    verb = {"approved": "Approved", "corrected": "Corrected to", "rejected": "Rejected"}[
        result["status"]
    ]
    message = (
        f"{verb} `{result['label']}`" if result["status"] != "rejected" else f"{verb} sample"
    )
    state.set_feedback("data", task, kind="success", message=f"{message} — `{item_id}`")


def _render_pending(task: str, pending: dict) -> None:
    """One card per queued item, pre-filled with the model's own prediction."""
    if not pending["items"]:
        st.success(
            "Nothing awaiting review. Replay a stream slice from the Monitor page "
            "to populate the queue."
        )
        return

    options = pending["label_options"]
    for item in pending["items"]:
        with st.container(border=True):
            st.code(item["query"], language="sql")
            meta = st.columns(3)
            meta[0].metric("AI label", item["ai_label"] or "—")
            meta[1].metric(
                "Confidence",
                f"{item['ai_confidence']:.1%}" if item["ai_confidence"] is not None else "—",
            )
            meta[2].metric("Queued by", item["source"])

            buttons = st.columns([1, 1, 2])
            if buttons[0].button(
                "✅ Approve",
                key=state.widget_key("data", task, "approve", item["id"]),
                width="stretch",
                help="Accept the model's label as correct.",
            ):
                _decide(task, item["id"], "approve")
                st.rerun()
            if buttons[1].button(
                "🗑 Reject",
                key=state.widget_key("data", task, "reject", item["id"]),
                width="stretch",
                help="Drop this sample — it will never be trained on.",
            ):
                _decide(task, item["id"], "reject")
                st.rerun()
            with buttons[2]:
                correction = st.selectbox(
                    "Correct to",
                    options,
                    index=options.index(item["ai_label"]) if item["ai_label"] in options else 0,
                    key=state.widget_key("data", task, "label", item["id"]),
                    label_visibility="collapsed",
                )
                if st.button(
                    "✏️ Correct",
                    key=state.widget_key("data", task, "correct", item["id"]),
                    width="stretch",
                ):
                    _decide(task, item["id"], "correct", correction)
                    st.rerun()


def _render_confirmed(task: str, done: dict) -> None:
    """The confirmed-label ledger that feeds the next data version."""
    if not done["items"]:
        st.info("No confirmed labels yet.")
        return
    st.dataframe(pd.DataFrame(done["items"]), width="stretch")
    offset = state.get_offset(task)
    st.caption(f"Showing {offset + 1:,}–{offset + len(done['items']):,} of {done['count']:,}")

    prev_col, next_col, _ = st.columns([1, 1, 6])
    if prev_col.button("‹ Prev", key=state.widget_key("data", task, "prev"), disabled=offset == 0):
        state.set_offset(task, offset - PAGE_SIZE)
        st.rerun()
    if next_col.button(
        "Next ›",
        key=state.widget_key("data", task, "next"),
        disabled=offset + len(done["items"]) >= done["count"],
    ):
        state.set_offset(task, offset + PAGE_SIZE)
        st.rerun()


def render_task(task: str) -> None:
    """Render queue counts, the review cards and the confirmed ledger."""
    offset = state.get_offset(task)
    try:
        pending = cache.unannotated(task, limit=PAGE_SIZE)
        done = cache.annotated(task, limit=PAGE_SIZE, offset=offset)
    except api_client.ApiError as exc:
        ui.show_api_error(exc)
        return

    cols = st.columns(3)
    cols[0].metric("Awaiting review", f"{pending['count']:,}")
    cols[1].metric("Confirmed", f"{done['count']:,}")
    rate = pending.get("acceptance_rate")
    cols[2].metric(
        "Pre-label acceptance",
        f"{rate:.1%}" if rate is not None else "—",
        help=(
            "Share of AI labels accepted unchanged. The queue holds the model's "
            "least certain queries, so this is a live measure of its quality."
        ),
    )

    ui.render_feedback("data", task)

    pending_tab, confirmed_tab = st.tabs(["Awaiting review", "Confirmed"])
    with pending_tab:
        _render_pending(task, pending)
    with confirmed_tab:
        _render_confirmed(task, done)


ui.page_header(
    "🏷️ Data",
    "Every queued query arrives with the model's own prediction — accept it, "
    "correct it, or drop the sample.",
)

for tab, task in zip(st.tabs([ui.TASK_LABELS[t] for t in ui.TASKS]), ui.TASKS):
    with tab:
        render_task(task)
