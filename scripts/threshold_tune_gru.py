"""Threshold tuning for adapted GRU on Cach B.

Splits Cach B into val/test (60/40). Chooses threshold on val set,
reports final metrics on held-out test set. Avoids overfitting to 86 sessions.

AUC=1.000 means there exists a threshold with perfect separation.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from src.models.nhanh3_gru import FEATURE_NAMES, GRUSessionClassifier
from src.utils import get_logger, load_config

logger = get_logger(__name__)
DEVICE = torch.device("cpu")


def _compute_confidences(df: pd.DataFrame, gru, scaler) -> pd.DataFrame:
    session_ids = sorted(df["session_id"].unique())
    records = []
    for sid in session_ids:
        grp = df[df["session_id"] == sid].sort_values("step")
        feats = grp[FEATURE_NAMES].values.astype(np.float32)
        feats_s = scaler.transform(feats)
        x = torch.from_numpy(feats_s).unsqueeze(0)
        with torch.no_grad():
            logits = gru(x)
            probs = torch.softmax(logits, dim=1)
            attack_conf = float(probs[0][1])
        label = int(grp["session_label"].iloc[0])
        label_name = grp["session_label_name"].iloc[0]
        records.append({"session_id": sid, "label": label, "label_name": label_name, "attack_conf": attack_conf})
    return pd.DataFrame(records)


def _eval_at_threshold(y_true, y_prob, thresh):
    y_pred = (y_prob >= thresh).astype(int)
    cm = confusion_matrix(y_true, y_pred)
    tn, fp, fn, tp = cm.ravel()
    return {
        "threshold": round(thresh, 4),
        "f1": round(f1_score(y_true, y_pred, zero_division=0), 4),
        "precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
        "recall": round(recall_score(y_true, y_pred, zero_division=0), 4),
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
        "confusion_matrix": cm.tolist(),
    }


def main() -> None:
    cfg = load_config()
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    models_base = Path(cfg.get_path("paths.models_dir", "models"))
    reports_dir = Path(cfg.get_path("paths.reports_dir", "reports"))
    seed = cfg.get_path("project.random_seed", 42)

    adapted_dir = models_base / "nhanh3_gru_v2_adapted"

    df = pd.read_csv(processed_dir / "nhanh3_session_data_cachb.csv")
    df["session_label"] = (df["session_label"] > 0).astype(int)

    gru = GRUSessionClassifier(input_dim=5, hidden_dim=64, num_layers=2, dropout=0.3)
    gru.load_state_dict(
        torch.load(adapted_dir / "session_gru.pt", map_location=DEVICE, weights_only=True)
    )
    gru.eval()
    scaler = joblib.load(adapted_dir / "session_scaler.joblib")

    # Compute per-session confidences
    scores_df = _compute_confidences(df, gru, scaler)

    # Split sessions: 60% val (for threshold tuning), 40% test (held-out)
    session_ids = sorted(scores_df["session_id"].unique())
    labels = scores_df.set_index("session_id").loc[session_ids, "label"].values
    val_ids, test_ids = train_test_split(
        session_ids, test_size=0.4, random_state=seed, stratify=labels,
    )
    val_df = scores_df[scores_df["session_id"].isin(val_ids)]
    test_df = scores_df[scores_df["session_id"].isin(test_ids)]

    logger.info("Val sessions: %d (%d benign, %d attack)",
                len(val_df), int((val_df["label"] == 0).sum()), int((val_df["label"] == 1).sum()))
    logger.info("Test sessions: %d (%d benign, %d attack)",
                len(test_df), int((test_df["label"] == 0).sum()), int((test_df["label"] == 1).sum()))

    # Threshold sweep on VAL set
    thresholds = np.linspace(0.0, 1.0, 1001)
    best_thresh, best_f1 = 0.5, 0.0
    sweep = []
    for thresh in thresholds:
        m = _eval_at_threshold(val_df["label"].values, val_df["attack_conf"].values, thresh)
        sweep.append(m)
        if m["f1"] > best_f1:
            best_f1 = m["f1"]
            best_thresh = thresh

    logger.info("Best threshold on VAL = %.4f with F1 = %.4f", best_thresh, best_f1)

    # Evaluate on held-out TEST set
    test_metrics = _eval_at_threshold(test_df["label"].values, test_df["attack_conf"].values, best_thresh)
    default_metrics = _eval_at_threshold(test_df["label"].values, test_df["attack_conf"].values, 0.5)

    cm_best = test_metrics["confusion_matrix"]
    cm_def = default_metrics["confusion_matrix"]
    logger.info("=== Test set @ thresh=%.4f ===", best_thresh)
    logger.info("F1=%.4f  Prec=%.4f  Rec=%.4f  Acc=%.4f",
                test_metrics["f1"], test_metrics["precision"], test_metrics["recall"], test_metrics["accuracy"])
    logger.info("CM: [[%d %d] [%d %d]]", cm_best[0][0], cm_best[0][1], cm_best[1][0], cm_best[1][1])
    logger.info("Default (0.5) CM on test: [[%d %d] [%d %d]]", cm_def[0][0], cm_def[0][1], cm_def[1][0], cm_def[1][1])

    logger.info("\nVal-set per-session breakdown:")
    for _, row in val_df.sort_values("attack_conf").iterrows():
        pred = "ATTACK" if row["attack_conf"] >= best_thresh else "benign"
        logger.info("  Sess %3d | true=%-7s | conf=%.6f | pred=%-6s",
                    row["session_id"], row["label_name"], row["attack_conf"], pred)

    logger.info("\nTest-set per-session breakdown:")
    for _, row in test_df.sort_values("attack_conf").iterrows():
        pred = "ATTACK" if row["attack_conf"] >= best_thresh else "benign"
        logger.info("  Sess %3d | true=%-7s | conf=%.6f | pred=%-6s",
                    row["session_id"], row["label_name"], row["attack_conf"], pred)

    report = {
        "n_val_sessions": len(val_df),
        "n_test_sessions": len(test_df),
        "best_threshold_val": round(best_thresh, 4),
        "val_metrics_at_best": _eval_at_threshold(val_df["label"].values, val_df["attack_conf"].values, best_thresh),
        "test_metrics_at_best": test_metrics,
        "test_metrics_default_0_5": default_metrics,
        "val_sessions": val_df.to_dict("records"),
        "test_sessions": test_df.to_dict("records"),
        "threshold_sweep_val": [{k: v for k, v in m.items() if k not in ("tn", "fp", "fn", "tp", "confusion_matrix")}
                                for m in sweep if m["threshold"] in [round(t, 4) for t in np.arange(0, 1.01, 0.05)]],
    }

    report_path = reports_dir / "nhanh3_gru_threshold_tune.json"
    with report_path.open("w") as f:
        json.dump(report, f, indent=2)
    logger.info("Report saved to %s", report_path)


if __name__ == "__main__":
    main()
