"""Ablation — drop từng feature group, retrain GRU, đo F1.

AGENTS.md Rule 4: "Never trust a suspiciously perfect score without ablations"
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.models.branch3_features import (
    branch1_prob_columns,
    class_names_from_config,
    evaluate_sessions,
    sessions_to_arrays,
)
from src.models.branch3_session import SessionSequenceDetector
from src.utils import get_logger, load_config

logger = get_logger(__name__)


def main():
    cfg = load_config()
    seed = int(cfg.get_path("project.random_seed", 42))
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    reports_dir = Path(cfg.get_path("paths.reports_dir", "report/metrics"))
    train_cfg = cfg.get_path("branch3_session.train")

    data_path = processed_dir / "branch3_sessions_cach_a.csv"
    df = pd.read_csv(data_path)
    df["gap_seconds_log1p"] = np.log1p(df["gap_seconds"].fillna(0))
    class_names = class_names_from_config(cfg)
    prob_cols = branch1_prob_columns()

    # Feature groups
    configs = {
        "full (7 features)": prob_cols + ["branch2_anomaly_score", "gap_seconds_log1p"],
        "drop B1 probs (only B2+gap)": ["branch2_anomaly_score", "gap_seconds_log1p"],
        "drop B2 score (only B1+gap)": prob_cols + ["gap_seconds_log1p"],
        "drop gap (only B1+B2)": prob_cols + ["branch2_anomaly_score"],
        "only B1 probs": prob_cols,
        "only B2 score": ["branch2_anomaly_score"],
        "only gap time": ["gap_seconds_log1p"],
    }

    results = {}
    for label, feat_cols in configs.items():
        logger.info("=" * 60)
        logger.info("Ablation: %s", label)
        # Filter columns that actually exist
        feat_cols = [c for c in feat_cols if c in df.columns]
        if not feat_cols:
            logger.warning("  Skipping — no valid columns")
            continue

        train_df = df[df["split"] == "train"].reset_index(drop=True)
        test_df = df[df["split"] == "test"].reset_index(drop=True)

        X_train, y_train = sessions_to_arrays(train_df, feat_cols)
        X_test, y_test = sessions_to_arrays(test_df, feat_cols)
        logger.info("  Train sessions=%d  Test sessions=%d", len(X_train), len(X_test))

        detector = SessionSequenceDetector(
            input_dim=len(feat_cols), hidden_dim=int(train_cfg["hidden_dim"]),
            num_classes=len(class_names), class_names=class_names,
            random_seed=seed, max_len=int(cfg.get_path("branch3_session.max_session_len", 64)),
        )
        detector.fit(
            X_train, y_train, epochs=int(train_cfg["epochs"]),
            lr=float(train_cfg["learning_rate"]),
            batch_size=int(train_cfg["batch_size"]),
        )

        metrics = evaluate_sessions(detector, X_test, y_test, class_names)
        logger.info("  F1-macro=%.4f  Accuracy=%.4f  FPR(benign)=%s",
                    metrics["f1_macro"], metrics["accuracy"], metrics["fpr_benign"])
        for name, dr in metrics["detection_rate"].items():
            logger.info("    DR [%s] = %.4f", name, dr)
        results[label] = metrics

    # Save
    out_path = reports_dir / "branch3_ablation.json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    logger.info("Saved ablation results to %s", out_path)

    # Summary table
    print("\n" + "=" * 72)
    print("ABLATION SUMMARY")
    print("=" * 72)
    print(f"{'Config':<30} {'F1-macro':<10} {'Accuracy':<10} {'FPR':<8} {'DR_bb':<8} {'DR_tb':<8} {'DR_qs':<8}")
    print("-" * 72)
    for label, m in results.items():
        dr = m["detection_rate"]
        print(f"{label:<30} {m['f1_macro']:<10.4f} {m['accuracy']:<10.4f} {m['fpr_benign']:<8.4f} "
              f"{dr.get('boolean_blind', 0):<8.4f} {dr.get('time_blind', 0):<8.4f} {dr.get('query_splitting', 0):<8.4f}")
    print("=" * 72)


if __name__ == "__main__":
    main()
