"""Tests for the FastAPI service (contract + Branch-1 inference)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from deploy.main import app

client = TestClient(app)


def _branch1_ready() -> bool:
    return client.get("/health").json()["branches"]["branch1"] == "ready"


def _branch2_ready() -> bool:
    return client.get("/health").json()["branches"]["branch2"] == "ready"


def _branch3_ready() -> bool:
    return client.get("/health").json()["branches"]["branch3"] == "ready"


def test_health_lists_all_branches() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert set(body["branches"]) == {"branch1", "branch2", "branch3"}


def test_predict_benign_query() -> None:
    if not _branch1_ready():
        pytest.skip("Branch-1 model not trained in this environment")
    resp = client.post(
        "/api/v1/branch1/predict", json={"query": "SELECT name FROM users WHERE id = 1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["is_sqli"] is False
    assert body["label_name"] == "normal"


def test_predict_sqli_query() -> None:
    if not _branch1_ready():
        pytest.skip("Branch-1 model not trained in this environment")
    resp = client.post(
        "/api/v1/branch1/predict",
        json={"query": "1' OR '1'='1' UNION SELECT username, password FROM users --"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["is_sqli"] is True
    assert body["label_name"] != "normal"


def test_predict_missing_query_is_422() -> None:
    resp = client.post("/api/v1/branch1/predict", json={})
    assert resp.status_code == 422


def test_branch2_scores_anomaly() -> None:
    resp = client.post("/api/v1/branch2/score", json={"query": "SELECT 1"})
    assert resp.status_code == 200
    body = resp.json()
    if not _branch2_ready():
        assert body["status"] == "not_ready"
        return
    assert body["status"] == "ready"
    assert isinstance(body["anomaly_score"], float)
    assert isinstance(body["is_anomaly"], bool)


def test_branch3_session_correlator() -> None:
    r3 = client.post("/api/v1/branch3/session", json={"queries": ["a", "b"]})
    assert r3.status_code == 200
    body = r3.json()
    if not _branch3_ready():
        assert body["status"] == "not_ready"
        return
    assert body["status"] == "ready"
    assert isinstance(body["is_attack"], bool)
    assert isinstance(body["session_label"], str)


def test_detect_returns_all_branches_and_decision() -> None:
    resp = client.post("/api/v1/detect", json={"query": "SELECT 1"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) >= {"branch1", "branch2", "branch3", "decision"}
    assert body["decision"]["action"] in {"BLOCK", "OVERKILL", "ALLOW", "UNKNOWN"}
    assert "reason" in body["decision"]


def test_detect_blocks_obvious_sqli() -> None:
    if not _branch1_ready():
        pytest.skip("Branch-1 model not trained in this environment")
    resp = client.post(
        "/api/v1/detect",
        json={"query": "admin' OR 1=1 UNION SELECT password FROM users --"},
    )
    assert resp.json()["decision"]["action"] == "BLOCK"


@pytest.mark.parametrize("task", ["branch1", "branch2", "branch3"])
def test_metrics_endpoint_responds(task: str) -> None:
    resp = client.get(f"/api/v1/metrics/{task}")
    assert resp.status_code == 200
    assert resp.json()["status"] in {"ready", "not_ready"}


def test_metrics_unknown_task_404() -> None:
    assert client.get("/api/v1/metrics/nope").status_code == 404


def test_admin_overkill_queue_stub() -> None:
    resp = client.get("/api/v1/admin/overkill-queue")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0

    action = client.post("/api/v1/admin/overkill/abc/confirm")
    assert action.status_code == 200
    body = action.json()
    assert body["ok"] is True and body["persisted"] is False


# --------------------------------------------------------------------------- #
# Test page — demo DB
# --------------------------------------------------------------------------- #
def test_demo_database_table() -> None:
    resp = client.get("/api/v1/demo/database")
    assert resp.status_code == 200
    body = resp.json()
    assert body["table"] == "users"
    assert body["row_count"] == len(body["rows"]) > 0


def test_demo_execute_no_model_leaks() -> None:
    resp = client.post(
        "/api/v1/demo/execute", json={"inputs": ["' OR '1'='1"], "protected": False}
    )
    assert resp.status_code == 200
    step = resp.json()["results"][0]
    assert step["executed"] is True
    assert step["leaked"] is True  # injection dumped the whole table
    assert step["row_count"] > 1


def test_demo_execute_with_model_blocks() -> None:
    if not _branch1_ready():
        pytest.skip("Branch-1 model not trained in this environment")
    resp = client.post(
        "/api/v1/demo/execute", json={"inputs": ["' OR '1'='1"], "protected": True}
    )
    body = resp.json()
    assert body["decision"]["action"] == "BLOCK"
    assert body["results"][0]["executed"] is False


def test_demo_execute_benign_username_is_single_row() -> None:
    resp = client.post(
        "/api/v1/demo/execute", json={"inputs": ["admin"], "protected": False}
    )
    step = resp.json()["results"][0]
    assert step["row_count"] == 1
    assert step["leaked"] is False


# --------------------------------------------------------------------------- #
# Monitor
# --------------------------------------------------------------------------- #
def test_monitor_drift_shape() -> None:
    """Drift is real now, so it may legitimately be absent until a replay runs."""
    resp = client.get("/api/v1/monitor/drift/branch1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["task"] == "branch1"
    assert isinstance(body["alert"], bool)
    if body["status"] == "not_ready":
        assert body["points"] == []
        assert body["detail"]
    else:
        assert len(body["points"]) > 0
        assert body["signals"]
        # Every window carries each signal, which is what lets the UI show that
        # some signals move while others stay flat.
        assert set(body["points"][0]["psi"]) == set(body["signals"])


def test_monitor_drift_is_not_ready_for_unwired_branches() -> None:
    body = client.get("/api/v1/monitor/drift/branch2").json()
    assert body["status"] == "not_ready"
    assert body["points"] == []


def test_monitor_unknown_task_404() -> None:
    assert client.get("/api/v1/monitor/drift/nhanhX").status_code == 404


def test_monitor_retrain_is_declined_for_unwired_branches() -> None:
    """Branch 2/3 have no training path yet — say so rather than pretend."""
    r = client.post("/api/v1/monitor/retrain/branch2")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["status"] == "not_ready"


def test_monitor_logs_always_respond() -> None:
    logs = client.get("/api/v1/monitor/logs/branch3")
    assert logs.status_code == 200 and len(logs.json()["lines"]) > 0


# --------------------------------------------------------------------------- #
# Data — annotation
# --------------------------------------------------------------------------- #
def test_data_unannotated_lists_options() -> None:
    resp = client.get("/api/v1/data/branch1/unannotated")
    assert resp.status_code == 200
    body = resp.json()
    assert "normal" in body["label_options"]
    assert body["count"] >= len(body["items"])


@pytest.fixture()
def isolated_queue(tmp_path, monkeypatch):
    """Point the data router at a throwaway queue and ledger.

    These endpoints write to real storage, so tests must never use the
    configured paths.
    """
    from deploy.routers import data as data_router
    from src.decision.queue import ReviewItem, ReviewQueue

    queue = ReviewQueue(tmp_path / "queue.db")
    ledger = tmp_path / "confirmed.jsonl"
    queue.enqueue(
        [
            ReviewItem(
                id="q1",
                query_raw="1' OR 1=1--",
                query_canonical="1' or 1=1--",
                source="low_confidence",
                ai_label="union_based",
                ai_confidence=0.55,
                round_id="test",
            )
        ]
    )
    monkeypatch.setattr(data_router, "open_queue", lambda cfg=None: queue)
    monkeypatch.setattr(data_router, "confirmed_labels_path", lambda cfg=None: ledger)
    return queue


def test_unannotated_items_carry_the_ai_prelabel(isolated_queue) -> None:
    body = client.get("/api/v1/data/branch1/unannotated").json()
    assert body["count"] == 1
    item = body["items"][0]
    assert item["ai_label"] == "union_based"
    assert item["ai_confidence"] == pytest.approx(0.55)


def test_approve_accepts_the_prelabel(isolated_queue) -> None:
    body = client.post(
        "/api/v1/data/branch1/annotate", json={"id": "q1", "action": "approve"}
    ).json()
    assert body["ok"] is True
    assert body["label"] == "union_based"
    assert body["was_corrected"] is False
    assert body["persisted"] is True
    # It leaves the pending queue.
    assert client.get("/api/v1/data/branch1/unannotated").json()["count"] == 0


def test_correct_records_a_different_label(isolated_queue) -> None:
    body = client.post(
        "/api/v1/data/branch1/annotate",
        json={"id": "q1", "action": "correct", "label": "boolean_blind"},
    ).json()
    assert body["label"] == "boolean_blind"
    assert body["was_corrected"] is True


def test_annotate_rejects_an_unknown_label(isolated_queue) -> None:
    bad = client.post(
        "/api/v1/data/branch1/annotate",
        json={"id": "q1", "action": "correct", "label": "not_a_label"},
    )
    assert bad.status_code == 422


def test_annotate_unknown_item_is_404(isolated_queue) -> None:
    missing = client.post(
        "/api/v1/data/branch1/annotate", json={"id": "nope", "action": "approve"}
    )
    assert missing.status_code == 404


def test_confirmed_labels_are_listed(isolated_queue) -> None:
    client.post("/api/v1/data/branch1/annotate", json={"id": "q1", "action": "approve"})
    body = client.get("/api/v1/data/branch1/annotated").json()
    assert body["count"] == 1
    assert body["items"][0]["label"] == "union_based"


# --------------------------------------------------------------------------- #
# Train — simulated job
# --------------------------------------------------------------------------- #
def test_train_split_must_sum_to_100() -> None:
    resp = client.post(
        "/api/v1/train/branch1/start", json={"train": 70, "valid": 10, "test": 10}
    )
    assert resp.status_code == 422


def test_simulated_train_job_lifecycle() -> None:
    """Branch 2 still uses the simulator, so its full lifecycle is safe to run."""
    start = client.post(
        "/api/v1/train/branch2/start", json={"train": 70, "valid": 15, "test": 15}
    )
    assert start.status_code == 200
    assert start.json()["real"] is False
    job_id = start.json()["job_id"]

    status = client.get(f"/api/v1/train/branch2/status/{job_id}")
    assert status.status_code == 200
    assert status.json()["status"] in {"running", "done"}

    import time as _time

    for _ in range(80):
        s = client.get(f"/api/v1/train/branch2/status/{job_id}").json()
        if s["status"] == "done":
            break
        _time.sleep(0.2)
    body = client.get(f"/api/v1/train/branch2/result/{job_id}").json()
    assert body["status"] == "done"
    assert body["confusion_matrix"] is not None
    assert len(body["labels"]) == len(body["confusion_matrix"])


def test_branch1_training_is_real_and_reports_the_gate(monkeypatch) -> None:
    """Branch 1 trains for real; the trainer is stubbed so no state is written.

    Exercising the true trainer here would write models, seal versions and edit
    configs/config.yaml — tests must not mutate the repository.
    """
    from deploy.routers import train as train_router
    from src.continual_learning.gate import GateDecision, ModelEvaluation
    from src.continual_learning.trainer import TrainOutcome

    candidate = ModelEvaluation(
        model_version="branch1_v2_0",
        data_version="2.0",
        f1_macro=0.97,
        fpr=0.02,
        per_class_recall={"normal": 0.98},
    )
    monkeypatch.setattr(
        train_router,
        "train_and_seal",
        lambda: TrainOutcome(
            status="completed",
            run_id="deadbeef1234",
            model_version="branch1_v2_0",
            data_version="2.0",
            bump="major",
            metrics={"f1_macro": 0.97},
            duration_s=1.0,
        ),
    )
    monkeypatch.setattr(
        train_router, "evaluate_on_golden", lambda mv, dv, cfg=None: candidate
    )
    promoted: list[str] = []
    monkeypatch.setattr(
        train_router, "promote", lambda version, cfg=None: promoted.append(version)
    )
    # The decision log is a real repository file; capture instead of appending.
    recorded: list[GateDecision] = []
    monkeypatch.setattr(
        train_router, "append_decision", lambda decision, path: recorded.append(decision)
    )

    start = client.post(
        "/api/v1/train/branch1/start", json={"train": 70, "valid": 15, "test": 15}
    ).json()
    assert start["real"] is True

    import time as _time

    for _ in range(100):
        s = client.get(f"/api/v1/train/branch1/status/{start['job_id']}").json()
        if s["status"] != "running":
            break
        _time.sleep(0.1)

    body = client.get(f"/api/v1/train/branch1/result/{start['job_id']}").json()
    assert body["status"] == "done"
    assert body["real"] is True
    assert body["saved_version"] == "branch1_v2_0"
    assert body["data_version"] == "2.0"
    assert body["bump"] == "major"
    assert body["run_id"] == "deadbeef1234"
    # No champion evaluation differs -> the gate should have run and decided.
    assert body["decision"] is not None
    assert body["decision"]["verdict"] in {"promote", "direct_promote", "reject"}


def test_repeated_identical_run_is_reported_not_repeated(monkeypatch) -> None:
    """The run_id check is what makes Train idempotent."""
    from deploy.routers import train as train_router
    from src.continual_learning.trainer import TrainOutcome

    monkeypatch.setattr(
        train_router,
        "train_and_seal",
        lambda: TrainOutcome(
            status="exists",
            run_id="deadbeef1234",
            model_version="branch1_v2_0",
            data_version="2.0",
            detail="An identical run already completed.",
        ),
    )
    start = client.post(
        "/api/v1/train/branch1/start", json={"train": 70, "valid": 15, "test": 15}
    ).json()

    import time as _time

    for _ in range(100):
        s = client.get(f"/api/v1/train/branch1/status/{start['job_id']}").json()
        if s["status"] != "running":
            break
        _time.sleep(0.1)

    body = client.get(f"/api/v1/train/branch1/result/{start['job_id']}").json()
    assert body["run_status"] == "exists"
    assert "already completed" in (body["detail"] or "")


def test_train_unknown_job_404() -> None:
    assert client.get("/api/v1/train/branch1/status/nope").status_code == 404
