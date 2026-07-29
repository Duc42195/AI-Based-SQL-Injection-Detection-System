"""Headless tests for the Streamlit pages using ``AppTest``.

The backend is mocked, so these run without a live API. The important case is
:func:`test_result_survives_unrelated_interaction` — Streamlit re-runs the whole
script on every interaction, so a result rendered directly inside an
``if st.button(...)`` block disappears on the next click. These tests pin the
state-backed behaviour that prevents that.
"""

from __future__ import annotations

from typing import Any, Callable

import pytest
from streamlit.testing.v1 import AppTest

from app import api_client, cache

APP = "app/streamlit_app.py"
MONITOR = "app/pages/1_Monitor.py"
DATA = "app/pages/2_Data.py"
TRAIN = "app/pages/3_Train.py"
METRICS = "app/pages/4_Metrics.py"
TIMEOUT = 30

PAYLOAD_SAMPLE = "Classic tautology"  # a non-empty entry in SAMPLE_INPUTS

_HEALTH = {
    "status": "ok",
    "api_version": "v1",
    "branches": {"branch1": "ready", "branch2": "ready"},
}
_DEMO_DB = {
    "table": "users",
    "columns": ["id", "username"],
    "rows": [{"id": 1, "username": "admin"}],
    "row_count": 1,
    "query_template": "SELECT * FROM users WHERE username = '{input}'",
}
_BRANCH1 = {
    "status": "ready",
    "query_canonical": "x",
    "label": 3,
    "label_name": "boolean_blind",
    "is_sqli": True,
    "confidence": 0.78,
    "attack_probability": 0.97,
    "probabilities": {"normal": 0.03, "boolean_blind": 0.78},
    "threshold": 0.5,
}
_BRANCH2 = {
    "status": "ready",
    "query_canonical": "x",
    "anomaly_score": -3.9,
    "is_anomaly": False,
}
_BLOCKED = {
    "protected": True,
    "results": [
        {
            "input": "' OR '1'='1",
            "constructed_sql": "SELECT * FROM users WHERE username = '' OR '1'='1'",
            "executed": False,
            "row_count": 0,
            "leaked": False,
            "rows": [],
            "error": None,
            "branch1": _BRANCH1,
            "branch2": _BRANCH2,
        }
    ],
    "decision": {"action": "BLOCK", "reason": "Branch-1 detected attack class"},
}


def _cached(func: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a stub so it mimics an ``st.cache_data`` function (has ``.clear``)."""
    func.clear = lambda: None  # type: ignore[attr-defined]
    return func


@pytest.fixture(autouse=True)
def _mock_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point every cached read and write at in-memory fixtures."""
    monkeypatch.setattr(cache, "health", _cached(lambda: _HEALTH))
    monkeypatch.setattr(cache, "demo_database", _cached(lambda: _DEMO_DB))
    monkeypatch.setattr(cache, "metrics", _cached(lambda task: {"status": "not_ready"}))
    monkeypatch.setattr(
        cache,
        "drift",
        _cached(
            lambda task: {
                "task": task,
                "metric": "psi",
                "threshold": 0.2,
                "alert": task == "branch1",
                "points": [{"date": "2026-07-01", "value": 0.1}],
            }
        ),
    )
    monkeypatch.setattr(
        cache, "logs", _cached(lambda task: {"task": task, "lines": ["log line"]})
    )
    monkeypatch.setattr(
        cache,
        "unannotated",
        _cached(
            lambda task, limit=20, offset=0: {
                "task": task,
                "count": 1,
                "items": [
                    {"id": "u1", "query": "1' OR 1=1--", "source": "overkill_queue"}
                ],
                "label_options": ["normal", "union_based"],
            }
        ),
    )
    monkeypatch.setattr(
        cache,
        "annotated",
        _cached(
            lambda task, limit=20, offset=0: {
                "task": task,
                "count": 100,
                "items": [
                    {
                        "id": "a1",
                        "query": "SELECT 1",
                        "label": "normal",
                        "annotated_at": "t",
                    }
                ],
            }
        ),
    )
    monkeypatch.setattr(
        api_client, "demo_execute", lambda inputs, protected: dict(_BLOCKED)
    )
    monkeypatch.setattr(
        api_client,
        "annotate",
        lambda task, item_id, label: {
            "ok": True,
            "id": item_id,
            "label": label,
            "persisted": False,
        },
    )
    monkeypatch.setattr(
        api_client,
        "train_start",
        lambda task, train, valid, test: {
            "job_id": "job_x",
            "task": task,
            "status": "running",
            "total_epochs": 5,
        },
    )
    monkeypatch.setattr(
        api_client,
        "train_status",
        lambda task, job_id: {
            "job_id": job_id,
            "task": task,
            "status": "running",
            "epoch": 1,
            "total_epochs": 5,
            "loss_curve": [{"epoch": 1, "train_loss": 0.5, "valid_loss": 0.55}],
            "logs": ["epoch 1/5"],
        },
    )


def _run_app(path: str = APP) -> AppTest:
    app = AppTest.from_file(path, default_timeout=TIMEOUT)
    app.run()
    assert not app.exception, app.exception
    return app


def _verdict_shown(app: AppTest) -> bool:
    """True if a BLOCK verdict is rendered anywhere on the page."""
    return any("BLOCK" in str(el.value) for el in app.error)


def _submit_payload(app: AppTest) -> AppTest:
    """Choose a non-empty sample payload and click 'Run WITH model'."""
    app.selectbox(key="sqli.w.test.single.sample").select(PAYLOAD_SAMPLE).run()
    app.button(key="sqli.w.test.single.protected").click().run()
    assert not app.exception, app.exception
    return app


@pytest.mark.parametrize("page", [APP, MONITOR, DATA, TRAIN, METRICS])
def test_page_renders_without_exception(page: str) -> None:
    _run_app(page)


def test_run_with_model_shows_verdict() -> None:
    app = _submit_payload(_run_app())
    assert _verdict_shown(app)


def test_result_survives_unrelated_interaction() -> None:
    """A verdict must not vanish when an unrelated widget triggers a re-run."""
    app = _submit_payload(_run_app())
    assert _verdict_shown(app), "verdict missing right after the click"

    # Interact with something unrelated — this re-runs the whole script and the
    # button now reports False.
    app.selectbox(key="sqli.w.test.single.sample").select("Comment terminator").run()
    assert not app.exception, app.exception
    assert _verdict_shown(app), "verdict disappeared after an unrelated re-run"


def test_button_scoped_rendering_loses_the_result() -> None:
    """Documents the failure mode the state layer exists to prevent.

    Rendering inside ``if st.button(...)`` works only for the run triggered by
    that click; the next interaction re-runs the script with the button back to
    False and the output gone. This is why results go through ``app.state``.
    """
    app = AppTest.from_string(
        "import streamlit as st\n"
        "st.selectbox('s', ['a', 'b'], key='sel')\n"
        "if st.button('run', key='btn'):\n"
        "    st.error('BLOCK verdict')\n"
    )
    app.run()
    app.button(key="btn").click().run()
    assert any("BLOCK" in str(el.value) for el in app.error)

    app.selectbox(key="sel").select("b").run()
    assert not any("BLOCK" in str(el.value) for el in app.error), (
        "expected the naive pattern to lose its output on re-run"
    )


def test_empty_input_warns_instead_of_calling_backend() -> None:
    app = _run_app()
    # The default sample is "(type your own)" → empty query.
    app.button(key="sqli.w.test.single.protected").click().run()
    assert any("Enter an input value" in str(el.value) for el in app.warning)
    assert not _verdict_shown(app)


def test_train_start_creates_job_in_state() -> None:
    app = _run_app(TRAIN)
    app.button(key="sqli.w.train.branch1.start").click().run()
    assert not app.exception, app.exception

    job = app.session_state["sqli.train.branch1.job"]
    assert job.job_id == "job_x"
    assert job.total_epochs == 5
    assert job.finished is False
    # Other tasks must not have been started.
    assert "sqli.train.branch2.job" not in app.session_state


def test_data_annotation_feedback_is_show_once() -> None:
    app = _run_app(DATA)
    app.button(key="sqli.w.data.branch1.save.u1").click().run()
    assert not app.exception, app.exception
    assert any("Accepted" in str(el.value) for el in app.info)

    # Feedback is consumed on render: an unrelated re-run must not repeat it.
    app.run()
    assert not any("Accepted" in str(el.value) for el in app.info)


def test_data_pagination_offset_advances() -> None:
    app = _run_app(DATA)
    app.button(key="sqli.w.data.branch1.next").click().run()
    assert not app.exception, app.exception
    assert app.session_state["sqli.data.branch1.offset"] == 20
