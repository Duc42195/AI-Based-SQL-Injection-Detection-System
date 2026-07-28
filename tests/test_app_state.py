"""Unit tests for the Streamlit app's central state module.

``app.state`` reads and writes ``st.session_state``, which needs a script run
context. ``AppTest`` provides one, so each test runs a tiny script that
exercises the accessors and leaves assertions in ``session_state``.
"""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

from app.state import DemoRun, TrainJob


def _run(body: str) -> AppTest:
    """Run a snippet inside an AppTest script context."""
    script = "from app import state\n" + body
    app = AppTest.from_string(script)
    app.run()
    assert not app.exception, app.exception
    return app


def test_widget_keys_are_namespaced_and_unique() -> None:
    app = _run(
        "st_a = state.widget_key('test', 'single', 'query')\n"
        "st_b = state.widget_key('test', 'session', 'query')\n"
        "import streamlit as st\n"
        "st.session_state['a'] = st_a\n"
        "st.session_state['b'] = st_b\n"
    )
    assert app.session_state["a"].startswith("sqli.w.")
    assert app.session_state["a"] != app.session_state["b"]


def test_demo_run_roundtrip_and_clear() -> None:
    app = _run(
        "import streamlit as st\n"
        "state.set_demo_run('single', state.DemoRun(True, ['q'], {'ok': 1}))\n"
        "st.session_state['stored'] = state.get_demo_run('single')\n"
        "st.session_state['other'] = state.get_demo_run('session')\n"
        "state.clear_demo_run('single')\n"
        "st.session_state['after_clear'] = state.get_demo_run('single')\n"
    )
    stored = app.session_state["stored"]
    assert isinstance(stored, DemoRun)
    assert stored.protected is True and stored.response == {"ok": 1}
    # Modes are independent, and clearing removes only the one asked for.
    assert app.session_state["other"] is None
    assert app.session_state["after_clear"] is None


def test_train_job_progress_and_finished() -> None:
    running = TrainJob(job_id="j", task="branch1", total_epochs=5, epoch=2)
    assert running.finished is False
    assert running.progress == 2 / 5

    done = TrainJob(job_id="j", task="branch1", total_epochs=5, epoch=5, status="done")
    assert done.finished is True
    assert done.progress == 1.0


def test_train_job_progress_never_exceeds_one() -> None:
    overrun = TrainJob(job_id="j", task="branch1", total_epochs=5, epoch=9)
    assert overrun.progress == 1.0


def test_train_job_is_per_task() -> None:
    app = _run(
        "import streamlit as st\n"
        "state.set_train_job('branch1', state.TrainJob('j1', 'branch1', 5))\n"
        "st.session_state['b1'] = state.get_train_job('branch1')\n"
        "st.session_state['b2'] = state.get_train_job('branch2')\n"
    )
    assert app.session_state["b1"].job_id == "j1"
    assert app.session_state["b2"] is None


def test_feedback_is_show_once() -> None:
    app = _run(
        "import streamlit as st\n"
        "state.set_feedback('data', 'branch1', kind='success', message='saved')\n"
        "st.session_state['first'] = state.pop_feedback('data', 'branch1')\n"
        "st.session_state['second'] = state.pop_feedback('data', 'branch1')\n"
    )
    assert app.session_state["first"].message == "saved"
    assert app.session_state["second"] is None


def test_offset_defaults_to_zero_and_never_negative() -> None:
    app = _run(
        "import streamlit as st\n"
        "st.session_state['default'] = state.get_offset('branch1')\n"
        "state.set_offset('branch1', -20)\n"
        "st.session_state['clamped'] = state.get_offset('branch1')\n"
    )
    assert app.session_state["default"] == 0
    assert app.session_state["clamped"] == 0


def test_app_state_excludes_widget_keys_and_reset_clears() -> None:
    app = _run(
        "import streamlit as st\n"
        "st.session_state[state.widget_key('some', 'widget')] = 'widget value'\n"
        "state.set_demo_run('single', state.DemoRun(False, [], {}))\n"
        "st.session_state['tracked'] = list(state.app_state())\n"
        "state.reset()\n"
        "st.session_state['after_reset'] = list(state.app_state())\n"
        "st.session_state['widget_survived'] = "
        "state.widget_key('some', 'widget') in st.session_state\n"
    )
    tracked = app.session_state["tracked"]
    assert any(k.endswith("test.single.run") for k in tracked)
    assert not any(".w." in k for k in tracked)
    assert app.session_state["after_reset"] == []
    # reset() must not destroy widget state.
    assert app.session_state["widget_survived"] is True
