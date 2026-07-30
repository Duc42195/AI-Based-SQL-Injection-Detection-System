from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from src.models.branch3_session import (
    SessionDataset,
    SessionSequenceDetector,
    collate_fn,
    eval_epoch,
)
from src.utils import load_config


def _load_npy(data_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    X = np.load(data_dir / "test_features.npy")
    y = np.load(data_dir / "test_labels.npy")
    return X, y


@pytest.fixture
def cfg():
    return load_config()


@pytest.fixture
def data_dir(cfg):
    proc_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    return proc_dir / "branch3_session_features"


class TestCandidateData:
    def test_feature_shape(self, data_dir):
        X, y = _load_npy(data_dir)
        assert X.ndim == 3
        assert X.shape[0] == y.shape[0]
        assert X.shape[2] == 7

    def test_labels_balanced(self, data_dir):
        _, y = _load_npy(data_dir)
        counts = np.bincount(y)
        assert len(counts) == 4
        assert all(c == 500 for c in counts)

    def test_b1_probs_sum_to_one(self, data_dir):
        X, _ = _load_npy(data_dir)
        b1_sum = X[:, :, :5].sum(axis=2)
        present = b1_sum > 1e-6
        assert present.any()
        assert np.allclose(b1_sum[present], 1.0, atol=0.01)


class TestCandidateInference:
    def test_tfidf_logreg_default_backbone(self, cfg):
        backbone = cfg.get_path("branch3_session.b1_backbone", "tfidf_logreg")
        assert backbone == "tfidf_logreg"

    def test_model_loads_for_all_backbones(self, cfg):
        model_dir = Path(cfg.get_path("paths.models_dir", "models"))
        backbones = ["branch3_v2"]
        for v in backbones:
            p = model_dir / v
            assert (p / "metadata.json").exists(), f"Missing {v}/metadata.json"

    def test_session_dataset_gives_consistent_output(self, data_dir):
        X1, y1 = _load_npy(data_dir)
        X2, y2 = _load_npy(data_dir)
        assert np.array_equal(X1, X2)
        assert np.array_equal(y1, y2)


class TestCandidateMetrics:
    def test_metrics_json_exists(self):
        BASE = Path.cwd()
        p = BASE / "report/metrics/branch3_train.json"
        assert p.exists(), f"Missing {p}"

    def test_metrics_contains_f1(self):
        BASE = Path.cwd()
        p = BASE / "report/metrics/branch3_train.json"
        with open(p) as f:
            m = json.load(f)
        assert "test_acc" in m
        assert "history" in m
        assert "train_loss" in m["history"]

    def test_confusion_json_exists(self):
        BASE = Path.cwd()
        p = BASE / "report/metrics/branch3_confusion.json"
        assert p.exists(), f"Missing {p}"

    def test_confusion_has_all_classes(self):
        BASE = Path.cwd()
        p = BASE / "report/metrics/branch3_confusion.json"
        with open(p) as f:
            cm = json.load(f)
        assert len(cm["class_names"]) == 4
        assert cm["f1_macro"] == 1.0

    def test_candidate_comparison_placeholder(self):
        """Placeholder: when distilbert/cnn_sqltok are integrated, expand this."""
        pass
