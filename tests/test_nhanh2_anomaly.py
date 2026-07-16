"""Unit tests for Branch 2 anomaly detection model."""

from __future__ import annotations

import numpy as np
import pytest

from src.models.nhanh2_anomaly import AnomalyDetector


@pytest.fixture
def benign_features() -> np.ndarray:
    rng = np.random.RandomState(42)
    return rng.rand(200, 4) * np.array([100, 1, 5, 4])  # length, ratio, kw_count, entropy


@pytest.fixture
def anomalous_features() -> np.ndarray:
    rng = np.random.RandomState(99)
    return rng.rand(50, 4) * np.array([500, 0.8, 15, 6]) + np.array([100, 0.2, 5, 1])


class TestIsolationForest:
    def test_fit_and_predict_shape(self, benign_features: np.ndarray) -> None:
        det = AnomalyDetector(algorithm="isolation_forest", contamination=0.05, random_seed=42)
        det.fit(benign_features)
        preds = det.predict(benign_features)
        assert preds.shape == (200,)
        assert set(preds.tolist()).issubset({-1, 1})

    def test_score_higher_for_anomalies(self, benign_features: np.ndarray, anomalous_features: np.ndarray) -> None:
        det = AnomalyDetector(algorithm="isolation_forest", contamination=0.05, random_seed=42)
        X = np.vstack([benign_features, anomalous_features])
        det.fit(X)

        benign_scores = det.score(benign_features)
        anom_scores = det.score(anomalous_features)

        assert anom_scores.mean() > benign_scores.mean()

    def test_anomaly_flags_returns_0_or_1(self, benign_features: np.ndarray) -> None:
        det = AnomalyDetector(algorithm="isolation_forest", contamination=0.05, random_seed=42)
        det.fit(benign_features)
        flags = det.anomaly_flags(benign_features)
        assert flags.shape == (200,)
        assert set(flags.tolist()).issubset({0, 1})


class TestOneClassSVM:
    def test_fit_and_predict_shape(self, benign_features: np.ndarray) -> None:
        det = AnomalyDetector(algorithm="one_class_svm", contamination=0.05, random_seed=42)
        det.fit(benign_features)
        preds = det.predict(benign_features)
        assert preds.shape == (200,)
        assert set(preds.tolist()).issubset({-1, 1})

    def test_score_returns_float_array(self, benign_features: np.ndarray) -> None:
        det = AnomalyDetector(algorithm="one_class_svm", contamination=0.05, random_seed=42)
        det.fit(benign_features)
        scores = det.score(benign_features)
        assert scores.shape == (200,)
        assert scores.dtype in (np.float64, np.float32)


class TestSaveLoad:
    def test_roundtrip(self, benign_features: np.ndarray, tmp_path) -> None:
        det = AnomalyDetector(algorithm="isolation_forest", contamination=0.05, random_seed=42)
        det.fit(benign_features)
        scores_before = det.score(benign_features)

        det.save(tmp_path)
        loaded = AnomalyDetector.load(tmp_path)
        scores_after = loaded.score(benign_features)

        assert np.allclose(scores_before, scores_after)

    def test_metadata_preserved(self, benign_features: np.ndarray, tmp_path) -> None:
        det = AnomalyDetector(algorithm="one_class_svm", contamination=0.1, random_seed=7)
        det.fit(benign_features)
        det.save(tmp_path)

        loaded = AnomalyDetector.load(tmp_path)
        assert loaded.algorithm == "one_class_svm"
        assert loaded.contamination == 0.1
        assert loaded.random_seed == 7


class TestInvalidAlgorithm:
    def test_raises_on_unknown_algorithm(self) -> None:
        with pytest.raises(ValueError, match=r".*Unknown algorithm.*"):
            AnomalyDetector(algorithm="invalid_algo")  # type: ignore[arg-type]
