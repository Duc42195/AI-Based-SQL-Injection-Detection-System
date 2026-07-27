"""Train, evaluate and save the Branch 3 session sequence model.

Reads data/processed/branch3_sessions_cach_a.csv (built by
train/build_session_dataset.py), groups rows into per-session feature
sequences [Branch-1 probabilities ⊕ Branch-2 anomaly score], trains the GRU
classifier (src/models/branch3_session.py), and writes:

  - models/branch3_v1/{model.pt,metadata.json}
  - report/metrics/branch3_eval.json (confusion matrix, per-class P/R/F1,
    detection rate per attack class, FPR on benign sessions)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src.models.branch3_features import (
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
    if not data_path.exists():
        raise FileNotFoundError(f"{data_path} not found. Run train/build_session_dataset.py first.")
    df = pd.read_csv(data_path)
    # log1p-transform the inter-step gap: raw seconds range from 0 to ~120,
    # right-skewed like Branch 2's "length" feature, and it's the ratio/order
    # of magnitude that matters (scripted probing vs human browsing), not
    # the absolute value.
    df["gap_seconds_log1p"] = np.log1p(df["gap_seconds"])

    class_names = class_names_from_config(cfg)
    feature_cols = prob_columns_in(df) + ["branch2_anomaly_score", "gap_seconds_log1p"]
    logger.info("Feature columns (%d): %s", len(feature_cols), feature_cols)

    train_df = df[df["split"] == "train"]
    test_df = df[df["split"] == "test"]
    X_train, y_train = sessions_to_arrays(train_df, feature_cols)
    X_test, y_test = sessions_to_arrays(test_df, feature_cols)
    logger.info("Train sessions=%d  Test sessions=%d", len(X_train), len(X_test))

    train_cfg = cfg.get_path("branch3_session.train")
    max_len = int(cfg.get_path("branch3_session.max_session_len", 64))

    detector = SessionSequenceDetector(
        input_dim=len(feature_cols),
        hidden_dim=int(train_cfg["hidden_dim"]),
        num_classes=len(class_names),
        class_names=class_names,
        random_seed=seed,
        max_len=max_len,
    )

    loss_history = detector.fit(
        X_train, y_train,
        epochs=int(train_cfg["epochs"]),
        lr=float(train_cfg["learning_rate"]),
        batch_size=int(train_cfg["batch_size"]),
    )

    metrics = evaluate_sessions(detector, X_test, y_test, class_names)
    logger.info("Test F1-macro=%.4f  Accuracy=%.4f  FPR(benign)=%s", metrics["f1_macro"], metrics["accuracy"], metrics["fpr_benign"])
    for name, dr in metrics["detection_rate"].items():
        logger.info("  Detection rate [%s] = %.4f", name, dr)

    version = "branch3_v1"
    out_dir = models_dir / version
    detector.save(out_dir)

    eval_report = {
        "version": version,
        "branch": "branch3_session",
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset": str(data_path),
        "dataset_source": {
            k: int(v) for k, v in df.drop_duplicates("session_id")["session_source"].value_counts().items()
        },
        "model": {
            "architecture": "gru",
            "input_dim": len(feature_cols),
            "hidden_dim": int(train_cfg["hidden_dim"]),
            "epochs": int(train_cfg["epochs"]),
            "learning_rate": float(train_cfg["learning_rate"]),
            "batch_size": int(train_cfg["batch_size"]),
        },
        "train_sessions": len(X_train),
        "loss_curve": [round(v, 6) for v in loss_history],
        "metrics": metrics,
    }

    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "branch3_eval.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(eval_report, f, indent=2)
    logger.info("Saved eval report to %s", report_path)
    logger.info("=== Done ===")


if __name__ == "__main__":
    main()
