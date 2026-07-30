"""Tests for eval_branch3_hard.py — Phase 4 hard evaluation."""

from __future__ import annotations

import json
import numpy as np
import pytest

from train.eval_branch3_hard import (
    _classification_report,
    run_shuffle_test,
    run_ablation_verification,
    run_diversity_check,
    CLASS_NAMES,
)


class DummyModel:
    def predict(self, sequences):
        N = len(sequences)
        return np.zeros(N, dtype=np.int64), np.zeros((N, 4), dtype=np.float32)


def test_classification_report():
    y_true = np.array([0, 1, 2, 3, 0, 1, 2, 3])
    y_pred = np.array([0, 1, 2, 3, 0, 1, 2, 3])
    r = _classification_report(y_true, y_pred)
    assert r["accuracy"] == 1.0
    assert r["f1_macro"] == 1.0
    assert len(r["f1_per_class"]) == 4
    assert all(v == 1.0 for v in r["f1_per_class"].values())


def test_classification_report_zeros():
    y_true = np.zeros(10, dtype=np.int64)
    y_pred = np.ones(10, dtype=np.int64)
    r = _classification_report(y_true, y_pred)
    assert r["accuracy"] == 0.0


def test_shuffle_test_no_drop():
    model = DummyModel()
    rng = np.random.RandomState(42)
    X = rng.randn(10, 64, 7).astype(np.float32)
    y = rng.randint(0, 4, size=10)
    # Zero out padding
    for i in range(10):
        X[i, 10:] = 0.0

    result = run_shuffle_test(model, X, y, seed=42)
    assert "original_accuracy" in result
    assert "shuffled_accuracy" in result
    assert "f1_drop" in result
    # DummyModel returns all zeros → accuracy depends on y
    assert isinstance(result["passes"], bool)


def test_shuffle_test_shapes():
    """Basic shape/type check."""
    model = DummyModel()
    X = np.zeros((5, 64, 7), dtype=np.float32)
    y = np.array([0, 1, 2, 3, 0], dtype=np.int64)
    result = run_shuffle_test(model, X, y, seed=0)
    assert isinstance(result["original_accuracy"], float)
    assert isinstance(result["f1_drop"], float)


def test_ablation_verification(tmp_path):
    data = {
        "configs": ["Full(7d)", "Drop B2", "Only Gap", "Shuffled"],
        "test_accs": [1.0, 1.0, 0.5, 0.3],
    }
    fpath = tmp_path / "branch3_ablation.json"
    with fpath.open("w") as f:
        json.dump(data, f)

    result = run_ablation_verification(tmp_path)
    assert result["drop_gap_passes"] is True   # 0.5 < 0.99
    assert result["drop_b2_passes"] is True     # 1.0 >= 0.99
    assert result["shuffle_passes"] is True      # 0.3 < 0.5


def test_ablation_verification_missing(tmp_path):
    result = run_ablation_verification(tmp_path)
    assert "error" in result
    assert result["passes"] is False


def test_ablation_verification_thresholds(tmp_path):
    """Edge: exactly on threshold boundary."""
    data = {
        "configs": ["Only Gap", "Drop B2", "Shuffled"],
        "test_accs": [0.99, 0.989, 0.5],
    }
    fpath = tmp_path / "branch3_ablation.json"
    with fpath.open("w") as f:
        json.dump(data, f)
    result = run_ablation_verification(tmp_path)
    # 0.99 >= 0.99 → NOT less → Only Gap fails (passes=False means it failed the drop_gap check)
    assert result["drop_gap_passes"] is False
    # 0.989 < 0.99 → Drop B2 fails (not >= 0.99)
    assert result["drop_b2_passes"] is False
    # 0.5 is not < 0.5 → Shuffled fails
    assert result["shuffle_passes"] is False


def test_diversity_check(tmp_path):
    # Create a minimal CSV
    import pandas as pd
    rows = []
    for sid in range(10):
        for step in range(5):
            rows.append({"session_id": sid, "step_idx": step, "query": "test", "session_label": 1, "class": "boolean_blind", "row_count": 1, "timing_seconds": 0.01})
    df = pd.DataFrame(rows)

    sub = tmp_path / "boolean_blind_train.csv"
    df.to_csv(sub, index=False)

    result = run_diversity_check(tmp_path)
    assert "boolean_blind" in result
    assert result["boolean_blind"]["total_sessions"] == 10
    assert result["boolean_blind"]["diversity_ratio"] == 1.0


def test_diversity_check_missing(tmp_path):
    result = run_diversity_check(tmp_path)
    assert result == {}  # no matching CSVs found
