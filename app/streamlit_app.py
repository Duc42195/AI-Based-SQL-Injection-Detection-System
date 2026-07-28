"""Test page — demo database + with/without-model attack comparison.

Entry point of the Streamlit app:
    uv run streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import api_client, ui

st.set_page_config(page_title="SQLi Detection — Test", page_icon="🛡️", layout="wide")

# Example payloads offered in the dropdown (label → input value).
SAMPLE_INPUTS = {
    "(type your own)": "",
    "Benign — existing user": "admin",
    "Benign — normal lookup": "alice",
    "Classic tautology": "' OR '1'='1",
    "Comment terminator": "admin'--",
    "UNION data theft": "' UNION SELECT id, username, password, email, role FROM users--",
    "Obfuscated (comments)": "admin'/**/OR/**/1=1--",
}

SAMPLE_SESSIONS = {
    "(type your own)": ("", ""),
    "Boolean-blind probing": (
        "admin' AND SUBSTR(password,1,1) > 'm'--",
        "admin' AND SUBSTR(password,1,1) > 'g'--",
    ),
    "Query splitting": ("admin' AND 1=1--", "admin' UNION SELECT password FROM users--"),
    "Benign session": ("alice", "bob"),
}


def _render_leak(step: dict) -> None:
    """Render one execution step: the SQL built and what came back."""
    st.code(step["constructed_sql"], language="sql")
    if step.get("error"):
        st.warning(f"SQL error: {step['error']}")
        return
    if not step["executed"]:
        st.success("🛡️ Query was **blocked** — never reached the database.")
        return
    if step["leaked"]:
        st.error(
            f"⚠️ Executed and returned **{step['row_count']} rows** — "
            "the WHERE clause was subverted and data leaked."
        )
    else:
        st.info(f"Executed normally — {step['row_count']} row(s).")
    if step["rows"]:
        st.dataframe(pd.DataFrame(step["rows"]), width="stretch")


def tab_database() -> None:
    """Tab 1 — show the demo table being protected."""
    st.subheader("Simulated database")
    st.caption(
        "A throwaway in-memory SQLite table with fake data. The demo backend "
        "builds SQL by string concatenation on purpose, so real injection works."
    )
    try:
        data = api_client.demo_database()
    except api_client.ApiError as exc:
        ui.show_api_error(exc)
        return
    st.code(data["query_template"], language="sql")
    st.dataframe(pd.DataFrame(data["rows"]), width="stretch")
    st.caption(f"Table `{data['table']}` · {data['row_count']} rows")


def tab_single_query() -> None:
    """Tab 2 — Branch 1 + 2 on a single input."""
    st.subheader("Test Branch 1 + Branch 2")
    choice = st.selectbox("Example payload", list(SAMPLE_INPUTS), key="single_sample")
    query = st.text_area(
        "Input value (goes into the WHERE clause)",
        value=SAMPLE_INPUTS[choice],
        key=f"single_query_{choice}",
        height=80,
    )

    col_unprotected, col_protected = st.columns(2)
    run_unprotected = col_unprotected.button(
        "▶ Run WITHOUT model", width="stretch", key="btn_unprotected"
    )
    run_protected = col_protected.button(
        "🛡️ Run WITH model", type="primary", width="stretch", key="btn_protected"
    )

    if not (run_unprotected or run_protected):
        return
    if not query.strip():
        st.warning("Enter an input value first.")
        return

    protected = bool(run_protected)
    try:
        result = api_client.demo_execute([query], protected=protected)
    except api_client.ApiError as exc:
        ui.show_api_error(exc)
        return

    st.divider()
    if protected:
        ui.render_decision(result.get("decision"))
    step = result["results"][0]
    _render_leak(step)

    if protected:
        st.divider()
        left, right = st.columns(2)
        with left:
            ui.render_branch1(step.get("branch1"))
        with right:
            ui.render_branch2(step.get("branch2"))


def tab_session() -> None:
    """Tab 3 — Branch 3 session-level test (two queries)."""
    st.subheader("Test Branch 3 (session)")
    st.caption(
        "Two queries from the same session. Branch 3 catches attacks that only "
        "become visible across multiple steps (blind probing, query splitting)."
    )
    choice = st.selectbox("Example session", list(SAMPLE_SESSIONS), key="session_sample")
    default_first, default_second = SAMPLE_SESSIONS[choice]
    first = st.text_input("Query 1", value=default_first, key=f"s1_{choice}")
    second = st.text_input("Query 2", value=default_second, key=f"s2_{choice}")

    col_unprotected, col_protected = st.columns(2)
    run_unprotected = col_unprotected.button(
        "▶ Run WITHOUT model", width="stretch", key="btn_sess_unprotected"
    )
    run_protected = col_protected.button(
        "🛡️ Run WITH model", type="primary", width="stretch", key="btn_sess_protected"
    )

    if not (run_unprotected or run_protected):
        return
    inputs = [q for q in (first, second) if q.strip()]
    if len(inputs) < 2:
        st.warning("Enter both queries first.")
        return

    protected = bool(run_protected)
    try:
        result = api_client.demo_execute(inputs, protected=protected)
    except api_client.ApiError as exc:
        ui.show_api_error(exc)
        return

    st.divider()
    if protected:
        ui.render_decision(result.get("decision"))
    for i, step in enumerate(result["results"], start=1):
        st.markdown(f"**Step {i}** — `{step['input']}`")
        _render_leak(step)
        if protected:
            left, right = st.columns(2)
            with left:
                ui.render_branch1(step.get("branch1"))
            with right:
                ui.render_branch2(step.get("branch2"))
        st.divider()

    if protected:
        ui.render_branch3(result.get("branch3"))


ui.page_header(
    "🧪 Test",
    "Run queries against a deliberately vulnerable demo database, with and "
    "without the detector in front of it.",
)

tab1, tab2, tab3 = st.tabs(
    ["Simulated database", "Branch 1 + 2 (single query)", "Branch 3 (session)"]
)
with tab1:
    tab_database()
with tab2:
    tab_single_query()
with tab3:
    tab_session()
