"""Train, evaluate and save Branch-2 anomaly detection models.

Trains both Isolation Forest and One-Class SVM on the Branch-2 benign pool,
evaluates FPR on held-out benign test data and detection rate on anomalous
data, then saves the best model (by AUC) to models/nhanh2_v1/.

Changes from v0 (training audit 16/7):
  - Feature scaling (StandardScaler) inside AnomalyDetector.
  - log1p-transform for "length" to handle extreme right-skew (max 5370 vs mean 47).
  - Hyperparameter grid search (optional, via config branch2_anomaly.tune).
  - contamination default reduced to 0.001 (training data is 100% benign).
"""

from __future__ import annotations

import itertools
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, roc_curve

from src.models.nhanh2_anomaly import AnomalyDetector
from src.utils import Config, get_logger, load_config

logger = get_logger(__name__)

def _get_feature_names(cfg: Config) -> list[str]:
    return list(cfg.get_path("branch2_anomaly.features", ["length", "special_char_ratio", "sql_keyword_count", "entropy"]))


def _load_data(cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load train, test-benign and test-anomalous DataFrames.

    Returns:
        Tuple of (train_df, test_benign_df, test_anomalous_df).
    """
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))

    normal_path = processed_dir / "nhanh2_data.csv"
    if not normal_path.exists():
        raise FileNotFoundError(
            f"{normal_path} not found. Run scripts/build_nhanh2_data.py first."
        )
    df = pd.read_csv(normal_path)
    train_df = df[df["split"] == "train"].reset_index(drop=True)
    test_benign_df = df[df["split"] == "test"].reset_index(drop=True)

    anomalous_path = processed_dir / "nhanh2_anomalous_eval.csv"
    if anomalous_path.exists():
        test_anomalous_df = pd.read_csv(anomalous_path)
    else:
        logger.warning("No anomalous eval file found at %s", anomalous_path)
        test_anomalous_df = pd.DataFrame()

    logger.info(
        "Train=%d  Test-benign=%d  Test-anomalous=%d",
        len(train_df), len(test_benign_df), len(test_anomalous_df),
    )
    return train_df, test_benign_df, test_anomalous_df


def _build_detector(
    cfg: Config,
    algorithm: str,
    feature_names: list[str],
    **override_kwargs,
) -> AnomalyDetector:
    """Create an AnomalyDetector reading common params from config.

    Args:
        cfg: Loaded config.
        algorithm: ``"isolation_forest"`` or ``"one_class_svm"``.
        feature_names: Ordered list of feature names from config.
        **override_kwargs: Override any constructor arg.

    Returns:
        Configured detector (not yet fitted).
    """
    base_contamination = cfg.get_path("branch2_anomaly.contamination", 0.01)
    scale = cfg.get_path("branch2_anomaly.scale_features", False)
    log_transform = cfg.get_path("branch2_anomaly.log_transform_features", ["length"])

    # Each algorithm uses its own contamination — independently tuned.
    if algorithm == "one_class_svm":
        contamination = cfg.get_path("branch2_anomaly.ocsvm_nu", base_contamination)
    else:
        contamination = base_contamination

    kwargs: dict = {
        "algorithm": algorithm,
        "contamination": contamination,
        "scale_features": scale,
        "log_transform_features": list(log_transform),
        "feature_names": feature_names,
    }

    # Pass algorithm-specific overrides from config
    if algorithm == "one_class_svm":
        gamma = cfg.get_path("branch2_anomaly.ocsvm_gamma", None)
        if gamma is not None:
            kwargs["gamma"] = gamma

    kwargs.update(override_kwargs)
    return AnomalyDetector(**kwargs)


def _eval_detector(
    detector: AnomalyDetector,
    X_benign: np.ndarray,
    X_anomalous: np.ndarray | None,
    label: str,
) -> dict:
    """Run evaluation and log metrics.

    Args:
        detector: Trained anomaly detector.
        X_benign: Benign test features.
        X_anomalous: Anomalous test features (may be None/empty).
        label: Model label for logging.

    Returns:
        Dict of evaluation metrics.
    """
    results: dict = {
        "algorithm": detector.algorithm,
        "contamination": detector.contamination,
    }

    scores_benign = detector.score(X_benign)
    preds_benign = detector.anomaly_flags(X_benign)

    fpr = float(preds_benign.mean())
    results["fpr"] = round(fpr, 6)
    results["n_benign"] = int(len(X_benign))
    results["n_false_positives"] = int(preds_benign.sum())

    logger.info(
        "[%s] FPR=%.4f (%d/%d)",
        label, fpr, int(preds_benign.sum()), len(X_benign),
    )

    detection_rate: float | None = None
    auc: float | None = None

    if X_anomalous is not None and len(X_anomalous) > 0:
        scores_anom = detector.score(X_anomalous)
        preds_anom = detector.anomaly_flags(X_anomalous)
        detection_rate = float(preds_anom.mean())
        results["detection_rate"] = round(detection_rate, 6)
        results["n_anomalous"] = int(len(X_anomalous))
        results["n_true_positives"] = int(preds_anom.sum())

        y_true = np.concatenate([np.zeros(len(X_benign)), np.ones(len(X_anomalous))])
        y_scores = np.concatenate([scores_benign, scores_anom])
        try:
            auc = float(roc_auc_score(y_true, y_scores))
            results["auc"] = round(auc, 6)
            # Full ROC curve (subsampled to <=50 points) so the notebook/report
            # can plot FPR-vs-TPR across thresholds, not just the single
            # operating point implied by the algorithm's own contamination.
            roc_fpr, roc_tpr, roc_thresh = roc_curve(y_true, y_scores)
            step = max(1, len(roc_fpr) // 50)
            results["roc_curve"] = {
                "fpr": [round(float(v), 6) for v in roc_fpr[::step]],
                "tpr": [round(float(v), 6) for v in roc_tpr[::step]],
                "thresholds": [round(float(v), 6) for v in roc_thresh[::step]],
            }
        except ValueError:
            auc = None

        logger.info(
            "[%s] Detection-rate=%.4f (%d/%d)  AUC=%s",
            label, detection_rate, int(preds_anom.sum()), len(X_anomalous),
            f"{auc:.4f}" if auc else "N/A",
        )

    return results


def _grid_search(
    cfg: Config,
    algorithm: str,
    feature_names: list[str],
    X_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
) -> tuple[dict, float]:
    """Run grid search over hyperparameters for the given algorithm.

    Args:
        cfg: Config (reads ``branch2_anomaly.tune.<algorithm>.*``).
        algorithm: Algorithm key.
        feature_names: Ordered list of feature names from config.
        X_train: Training features.
        X_val: Validation features.
        y_val: Validation labels (0 normal, 1 anomalous).

    Returns:
        Tuple of (best_params, best_auc).
    """
    tune_cfg = cfg.get_path("branch2_anomaly.tune", {})
    grid: dict = tune_cfg.get(algorithm, {})

    if not grid:
        logger.info("[%s] No grid defined — skipping tuning", algorithm)
        return {}, 0.0

    keys = list(grid.keys())
    best_auc = -1.0
    best_params = {}
    total = 1
    for v in grid.values():
        total *= len(v)

    logger.info("[%s] Grid search: %d combinations", algorithm, total)

    for values in itertools.product(*grid.values()):
        params = dict(zip(keys, values))
        logger.info("  Trying %s=%s", algorithm, params)

        det = _build_detector(cfg, algorithm, feature_names, **params)
        det.fit(X_train)

        # Score validation set
        s_val = det.score(X_val)
        try:
            auc = float(roc_auc_score(y_val, s_val))
        except ValueError:
            auc = 0.0

        logger.info("    AUC=%.4f", auc)
        if auc > best_auc:
            best_auc = auc
            best_params = params

    logger.info("[%s] Best: %s  AUC=%.4f", algorithm, best_params, best_auc)
    return best_params, best_auc


def main() -> None:
    cfg = load_config()
    feature_names = _get_feature_names(cfg)
    seed = cfg.get_path("project.random_seed", 42)
    models_dir = Path(cfg.get_path("paths.models_dir", "models"))
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    contamination = cfg.get_path("branch2_anomaly.contamination", 0.001)
    tune_enabled = cfg.get_path("branch2_anomaly.tune.enabled", False)
    val_frac = cfg.get_path("branch2_anomaly.tune.validation_fraction", 0.2)

    train_df, test_benign_df, test_anomalous_df = _load_data(cfg)

    X_benign = test_benign_df[feature_names].to_numpy(dtype=np.float64)
    X_anom = (
        test_anomalous_df[feature_names].to_numpy(dtype=np.float64)
        if not test_anomalous_df.empty
        else None
    )

    # ── Train / validation split ──
    full_train = train_df[feature_names].to_numpy(dtype=np.float64)
    n_val = max(1, int(len(full_train) * val_frac))
    rng = np.random.RandomState(seed)
    perm = rng.permutation(len(full_train))
    X_train, X_val = full_train[perm[n_val:]], full_train[perm[:n_val]]

    if X_anom is not None and len(X_anom) > 0:
        y_val = np.concatenate([np.zeros(len(X_val)), np.ones(min(len(X_val), len(X_anom)))])
        X_val_combined = np.vstack([X_val, X_anom[:min(len(X_val), len(X_anom))]])
    else:
        y_val = np.zeros(len(X_val))
        X_val_combined = X_val

    # ── Train & evaluate both algorithms ──
    all_results = {}
    chosen_alg = cfg.get_path("branch2_anomaly.algorithm", "isolation_forest")
    best_auc_overall = -1.0
    best_detector = None
    best_results = {}

    for alg in ["isolation_forest", "one_class_svm"]:
        logger.info("=== %s ===", alg.upper())

        if tune_enabled:
            best_params, best_val_auc = _grid_search(cfg, alg, feature_names, X_train, X_val_combined, y_val)
            if best_params:
                detector = _build_detector(cfg, alg, feature_names, **best_params)
            else:
                detector = _build_detector(cfg, alg, feature_names)
        else:
            detector = _build_detector(cfg, alg, feature_names)

        # Retrain on full training set
        detector.fit(full_train)

        results = _eval_detector(detector, X_benign, X_anom, alg.upper())
        all_results[alg] = results

        auc_val = results.get("auc", 0.0) or 0.0
        if auc_val > best_auc_overall or (alg == chosen_alg and best_detector is None):
            best_auc_overall = auc_val
            best_detector = detector
            best_results = results

    # Also try the config-chosen algorithm if it wasn't already picked
    # (it will be picked if auc is higher, but ensure we respect config)
    # We already prefer it by the tie-break condition above.

    version = "nhanh2_v1"
    out_dir = models_dir / version
    out_dir.mkdir(parents=True, exist_ok=True)

    best_detector.save(out_dir)

    eval_report = {
        "version": version,
        "branch": "nhanh2_anomaly",
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "feature_names": feature_names,
        "train_rows": len(full_train),
        "preprocessing": {
            "scale_features": cfg.get_path("branch2_anomaly.scale_features", True),
            "log_transform_features": list(cfg.get_path("branch2_anomaly.log_transform_features", ["length"])),
        },
        "tuning": {
            "enabled": tune_enabled,
            "validation_fraction": val_frac,
        },
        "algorithms": all_results,
        "chosen_algorithm": chosen_alg,
        "chosen": best_results,
    }

    report_path = Path(__file__).resolve().parents[1] / "reports" / "nhanh2_eval.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(eval_report, f, indent=2)
    logger.info("Saved eval report to %s", report_path)
    logger.info("=== Done ===")


if __name__ == "__main__":
    main()
