"""Generate comprehensive metrics for both Nhánh 1 and Nhánh 2.

Produces:
- reports/nhanh1_eval.json (updated with per-class ROC curves)
- reports/nhanh2_eval.json (updated with PR curve, confusion matrix)
- reports/nhanh2_threshold_sweep.csv
- reports/figures/ (6+ PNG figures for the report)
"""

from __future__ import annotations

import csv, json, os, warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from datasets import load_dataset
from sklearn.metrics import (
    accuracy_score, auc, confusion_matrix, precision_recall_curve,
    average_precision_score, roc_curve, roc_auc_score, classification_report,
)
from sklearn.preprocessing import LabelBinarizer

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams

from src.models.nhanh2_anomaly import AnomalyDetector
from src.preprocessing.multiclass_tagger import LABEL_NAMES
from src.preprocessing.statistical_features import extract_statistical_features
from src.utils import get_logger, load_config

warnings.filterwarnings("ignore")
logger = get_logger(__name__)

rcParams.update({
    "font.family": "serif",
    "font.serif": ["DejaVu Serif", "Times New Roman"],
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "axes.grid": False,
})

PROJECT = Path(__file__).resolve().parent.parent
FIGURES_DIR = PROJECT / "report" / "metrics" / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)


# ─── Nhánh 1: Per-class ROC curves ────────────────────────────────────────────


def load_nhanh1_model_and_data():
    logger.info("[Nhánh 1] Loading model from models/nhanh1_v1/")
    vectorizer = joblib.load(PROJECT / "models/nhanh1_v1" / "vectorizer.joblib")
    clf = joblib.load(PROJECT / "models/nhanh1_v1" / "model.joblib")

    logger.info("[Nhánh 1] Loading test data from HF ...")
    ds = load_dataset(
        "Jason-42195/VNU-SQLi-Detection",
        data_files="nhanh1_train.csv",
        split="train",
    )
    df = ds.to_pandas()
    # Use same test split as training (20% stratified)
    test_df = df[df["split"] == "test"].copy()
    logger.info("[Nhánh 1] Test rows: %d", len(test_df))
    return vectorizer, clf, test_df


def compute_nhanh1_roc_per_class(clf, vectorizer, test_df):
    logger.info("[Nhánh 1] Computing per-class ROC curves ...")
    X_test = vectorizer.transform(test_df["query_canonical"].astype(str))
    y_test = test_df["label"].to_numpy()

    if hasattr(clf, "predict_proba"):
        y_score = clf.predict_proba(X_test)
    elif hasattr(clf, "decision_function"):
        y_score = clf.decision_function(X_test)
        n_classes = len(np.unique(y_test))
        if y_score.ndim == 1:
            y_score = np.column_stack([-y_score, y_score])
    else:
        raise ValueError("Model has neither predict_proba nor decision_function")

    classes = sorted(np.unique(y_test))
    lb = LabelBinarizer()
    lb.fit(classes)
    y_bin = lb.transform(y_test)

    roc_data = {}
    fig, ax = plt.subplots(figsize=(5, 4.5))
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]

    for i, cls in enumerate(classes):
        fpr, tpr, _ = roc_curve(y_bin[:, i], y_score[:, i])
        roc_auc = auc(fpr, tpr)
        roc_data[str(cls)] = {
            "label": LABEL_NAMES[cls],
            "fpr": fpr.tolist(),
            "tpr": tpr.tolist(),
            "auc": round(roc_auc, 4),
        }
        ax.plot(
            fpr, tpr, color=colors[i % len(colors)], lw=1.5,
            label=f"{LABEL_NAMES[cls]} (AUC={roc_auc:.3f})",
        )

    ax.plot([0, 1], [0, 1], "k--", lw=0.8, alpha=0.6)
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("Nhánh 1 — ROC Curves per Class")
    ax.legend(loc="lower right", fontsize=8)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    fig.savefig(FIGURES_DIR / "nhanh1_roc_per_class.png")
    plt.close(fig)
    logger.info("[Nhánh 1] ROC curves saved")
    return roc_data


def update_nhanh1_eval(roc_data):
    eval_path = PROJECT / "report" / "metrics" / "nhanh1_eval.json"
    with eval_path.open("r", encoding="utf-8") as f:
        report = json.load(f)
    report["roc_curves_per_class"] = roc_data
    report["eval_note"] = (
        "Per-class ROC curves added on 21/7 for report figures. "
        "Model unchanged from 16/7 training."
    )
    with eval_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    logger.info("[Nhánh 1] Updated %s", eval_path)


# ─── Nhánh 2: PR curve, confusion matrix, per-class DR, threshold sweep ──────


def load_nhanh2_model_and_data():
    logger.info("[Nhánh 2] Loading model from models/nhanh2_v1/")
    detector = AnomalyDetector.load(PROJECT / "models" / "nhanh2_v1")

    logger.info("[Nhánh 2] Loading eval data ...")
    data_dir = PROJECT / "data" / "processed"
    benign_df = pd.read_csv(data_dir / "nhanh2_data.csv")
    test_benign = benign_df[benign_df["split"] == "test"].copy()
    anom_df = pd.read_csv(data_dir / "nhanh2_anomalous_eval.csv")

    logger.info("[Nhánh 2] Test benign: %d | Anomalous: %d", len(test_benign), len(anom_df))
    return detector, test_benign, anom_df


def compute_nhanh2_metrics(detector, test_benign, anom_df):
    logger.info("[Nhánh 2] Computing features ...")
    feat_names = ["length", "special_char_ratio", "sql_keyword_count", "entropy"]

    X_benign = test_benign[feat_names].to_numpy()
    X_anom = anom_df[feat_names].to_numpy()

    # Combine
    X_all = np.vstack([X_benign, X_anom])
    y_all = np.array([0] * len(X_benign) + [1] * len(X_anom))

    # Scores (higher = more anomalous)
    scores_all = detector.score(X_all)

    # ── PR Curve ──
    logger.info("[Nhánh 2] Computing PR curve ...")
    precision, recall, pr_thresholds = precision_recall_curve(y_all, scores_all)
    avg_prec = average_precision_score(y_all, scores_all)

    fig, ax = plt.subplots(figsize=(5, 4.5))
    ax.plot(recall, precision, color="#2ca02c", lw=1.5, label=f"AP={avg_prec:.3f}")
    ax.axhline(y=y_all.sum() / len(y_all), color="gray", ls="--", lw=0.8, alpha=0.6)
    ax.set_xlabel("Recall (Detection Rate)")
    ax.set_ylabel("Precision")
    ax.set_title("Nhánh 2 — Precision-Recall Curve")
    ax.legend(loc="upper right")
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    fig.savefig(FIGURES_DIR / "nhanh2_pr_curve.png")
    plt.close(fig)
    logger.info("[Nhánh 2] PR curve saved (AP=%.4f)", avg_prec)

    # ── Confusion Matrix at current threshold (OCSVM default) ──
    predictions = detector.predict(X_all)  # 1 = normal, -1 = anomaly
    y_pred_binary = np.where(predictions == -1, 1, 0)
    cm = confusion_matrix(y_all, y_pred_binary)

    tn, fp, fn, tp = cm.ravel()
    fpr_val = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    dr_val = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    logger.info("[Nhánh 2] CM: TN=%d FP=%d FN=%d TP=%d", tn, fp, fn, tp)
    logger.info("[Nhánh 2] FPR=%.4f  DR=%.4f", fpr_val, dr_val)

    # ── Per-class Detection Rate ──
    logger.info("[Nhánh 2] Computing per-class DR ...")
    anom_predictions = detector.predict(X_anom)
    anom_pred_binary = np.where(anom_predictions == -1, 1, 0)
    anom_df = anom_df.copy()
    anom_df["pred_anomaly"] = anom_pred_binary

    per_class_dr = {}
    if "source" in anom_df.columns:
        for label in sorted(anom_df["source"].unique()):
            subset = anom_df[anom_df["source"] == label]
            if len(subset) == 0:
                continue
            detected = subset["pred_anomaly"].sum()
            dr = detected / len(subset)
            per_class_dr[str(label)] = {
                "total": int(len(subset)),
                "detected": int(detected),
                "dr": round(dr, 4),
            }
            logger.info("  %s: DR=%.4f (%d/%d)", label, dr, detected, len(subset))

    # ── Threshold Sweep ──
    logger.info("[Nhánh 2] Computing threshold sweep ...")
    benign_scores = scores_all[: len(X_benign)]
    anom_scores = scores_all[len(X_benign) :]

    thresholds = sorted(
        set(np.percentile(scores_all, [5, 10, 20, 30, 40, 50, 60, 70, 80, 85, 90, 92, 94, 95, 96, 97, 98, 99]))
        | {0.0}
        | {float(np.min(scores_all)), float(np.max(scores_all))}
    )

    sweep_rows = []
    for thresh in reversed(sorted(thresholds)):
        fp_at = int((benign_scores > thresh).sum())
        tp_at = int((anom_scores > thresh).sum())
        fn_at = len(anom_scores) - tp_at
        tn_at = len(benign_scores) - fp_at
        fpr_at = fp_at / len(benign_scores) if len(benign_scores) > 0 else 0.0
        dr_at = tp_at / len(anom_scores) if len(anom_scores) > 0 else 0.0
        prec_at = tp_at / (tp_at + fp_at) if (tp_at + fp_at) > 0 else 0.0
        sweep_rows.append({
            "threshold": round(thresh, 6),
            "fpr": round(fpr_at, 4),
            "dr": round(dr_at, 4),
            "precision": round(prec_at, 4),
            "fp_count": fp_at,
            "tp_count": tp_at,
            "tn_count": tn_at,
            "fn_count": fn_at,
        })

    # Identify current default threshold score (approx)
    current_thresh_approx = float(np.percentile(benign_scores, fpr_val * 100))
    logger.info("[Nhánh 2] Current approx threshold: %.6f (FPR=%.4f)", current_thresh_approx, fpr_val)

    # Save sweep CSV
    sweep_path = PROJECT / "report" / "metrics" / "nhanh2_threshold_sweep.csv"
    with sweep_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=sweep_rows[0].keys())
        writer.writeheader()
        writer.writerows(sweep_rows)
    logger.info("[Nhánh 2] Threshold sweep saved to %s (%d rows)", sweep_path, len(sweep_rows))

    # ── Threshold Trade-off Plot ──
    fig, ax1 = plt.subplots(figsize=(5, 4.5))
    fpr_vals = [r["fpr"] for r in sweep_rows]
    dr_vals = [r["dr"] for r in sweep_rows]
    thresh_vals = [r["threshold"] for r in sweep_rows]
    ax1.plot(thresh_vals, fpr_vals, color="#d62728", lw=1.5, label="FPR")
    ax1.plot(thresh_vals, dr_vals, color="#2ca02c", lw=1.5, label="Detection Rate")
    ax1.axvline(x=current_thresh_approx, color="gray", ls="--", lw=0.8, alpha=0.5)
    ax1.set_xlabel("Anomaly Threshold (higher = more strict)")
    ax1.set_ylabel("Rate")
    ax1.set_title("Nhánh 2 — Threshold Trade-off")
    ax1.legend(loc="center right")
    ax1.set_xlim(min(thresh_vals), max(thresh_vals))
    fig.savefig(FIGURES_DIR / "nhanh2_threshold_tradeoff.png")
    plt.close(fig)
    logger.info("[Nhánh 2] Threshold trade-off plot saved")

    # ── Score Distribution ──
    fig, ax = plt.subplots(figsize=(5, 4.5))
    ax.hist(benign_scores, bins=50, alpha=0.7, color="#1f77b4", label=f"Benign (n={len(benign_scores)})")
    ax.hist(anom_scores, bins=50, alpha=0.6, color="#d62728", label=f"Anomalous (n={len(anom_scores)})")
    ax.axvline(x=current_thresh_approx, color="gray", ls="--", lw=1, alpha=0.7)
    ax.set_xlabel("Anomaly Score")
    ax.set_ylabel("Frequency")
    ax.set_title("Nhánh 2 — Score Distribution")
    ax.legend(fontsize=8)
    fig.savefig(FIGURES_DIR / "nhanh2_score_dist.png")
    plt.close(fig)
    logger.info("[Nhánh 2] Score distribution saved")

    return {
        "avg_precision": round(float(avg_prec), 4),
        "pr_curve": {
            "precision": precision.tolist(),
            "recall": recall.tolist(),
        },
        "confusion_matrix": {
            "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
            "fpr": round(float(fpr_val), 4),
            "dr": round(float(dr_val), 4),
        },
        "per_class_dr": per_class_dr,
        "threshold_sweep": sweep_path.name,
    }


def update_nhanh2_eval(new_metrics):
    eval_path = PROJECT / "report" / "metrics" / "nhanh2_eval.json"
    with eval_path.open("r", encoding="utf-8") as f:
        report = json.load(f)
    report["precision_recall"] = new_metrics["pr_curve"]
    report["average_precision"] = new_metrics["avg_precision"]
    report["confusion_matrix"] = new_metrics["confusion_matrix"]
    report["per_class_detection_rate"] = new_metrics["per_class_dr"]
    report["threshold_sweep_file"] = new_metrics["threshold_sweep"]
    report["eval_note"] = (
        "PR curve, confusion matrix, per-class DR, and threshold sweep "
        "added on 21/7 for report. Model retrained with same config."
    )
    with eval_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    logger.info("[Nhánh 2] Updated %s", eval_path)


# ─── Main ─────────────────────────────────────────────────────────────────────


def main():
    logger.info("=" * 60)
    logger.info("Generating comprehensive metrics for report")
    logger.info("=" * 60)

    # ── Nhánh 1 ──
    vectorizer, clf, test_df = load_nhanh1_model_and_data()
    roc_data = compute_nhanh1_roc_per_class(clf, vectorizer, test_df)
    update_nhanh1_eval(roc_data)

    # ── Nhánh 2 ──
    detector, test_benign, anom_df = load_nhanh2_model_and_data()
    new_metrics = compute_nhanh2_metrics(detector, test_benign, anom_df)
    update_nhanh2_eval(new_metrics)

    logger.info("=" * 60)
    logger.info("All metrics generated. Figures saved to %s", FIGURES_DIR)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
