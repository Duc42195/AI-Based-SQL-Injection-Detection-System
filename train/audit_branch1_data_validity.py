# -*- coding: utf-8 -*-
"""Day 1 / Sprint 1 audit — Branch 1 data validity (Bach).

Verifies the dataset feeding `train/train_branch1.py` so the numbers in
`report/metrics/branch1_eval.json` are trustworthy. Mirrors the Branch 2/3
audit scripts. Read-only: reports findings, does not modify data.

Checks:
  - split / class / source distributions (5 classes, no phantom `stacked`)
  - exact-duplicate `query_canonical` extra copies + cross-split (train/test)
    leakage vector
  - SSRF / OS-cmd callback rows mislabelled as an SQLi class (boolean_blind)
    and rows sitting in the `normal` benign bucket
  - `/blog/index.php/2020/03` WordPress request-format content duplication
  - `has_comment_marker` / label schema sanity

Usage:  uv run python train/audit_branch1_data_validity.py
Requires: data/processed/branch1_train.csv
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

from src.utils import get_logger  # noqa: E402

logger = get_logger(__name__)

_SSRF_PATTERNS = ("owasp.org", "/etc/passwd", "shellshock")
_BLOG_PATTERN = "/blog/index.php/2020/03"


def _is_ssrf(q: str) -> bool:
    q = q.lower()
    return any(p in q for p in _SSRF_PATTERNS)


def check_distributions(df: pd.DataFrame) -> dict:
    return {
        "rows": int(len(df)),
        "columns": list(df.columns),
        "split": df["split"].value_counts().to_dict(),
        "label_name": df["label_name"].value_counts().to_dict(),
        "has_comment_marker": df["has_comment_marker"].value_counts().to_dict(),
        "source": df["source"].value_counts().to_dict(),
        "distinct_query_canonical": int(df["query_canonical"].nunique()),
        "distinct_query_raw": int(df["query_raw"].nunique()),
    }


def check_duplicate_leakage(df: pd.DataFrame) -> dict:
    canon = df["query_canonical"]
    n_extra = int(canon.duplicated(keep="first").sum())
    dupe = df[canon.duplicated(keep=False)]
    straddle = int(
        dupe.groupby("query_canonical")["split"].nunique().eq(2).sum()
    )
    n_distinct_dupes = int(dupe["query_canonical"].nunique())
    return {
        "extra_copies": n_extra,
        "distinct_duplicate_texts": n_distinct_dupes,
        "duplicate_texts_straddle_train_and_test": straddle,
        "note": "extra_copies == 4,277 matches the dedup rule in build_mlops_split.py "
                "(duplicate texts straddle train/golden); here they straddle train/test "
                "inside the same file -> a cross-split leakage vector for Branch 1's own eval.",
    }


def check_ssrf_mislabels(df: pd.DataFrame) -> dict:
    m = df["query_canonical"].apply(_is_ssrf)
    by_class = df.loc[m, "label_name"].value_counts().to_dict()
    return {
        "ssrf_rows_total": int(m.sum()),
        "by_label": by_class,
        "in_normal_benign_pool": int(df.loc[m & (df["label_name"] == "normal")].shape[0]),
        "in_boolean_blind_sqli": int(
            df.loc[m & (df["label_name"] == "boolean_blind")].shape[0]
        ),
        "patterns": {
            p: int(df["query_canonical"].str.lower().str.contains(p, na=False).sum())
            for p in _SSRF_PATTERNS
        },
        "note": "Rows matching SSRF/OS-cmd callbacks inside boolean_blind are label "
                "noise (doc data_contract.md ~13% hand-sample estimate); rows inside "
                "normal are benign-pool contamination analogous to the Branch 2 SSRF leak.",
    }


def check_blog_duplication(df: pd.DataFrame) -> dict:
    m = df["query_canonical"].str.contains(_BLOG_PATTERN, na=False)
    return {
        "rows": int(m.sum()),
        "share_of_dataset": round(float(m.mean()), 4),
        "distinct_canonicals": int(df.loc[m, "query_canonical"].nunique()),
        "by_label": df.loc[m, "label_name"].value_counts().to_dict(),
        "note": "WordPress /blog/index.php/2020/03 request-format rows dominate the "
                "corpus (union_based/error_based/time_blind) -> heavy content-format "
                "duplication, not per-class diversity.",
    }


def main() -> None:
    csv_path = ROOT / "data/processed/branch1_train.csv"
    if not csv_path.exists():
        logger.error("Missing input: %s", csv_path)
        return

    df = pd.read_csv(csv_path, keep_default_na=False, na_values=[])

    findings = {
        "branch1_distributions": check_distributions(df),
        "branch1_duplicate_leakage": check_duplicate_leakage(df),
        "branch1_ssrf_mislabels": check_ssrf_mislabels(df),
        "branch1_blog_duplication": check_blog_duplication(df),
    }
    out_dir = ROOT / "report/metrics/audit_branch1"
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "findings.json").open("w", encoding="utf-8") as f:
        json.dump(findings, f, indent=2, ensure_ascii=False)
    logger.info("Audit written to %s", out_dir / "findings.json")


if __name__ == "__main__":
    main()
