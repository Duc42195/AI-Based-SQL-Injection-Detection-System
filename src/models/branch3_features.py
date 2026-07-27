"""Shared helpers for building/scoring/evaluating Branch 3 session data.

Used by train/build_session_dataset.py (data generation), train/train_branch3.py
(training), and train/eval_branch3_hard.py (the zero-day hard-mode check) —
extracted here once a 4th consumer (train/attack_simulator.py's caller) would
otherwise have made this a 4th copy-paste of the same ~5 functions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix

from src.preprocessing.multiclass_tagger import LABEL_NAMES
from src.utils import Config

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
