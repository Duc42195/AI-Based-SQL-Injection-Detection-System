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
from sklearn.metrics import classification_report, confusion_matrix

from src.models.branch3_session import SessionSequenceDetector
from src.utils import Config, get_logger, load_config

logger = get_logger(__name__)


def _class_names(cfg: Config) -> list[str]:
    """Ordered class names from config, indexed by label id."""
    classes: dict[str, int] = cfg.get_path("branch3_session.session_classes")
    return [name for name, _ in sorted(classes.items(), key=lambda kv: kv[1])]


def _prob_columns(df: pd.DataFrame) -> list[str]:
    return sorted(c for c in df.columns if c.startswith("branch1_prob_"))


def _sessions_to_arrays(df: pd.DataFrame, feature_cols: list[str]) -> tuple[list[np.ndarray], np.ndarray]:
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


def _evaluate(
    detector: SessionSequenceDetector,
    X_test: list[np.ndarray],
    y_test: np.ndarray,
    class_names: list[str],
) -> dict:
    """Compute confusion matrix, per-class P/R/F1, detection rate, and FPR."""
    y_pred = detector.predict(X_test)

    labels = list(range(len(class_names)))
    cm = confusion_matrix(y_test, y_pred, labels=labels)
    report = classification_report(
        y_test, y_pred, labels=labels, target_names=class_names,
        output_dict=True, zero_division=0,
    )

    # FPR: benign (label 0) sessions predicted as ANY attack class.
    benign_mask = y_test == 0
    fpr = float((y_pred[benign_mask] != 0).mean()) if benign_mask.any() else None

    # Detection rate per attack class = recall for that class (already in
    # `report`), surfaced here explicitly for readability in the JSON.
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

    class_names = _class_names(cfg)
    feature_cols = _prob_columns(df) + ["branch2_anomaly_score", "gap_seconds_log1p"]
    logger.info("Feature columns (%d): %s", len(feature_cols), feature_cols)

    train_df = df[df["split"] == "train"]
    test_df = df[df["split"] == "test"]
    X_train, y_train = _sessions_to_arrays(train_df, feature_cols)
    X_test, y_test = _sessions_to_arrays(test_df, feature_cols)
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

    metrics = _evaluate(detector, X_test, y_test, class_names)
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
        "dataset_source": "A_simulated",
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
