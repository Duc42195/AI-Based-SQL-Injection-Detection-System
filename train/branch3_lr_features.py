"""Session-level feature aggregation for LogisticRegression baseline.

Turns per-step 7-dim features into a fixed-length session-level vector
using mean, std, max, and linear trend. Designed to match the interface
of ``src.models.branch3_features.sessions_to_arrays`` for drop-in
comparison with the GRU model.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# Per-step feature names (same order as sessions_to_arrays expects)
FEATURE_NAMES_7 = [
    "branch1_prob_normal",
    "branch1_prob_union_based",
    "branch1_prob_error_based",
    "branch1_prob_boolean_blind",
    "branch1_prob_time_blind",
    "branch2_anomaly_score",
    "gap_seconds_log1p",
]


def session_aggregate_features(df: pd.DataFrame, feature_cols: list[str] | None = None) -> np.ndarray:
    """Aggregate per-step features into a fixed-length session-level vector.

    For each session, computes:
    - ``mean`` and ``std`` for all 7 features → 14
    - ``max`` for gap_seconds_log1p → 1
    - ``slope`` (linear trend) for gap_seconds_log1p → 1

    Returns:
        ``(n_sessions, 16)`` array.
    """
    if feature_cols is None:
        feature_cols = [c for c in FEATURE_NAMES_7 if c in df.columns]

    has_gap = "gap_seconds_log1p" in feature_cols

    rows: list[np.ndarray] = []
    for _sid, group in df.sort_values("step_index").groupby("session_id", sort=False):
        feats = group[feature_cols].to_numpy(dtype=np.float32)
        vec = []
        # mean + std for each feature
        vec.extend(feats.mean(axis=0))
        vec.extend(feats.std(axis=0))
        # max gap
        if has_gap:
            gap_col = feature_cols.index("gap_seconds_log1p")
            vec.append(float(feats[:, gap_col].max()))
        # slope of gap (linear trend over steps)
        if has_gap and feats.shape[0] > 1:
            x = np.arange(feats.shape[0], dtype=np.float32)
            y = feats[:, gap_col]
            slope = np.polyfit(x, y, 1)[0]
        elif has_gap:
            slope = 0.0
        if has_gap:
            vec.append(float(slope))
        rows.append(np.array(vec, dtype=np.float32))

    return np.array(rows, dtype=np.float32)


def feature_names_out(feature_cols: list[str] | None = None) -> list[str]:
    """Return ordered names of the output features."""
    if feature_cols is None:
        feature_cols = FEATURE_NAMES_7
    has_gap = "gap_seconds_log1p" in feature_cols
    names: list[str] = []
    names.extend(f"{c}_mean" for c in feature_cols)
    names.extend(f"{c}_std" for c in feature_cols)
    if has_gap:
        names.append("gap_seconds_log1p_max")
        names.append("gap_seconds_log1p_slope")
    return names


def session_labels(df: pd.DataFrame) -> np.ndarray:
    """Extract per-session labels in the same order as ``session_aggregate_features``."""
    return np.array(
        [int(g["session_label"].iloc[0]) for _sid, g in df.sort_values("step_index").groupby("session_id", sort=False)],
        dtype=np.int64,
    )
