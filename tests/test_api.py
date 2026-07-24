"""Tests for the FastAPI service (contract + Branch-1 inference)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from deploy.main import app

client = TestClient(app)


def _nhanh1_ready() -> bool:
    return client.get("/health").json()["branches"]["nhanh1"] == "ready"


def test_health_lists_all_branches() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert set(body["branches"]) == {"nhanh1", "nhanh2", "nhanh3"}


def test_predict_benign_query() -> None:
    if not _nhanh1_ready():
        pytest.skip("Branch-1 model not trained in this environment")
    resp = client.post(
        "/api/v1/nhanh1/predict", json={"query": "SELECT name FROM users WHERE id = 1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["is_sqli"] is False
    assert body["label_name"] == "normal"


def test_predict_sqli_query() -> None:
    if not _nhanh1_ready():
        pytest.skip("Branch-1 model not trained in this environment")
    resp = client.post(
        "/api/v1/nhanh1/predict",
        json={"query": "1' OR '1'='1' UNION SELECT username, password FROM users --"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["is_sqli"] is True
    assert body["label_name"] != "normal"


def test_predict_missing_query_is_422() -> None:
    resp = client.post("/api/v1/nhanh1/predict", json={})
    assert resp.status_code == 422


def test_nhanh2_and_nhanh3_are_not_ready_stubs() -> None:
    r2 = client.post("/api/v1/nhanh2/score", json={"query": "anything"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "not_ready"

    r3 = client.post("/api/v1/nhanh3/session", json={"queries": ["a", "b"]})
    assert r3.status_code == 200
    assert r3.json()["status"] == "not_ready"


def test_detect_returns_all_branches_and_decision() -> None:
    resp = client.post("/api/v1/detect", json={"query": "SELECT 1"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) >= {"nhanh1", "nhanh2", "nhanh3", "decision"}
    assert body["decision"]["action"] in {"BLOCK", "OVERKILL", "ALLOW", "UNKNOWN"}
    assert "reason" in body["decision"]


def test_detect_blocks_obvious_sqli() -> None:
    if not _nhanh1_ready():
        pytest.skip("Branch-1 model not trained in this environment")
    resp = client.post(
        "/api/v1/detect",
        json={"query": "admin' OR 1=1 UNION SELECT password FROM users --"},
    )
    assert resp.json()["decision"]["action"] == "BLOCK"


def test_metrics_endpoint_responds() -> None:
    resp = client.get("/api/v1/metrics/nhanh1")
    assert resp.status_code == 200
    assert resp.json()["status"] in {"ready", "not_ready"}


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
    if not _nhanh1_ready():
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
    resp = client.get("/api/v1/monitor/drift/nhanh1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["task"] == "nhanh1"
    assert len(body["points"]) > 0
    assert isinstance(body["alert"], bool)


def test_monitor_unknown_task_404() -> None:
    assert client.get("/api/v1/monitor/drift/nhanhX").status_code == 404


def test_monitor_retrain_and_logs() -> None:
    r = client.post("/api/v1/monitor/retrain/nhanh2")
    assert r.status_code == 200 and r.json()["ok"] is True
    logs = client.get("/api/v1/monitor/logs/nhanh3")
    assert logs.status_code == 200 and len(logs.json()["lines"]) > 0


# --------------------------------------------------------------------------- #
# Data — annotation
# --------------------------------------------------------------------------- #
def test_data_unannotated_lists_options() -> None:
    resp = client.get("/api/v1/data/nhanh1/unannotated")
    assert resp.status_code == 200
    body = resp.json()
    assert "normal" in body["label_options"]
    assert body["count"] >= len(body["items"])


def test_data_annotate_validates_label() -> None:
    ok = client.post(
        "/api/v1/data/nhanh1/annotate",
        json={"id": "u_n1_001", "label": "union_based"},
    )
    assert ok.status_code == 200 and ok.json()["ok"] is True

    bad = client.post(
        "/api/v1/data/nhanh1/annotate",
        json={"id": "u_n1_001", "label": "not_a_label"},
    )
    assert bad.status_code == 422


# --------------------------------------------------------------------------- #
# Train — simulated job
# --------------------------------------------------------------------------- #
def test_train_split_must_sum_to_100() -> None:
    resp = client.post(
        "/api/v1/train/nhanh1/start", json={"train": 70, "valid": 10, "test": 10}
    )
    assert resp.status_code == 422


def test_train_job_lifecycle() -> None:
    start = client.post(
        "/api/v1/train/nhanh1/start", json={"train": 70, "valid": 15, "test": 15}
    )
    assert start.status_code == 200
    job_id = start.json()["job_id"]

    status = client.get(f"/api/v1/train/nhanh1/status/{job_id}")
    assert status.status_code == 200
    assert status.json()["status"] in {"running", "done"}

    # Wait for the simulated job to finish, then fetch the result.
    import time as _time

    for _ in range(80):
        s = client.get(f"/api/v1/train/nhanh1/status/{job_id}").json()
        if s["status"] == "done":
            break
        _time.sleep(0.2)
    result = client.get(f"/api/v1/train/nhanh1/result/{job_id}")
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "done"
    assert body["confusion_matrix"] is not None
    assert body["metrics"]["f1_macro"] >= 0.0
    assert len(body["labels"]) == len(body["confusion_matrix"])


def test_train_unknown_job_404() -> None:
    assert client.get("/api/v1/train/nhanh1/status/nope").status_code == 404
