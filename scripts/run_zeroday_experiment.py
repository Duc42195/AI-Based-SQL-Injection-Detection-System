"""Zero-day detection experiment for Branch 2.

Leave-one-out protocol:
  For each SQLi label {union_based, error_based, boolean_blind, time_blind}:
    1. Train Branch 1 WITHOUT that label (4-class classifier on remaining types).
    2. Feed the excluded label's queries to both Branch 1 and Branch 2.
    3. Measure: does Branch 2 catch what Branch 1 was never trained to see?

Metrics per excluded label:
  - Branch 1 miss rate (% predicted as normal — the attack bypasses supervised).
  - Branch 2 detection rate (% flagged anomalous — zero-day caught).
  - Combined coverage (% caught by at least one branch).
"""

from __future__ import annotations

import json
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report

from src.models.nhanh2_anomaly import AnomalyDetector
from src.preprocessing.statistical_features import extract_statistical_features
from src.preprocessing.multiclass_tagger import LABEL_NAMES
from src.utils import get_logger, load_config

warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")
logger = get_logger(__name__)

# Labels we test: skip label 0 (normal) — we only care about SQLi types.
EXCLUDED_LABELS = [1, 2, 3, 4]  # union_based, error_based, boolean_blind, time_blind


def train_nhanh1_exclude(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    exclude_label: int,
    cfg,
) -> tuple[TfidfVectorizer, LogisticRegression, float]:
    """Train Branch 1 (TF-IDF + LogReg) excluding one label.

    Returns:
        (vectorizer, classifier, f1_macro) on the reduced label set.
    """
    # Filter out the excluded label
    train_mask = train_df["label"] != exclude_label
    test_mask = test_df["label"] != exclude_label

    train_subset = train_df[train_mask].reset_index(drop=True)
    test_subset = test_df[test_mask].reset_index(drop=True)

    tfidf_cfg = cfg.get_path("branch1_supervised.tfidf")
    vectorizer = TfidfVectorizer(
        analyzer=tfidf_cfg["analyzer"],
        ngram_range=(tfidf_cfg["ngram_min"], tfidf_cfg["ngram_max"]),
        max_features=tfidf_cfg["max_features"],
    )

    X_train = vectorizer.fit_transform(train_subset["query_canonical"].astype(str))
    clf = LogisticRegression(max_iter=1000)
    clf.fit(X_train, train_subset["label"].to_numpy())

    X_test = vectorizer.transform(test_subset["query_canonical"].astype(str))
    labels_present = sorted(set(train_subset["label"]) | set(test_subset["label"]))
    target_names = [LABEL_NAMES[i] for i in labels_present]
    report = classification_report(
        test_subset["label"].to_numpy(),
        clf.predict(X_test),
        labels=labels_present,
        target_names=target_names,
        output_dict=True,
        zero_division=0,
    )

    return vectorizer, clf, report["macro avg"]["f1-score"]


def extract_features_df(df: pd.DataFrame, feature_names: list[str]) -> np.ndarray:
    """Compute Branch-2 features for each row, preferring precomputed columns.

    If the DataFrame already has all feature columns, use them directly.
    Otherwise compute from the canonical/raw query text.
    """
    if all(f in df.columns for f in feature_names):
        return df[feature_names].to_numpy(dtype=np.float64)
    text_col = "query_canonical" if "query_canonical" in df.columns else "query_raw"
    rows = []
    for text in df[text_col].astype(str):
        feats = extract_statistical_features(text)
        rows.append({
            "length": float(feats.length),
            "special_char_ratio": feats.special_char_ratio,
            "sql_keyword_count": float(feats.sql_keyword_count),
            "entropy": feats.entropy,
        })
    return pd.DataFrame(rows)[feature_names].to_numpy(dtype=np.float64)


def main() -> None:
    cfg = load_config()
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    models_dir = Path(cfg.get_path("paths.models_dir", "models"))
    feature_names = list(cfg.get_path("branch2_anomaly.features", [
        "length", "special_char_ratio", "sql_keyword_count", "entropy",
    ]))

    # ── 1. Load data ──
    nhanh1_df = pd.read_csv(processed_dir / "nhanh1_train.csv")
    nhanh2_df = pd.read_csv(processed_dir / "nhanh2_data.csv")
    anomalous_df = pd.read_csv(processed_dir / "nhanh2_anomalous_eval.csv")

    train_df = nhanh1_df[nhanh1_df["split"] == "train"].reset_index(drop=True)
    test_df = nhanh1_df[nhanh1_df["split"] == "test"].reset_index(drop=True)
    nhanh2_train = nhanh2_df[nhanh2_df["split"] == "train"].reset_index(drop=True)
    nhanh2_test = nhanh2_df[nhanh2_df["split"] == "test"].reset_index(drop=True)

    logger.info("Data: nhanh1_train=%d test=%d | nhanh2_train=%d test=%d | anomalous=%d",
                len(train_df), len(test_df), len(nhanh2_train), len(nhanh2_test), len(anomalous_df))

    # ── 2. Train Branch 2 (anomaly) ──
    nhanh2_model_dir = models_dir / "nhanh2_zeroday"
    if nhanh2_model_dir.exists():
        logger.info("Loading existing Branch 2 model from %s", nhanh2_model_dir)
        detector = AnomalyDetector.load(nhanh2_model_dir)
    else:
        logger.info("Training Branch 2 (One-Class SVM) on %d benign samples ...", len(nhanh2_train))
        X_n2_train = nhanh2_train[feature_names].to_numpy(dtype=np.float64)
        detector = AnomalyDetector(
            algorithm="one_class_svm",
            contamination=0.005,
            scale_features=False,
            log_transform_features=["length"],
            feature_names=feature_names,
        )
        detector.fit(X_n2_train)
        detector.save(nhanh2_model_dir)

    # ── Baseline: Branch 2 on normal test data ──
    X_benign_test = nhanh2_test[feature_names].to_numpy(dtype=np.float64)
    benign_scores = detector.score(X_benign_test)
    benign_flags = detector.anomaly_flags(X_benign_test)
    baseline_fpr = float(benign_flags.mean())
    logger.info("Baseline FPR=%.4f (%d/%d)", baseline_fpr,
                int(benign_flags.sum()), len(benign_flags))

    # ── Baseline: Branch 2 on ALL anomalous eval data ──
    X_anom = extract_features_df(anomalous_df, feature_names)
    anom_scores = detector.score(X_anom)
    anom_flags = detector.anomaly_flags(X_anom)
    baseline_dr = float(anom_flags.mean())
    logger.info("Baseline DR=%.4f (%d/%d) on anomalous eval set",
                baseline_dr, int(anom_flags.sum()), len(anom_flags))

    # ── 3. Leave-one-out experiment ──
    experiment_dir = Path(__file__).resolve().parents[1] / "reports" / "zeroday_experiment"
    experiment_dir.mkdir(parents=True, exist_ok=True)

    all_results: dict[str, dict] = {}

    for label_id in EXCLUDED_LABELS:
        label_name = LABEL_NAMES[label_id]
        logger.info("=" * 60)
        logger.info("Excluding label %d (%s)", label_id, label_name)

        # 3a. Train Branch 1 without this label
        logger.info("Training Branch 1 without '%s' ...", label_name)
        vectorizer, clf, f1_macro = train_nhanh1_exclude(train_df, test_df, label_id, cfg)
        logger.info("F1-macro (excl %s)=%.4f", label_name, f1_macro)

        # 3b. Get excluded label's data from test set
        excluded_data = test_df[test_df["label"] == label_id].reset_index(drop=True)
        logger.info("Excluded-label test samples: %d", len(excluded_data))

        if len(excluded_data) == 0:
            logger.warning("No test samples for label %d — skipping", label_id)
            continue

        # 3c. Branch 1 prediction on excluded-label data
        X_excl_tfidf = vectorizer.transform(excluded_data["query_canonical"].astype(str))
        preds_nhanh1 = clf.predict(X_excl_tfidf)
        pred_labels = [LABEL_NAMES.get(p, f"label_{p}") for p in preds_nhanh1]
        pred_distro = pd.Series(pred_labels).value_counts().to_dict()
        miss_rate = float((preds_nhanh1 == 0).mean())  # predicted as normal
        logger.info("Branch 1 predictions on excluded '%s': %s", label_name, pred_distro)
        logger.info("Branch 1 miss rate (predicted normal): %.4f", miss_rate)

        # 3d. Branch 2 anomaly detection on excluded-label data
        X_excl_feats = extract_features_df(excluded_data, feature_names)

        scores_nhanh2 = detector.score(X_excl_feats)
        flags_nhanh2 = detector.anomaly_flags(X_excl_feats)
        dr_nhanh2 = float(flags_nhanh2.mean())
        logger.info("Branch 2 DR on excluded '%s': %.4f (%d/%d)",
                    label_name, dr_nhanh2, int(flags_nhanh2.sum()), len(flags_nhanh2))

        # 3e. Combined coverage
        either_flag = (preds_nhanh1 == 0) | (flags_nhanh2 == 1)
        combined_coverage = float(either_flag.mean())
        logger.info("Combined coverage (B1 miss OR B2 anomaly): %.4f", combined_coverage)

        save_dir = models_dir / f"nhanh1_no_{label_name}"
        save_dir.mkdir(parents=True, exist_ok=True)
        import joblib
        joblib.dump(vectorizer, save_dir / "vectorizer.joblib")
        joblib.dump(clf, save_dir / "model.joblib")
        with (save_dir / "metadata.json").open("w") as f:
            json.dump({
                "excluded_label": label_id,
                "excluded_label_name": label_name,
                "f1_macro_on_remaining": round(f1_macro, 4),
                "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }, f, indent=2)
        logger.info("Saved model to %s", save_dir)

        all_results[label_name] = {
            "excluded_label_id": label_id,
            "excluded_label_name": label_name,
            "n_test_samples": int(len(excluded_data)),
            "branch1_f1_macro": round(f1_macro, 4),
            "branch1_miss_rate": round(miss_rate, 4),
            "branch1_prediction_distribution": {str(k): int(v) for k, v in pred_distro.items()},
            "branch2_detection_rate": round(dr_nhanh2, 4),
            "branch2_n_detected": int(flags_nhanh2.sum()),
            "combined_coverage": round(combined_coverage, 4),
        }

    # ── 4. Summary ──
    summary = {
        "experiment": "zero-day-detection-leave-one-out",
        "description": "For each SQLi label, train Branch 1 without it and test Branch 2 detection rate on the unseen label",
        "baseline": {
            "branch2_algorithm": "one_class_svm",
            "branch2_contamination": 0.005,
            "fpr": round(baseline_fpr, 4),
            "dr_all_anomalous": round(baseline_dr, 4),
        },
        "results": all_results,
    }

    report_path = experiment_dir / "summary.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    logger.info("Saved experiment summary to %s", report_path)

    # Pretty print
    print()
    print("=" * 70)
    print("ZERO-DAY DETECTION — LEAVE-ONE-OUT RESULTS")
    print("=" * 70)
    print(f"{'Excluded label':<18} {'B1 F1':>8} {'B1 miss':>8} {'B2 DR':>8} {'Combined':>8}")
    print("-" * 70)
    for label_name, res in all_results.items():
        print(f"{label_name:<18} {res['branch1_f1_macro']:>8.4f} {res['branch1_miss_rate']:>8.4f} "
              f"{res['branch2_detection_rate']:>8.4f} {res['combined_coverage']:>8.4f}")
    print(f"\nBaseline FPR={baseline_fpr:.4f}  Baseline DR (all anomalous)={baseline_dr:.4f}")
    print("=" * 70)


if __name__ == "__main__":
    main()
