# -*- coding: utf-8 -*-
"""Impact analysis (NO code change) — SSRF rows leaked into Branch 2 benign pool.

Purpose: give Duc numbers on what happens if we drop the SSRF-callback rows
(owasp.org etc.) that polluted the "100% benign" pool used to train
branch2_v1 (OCI confirmed in data_contract.md §3.1: the anchor filter targets
SQLi + OS-cmd/SSI, NOT SSRF).

Does NOT modify any training code or model. It ONLY re-trains an OCSVM with the
SAME hyperparameters as branch2_v1 (config branch2_anomaly: one_class_svm,
gamma=0.01, nu=0.005, scale_features=false, log_transform=["length"]) on
(a) the current benign pool vs (b) the pool minus SSRF rows, and reports how
FPR / detection-rate / benign score percentiles shift.

Usage:  uv run python train/audit_branch2_ssrf_impact.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.chdir(Path(__file__).resolve().parents[1])

from src.models.branch2_anomaly import AnomalyDetector  # noqa: E402
from src.utils import get_logger  # noqa: E402

logger = get_logger(__name__)

FEATURES = ["length", "special_char_ratio", "sql_keyword_count", "entropy"]
SSRF_PATTERNS = ["owasp.org", "/etc/passwd", "shellshock"]


def _is_leaky(row) -> bool:
    t = str(row["query_canonical"]).lower()
    return any(p in t for p in SSRF_PATTERNS)


def _fit(detector, X):
    detector.fit(X)
    return detector


def _score_stats(scores: np.ndarray) -> dict:
    return {
        "p50": round(float(np.percentile(scores, 50)), 5),
        "p90": round(float(np.percentile(scores, 90)), 5),
        "p99": round(float(np.percentile(scores, 99)), 5),
        "max": round(float(scores.max()), 5),
        "mean": round(float(scores.mean()), 5),
    }


def main() -> None:
    processed = Path(__file__).resolve().parents[1] / "data" / "processed"
    df = pd.read_csv(processed / "branch2_data.csv", keep_default_na=False, na_values=[])
    train_df = df[df["split"] == "train"].reset_index(drop=True)
    test_df = df[df["split"] == "test"].reset_index(drop=True)

    anom_path = processed / "branch2_anomalous_eval.csv"
    anom_df = pd.read_csv(anom_path) if anom_path.exists() else pd.DataFrame()
    X_anom = anom_df[FEATURES].to_numpy(np.float64) if not anom_df.empty else None

    leaky_mask = train_df.apply(_is_leaky, axis=1)
    n_leaky_train = int(leaky_mask.sum())
    # also detect any SSRF leaks sitting in the test split
    leaky_mask_test = test_df.apply(_is_leaky, axis=1)
    n_leaky_test = int(leaky_mask_test.sum())

    X_full = train_df[FEATURES].to_numpy(np.float64)
    X_clean = train_df[~leaky_mask][FEATURES].to_numpy(np.float64)
    X_benign_test = test_df[FEATURES].to_numpy(np.float64)

    params = dict(
        algorithm="one_class_svm",
        contamination=0.005,  # ocsvm_nu (config branch2_anomaly.ocsvm_nu)
        gamma=0.01,           # ocsvm_gamma
        scale_features=False, # config branch2_anomaly.scale_features
        log_transform_features=["length"],
        feature_names=FEATURES,
    )

    # ---- (a) current pool ----
    det_full = _fit(AnomalyDetector(**params), X_full)
    s_full_benign = det_full.score(X_benign_test)
    fpr_full = float((det_full.anomaly_flags(X_benign_test)).mean())
    dr_full = (
        float(det_full.anomaly_flags(X_anom).mean())
        if X_anom is not None and len(X_anom)
        else None
    )

    # ---- (b) cleaned pool ----
    det_clean = _fit(AnomalyDetector(**params), X_clean)
    s_clean_benign = det_clean.score(X_benign_test)
    fpr_clean = float((det_clean.anomaly_flags(X_benign_test)).mean())
    dr_clean = (
        float(det_clean.anomaly_flags(X_anom).mean())
        if X_anom is not None and len(X_anom)
        else None
    )

    # ---- how does the CURRENT model treat the leaked SSRF train rows? ----
    s_leaky_current = det_full.score(X_full[leaky_mask.to_numpy()])
    frac_leaky_anomalous = float(
        (det_full.anomaly_flags(X_full[leaky_mask.to_numpy()])).mean()
    )

    out = {
        "config": params,
        "sizes": {
            "train_total": int(len(train_df)),
            "leaky_train_rows": n_leaky_train,
            "leaky_train_pct": round(n_leaky_train / len(train_df) * 100, 3),
            "test_leaky_rows": n_leaky_test,
            "anomalous_eval_rows": int(len(anom_df)),
        },
        "current_pool": {
            "fpr_benign": round(fpr_full, 6),
            "detection_rate": round(dr_full, 6) if dr_full is not None else None,
            "benign_score": _score_stats(s_full_benign),
            "leaky_train_rows_flag_anomalous_pct": round(frac_leaky_anomalous * 100, 3),
            "leaky_train_score": _score_stats(s_leaky_current),
        },
        "cleaned_pool": {
            "fpr_benign": round(fpr_clean, 6),
            "detection_rate": round(dr_clean, 6) if dr_clean is not None else None,
            "benign_score": _score_stats(s_clean_benign),
        },
        "delta": {
            "fpr_diff": round(fpr_clean - fpr_full, 6),
            "dr_diff": round((dr_clean - dr_full), 6) if dr_full is not None and dr_clean is not None else None,
            "p90_diff": round(float(np.percentile(s_clean_benign, 90) - np.percentile(s_full_benign, 90)), 5),
        },
    }

    out_dir = Path(__file__).resolve().parents[1] / "report" / "metrics" / "audit_branch3"
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "branch2_ssrf_impact.json").open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    logger.info("Wrote %s", out_dir / "branch2_ssrf_impact.json")


if __name__ == "__main__":
    main()