"""Harder, more honest test of Branch 3's session-level value-add.

The default Cách A dataset (build_session_dataset.py) scores every step with
the REGULAR branch1_v1 model, which already recognizes real boolean_blind /
time_blind payloads correctly most of the time per-query (they're real
attacks from the pool branch1_v1 was trained on). That makes the GRU's job
"classify a bag of already-correctly-flagged steps" — easy, and NOT a test
of Branch 3's actual value proposition (catching sessions where per-query
signals are weak/ambiguous).

This script re-scores `boolean_blind` session steps using
`models/branch1_no_boolean_blind` instead — a Branch-1 variant that has
NEVER seen a boolean_blind example (leave-one-out, see
train/run_zeroday_experiment.py) and misses 90.2% of them per-query
(report/metrics/zeroday_experiment/summary.json). `time_blind` is left
scored by the regular model: its own zero-day miss rate is only 0.27%
(mostly misrouted to boolean_blind, still flagged as *an* attack), so it
isn't a meaningful "Branch 1 is blind to this" case the way boolean_blind is.

If Branch 3 still detects boolean_blind sessions reasonably well here, that
demonstrates real session-level value (timing pattern + weak/misrouted
per-step signal, aggregated over the sequence) rather than just re-surfacing
what Branch 1 already knew per-query.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.models.branch3_features import (
    BRANCH1_LABEL_ORDER,
    branch1_prob_columns,
    branch1_probabilities,
    class_names_from_config,
    evaluate_sessions,
    prob_columns_in,
    sessions_to_arrays,
)
from src.models.branch3_session import SessionSequenceDetector
from src.utils import get_logger, load_config

logger = get_logger(__name__)


def main() -> None:
    cfg = load_config()
    seed = int(cfg.get_path("project.random_seed", 42))
    models_dir = Path(cfg.get_path("paths.models_dir", "models"))
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    reports_dir = Path(cfg.get_path("paths.reports_dir", "report/metrics"))

    data_path = processed_dir / "branch3_sessions_cach_a.csv"
    df = pd.read_csv(data_path)
    class_names = class_names_from_config(cfg)
    prob_cols = prob_columns_in(df)

    # Re-score boolean_blind (session_label==1) steps with the zero-day
    # "never seen boolean_blind" Branch-1 variant.
    hard_model_dir = models_dir / "branch1_no_boolean_blind"
    vectorizer = joblib.load(hard_model_dir / "vectorizer.joblib")
    clf = joblib.load(hard_model_dir / "model.joblib")
    logger.info("Loaded hard-mode Branch 1 (never seen boolean_blind) from %s", hard_model_dir)

    mask = df["session_label"] == 1
    logger.info("Re-scoring %d boolean_blind steps (%d sessions) with the zero-day model",
                mask.sum(), df.loc[mask, "session_id"].nunique())
    hard_probs = branch1_probabilities(df.loc[mask, "query_canonical"].tolist(), vectorizer, clf)
    for idx, col in enumerate(branch1_prob_columns()):
        df.loc[mask, col] = hard_probs[:, idx]
    # branch1_label (argmax) also needs updating for consistency/inspection.
    df.loc[mask, "branch1_label"] = [
        int(BRANCH1_LABEL_ORDER[i]) for i in np.argmax(hard_probs, axis=1)
    ]

    df["gap_seconds_log1p"] = np.log1p(df["gap_seconds"])
    feature_cols = prob_cols + ["branch2_anomaly_score", "gap_seconds_log1p"]

    train_df, test_df = df[df["split"] == "train"], df[df["split"] == "test"]
    X_train, y_train = sessions_to_arrays(train_df, feature_cols)
    X_test, y_test = sessions_to_arrays(test_df, feature_cols)
    logger.info("Train sessions=%d  Test sessions=%d", len(X_train), len(X_test))

    train_cfg = cfg.get_path("branch3_session.train")
    max_len = int(cfg.get_path("branch3_session.max_session_len", 64))
    detector = SessionSequenceDetector(
        input_dim=len(feature_cols), hidden_dim=int(train_cfg["hidden_dim"]),
        num_classes=len(class_names), class_names=class_names,
        random_seed=seed, max_len=max_len,
    )
    detector.fit(
        X_train, y_train, epochs=int(train_cfg["epochs"]),
        lr=float(train_cfg["learning_rate"]), batch_size=int(train_cfg["batch_size"]),
    )

    metrics = evaluate_sessions(detector, X_test, y_test, class_names)
    logger.info("=== HARD-MODE (boolean_blind scored by a Branch-1 blind to it) ===")
    logger.info("Test F1-macro=%.4f  Accuracy=%.4f  FPR(benign)=%s", metrics["f1_macro"], metrics["accuracy"], metrics["fpr_benign"])
    for name, dr in metrics["detection_rate"].items():
        logger.info("  Detection rate [%s] = %.4f", name, dr)
    logger.info("boolean_blind per-class: %s", metrics["per_class"]["boolean_blind"])

    out_path = reports_dir / "branch3_eval_hard.json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "description": "Hard-mode: boolean_blind session steps scored by "
                "branch1_no_boolean_blind (a Branch-1 variant that has never seen "
                "boolean_blind and misses 90.2% of it per-query). Tests whether "
                "Branch 3 adds real session-level value vs. just aggregating an "
                "already-correct per-step Branch-1 signal.",
                "metrics": metrics,
            },
            f, indent=2,
        )
    logger.info("Saved to %s", out_path)


if __name__ == "__main__":
    main()
