"""Unit tests for Branch 3 / Session Correlator.

``TestSessionSequenceDetector*`` below test the SUPERSEDED GRU (kept for the
record, see src/models/branch3_session.py's module docstring). The active
mechanism, ``SessionCorrelator``, is tested in ``TestSessionCorrelator*``.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.models.branch3_session import SessionCorrelator, SessionSequenceDetector

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


class _FakeVectorizer:
    """Fake TF-IDF vectorizer: 1 feature, 1.0 if the text contains 'attack'."""

    def transform(self, texts: list[str]) -> np.ndarray:
        return np.array([[1.0] if "attack" in t else [0.0] for t in texts])


class _FakeClf:
    """Fake Branch-1 classifier: 'attack' -> mostly boolean_blind (id 3)."""

    classes_ = np.array([0, 1, 2, 3, 4])

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        out = np.zeros((len(X), 5))
        for i, x in enumerate(X):
            out[i] = [0.1, 0.05, 0.05, 0.75, 0.05] if x[0] > 0 else [0.9, 0.025, 0.025, 0.025, 0.025]
        return out


class _FakeB2Detector:
    """Fake AnomalyDetector: score = length feature (column 0), unscaled."""

    def score(self, X: np.ndarray) -> np.ndarray:
        return X[:, 0]


def _make_correlator(**overrides) -> SessionCorrelator:
    defaults = dict(
        b1_vectorizer=_FakeVectorizer(), b1_clf=_FakeClf(), b2_detector=_FakeB2Detector(),
        content_threshold=0.5, per_query_threshold=50.0, mean_threshold=50.0, fraction_threshold=0.5,
    )
    defaults.update(overrides)
    return SessionCorrelator(**defaults)


class TestSessionCorrelatorScore:
    def test_fires_content_when_concatenated_text_scores_high(self) -> None:
        correlator = _make_correlator()
        result = correlator.score(["select 1", "attack payload"], branch2_scores=[0.0, 0.0])
        assert result["fires_content"] is True
        assert result["fires_behavior"] is False
        assert result["is_attack"] is True
        assert result["predicted_label"] == "boolean_blind"

    def test_predicted_label_uses_branch1_schema_not_session_schema(self) -> None:
        """Regression test: Branch-1 id 3 = boolean_blind, but the SESSION-level
        schema's id 3 = query_splitting — same integer, different meaning.
        An earlier version of this class indexed into the wrong one and
        silently mislabeled every content-check hit (found via the live API,
        not by inspection)."""
        correlator = _make_correlator()
        result = correlator.score(["attack payload"], branch2_scores=[0.0])
        assert result["predicted_label"] == "boolean_blind"
        assert result["predicted_label"] != "query_splitting"

    def test_fires_behavior_when_b2_scores_elevated(self) -> None:
        correlator = _make_correlator()
        result = correlator.score(["select 1", "select 2"], branch2_scores=[100.0, 100.0])
        assert result["fires_content"] is False
        assert result["fires_behavior"] is True
        assert result["is_attack"] is True
        assert result["predicted_label"] == "anomalous_session"

    def test_benign_when_neither_check_fires(self) -> None:
        correlator = _make_correlator()
        result = correlator.score(["select 1", "select 2"], branch2_scores=[0.0, 0.0])
        assert result["is_attack"] is False
        assert result["predicted_label"] == "benign"

    def test_computes_branch2_scores_internally_when_not_provided(self) -> None:
        correlator = _make_correlator(per_query_threshold=1.0, mean_threshold=1.0)
        # No branch2_scores passed — must fall back to self.b2_detector via
        # branch2_scores_for_texts (real extract_statistical_features, so a
        # long text produces a large "length" feature -> fires behavior).
        result = correlator.score(["x" * 500])
        assert result["fires_behavior"] is True


class TestSessionCorrelatorCalibrate:
    def test_calibrate_separates_benign_from_attack(self) -> None:
        correlator = _make_correlator(per_query_threshold=0.0, mean_threshold=0.0, fraction_threshold=0.0)
        train_sessions = [
            (["select 1", "select 2"], [1.0, 1.1], 0),
            (["select 3", "select 4"], [0.9, 1.0], 0),
            (["p1", "p2", "p3"], [9.0, 9.5, 9.2], 1),
            (["p4", "p5", "p6"], [8.8, 9.1, 9.4], 2),
        ]
        correlator.calibrate(train_sessions, percentile=0.90)
        # per_query_threshold = P90 of benign per-query scores [1.0,1.1,0.9,1.0] -> within their range.
        assert 0.9 <= correlator.per_query_threshold <= 1.1
        # mean_threshold must separate benign session means (~0.95, 1.05) from
        # attack session means (~9.23, 9.43).
        assert 1.05 < correlator.mean_threshold < 9.23


class TestSessionCorrelatorSaveLoad:
    def test_roundtrip_thresholds_and_scoring_match(self, tmp_path) -> None:
        correlator = _make_correlator(per_query_threshold=1.0, mean_threshold=2.0, fraction_threshold=0.3)
        before = correlator.score(["attack payload", "select 1"], branch2_scores=[0.5, 0.5])

        correlator.save(tmp_path)
        loaded = SessionCorrelator.load(tmp_path, _FakeVectorizer(), _FakeClf(), _FakeB2Detector())
        after = loaded.score(["attack payload", "select 1"], branch2_scores=[0.5, 0.5])

        assert loaded.content_threshold == correlator.content_threshold
        assert loaded.per_query_threshold == correlator.per_query_threshold
        assert loaded.mean_threshold == correlator.mean_threshold
        assert loaded.fraction_threshold == correlator.fraction_threshold
        assert before == after

    def test_creates_expected_files(self, tmp_path) -> None:
        correlator = _make_correlator()
        correlator.save(tmp_path)
        assert (tmp_path / "metadata.json").exists()
        assert not (tmp_path / "model.pt").exists()  # no weights — not a trained model


_REAL_ARTIFACTS = [
    "models/branch1_v1/vectorizer.joblib",
    "models/branch2_v1/model.joblib",
    "models/branch3_v2/metadata.json",
    "data/processed/branch3_sessions_cach_a.csv",
]


def _real_artifacts_present() -> bool:
    from pathlib import Path

    return all(Path(p).exists() for p in _REAL_ARTIFACTS)


@pytest.mark.skipif(not _real_artifacts_present(), reason="real branch1/branch2/branch3 artifacts not present locally")
class TestSessionCorrelatorBehaviorCoversContentGap:
    """Regression test for a real finding from this project's diagnostic session:

    a session's WEAK-per-content-check steps alone (a boolean_blind session's
    length-bisection phase — no strong character-extraction steps mixed in)
    do NOT push the content check over threshold even when concatenated
    together, but ARE caught by the behavior check alone — this is why the
    two checks are OR'd rather than relying on either in isolation. See the
    module docstring and report/plan/data_contract.md SS4.2 for the full
    account. If this test starts failing, the "OR'd checks cover each
    other's blind spot" claim in the paper's Limitations no longer holds and
    must be re-verified before citing it.
    """

    def test_weak_content_steps_still_fire_behavior_check(self) -> None:
        import joblib
        import pandas as pd

        from src.models.branch2_anomaly import AnomalyDetector

        vectorizer = joblib.load("models/branch1_v1/vectorizer.joblib")
        clf = joblib.load("models/branch1_v1/model.joblib")
        b2_detector = AnomalyDetector.load("models/branch2_v1")
        correlator = SessionCorrelator.load("models/branch3_v2", vectorizer, clf, b2_detector)

        df = pd.read_csv("data/processed/branch3_sessions_cach_a.csv")
        sess = df[(df["session_label"] == 1) & (df["split"] == "test")].sort_values(["session_id", "step_index"])
        sid = sess["session_id"].iloc[0]
        texts = sess.loc[sess["session_id"] == sid, "query_canonical"].tolist()
        b2_scores = sess.loc[sess["session_id"] == sid, "branch2_anomaly_score"].tolist()

        # First 5 steps = the length-bisection phase, each individually below
        # Branch 1's 0.5 threshold (measured 0.44-0.47 per-step).
        weak_texts, weak_scores = texts[:5], b2_scores[:5]

        content_only = correlator.score(weak_texts, branch2_scores=[-999.0] * 5)  # force behavior off
        assert content_only["fires_content"] is False, (
            "precondition: concatenating only the weak steps should NOT cross "
            "the content threshold on its own"
        )

        combined = correlator.score(weak_texts, branch2_scores=weak_scores)
        assert combined["fires_behavior"] is True
        assert combined["is_attack"] is True
