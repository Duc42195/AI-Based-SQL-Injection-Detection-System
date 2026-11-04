"""Unit tests for Branch 3 / Session Correlator (`SessionCorrelator`).

The superseded GRU design (`SessionSequenceDetector`) and its tests were
removed once `SessionCorrelator` was validated and merged — see git history
or report/plan/data_contract.md §4.2 for the full write-up and original code.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.models.branch3_session import SessionCorrelator


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
        content_threshold=0.5, per_query_threshold=50.0, median_threshold=50.0, fraction_threshold=0.5,
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
        correlator = _make_correlator(per_query_threshold=1.0, median_threshold=1.0)
        # No branch2_scores passed — must fall back to self.b2_detector via
        # branch2_scores_for_texts (real extract_statistical_features, so a
        # long text produces a large "length" feature -> fires behavior).
        result = correlator.score(["x" * 500])
        assert result["fires_behavior"] is True


class TestSessionCorrelatorCalibrate:
    def test_calibrate_separates_benign_from_attack(self) -> None:
        correlator = _make_correlator(per_query_threshold=0.0, median_threshold=0.0, fraction_threshold=0.0)
        train_sessions = [
            (["select 1", "select 2"], [1.0, 1.1], 0),
            (["select 3", "select 4"], [0.9, 1.0], 0),
            (["p1", "p2", "p3"], [9.0, 9.5, 9.2], 1),
            (["p4", "p5", "p6"], [8.8, 9.1, 9.4], 2),
        ]
        correlator.calibrate(train_sessions, percentile=0.90)
        # per_query_threshold = P90 of benign per-query scores [1.0,1.1,0.9,1.0] -> within their range.
        assert 0.9 <= correlator.per_query_threshold <= 1.1
        # median_threshold must separate benign session medians (~0.95, 1.05) from
        # attack session medians (~9.23, 9.43).
        assert 1.05 < correlator.median_threshold < 9.23

    def test_calibrate_picks_content_threshold_from_train_data(self) -> None:
        """content_threshold must come from calibrate(), not stay pinned at the
        constructor's placeholder (0.5, B1's single-query decision_threshold)."""
        correlator = _make_correlator(content_threshold=0.5, per_query_threshold=0.0,
                                       median_threshold=0.0, fraction_threshold=0.0)
        train_sessions = [
            (["select 1", "select 2"], [1.0, 1.1], 0),  # benign, no "attack" -> concat content_prob = 0.1
            (["select 3", "select 4"], [0.9, 1.0], 0),  # benign -> 0.1
            (["attack p1", "attack p2"], [9.0, 9.5], 1),  # attack -> 0.9
            (["attack p3", "attack p4"], [8.8, 9.1], 2),  # attack -> 0.9
        ]
        correlator.calibrate(train_sessions, percentile=0.90)
        # Perfectly separable at any threshold in (0.1, 0.9]; the max-margin
        # search must land strictly between the benign and attack content_prob values.
        assert 0.1 < correlator.content_threshold <= 0.9

    def test_calibrate_content_threshold_persists_through_save_load(self, tmp_path) -> None:
        correlator = _make_correlator(content_threshold=0.5, per_query_threshold=0.0,
                                       median_threshold=0.0, fraction_threshold=0.0)
        train_sessions = [
            (["select 1"], [1.0], 0),
            (["attack p1"], [9.0], 1),
        ]
        correlator.calibrate(train_sessions, percentile=0.90)
        calibrated_threshold = correlator.content_threshold

        correlator.save(tmp_path)
        loaded = SessionCorrelator.load(tmp_path, _FakeVectorizer(), _FakeClf(), _FakeB2Detector())
        assert loaded.content_threshold == calibrated_threshold


class TestSessionCorrelatorSaveLoad:
    def test_roundtrip_thresholds_and_scoring_match(self, tmp_path) -> None:
        correlator = _make_correlator(per_query_threshold=1.0, median_threshold=2.0, fraction_threshold=0.3)
        before = correlator.score(["attack payload", "select 1"], branch2_scores=[0.5, 0.5])

        correlator.save(tmp_path)
        loaded = SessionCorrelator.load(tmp_path, _FakeVectorizer(), _FakeClf(), _FakeB2Detector())
        after = loaded.score(["attack payload", "select 1"], branch2_scores=[0.5, 0.5])

        assert loaded.content_threshold == correlator.content_threshold
        assert loaded.per_query_threshold == correlator.per_query_threshold
        assert loaded.median_threshold == correlator.median_threshold
        assert loaded.fraction_threshold == correlator.fraction_threshold
        assert before == after

    def test_creates_expected_files(self, tmp_path) -> None:
        correlator = _make_correlator()
        correlator.save(tmp_path)
        assert (tmp_path / "metadata.json").exists()
        assert not (tmp_path / "model.pt").exists()  # no weights — not a trained model


_REAL_ARTIFACTS = [
    "models/branch2_v1/model.joblib",
    "models/branch3_v2/metadata.json",
    "data/processed/branch3_sessions_cach_a.csv",
]


def _real_artifacts_present() -> bool:
    from pathlib import Path

    from src.models.branch1_loader import branch1_artifacts_exist

    return branch1_artifacts_exist("models/branch1_v1") and all(
        Path(p).exists() for p in _REAL_ARTIFACTS
    )


@pytest.mark.skipif(not _real_artifacts_present(), reason="real branch1/branch2/branch3 artifacts not present locally")
class TestSessionCorrelatorContentAndBehaviorBothCoverWeakSteps:
    """Regression test for a real finding from this project's diagnostic session.

    A boolean_blind session's WEAK-per-content-check steps alone (the
    length-bisection phase — no strong character-extraction steps mixed in)
    concatenate to only 0.45-0.46 content probability — below Branch 1's
    single-query 0.5 threshold, but above the session-level
    ``content_threshold`` (~0.34) calibrated by ``calibrate()`` once it
    started separately calibrating this threshold from TRAIN data instead of
    reusing 0.5 (benign sessions concatenate to <=0.172 — see
    ``SessionCorrelator.calibrate``'s docstring and
    ``report/plan/data_contract.md`` SS4.2). The behavior check independently
    catches the same steps regardless (Branch 2 scores structural shape, not
    attack type).

    UPDATE 27/8 (twice in one day — both times re-verified, not papered
    over): this test's own docstring said "if this test starts failing, the
    OR'd-checks-resilient claim no longer holds and must be re-verified
    before citing it."
    (1) It first started failing after Branch 1 was retrained with
        D3/Superviz25 added (data_contract.md SS6/SS7): per-step attack
        probabilities rose (0.44-0.47 -> 0.52-0.55) but the recalibrated
        content_threshold rose more (~0.34 -> 0.6506), so this session's
        concatenated probability (0.541) fell just short - content check
        alone no longer independently rescued it, only the behavior check
        did.
    (2) After the TF-IDF retune that followed (ngram (2,4)->(1,2), C=10 -
        data_contract.md SS7, a large accuracy win found via grid search,
        not done to fix this test), Branch 1's per-step probabilities on
        this SAME session rose much further (concatenated: 0.782) while the
        freshly recalibrated content_threshold fell (0.6506 -> 0.1299) -
        the smaller, sharper (1,2)-gram model is both more confident here
        and better separated from benign sessions on TRAIN. Net effect:
        content check alone rescues this session again, restoring the
        original "both checks independently cover it" redundancy this test
        checks for. Recorded here so the next person doesn't need to
        re-derive this arc from git blame.
    """

    def test_weak_content_steps_fire_both_checks_independently(self) -> None:
        import copy

        import pandas as pd

        from src.models.branch1_loader import load_branch1_artifacts
        from src.models.branch2_anomaly import AnomalyDetector
        from src.utils import load_config

        cfg = load_config()
        vectorizer, clf = load_branch1_artifacts(
            "models/branch1_v1", cfg.get_path("branch1_supervised.distilbert", {})
        )
        b2_detector = AnomalyDetector.load("models/branch2_v1")
        correlator = SessionCorrelator.load("models/branch3_v2", vectorizer, clf, b2_detector)

        # keep_default_na=False: query_canonical can legitimately contain pandas'
        # default NA sentinel strings (e.g. a fragment literally reading "null").
        df = pd.read_csv("data/processed/branch3_sessions_cach_a.csv", keep_default_na=False, na_values=[])
        sess = df[(df["session_label"] == 1) & (df["split"] == "test")].sort_values(["session_id", "step_index"])
        sid = sess["session_id"].iloc[0]
        texts = sess.loc[sess["session_id"] == sid, "query_canonical"].tolist()
        b2_scores = sess.loc[sess["session_id"] == sid, "branch2_anomaly_score"].tolist()

        # First 5 steps = the length-bisection phase. Originally chosen
        # because each step sat individually BELOW Branch 1's 0.5 threshold
        # (0.44-0.47) - after the 27/8 TF-IDF retune (see class docstring),
        # that's no longer true for this session: per-step probs are now
        # 0.76-0.83, individually above 0.5. The retuned model is simply
        # much better at this content now. Kept as "weak_texts" for
        # continuity with the class docstring/data_contract.md's account,
        # but the assertions below test the OR mechanism, not weakness.
        weak_texts, weak_scores = texts[:5], b2_scores[:5]

        content_only = correlator.score(weak_texts, branch2_scores=[-999.0] * 5)  # force behavior off
        assert content_only["fires_content"] is True

        behavior_only_correlator = copy.copy(correlator)
        behavior_only_correlator.content_threshold = 1.1  # force content off (probs never exceed 1.0)
        behavior_only = behavior_only_correlator.score(weak_texts, branch2_scores=weak_scores)
        assert behavior_only["fires_behavior"] is True
        assert behavior_only["is_attack"] is True

        combined = correlator.score(weak_texts, branch2_scores=weak_scores)
        assert combined["fires_content"] is True
        assert combined["fires_behavior"] is True
        assert combined["is_attack"] is True
