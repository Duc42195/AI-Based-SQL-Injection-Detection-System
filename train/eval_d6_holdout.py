"""Held-out D6 (Superviz25) check on the REAL train/test split, post-retrain.

Unlike train/eval_zeroshot_superviz25.py (a fresh, ad-hoc reservoir sample
taken before any retraining decision was made), this script scores the exact
rows train/build_branch1_dataset.py + train/build_branch2_dataset.py already
marked split="test" for data_contract.md's D6 source (Superviz25) —
guaranteed disjoint from what models/branch1_v1 + models/branch2_v1 were
just retrained on, no re-sampling-overlap risk. Answers directly: did adding
D6 to training fix the zero-shot gaps found in
report/metrics/superviz25_zeroshot_eval.json (Branch 2 FPR 69-95%, Branch 1
DR 10-65% on real sqlmap-tampered attacks)?
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.models.branch1_loader import load_branch1_artifacts
from src.models.branch2_anomaly import AnomalyDetector
from src.preprocessing.multiclass_tagger import LABEL_NAMES
from src.utils import get_logger, load_config

logger = get_logger(__name__)


def main() -> None:
    cfg = load_config()
    models_dir = Path(cfg.get_path("paths.models_dir", "models"))
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    reports_dir = Path(cfg.get_path("paths.reports_dir", "report/metrics"))
    b1_threshold = float(cfg.get_path("branch1_supervised.decision_threshold", 0.5))

    # ---- Branch 1: D6 TEST rows (attack detection rate per class + benign FPR) ----
    b1_df = pd.read_csv(processed_dir / "branch1_train.csv", keep_default_na=False, na_values=[])
    d6_test = b1_df[(b1_df["source"].str.startswith("d6_superviz25")) & (b1_df["split"] == "test")]
    vectorizer, clf = load_branch1_artifacts(
        models_dir / "branch1_v1", cfg.get_path("branch1_supervised.distilbert", {})
    )
    classes = [int(c) for c in clf.classes_]
    probs = clf.predict_proba(vectorizer.transform(d6_test["query_canonical"].astype(str)))
    normal_col = classes.index(0)
    attack_prob = 1.0 - probs[:, normal_col]
    is_sqli = attack_prob >= b1_threshold

    branch1_result: dict[str, dict] = {}
    for label, group in d6_test.groupby("label"):
        mask = d6_test["label"] == label
        rate = float(is_sqli[mask.to_numpy()].mean())
        branch1_result[LABEL_NAMES[label]] = {
            "n": int(mask.sum()),
            "flag_rate": round(rate, 6),
            "interpretation": "false_positive_rate" if label == 0 else "detection_rate",
        }
        logger.info("Branch1 D6-test  label=%-14s n=%-5d flag_rate=%.4f", LABEL_NAMES[label], int(mask.sum()), rate)

    # ---- Branch 2: D6 TEST rows in the benign pool (FPR only - Branch 2 never trains/splits attack rows) ----
    b2_data_file = cfg.get_path("branch2_anomaly.data_file", "branch2_data_clean.csv")
    b2_df = pd.read_csv(processed_dir / b2_data_file, keep_default_na=False, na_values=[])
    d6_b2_test = b2_df[(b2_df["source"] == "d6_superviz25") & (b2_df["split"] == "test")]
    detector = AnomalyDetector.load(models_dir / "branch2_v1")
    feature_names = detector.feature_names or list(d6_b2_test.columns)
    X = d6_b2_test[feature_names].to_numpy(dtype=float)
    is_anomaly = detector.anomaly_flags(X)
    branch2_fpr = float(is_anomaly.mean()) if len(d6_b2_test) else None
    logger.info("Branch2 D6-test (benign) n=%d  FPR=%.4f", len(d6_b2_test), branch2_fpr or float("nan"))

    out = {
        "description": (
            "Held-out D6 (Superviz25) evaluation on the REAL train/test split "
            "written by build_branch1_dataset.py/build_branch2_dataset.py after "
            "D6 was added to training (26/8) - not a fresh ad-hoc sample. "
            "Compare against report/metrics/superviz25_zeroshot_eval.json (the "
            "pre-retrain zero-shot numbers) to see the effect of retraining."
        ),
        "branch1_d6_test": branch1_result,
        "branch2_d6_test_benign_fpr": round(branch2_fpr, 6) if branch2_fpr is not None else None,
        "branch2_d6_test_n": int(len(d6_b2_test)),
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / "d6_holdout_eval.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    logger.info("Saved to %s", out_path)


if __name__ == "__main__":
    main()
