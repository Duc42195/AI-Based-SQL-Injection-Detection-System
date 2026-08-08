"""Shared helpers for building/scoring/evaluating Branch 3 / Session Correlator data.

Used by train/build_session_dataset.py (data generation), train/calibrate_branch3.py
(threshold calibration + eval), and train/eval_branch3_hard.py (the zero-day
hard-mode check) — extracted here once a 4th consumer (train/attack_simulator.py's
caller) would otherwise have made this a 4th copy-paste of the same ~5 functions.

``sessions_to_arrays``/``evaluate_sessions`` are the SUPERSEDED GRU-era helpers
(kept for the record — operate on padded per-step feature arrays, see
``src/models/branch3_session.py``'s superseded ``SessionSequenceDetector``).
``sessions_to_correlator_inputs``/``evaluate_correlator_sessions`` are the
active helpers for ``SessionCorrelator``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix

from src.preprocessing.multiclass_tagger import LABEL_NAMES
from src.preprocessing.statistical_features import extract_statistical_features
from src.utils import Config

# extract_statistical_features always returns features in this fixed order —
# reorder only if config (branch2_anomaly.features) specifies a different one.
_DEFAULT_B2_FEATURE_ORDER = ["length", "special_char_ratio", "sql_keyword_count", "entropy"]


def branch2_scores_for_texts(texts: list[str], detector, feature_names: list[str] | None = None) -> np.ndarray:
    """Run Branch 2 inference, returning a (n,) anomaly-score vector.

    Shared by train/build_session_dataset.py (scoring dataset rows) and
    ``SessionCorrelator.score()`` (scoring a live session's raw queries) —
    the single place that knows how to turn query text into Branch-2's
    4-feature input.

    Rounded to 6 decimals (matching the precision already persisted in
    ``data/processed/branch3_sessions_cach_a.csv``, see
    ``train/build_session_dataset.py``'s own row-writing code) — found the
    hard way: ``SessionCorrelator``'s behavior-check thresholds are
    calibrated against those rounded CSV values, and benign per-query scores
    cluster on only a handful of distinct values (SQLite benign lookups
    produce few distinct feature combinations), so a calibrated threshold
    routinely lands EXACTLY on one of them. Comparing that threshold against
    *unrounded* live-recomputed scores let float64 noise (recomputing in a
    1-row batch vs. the original many-row batch) flip "equal to the
    threshold" into "greater than it" for the majority of a benign session's
    steps — a real false positive observed via the live API, not a
    hypothetical.
    """
    feature_names = feature_names or _DEFAULT_B2_FEATURE_ORDER
    X = np.array([extract_statistical_features(t).as_list() for t in texts], dtype=np.float64)
    if feature_names != _DEFAULT_B2_FEATURE_ORDER:
        idx = [_DEFAULT_B2_FEATURE_ORDER.index(f) for f in feature_names]
        X = X[:, idx]
    return np.round(detector.score(X), 6)

# Branch 1 label ids (from configs/config.yaml: labels.classes), fixed order
# for the probability-vector columns written to/read from the dataset CSV.
BRANCH1_LABEL_ORDER = [0, 1, 2, 3, 4]  # normal, union_based, error_based, boolean_blind, time_blind


def branch1_probabilities(texts: list[str], vectorizer, clf) -> np.ndarray:
    """Run Branch 1 inference, returning a (n, 5) probability matrix.

    Columns follow ``BRANCH1_LABEL_ORDER``. The classifier only knows the
    classes present at its own training time (e.g. a zero-day variant may be
    missing one), so this maps from ``clf.classes_`` rather than assuming a
    fixed column order — missing classes get probability 0.
    """
    probs = clf.predict_proba(vectorizer.transform(texts))
    classes = [int(c) for c in clf.classes_]
    out = np.zeros((len(texts), len(BRANCH1_LABEL_ORDER)), dtype=np.float64)
    for col, label in enumerate(BRANCH1_LABEL_ORDER):
        if label in classes:
            out[:, col] = probs[:, classes.index(label)]
    return out


def branch1_prob_columns() -> list[str]:
    """Ordered column names for the Branch-1 probability vector."""
    return [f"branch1_prob_{LABEL_NAMES[label]}" for label in BRANCH1_LABEL_ORDER]


def class_names_from_config(cfg: Config) -> list[str]:
    """Ordered session-class names from config, indexed by label id."""
    classes: dict[str, int] = cfg.get_path("branch3_session.session_classes")
    return [name for name, _ in sorted(classes.items(), key=lambda kv: kv[1])]


def prob_columns_in(df: pd.DataFrame) -> list[str]:
    """Find the Branch-1 probability columns actually present in a dataframe."""
    return sorted(c for c in df.columns if c.startswith("branch1_prob_"))


def sessions_to_arrays(df: pd.DataFrame, feature_cols: list[str]) -> tuple[list[np.ndarray], np.ndarray]:
    """Group rows by session_id (in step order) into per-session feature sequences.

    Returns:
        Tuple of (list of (seq_len, n_features) arrays, (n_sessions,) int labels).
    """
    X: list[np.ndarray] = []
    y: list[int] = []
    for session_id, group in df.sort_values("step_index").groupby("session_id", sort=False):
        X.append(group[feature_cols].to_numpy(dtype=np.float32))
        y.append(int(group["session_label"].iloc[0]))
    return X, np.array(y, dtype=np.int64)


def evaluate_sessions(detector, X_test: list[np.ndarray], y_test: np.ndarray, class_names: list[str]) -> dict:
    """Compute confusion matrix, per-class P/R/F1, detection rate, and FPR.

    Args:
        detector: A fitted SessionSequenceDetector (or compatible ``.predict``).
        X_test: Per-session feature sequences.
        y_test: True session labels.
        class_names: Ordered class names, index 0 assumed to be "benign".
    """
    y_pred = detector.predict(X_test)

    labels = list(range(len(class_names)))
    cm = confusion_matrix(y_test, y_pred, labels=labels)
    report = classification_report(
        y_test, y_pred, labels=labels, target_names=class_names,
        output_dict=True, zero_division=0,
    )

    benign_mask = y_test == 0
    fpr = float((y_pred[benign_mask] != 0).mean()) if benign_mask.any() else None

    detection_rate = {
        name: round(report[name]["recall"], 6)
        for name in class_names
        if name != "benign"
    }

    return {
        "n_test_sessions": int(len(y_test)),
        "confusion_matrix": cm.tolist(),
        "labels": class_names,
        "f1_macro": round(report["macro avg"]["f1-score"], 6),
        "accuracy": round(report["accuracy"], 6),
        "per_class": {
            name: {
                "precision": round(report[name]["precision"], 6),
                "recall": round(report[name]["recall"], 6),
                "f1": round(report[name]["f1-score"], 6),
                "support": int(report[name]["support"]),
            }
            for name in class_names
        },
        "fpr_benign": round(fpr, 6) if fpr is not None else None,
        "detection_rate": detection_rate,
    }


def sessions_to_correlator_inputs(df: pd.DataFrame) -> list[tuple[list[str], list[float], int]]:
    """Group rows by session_id (in step order) for ``SessionCorrelator``.

    Unlike ``sessions_to_arrays`` (padded feature matrices for the superseded
    GRU), this returns raw ``query_canonical`` text and Branch-2's per-query
    ``branch2_anomaly_score`` — exactly the inputs ``SessionCorrelator.score()``
    and ``.calibrate()`` expect, with no padding or fixed length at all.

    Returns:
        List of ``(query_texts, branch2_scores, session_label)`` per session.
    """
    sessions = []
    for _, group in df.sort_values("step_index").groupby("session_id", sort=False):
        sessions.append((
            group["query_canonical"].tolist(),
            group["branch2_anomaly_score"].tolist(),
            int(group["session_label"].iloc[0]),
        ))
    return sessions


def evaluate_correlator_sessions(correlator, sessions: list[tuple[list[str], list[float], int]], class_names: list[str]) -> dict:
    """Evaluate a calibrated ``SessionCorrelator`` on TEST sessions.

    Reports detection rate per attack class and FPR on benign for THREE
    configurations — content-only, behavior-only, and combined — the
    mandatory ablation (AGENTS.md: never trust a result without ablations;
    see also Experiment C in this project's diagnostic session, which this
    mirrors on the real train/test split).

    Args:
        correlator: A calibrated ``SessionCorrelator``.
        sessions: Output of ``sessions_to_correlator_inputs`` — TEST split.
        class_names: Ordered session-class names, index 0 = "benign".
    """
    rows = []
    for texts, b2_scores, label in sessions:
        result = correlator.score(texts, b2_scores)
        # NOTE: `result` already has its own "label" key (the correlator's
        # PREDICTED class name) — must use a distinct key for the ground
        # truth, or dict-literal ordering silently overwrites it.
        rows.append({"true_label": label, **result})

    def _rates(fire_key: str) -> dict:
        benign = [r for r in rows if r["true_label"] == 0]
        fpr = float(np.mean([r[fire_key] for r in benign])) if benign else None
        detection_rate = {}
        for label_id, name in enumerate(class_names):
            if label_id == 0:
                continue
            subset = [r for r in rows if r["true_label"] == label_id]
            if subset:
                detection_rate[name] = round(float(np.mean([r[fire_key] for r in subset])), 6)
        return {"fpr_benign": round(fpr, 6) if fpr is not None else None, "detection_rate": detection_rate}

    return {
        "n_test_sessions": len(rows),
        "content_only": _rates("fires_content"),
        "behavior_only": _rates("fires_behavior"),
        "combined": _rates("is_attack"),
    }
