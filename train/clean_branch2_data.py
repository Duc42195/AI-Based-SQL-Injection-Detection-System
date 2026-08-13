# -*- coding: utf-8 -*-
"""Clean the Branch-2 benign pool (post-audit cleanup, per mentor direction).

Implements plan_next_branch2_cleanup.md Bước 1:
  - Remove SSRF / OS-cmd callback rows from the benign TRAIN pool and move them
    to the anomalous eval set (so the detector can be tested on them).
  - Rebalance the short-string (length <= 10) proportion in TRAIN from ~18% down
    to a configurable target (literature-backed, default 3%) WITHOUT deleting
    the rows entirely (they are genuine benign traffic).

This writes cleaned CSVs that the evaluation notebook
(train/notebooks/branch2_normal_anomaly_dist.ipynb) reads. It does NOT retrain
or change the deployed branch2_v1 model.

Usage:  uv run python train/clean_branch2_data.py [--target-short-ratio 0.03] [--seed 42]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.chdir(Path(__file__).resolve().parents[1])

from src.utils import get_logger  # noqa: E402

logger = get_logger(__name__)

SSRF_PATTERNS = ["owasp.org", "/etc/passwd", "shellshock"]
SHORT_LEN = 10
DATA_COLUMNS = [
    "id", "query_raw", "query_canonical", "has_comment_marker",
    "length", "special_char_ratio", "sql_keyword_count", "entropy",
]


def _is_leaky(row) -> bool:
    t = str(row["query_canonical"]).lower()
    return any(p in t for p in SSRF_PATTERNS)


def _rebalance_short(df: pd.DataFrame, target_ratio: float, rng: np.random.Generator) -> pd.DataFrame:
    """Undersample short rows so they make up ~target_ratio of the result."""
    short_mask = df["length"] <= SHORT_LEN
    long_df = df[~short_mask]
    short_df = df[short_mask]
    if long_df.empty:
        return df
    # short_target / (long + short_target) = target_ratio
    short_target = int(round(target_ratio * len(long_df) / (1 - target_ratio)))
    short_target = max(0, min(short_target, len(short_df)))
    keep = rng.choice(len(short_df), size=short_target, replace=False)
    out = pd.concat([long_df, short_df.iloc[keep]], ignore_index=True)
    return out.sample(frac=1.0, random_state=int(rng.integers(0, 2**32 - 1))).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-short-ratio", type=float, default=0.03,
                        help="Target fraction of length<=10 rows in cleaned train (default 0.03).")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    processed = Path(__file__).resolve().parents[1] / "data" / "processed"
    df = pd.read_csv(processed / "branch2_data.csv", keep_default_na=False, na_values=[])
    train_df = df[df["split"] == "train"].reset_index(drop=True)
    test_df = df[df["split"] == "test"].reset_index(drop=True)

    # ---- 1) move SSRF out of benign train ----
    leaky_mask = train_df.apply(_is_leaky, axis=1)
    ssrf_rows = train_df[leaky_mask].copy()
    clean_train = train_df[~leaky_mask].reset_index(drop=True)
    logger.info("Moved %d SSRF rows out of benign train", len(ssrf_rows))

    # ---- 2) rebalance short strings in train ----
    before_short = int((clean_train["length"] <= SHORT_LEN).sum())
    rng = np.random.default_rng(args.seed)
    clean_train = _rebalance_short(clean_train, args.target_short_ratio, rng)
    after_short = int((clean_train["length"] <= SHORT_LEN).sum())
    logger.info("Short (len<=%d) train: %d (%.2f%%) -> %d (%.2f%%)",
                SHORT_LEN, before_short,
                before_short / len(train_df) * 100,
                after_short, after_short / len(clean_train) * 100)

    # ---- 3) append moved SSRF to the anomalous eval set ----
    anom_path = processed / "branch2_anomalous_eval.csv"
    anom_df = pd.read_csv(anom_path) if anom_path.exists() else pd.DataFrame()
    ssrf_rows = ssrf_rows[DATA_COLUMNS].copy()
    ssrf_rows["source"] = "ssrf_moved_from_benign"
    merged_anom = pd.concat([anom_df, ssrf_rows], ignore_index=True)
    logger.info("Anomalous eval: %d -> %d (added %d SSRF)",
                len(anom_df), len(merged_anom), len(ssrf_rows))

    # ---- write outputs ----
    clean_train_out = clean_train.copy()
    clean_train_out["split"] = "train"
    clean_test_out = test_df.copy()
    clean_test_out["split"] = "test"
    clean_all = pd.concat([clean_train_out, clean_test_out], ignore_index=True)

    clean_all.to_csv(processed / "branch2_data_clean.csv", index=False, encoding="utf-8")
    merged_anom.to_csv(processed / "branch2_anomalous_eval_clean.csv", index=False, encoding="utf-8")
    logger.info("Wrote branch2_data_clean.csv (%d rows) and branch2_anomalous_eval_clean.csv (%d rows)",
                len(clean_all), len(merged_anom))


if __name__ == "__main__":
    main()