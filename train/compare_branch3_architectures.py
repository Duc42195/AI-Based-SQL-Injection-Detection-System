"""Branch 3 — architecture comparison (GRU vs LR vs RF vs LGBM vs XGB).

Pattern mirrors train/compare_branch1_architectures.py:
- Consistent train/test split
- Same features (session-level 16-dim aggregates)
- Metrics: F1, accuracy, FPR, detection rates, latency (p50/p95), model size
- Cross-domain A -> B evaluation
- Output: report/metrics/branch3_architecture_comparison.json
"""

from __future__ import annotations

import json, time, warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import classification_report, confusion_matrix, f1_score, accuracy_score

from src.models.branch3_features import prob_columns_in, sessions_to_arrays, evaluate_sessions, class_names_from_config
from src.models.branch3_session import SessionSequenceDetector
from src.utils import load_config, get_logger

from train.branch3_lr_features import session_aggregate_features, session_labels

warnings.filterwarnings("ignore")
logger = get_logger(__name__)

SEED = 42
CLASS_NAMES = ["benign", "boolean_blind", "time_blind", "query_splitting"]
LATENCY_N = 200  # queries for latency benchmark


def measure_latency(predict_one, n: int = LATENCY_N) -> dict:
    """Return p50 and p95 latency in ms over n calls."""
    for _ in range(10):
        predict_one()
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        predict_one()
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    return {"p50_ms": round(times[n // 2], 4), "p95_ms": round(times[int(n * 0.95)], 4)}


def model_size_bytes(save_dir: Path) -> int:
    return sum(f.stat().st_size for f in save_dir.rglob("*") if f.is_file())


def evaluate(y_true, y_pred, class_names):
    labels_present = sorted(set(y_true) | set(y_pred))
    cm = confusion_matrix(y_true, y_pred, labels=labels_present)
    report = classification_report(y_true, y_pred, labels=labels_present,
                                   target_names=[class_names[i] for i in labels_present],
                                   output_dict=True, zero_division=0)
    benign_mask = y_true == 0
    fpr = float((y_pred[benign_mask] != 0).mean()) if benign_mask.any() else None
    detection_rate = {class_names[i]: round(report[class_names[i]]["recall"], 6)
                      for i in range(len(class_names)) if class_names[i] != "benign" and i in labels_present}
    f1 = round(report["macro avg"]["f1-score"], 6)
    acc = round(report["accuracy"], 6)
    return {"f1_macro": f1, "accuracy": acc, "fpr_benign": fpr,
            "detection_rate": detection_rate, "confusion_matrix": cm.tolist()}


def main():
    cfg = load_config()
    reports_dir = Path(cfg["paths"]["reports_dir"])
    if not reports_dir.is_absolute():
        ROOT = Path.cwd()
        for _ in range(5):
            if (ROOT / "report").exists():
                break
            ROOT = ROOT.parent
        reports_dir = ROOT / reports_dir
    processed_dir = ROOT / Path(cfg["paths"]["data_processed"])
    models_dir = ROOT / Path(cfg["paths"]["models_dir"])
    out_path = reports_dir / "branch3_architecture_comparison.json"

    # ---- Load data ----
    logger.info("Loading data...")
    df_a = pd.read_csv(processed_dir / "branch3_sessions_cach_a.csv")
    df_b = pd.read_csv(processed_dir / "branch3_sessions_cach_b_v2.csv")
    for df in [df_a, df_b]:
        df["gap_seconds_log1p"] = np.log1p(df["gap_seconds"])

    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED)
    ti, te = next(gss.split(df_b, groups=df_b["session_id"]))
    df_b["split"] = "train"
    df_b.loc[te, "split"] = "test"

    df_ab = pd.concat([df_a, df_b], ignore_index=True)
    train_df = df_ab[df_ab["split"] == "train"].copy()
    test_df = df_ab[df_ab["split"] == "test"].copy()
    feature_cols = prob_columns_in(df_a) + ["branch2_anomaly_score", "gap_seconds_log1p"]

    # Session-level features
    logger.info("Building session-level features...")
    X_train = session_aggregate_features(train_df, feature_cols)
    y_train = session_labels(train_df)
    X_test = session_aggregate_features(test_df, feature_cols)
    y_test = session_labels(test_df)
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    n_train = int(len(X_train))
    n_test = int(len(X_test))
    logger.info("Train sessions: %d, Test sessions: %d", n_train, n_test)

    # Cross-domain A->B data
    train_A_only = df_ab[df_ab["split"] == "train"]
    train_A_only = train_A_only[train_A_only["session_id"].str.startswith("cachA_")]
    test_B_only = df_b[df_b["split"] == "test"]
    X_crossA = session_aggregate_features(train_A_only, feature_cols)
    y_crossA = session_labels(train_A_only)
    X_crossB = session_aggregate_features(test_B_only, feature_cols)
    y_crossB = session_labels(test_B_only)
    scaler_cross = StandardScaler()
    X_crossA_s = scaler_cross.fit_transform(X_crossA)
    X_crossB_s = scaler_cross.transform(X_crossB)

    results: dict[str, dict] = {}

    # ---- 1. GRU ----
    logger.info("=" * 50)
    logger.info("[1/5] GRU (existing model)")
    det_gru = SessionSequenceDetector.load(models_dir / "branch3_v1_hybrid_AB_v3")
    X_test_seq, y_test_seq = sessions_to_arrays(test_df, feature_cols)
    pred_gru = det_gru.predict(X_test_seq)

    # GRU cross-domain
    X_crossB_seq, y_crossB_seq = sessions_to_arrays(test_B_only, feature_cols)
    pred_gru_cross = det_gru.predict(X_crossB_seq)
    cross_gru = evaluate(y_crossB_seq, pred_gru_cross, CLASS_NAMES)
    # GRU cross A->B (train on A only)
    X_crossA_seq, _ = sessions_to_arrays(train_A_only, feature_cols)
    from src.models.branch3_session import SessionSequenceDetector as SSD
    det_gru_cross = SSD(input_dim=len(feature_cols), hidden_dim=32, num_classes=4,
                        class_names=CLASS_NAMES, random_seed=SEED, max_len=64)
    det_gru_cross.fit(X_crossA_seq, y_crossA, epochs=30, lr=0.001, batch_size=16)
    pred_gru_cross_only = det_gru_cross.predict(X_crossB_seq)
    cross_gru_A2B = evaluate(y_crossB_seq, pred_gru_cross_only, CLASS_NAMES)

    def infer_gru():
        det_gru.predict([X_test_seq[0]])
    lat_gru = measure_latency(infer_gru)
    size_gru = model_size_bytes(models_dir / "branch3_v1_hybrid_AB_v3")

    metrics_gru = evaluate(y_test_seq, pred_gru, CLASS_NAMES)
    results["GRU"] = {**metrics_gru, "latency": lat_gru, "size_bytes": size_gru,
                      "cross_A2B_f1": cross_gru_A2B["f1_macro"]}

    logger.info("  F1=%.4f  cross_A2B=%.4f  p50=%.2fms  size=%dKB",
                metrics_gru["f1_macro"], cross_gru_A2B["f1_macro"], lat_gru["p50_ms"], size_gru // 1024)

    # ---- 2. LogisticRegression ----
    logger.info("[2/5] LogisticRegression")
    lr = LogisticRegression(solver="lbfgs", max_iter=1000, random_state=SEED)
    lr.fit(X_train_s, y_train)
    pred_lr = lr.predict(X_test_s)
    lr_cross = LogisticRegression(solver="lbfgs", max_iter=1000, random_state=SEED)
    lr_cross.fit(X_crossA_s, y_crossA)
    pred_lr_cross = lr_cross.predict(X_crossB_s)
    cross_lr = evaluate(y_crossB, pred_lr_cross, CLASS_NAMES)

    def infer_lr():
        lr.predict(X_test_s[:1])
    lat_lr = measure_latency(infer_lr)

    metrics_lr = evaluate(y_test, pred_lr, CLASS_NAMES)
    results["LogisticRegression"] = {**metrics_lr, "latency": lat_lr, "size_bytes": 0,
                                     "cross_A2B_f1": cross_lr["f1_macro"]}

    logger.info("  F1=%.4f  cross_A2B=%.4f  p50=%.2fms",
                metrics_lr["f1_macro"], cross_lr["f1_macro"], lat_lr["p50_ms"])

    # ---- 3. RandomForest ----
    logger.info("[3/5] RandomForest")
    rf = RandomForestClassifier(n_estimators=200, max_depth=16, random_state=SEED, n_jobs=-1)
    rf.fit(X_train_s, y_train)
    pred_rf = rf.predict(X_test_s)
    rf_cross = RandomForestClassifier(n_estimators=200, max_depth=16, random_state=SEED, n_jobs=-1)
    rf_cross.fit(X_crossA_s, y_crossA)
    pred_rf_cross = rf_cross.predict(X_crossB_s)
    cross_rf = evaluate(y_crossB, pred_rf_cross, CLASS_NAMES)

    def infer_rf():
        rf.predict(X_test_s[:1])
    lat_rf = measure_latency(infer_rf)

    metrics_rf = evaluate(y_test, pred_rf, CLASS_NAMES)
    results["RandomForest"] = {**metrics_rf, "latency": lat_rf, "size_bytes": 0,
                               "cross_A2B_f1": cross_rf["f1_macro"]}

    logger.info("  F1=%.4f  cross_A2B=%.4f  p50=%.2fms",
                metrics_rf["f1_macro"], cross_rf["f1_macro"], lat_rf["p50_ms"])

    # ---- 4. LightGBM ----
    logger.info("[4/5] LightGBM")
    import lightgbm as lgb
    lgbm = lgb.LGBMClassifier(objective="multiclass", num_class=4, n_estimators=200,
                              max_depth=8, random_state=SEED, verbose=-1)
    lgbm.fit(X_train_s, y_train)
    pred_lgbm = lgbm.predict(X_test_s)
    lgbm_cross = lgb.LGBMClassifier(objective="multiclass", num_class=4, n_estimators=200,
                                    max_depth=8, random_state=SEED, verbose=-1)
    lgbm_cross.fit(X_crossA_s, y_crossA)
    pred_lgbm_cross = lgbm_cross.predict(X_crossB_s)
    cross_lgbm = evaluate(y_crossB, pred_lgbm_cross, CLASS_NAMES)

    def infer_lgbm():
        lgbm.predict(X_test_s[:1])
    lat_lgbm = measure_latency(infer_lgbm)

    metrics_lgbm = evaluate(y_test, pred_lgbm, CLASS_NAMES)
    results["LightGBM"] = {**metrics_lgbm, "latency": lat_lgbm, "size_bytes": 0,
                           "cross_A2B_f1": cross_lgbm["f1_macro"]}

    logger.info("  F1=%.4f  cross_A2B=%.4f  p50=%.2fms",
                metrics_lgbm["f1_macro"], cross_lgbm["f1_macro"], lat_lgbm["p50_ms"])

    # ---- 5. XGBoost ----
    logger.info("[5/5] XGBoost")
    import xgboost as xgb
    xgb_model = xgb.XGBClassifier(objective="multi:softmax", num_class=4, n_estimators=200,
                                  max_depth=8, random_state=SEED, verbosity=0)
    xgb_model.fit(X_train_s, y_train)
    pred_xgb = xgb_model.predict(X_test_s)
    xgb_cross = xgb.XGBClassifier(objective="multi:softmax", num_class=4, n_estimators=200,
                                  max_depth=8, random_state=SEED, verbosity=0)
    xgb_cross.fit(X_crossA_s, y_crossA)
    pred_xgb_cross = xgb_cross.predict(X_crossB_s)
    cross_xgb = evaluate(y_crossB, pred_xgb_cross, CLASS_NAMES)

    def infer_xgb():
        xgb_model.predict(X_test_s[:1])
    lat_xgb = measure_latency(infer_xgb)

    metrics_xgb = evaluate(y_test, pred_xgb, CLASS_NAMES)
    results["XGBoost"] = {**metrics_xgb, "latency": lat_xgb, "size_bytes": 0,
                          "cross_A2B_f1": cross_xgb["f1_macro"]}

    logger.info("  F1=%.4f  cross_A2B=%.4f  p50=%.2fms",
                metrics_xgb["f1_macro"], cross_xgb["f1_macro"], lat_xgb["p50_ms"])

    # ---- Summary table ----
    logger.info("=" * 80)
    logger.info("%-20s %-10s %-10s %-12s %-12s %-10s", "Model", "F1", "CrossA2B", "p50(ms)", "p95(ms)", "Size(KB)")
    logger.info("-" * 80)
    for name, r in results.items():
        lat = r.get("latency", {})
        p50 = lat.get("p50_ms", 0)
        p95 = lat.get("p95_ms", 0)
        sz = r.get("size_bytes", 0) // 1024
        cross = r.get("cross_A2B_f1", 0)
        logger.info("%-20s %-10.4f %-10.4f %-12.2f %-12.2f %-10d", name, r["f1_macro"], cross, p50, p95, sz)

    # ---- Final artifact ----
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    logger.info("Saved to %s", out_path)

    # ---- Recommendation ----
    best_cross = max(results.items(), key=lambda kv: kv[1].get("cross_A2B_f1", 0))
    best_f1 = max(results.items(), key=lambda kv: kv[1]["f1_macro"])
    logger.info("=" * 80)
    logger.info("Best F1 on hybrid:       %s (F1=%.4f)", best_f1[0], best_f1[1]["f1_macro"])
    logger.info("Best cross-domain A->B:  %s (F1=%.4f)", best_cross[0], best_cross[1]["cross_A2B_f1"])


if __name__ == "__main__":
    main()
