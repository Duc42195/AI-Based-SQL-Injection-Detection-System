"""Unit tests for the Branch 3 session sequence model."""

from __future__ import annotations

import numpy as np
import pytest

from src.models.branch3_session import SessionSequenceDetector

CLASS_NAMES = ["benign", "boolean_blind", "time_blind", "query_splitting"]


@pytest.fixture
def sessions() -> tuple[list[np.ndarray], np.ndarray]:
    """20 synthetic sessions of varying length, 4 balanced classes."""
    rng = np.random.RandomState(42)
    X = [rng.rand(rng.randint(2, 8), 6).astype(np.float32) for _ in range(20)]
    y = np.array([i % 4 for i in range(20)])
    return X, y


class TestFitPredict:
    def test_predict_shape_and_range(self, sessions: tuple[list[np.ndarray], np.ndarray]) -> None:
        X, y = sessions
        det = SessionSequenceDetector(input_dim=6, hidden_dim=8, num_classes=4, class_names=CLASS_NAMES)
        det.fit(X, y, epochs=2, batch_size=4)

        preds = det.predict(X)
        assert preds.shape == (20,)
        assert set(preds.tolist()).issubset({0, 1, 2, 3})

    def test_predict_proba_sums_to_one(self, sessions: tuple[list[np.ndarray], np.ndarray]) -> None:
        X, y = sessions
        det = SessionSequenceDetector(input_dim=6, hidden_dim=8, num_classes=4, class_names=CLASS_NAMES)
        det.fit(X, y, epochs=2, batch_size=4)

        probs = det.predict_proba(X)
        assert probs.shape == (20, 4)
        assert np.allclose(probs.sum(axis=1), 1.0, atol=1e-5)

    def test_fit_returns_loss_per_epoch(self, sessions: tuple[list[np.ndarray], np.ndarray]) -> None:
        X, y = sessions
        det = SessionSequenceDetector(input_dim=6, hidden_dim=8, num_classes=4)
        losses = det.fit(X, y, epochs=4, batch_size=4)
        assert len(losses) == 4
        assert all(isinstance(v, float) for v in losses)

    def test_handles_variable_length_and_single_step_sessions(self) -> None:
        # A length-1 session is a real edge case (e.g. a single-query "session").
        X = [
            np.zeros((1, 6), dtype=np.float32),
            np.ones((5, 6), dtype=np.float32),
            np.random.RandomState(1).rand(3, 6).astype(np.float32),
        ]
        y = np.array([0, 1, 2])
        det = SessionSequenceDetector(input_dim=6, hidden_dim=4, num_classes=3)
        det.fit(X, y, epochs=2, batch_size=2)
        preds = det.predict(X)
        assert preds.shape == (3,)

    def test_truncates_sequences_longer_than_max_len(self) -> None:
        det = SessionSequenceDetector(input_dim=6, hidden_dim=4, num_classes=2, max_len=5)
        X = [np.random.RandomState(2).rand(50, 6).astype(np.float32)]
        # Should not raise despite the sequence being far longer than max_len.
        probs = det.predict_proba(X)
        assert probs.shape == (1, 2)


class TestSaveLoad:
    def test_roundtrip_predictions_match(self, sessions: tuple[list[np.ndarray], np.ndarray], tmp_path) -> None:
        X, y = sessions
        det = SessionSequenceDetector(input_dim=6, hidden_dim=8, num_classes=4, class_names=CLASS_NAMES)
        det.fit(X, y, epochs=3, batch_size=4)
        preds_before = det.predict(X)

        det.save(tmp_path)
        loaded = SessionSequenceDetector.load(tmp_path)
        preds_after = loaded.predict(X)

        assert np.array_equal(preds_before, preds_after)

    def test_metadata_preserved(self, tmp_path) -> None:
        det = SessionSequenceDetector(
            input_dim=6, hidden_dim=12, num_classes=4, class_names=CLASS_NAMES, random_seed=7, max_len=32
        )
        det.save(tmp_path)

        loaded = SessionSequenceDetector.load(tmp_path)
        assert loaded.hidden_dim == 12
        assert loaded.class_names == CLASS_NAMES
        assert loaded.random_seed == 7
        assert loaded.max_len == 32

    def test_creates_expected_files(self, tmp_path) -> None:
        det = SessionSequenceDetector(input_dim=6, hidden_dim=4, num_classes=4)
        det.save(tmp_path)
        assert (tmp_path / "model.pt").exists()
        assert (tmp_path / "metadata.json").exists()
