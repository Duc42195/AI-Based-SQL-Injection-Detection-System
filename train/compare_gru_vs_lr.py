"""Compare GRU vs LogisticRegression on session-level classification.

Runs both models on the same train/test split, measures F1, accuracy, FPR,
latency, and (for LR) coefficient interpretability.
"""

from __future__ import annotations

import json, time, warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import classification_report, confusion_matrix, f1_score, accuracy_score

from src.models.branch3_features import prob_columns_in, sessions_to_arrays, evaluate_sessions, class_names_from_config
from src.models.branch3_session import SessionSequenceDetector
from src.utils import load_config, get_logger

from train.branch3_lr_features import session_aggregate_features, feature_names_out, session_labels

warnings.filterwarnings("ignore")
logger = get_logger(__name__)

SEED = 42
CLASS_NAMES = ["benign", "boolean_blind", "time_blind", "query_splitting"]
N_TRIALS = 5  # repeat both models N times for stable latency


def latency_ms(fn, n: int = 100) -> float:
    """Mean latency in milliseconds over ``n`` calls."""
    # warmup
    for _ in range(10):
        fn()
    start = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - start) / n * 1000


def main():
    cfg = load_config()
    models_dir = Path(cfg["paths"]["models_dir"])
    processed_dir = Path(cfg["paths"]["data_processed"])
    if not processed_dir.is_absolute():
        ROOT = Path.cwd()
        for _ in range(5):
            if (ROOT / "report").exists():
                break
            ROOT = ROOT.parent
        processed_dir = ROOT / processed_dir
        models_dir = ROOT / models_dir
    reports_dir = Path(cfg["paths"]["reports_dir"])
    if not reports_dir.is_absolute():
        reports_dir = ROOT / reports_dir

    # ---- Load data ----
    logger.info("Loading data...")
    df_a = pd.read_csv(processed_dir / "branch3_sessions_cach_a.csv")
    df_b = pd.read_csv(processed_dir / "branch3_sessions_cach_b_v2.csv")
    for df in [df_a, df_b]:
        df["gap_seconds_log1p"] = np.log1p(df["gap_seconds"])

    # consistent stratified split
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED)
    ti, te = next(gss.split(df_b, groups=df_b["session_id"]))
    df_b["split"] = "train"
    df_b.loc[te, "split"] = "test"

    df_ab = pd.concat([df_a, df_b], ignore_index=True)
    train_df = df_ab[df_ab["split"] == "train"].copy()
    test_df = df_ab[df_ab["split"] == "test"].copy()

    feature_cols = prob_columns_in(df_a) + ["branch2_anomaly_score", "gap_seconds_log1p"]
    logger.info("Train: %d sessions, Test: %d sessions", train_df["session_id"].nunique(), test_df["session_id"].nunique())

    # ---- 1. GRU baseline ----
    logger.info("=" * 50)
    logger.info("1. GRU baseline")
    det = SessionSequenceDetector.load(models_dir / "branch3_v1_hybrid_AB_v3")
    X_test_seq, y_test = sessions_to_arrays(test_df, feature_cols)
    X_train_seq, y_train = sessions_to_arrays(train_df, feature_cols)

    pred_gru = det.predict(X_test_seq)
    gru_f1 = f1_score(y_test, pred_gru, average="macro")
    gru_acc = accuracy_score(y_test, pred_gru)
    gru_metrics = evaluate_sessions(det, X_test_seq, y_test, CLASS_NAMES)

    # latency: single session
    def infer_gru():
        det.predict([X_test_seq[0]])
    gru_lat = latency_ms(infer_gru, n=N_TRIALS)

    logger.info("  F1=%.4f  Acc=%.4f  FPR=%.4f  latency=%.3fms", gru_f1, gru_acc, gru_metrics["fpr_benign"], gru_lat)

    # ---- 2. LogisticRegression ----
    logger.info("2. LogisticRegression (session-level features)")
    X_train_agg = session_aggregate_features(train_df, feature_cols)
    y_train_agg = session_labels(train_df)
    X_test_agg = session_aggregate_features(test_df, feature_cols)
    y_test_agg = session_labels(test_df)
    feat_names = feature_names_out(feature_cols)

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_agg)
    X_test_scaled = scaler.transform(X_test_agg)

    lr = LogisticRegression(solver="lbfgs", max_iter=1000, random_state=SEED)
    lr.fit(X_train_scaled, y_train_agg)
    pred_lr = lr.predict(X_test_scaled)
    lr_f1 = f1_score(y_test_agg, pred_lr, average="macro")
    lr_acc = accuracy_score(y_test_agg, pred_lr)

    lr_cm = confusion_matrix(y_test_agg, pred_lr, labels=list(range(4)))
    benign_mask = y_test_agg == 0
    lr_fpr = float((pred_lr[benign_mask] != 0).mean()) if benign_mask.any() else None

    # per-class
    lr_report = classification_report(y_test_agg, pred_lr, labels=list(range(4)), target_names=CLASS_NAMES, output_dict=True, zero_division=0)
    lr_detection_rate = {n: round(lr_report[n]["recall"], 6) for n in CLASS_NAMES if n != "benign"}

    lr_metrics = {
        "n_test_sessions": int(len(y_test_agg)),
        "confusion_matrix": lr_cm.tolist(),
        "labels": CLASS_NAMES,
        "f1_macro": round(lr_f1, 6),
        "accuracy": round(lr_acc, 6),
        "per_class": {n: {"precision": round(lr_report[n]["precision"], 6), "recall": round(lr_report[n]["recall"], 6), "f1": round(lr_report[n]["f1-score"], 6), "support": int(lr_report[n]["support"])} for n in CLASS_NAMES},
        "fpr_benign": round(lr_fpr, 6) if lr_fpr is not None else None,
        "detection_rate": lr_detection_rate,
    }

    def infer_lr():
        scaler.transform(X_test_agg[:1])
        lr.predict(scaler.transform(X_test_agg[:1]))
    lr_lat = latency_ms(infer_lr, n=N_TRIALS)

    logger.info("  F1=%.4f  Acc=%.4f  FPR=%.4f  latency=%.3fms", lr_f1, lr_acc, lr_fpr or 0.0, lr_lat)

    # ---- 3. LogisticRegression with full features (all 7 * mean+std+max+slope) ----
    logger.info("3. LR full (mean + std + max + slope for all features)")
    def session_full_features(df, cols):
        rows = []
        for _sid, group in df.sort_values("step_index").groupby("session_id", sort=False):
            f = group[cols].to_numpy(dtype=np.float32)
            vec = list(f.mean(axis=0)) + list(f.std(axis=0)) + list(f.max(axis=0))
            if f.shape[0] > 1:
                slopes = [float(np.polyfit(np.arange(f.shape[0]), f[:, i], 1)[0]) for i in range(len(cols))]
            else:
                slopes = [0.0] * len(cols)
            vec.extend(slopes)
            rows.append(np.array(vec, dtype=np.float32))
        return np.array(rows)

    X_train_full = session_full_features(train_df, feature_cols)
    X_test_full = session_full_features(test_df, feature_cols)
    scaler_full = StandardScaler()
    X_train_full_s = scaler_full.fit_transform(X_train_full)
    X_test_full_s = scaler_full.transform(X_test_full)

    lr_full = LogisticRegression(solver="lbfgs", max_iter=1000, random_state=SEED)
    lr_full.fit(X_train_full_s, y_train_agg)
    pred_lr_full = lr_full.predict(X_test_full_s)
    lr_full_f1 = f1_score(y_test_agg, pred_lr_full, average="macro")
    lr_full_acc = accuracy_score(y_test_agg, pred_lr_full)
    lr_full_cm = confusion_matrix(y_test_agg, pred_lr_full, labels=list(range(4)))
    logger.info("  F1=%.4f  Acc=%.4f", lr_full_f1, lr_full_acc)

    # ---- 4. Coefficients ----
    logger.info("4. LR coefficients (top features)")
    coefs = lr.coef_  # (n_classes, n_features)
    for ci, cname in enumerate(CLASS_NAMES):
        top_idx = np.argsort(np.abs(coefs[ci]))[-5:]
        top_feats = [(feat_names[i], float(coefs[ci, i])) for i in top_idx]
        logger.info("  %s: %s", cname, top_feats)

    # ---- 5. Cross-domain: train on A only, test on B ----
    logger.info("5. Cross-domain A -> B")
    train_A = df_ab[df_ab["split"] == "train"]
    test_B = df_b[df_b["split"] == "test"]
    X_a = session_aggregate_features(train_A[train_A["session_id"].str.startswith("cachA_")], feature_cols)
    y_a = session_labels(train_A[train_A["session_id"].str.startswith("cachA_")])
    X_b = session_aggregate_features(test_B, feature_cols)
    y_b = session_labels(test_B)

    scaler_cross = StandardScaler()
    X_a_s = scaler_cross.fit_transform(X_a)
    X_b_s = scaler_cross.transform(X_b)
    lr_cross = LogisticRegression(solver="lbfgs", max_iter=1000, random_state=SEED)
    lr_cross.fit(X_a_s, y_a)
    pred_cross = lr_cross.predict(X_b_s)
    cross_f1 = f1_score(y_b, pred_cross, average="macro")
    cross_acc = accuracy_score(y_b, pred_cross)
    cross_fpr = float((pred_cross[y_b == 0] != 0).mean()) if (y_b == 0).any() else None
    logger.info("  F1=%.4f  Acc=%.4f  FPR=%.4f", cross_f1, cross_acc, cross_fpr or 0.0)

    # ---- Summary ----
    summary = {
        "comparison": {
            "GRU": {"f1_macro": gru_f1, "accuracy": gru_acc, "fpr_benign": gru_metrics["fpr_benign"], "latency_ms": round(gru_lat, 4)},
            "LR_16feat": {"f1_macro": lr_f1, "accuracy": lr_acc, "fpr_benign": lr_fpr, "latency_ms": round(lr_lat, 4)},
            "LR_28feat": {"f1_macro": lr_full_f1, "accuracy": lr_full_acc},
            "LR_cross_A2B": {"f1_macro": cross_f1, "accuracy": cross_acc, "fpr_benign": cross_fpr},
        },
        "feature_names": feat_names,
        "coefficients": {CLASS_NAMES[ci]: {feat_names[i]: round(float(coefs[ci, i]), 6) for i in range(len(feat_names))} for ci in range(4)},
        "conclusion": "",
    }

    if lr_f1 >= gru_f1 - 0.005:
        summary["conclusion"] = "LR matches or beats GRU on F1. Swap GRU -> LR recommended (faster, simpler, interpretable)."
    else:
        summary["conclusion"] = f"GRU still outperforms LR ({gru_f1:.4f} vs {lr_f1:.4f}). Keep GRU or try XGBoost."

    out_path = reports_dir / "branch3_gru_vs_lr.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("Results saved to %s", out_path)
    logger.info("=" * 50)
    logger.info(summary["conclusion"])


if __name__ == "__main__":
    main()
