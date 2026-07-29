"""Test page — demo database + with/without-model attack comparison.

Entry point of the Streamlit app:
    uv run streamlit run app/streamlit_app.py

Results are stored in :mod:`app.state`, so a verdict stays on screen when an
unrelated widget triggers a re-run (a bare ``if st.button(...)`` block would
disappear on the very next interaction).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import api_client, cache, state, ui

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


def _render_step(step: dict, protected: bool) -> None:
    """Render one execution step: the SQL built and what came back."""
    st.code(step["constructed_sql"], language="sql")
    if step.get("error"):
        st.warning(f"SQL error: {step['error']}")
    elif not step["executed"]:
        st.success("🛡️ Query was **blocked** — never reached the database.")
    elif step["leaked"]:
        st.error(
            f"⚠️ Executed and returned **{step['row_count']} rows** — "
            "the WHERE clause was subverted and data leaked."
        )
    else:
        st.info(f"Executed normally — {step['row_count']} row(s).")

    if step["rows"]:
        st.dataframe(pd.DataFrame(step["rows"]), width="stretch")

    if protected:
        left, right = st.columns(2)
        with left:
            ui.render_branch1(step.get("branch1"))
        with right:
            ui.render_branch2(step.get("branch2"))


def _render_run(run: state.DemoRun) -> None:
    """Render a stored run: verdict, then each step."""
    st.divider()
    mode_label = "WITH model" if run.protected else "WITHOUT model"
    st.caption(f"Last run: **{mode_label}**")
    if run.protected:
        ui.render_decision(run.response.get("decision"))

    steps = run.response["results"]
    for index, step in enumerate(steps, start=1):
        if len(steps) > 1:
            st.markdown(f"**Step {index}** — `{step['input']}`")
        _render_step(step, run.protected)
        if len(steps) > 1:
            st.divider()



def _execute(mode: str, inputs: list[str], protected: bool) -> None:
    """Call the backend and persist the result for this mode."""
    try:
        response = api_client.demo_execute(inputs, protected=protected)
    except api_client.ApiError as exc:
        state.set_feedback("test", mode, kind="error", message=str(exc))
        return
    state.set_demo_run(mode, state.DemoRun(protected, inputs, response))


def _run_buttons(mode: str) -> tuple[bool, bool]:
    """Render the two run buttons; return (unprotected, protected) clicks."""
    left, right = st.columns(2)
    unprotected = left.button(
        "▶ Run WITHOUT model",
        width="stretch",
        key=state.widget_key("test", mode, "unprotected"),
        help="Send the query straight to the database, with no detection.",
    )
    protected = right.button(
        "🛡️ Run WITH model",
        type="primary",
        width="stretch",
        key=state.widget_key("test", mode, "protected"),
        help="Run detection first; the query only executes if allowed.",
    )
    return unprotected, protected


def tab_database() -> None:
    """Tab 1 — show the demo table being protected."""
    st.subheader("Simulated database")
    st.caption(
        "A throwaway in-memory SQLite table with fake data. The demo backend "
        "builds SQL by string concatenation on purpose, so real injection works."
    )
    try:
        data = cache.demo_database()
    except api_client.ApiError as exc:
        ui.show_api_error(exc)
        return
    st.code(data["query_template"], language="sql")
    st.dataframe(pd.DataFrame(data["rows"]), width="stretch")
    st.caption(f"Table `{data['table']}` · {data['row_count']} rows")


def tab_single_query() -> None:
    """Tab 2 — Branch 1 + 2 on a single input."""
    mode = "single"
    st.subheader("Test Branch 1 + Branch 2")
    choice = st.selectbox(
        "Example payload", list(SAMPLE_INPUTS), key=state.widget_key("test", mode, "sample")
    )
    query = st.text_area(
        "Input value (goes into the WHERE clause)",
        value=SAMPLE_INPUTS[choice],
        key=state.widget_key("test", mode, "query", choice),
        height=80,
    )

    unprotected, protected = _run_buttons(mode)
    if unprotected or protected:
        if query.strip():
            _execute(mode, [query], protected=protected)
        else:
            state.set_feedback(
                "test", mode, kind="warning", message="Enter an input value first."
            )

    ui.render_feedback("test", mode)
    run = state.get_demo_run(mode)
    if run:
        _render_run(run)


def tab_session() -> None:
    """Tab 3 — Branch 3 session-level test (two queries)."""
    mode = "session"
    st.subheader("Test Branch 3 (session)")
    st.caption(
        "Two queries from the same session. Branch 3 catches attacks that only "
        "become visible across multiple steps (blind probing, query splitting)."
    )
    choice = st.selectbox(
        "Example session",
        list(SAMPLE_SESSIONS),
        key=state.widget_key("test", mode, "sample"),
    )
    default_first, default_second = SAMPLE_SESSIONS[choice]
    first = st.text_input(
        "Query 1", value=default_first, key=state.widget_key("test", mode, "q1", choice)
    )
    second = st.text_input(
        "Query 2", value=default_second, key=state.widget_key("test", mode, "q2", choice)
    )

    unprotected, protected = _run_buttons(mode)
    if unprotected or protected:
        inputs = [q for q in (first, second) if q.strip()]
        if len(inputs) == 2:
            _execute(mode, inputs, protected=protected)
        else:
            state.set_feedback(
                "test", mode, kind="warning", message="Enter both queries first."
            )

    ui.render_feedback("test", mode)
    run = state.get_demo_run(mode)
    if run:
        _render_run(run)


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
