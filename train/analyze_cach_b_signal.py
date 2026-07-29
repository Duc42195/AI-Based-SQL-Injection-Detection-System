"""Analyze whether Cách B data has real sequence signal.

Checks:
1. Shuffle test: train GRU on Cách B, test on shuffled vs original order
2. Autocorrelation: within-session step-to-step feature correlation
3. Cross-domain B->A: how does Cách B-trained model do on Cách A?
"""
from __future__ import annotations

import json, warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import f1_score

from src.models.branch3_features import prob_columns_in, sessions_to_arrays, class_names_from_config
from src.models.branch3_session import SessionSequenceDetector
from src.utils import load_config, get_logger

warnings.filterwarnings("ignore")
logger = get_logger(__name__)

SEED = 42
CLASS_NAMES = ["benign", "boolean_blind", "time_blind", "query_splitting"]
N_FOLDS = 5


def shuffle_sessions(X: list[np.ndarray], rng: np.random.RandomState) -> list[np.ndarray]:
    """Shuffle step order within each session."""
    return [arr[rng.permutation(len(arr))] for arr in X]


def eval_gru(detector, X: list[np.ndarray], y: np.ndarray) -> float:
    return float(f1_score(y, detector.predict(X), average="macro"))


def main():
    cfg = load_config()
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    reports_dir = Path(cfg.get_path("paths.reports_dir", "report/metrics"))

    df_b = pd.read_csv(processed_dir / "branch3_sessions_cach_b_v2.csv")
    df_b["gap_seconds_log1p"] = np.log1p(df_b["gap_seconds"])
    feature_cols = prob_columns_in(df_b) + ["branch2_anomaly_score", "gap_seconds_log1p"]

    # ---- 1. Per-step autocorrelation ----
    logger.info("=== Per-step autocorrelation ===")
    corrs = {}
    for label in [0, 1, 2]:
        session_corrs = []
        for sid, group in df_b[df_b["session_label"] == label].groupby("session_id"):
            feats = group.sort_values("step_index")[feature_cols].to_numpy()
            if len(feats) < 3:
                continue
            step_corrs = []
            for col in range(feats.shape[1]):
                c = np.corrcoef(feats[:-1, col], feats[1:, col])[0, 1]
                if not np.isnan(c):
                    step_corrs.append(c)
            session_corrs.append(np.mean(step_corrs) if step_corrs else 0)
        corrs[CLASS_NAMES[label]] = {
            "mean": round(float(np.mean(session_corrs)), 4),
            "std": round(float(np.std(session_corrs)), 4),
        }
    logger.info("Autocorrelation (step_n vs step_{n-1}): %s", corrs)

    # ---- 2. Shuffle test with cross-validation ----
    logger.info("=== Shuffle test (CV on Cách B) ===")
    session_ids = df_b["session_id"].unique()
    rng = np.random.RandomState(SEED)

    fold_results = []
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
    labels_lookup = df_b.groupby("session_id")["session_label"].first()

    for fold, (train_idx, test_idx) in enumerate(skf.split(session_ids, labels_lookup.loc[session_ids])):
        train_ids = session_ids[train_idx]
        test_ids = session_ids[test_idx]

        train_df = df_b[df_b["session_id"].isin(train_ids)]
        test_df = df_b[df_b["session_id"].isin(test_ids)]

        X_train, y_train = sessions_to_arrays(train_df, feature_cols)
        X_test, y_test = sessions_to_arrays(test_df, feature_cols)
        X_test_shuf = shuffle_sessions(X_test, rng)

        det = SessionSequenceDetector(
            input_dim=len(feature_cols), hidden_dim=32,
            num_classes=4, class_names=CLASS_NAMES,
            random_seed=SEED, max_len=64,
        )
        det.fit(X_train, y_train, epochs=20, lr=0.001, batch_size=8)

        f1_orig = eval_gru(det, X_test, y_test)
        f1_shuf = eval_gru(det, X_test_shuf, y_test)
        fold_results.append({"fold": fold, "f1_original": f1_orig, "f1_shuffled": f1_shuf})
        logger.info(f"  fold {fold}: orig={f1_orig:.4f} shuffled={f1_shuf:.4f}")

    shuffle_avg = {
        "f1_original_mean": round(float(np.mean([r["f1_original"] for r in fold_results])), 4),
        "f1_shuffled_mean": round(float(np.mean([r["f1_shuffled"] for r in fold_results])), 4),
        "f1_drop": round(float(np.mean([r["f1_original"] - r["f1_shuffled"] for r in fold_results])), 4),
        "fold_results": fold_results,
    }
    logger.info("Shuffle test avg: %s", shuffle_avg)

    # ---- 3. Cross-domain B->A ----
    logger.info("=== Cross-domain B->A ===")
    df_a = pd.read_csv(processed_dir / "branch3_sessions_cach_a.csv")
    df_a["gap_seconds_log1p"] = np.log1p(df_a["gap_seconds"])

    X_full_b, y_full_b = sessions_to_arrays(df_b, feature_cols)
    X_a, y_a = sessions_to_arrays(df_a, feature_cols)

    det_b = SessionSequenceDetector(
        input_dim=len(feature_cols), hidden_dim=32,
        num_classes=4, class_names=CLASS_NAMES,
        random_seed=SEED, max_len=64,
    )
    det_b.fit(X_full_b, y_full_b, epochs=20, lr=0.001, batch_size=8)
    f1_b2a = eval_gru(det_b, X_a, y_a)
    logger.info("GRU train on Cách B → test on Cách A: F1=%.4f", f1_b2a)

    cross_domain = {"B_to_A_f1": f1_b2a}

    # ---- Summary ----
    has_signal = shuffle_avg["f1_drop"] > 0.02
    result = {
        "has_sequence_signal": has_signal,
        "autocorrelation": corrs,
        "shuffle_test": shuffle_avg,
        "cross_domain": cross_domain,
        "conclusion": (
            "Cach B has real sequence signal" if has_signal
            else "Cach B also lacks sequence signal (shuffle test F1 drop < 0.02)"
        ),
    }

    out_path = reports_dir / "cach_b_signal_analysis.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info("Saved to %s", out_path)
    logger.info("Conclusion: %s", result["conclusion"])


if __name__ == "__main__":
    main()
