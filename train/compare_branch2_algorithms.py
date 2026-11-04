"""Re-compare Branch 2's 3 candidate algorithms on the CURRENT (D3/Superviz25-
inclusive) benign+anomalous pools, adding a criterion Table IV never measured:
score BOUNDEDNESS, not just FPR/DR/AUC.

Motivation: recalibrating the Session Correlator against the current LOF
model produced a real regression (behavior-check FPR 0%->37%), traced to
LOF's per-query anomaly score being mathematically unbounded - a handful of
extremely short/sparse query_splitting fragments score in the billions,
which distorts the mean-based threshold search over session-aggregated
scores. Table IV's own FPR/DR/AUC never surfaced this because those are
either rank-based (AUC) or binary-threshold-based (FPR/DR) - insensitive to
*how large* an outlier's score is, only whether it crosses a line.

This script does NOT touch models/branch2_v1 or any deployed artifact - it
is a comparison exercise to inform whether Branch 2's algorithm choice
should change, run against report/metrics/branch2_source_ablation.json's
same data files (data/processed/branch2_data_clean.csv,
data/processed/branch2_anomalous_eval_clean.csv).

Run:  uv run python train/compare_branch2_algorithms.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from src.models.branch2_anomaly import AnomalyDetector
from src.utils import get_logger, load_config

logger = get_logger(__name__)

PROJECT = Path(__file__).resolve().parent.parent

# The exact degenerate fragments that produced billion-scale LOF scores
# during Session Correlator recalibration (see report/plan/data_contract.md).
PROBLEM_TEXTS = ["by 1-- -", "( 15 )", "{ : ;", "( select", "1=1"]


def load_data(cfg) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    processed = Path(cfg.get_path("paths.data_processed", "data/processed"))
    b2 = cfg.get_path("branch2_anomaly")
    df = pd.read_csv(processed / b2["data_file"])
    anom = pd.read_csv(processed / b2["anomalous_eval_file"])
    feature_names = list(cfg.get_path("branch2_anomaly.features"))
    return df, anom, feature_names


def evaluate(
    detector: AnomalyDetector,
    test_benign: pd.DataFrame,
    anom: pd.DataFrame,
    feature_names: list[str],
) -> dict[str, Any]:
    X_benign = test_benign[feature_names].to_numpy(dtype=np.float64)
    X_anom = anom[feature_names].to_numpy(dtype=np.float64)
    scores_benign = detector.score(X_benign)
    scores_anom = detector.score(X_anom)

    y_true = np.concatenate([np.zeros(len(scores_benign)), np.ones(len(scores_anom))])
    y_score = np.concatenate([scores_benign, scores_anom])
    auc = roc_auc_score(y_true, y_score)

    # Matched operating point: threshold = 95th percentile of benign scores
    # (~5% FPR by construction), the same convention Table IV's own
    # cross-algorithm comparison uses.
    threshold = float(np.percentile(scores_benign, 95))
    fpr = float((scores_benign > threshold).mean())
    dr = float((scores_anom > threshold).mean())

    # Score-boundedness probe: known-degenerate short fragments that broke
    # Session Correlator's mean-based calibration under LOF.
    problem_features = []
    for text in PROBLEM_TEXTS:
        from src.preprocessing.statistical_features import extract_statistical_features

        feats = extract_statistical_features(text).as_dict()
        problem_features.append([feats[f] for f in feature_names])
    problem_scores = detector.score(np.array(problem_features, dtype=np.float64))

    return {
        "fpr_at_p95": round(fpr, 4),
        "dr_at_p95": round(dr, 4),
        "auc": round(float(auc), 4),
        "benign_score_p50": round(float(np.percentile(scores_benign, 50)), 4),
        "benign_score_p99": round(float(np.percentile(scores_benign, 99)), 4),
        "benign_score_max": round(float(scores_benign.max()), 4),
        "anom_score_max": round(float(scores_anom.max()), 4),
        "problem_fragment_scores": {t: round(float(s), 4) for t, s in zip(PROBLEM_TEXTS, problem_scores)},
        "problem_fragment_max": round(float(problem_scores.max()), 4),
    }


def main() -> None:
    cfg = load_config()
    df, anom, feature_names = load_data(cfg)
    train = df[df["split"] == "train"].reset_index(drop=True)
    test = df[df["split"] == "test"].reset_index(drop=True)
    logger.info("Train benign=%d  Test benign=%d  Anomalous=%d  Features=%d", len(train), len(test), len(anom), len(feature_names))

    b2 = cfg.get_path("branch2_anomaly")
    log_transform = list(b2.get("log_transform_features", []))
    X_train = train[feature_names].to_numpy(dtype=np.float64)

    configs = {
        "one_class_svm": dict(
            algorithm="one_class_svm",
            contamination=b2.get("ocsvm_nu", 0.001),
            gamma=b2.get("ocsvm_gamma", "scale"),
        ),
        "isolation_forest": dict(
            algorithm="isolation_forest",
            contamination=b2.get("contamination", 0.01),
            max_samples=b2.get("if_max_samples", 1.0),
        ),
        "local_outlier_factor": dict(
            algorithm="local_outlier_factor",
            contamination=b2.get("lof_contamination", 0.05),
            n_neighbors=b2.get("lof_n_neighbors", 5),
        ),
    }

    results: dict[str, Any] = {}
    for name, kwargs in configs.items():
        logger.info("=== %s ===", name)
        algorithm = kwargs.pop("algorithm")
        detector = AnomalyDetector(
            algorithm=algorithm,
            scale_features=b2.get("scale_features", True),
            log_transform_features=log_transform,
            feature_names=feature_names,
            **kwargs,
        )
        detector.fit(X_train)
        metrics = evaluate(detector, test, anom, feature_names)
        results[name] = metrics
        logger.info(
            "%-22s FPR@p95=%.4f DR@p95=%.4f AUC=%.4f | benign p99=%.2f max=%.2e | problem-fragment max=%.2e",
            name, metrics["fpr_at_p95"], metrics["dr_at_p95"], metrics["auc"],
            metrics["benign_score_p99"], metrics["benign_score_max"], metrics["problem_fragment_max"],
        )

    out_path = PROJECT / "report" / "metrics" / "branch2_algorithm_comparison.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    logger.info("Saved %s", out_path)


if __name__ == "__main__":
    main()
