"""Build Branch-2 benign pool from HF dataset.

Loads the unified HF dataset (Jason-42195/VNU-SQLi-Detection), keeps only
normal rows (label=0), extracts statistical features, and saves as a CSV for
anomaly detection training.

This replaces the old build_branch2_dataset.py approach (which built from raw
D1/D3/D7 sources). The HF dataset already includes properly canonicalized text
and stratified splits, so we skip de-novo cleaning and reuse split+label
directly.

Always computes/writes the FULL canonical feature set (statistical_features.
FEATURE_ORDER), not just whatever subset branch2_anomaly.features currently
trains the model on: downstream data-curation tooling (e.g.
train/clean_branch2_data.py's short-string rebalancing) needs columns like
`length` to exist regardless of whether the model itself uses them. Which
columns actually feed the model is a train/train_branch2.py-time decision
(it selects the branch2_anomaly.features subset from whatever's in the CSV).
"""

from __future__ import annotations

import csv
from pathlib import Path

from datasets import load_dataset

from src.preprocessing.statistical_features import FEATURE_ORDER, extract_statistical_features
from src.utils import get_logger, load_config

logger = get_logger(__name__)


def main() -> None:
    cfg = load_config()
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    processed_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading HF dataset Jason-42195/VNU-SQLi-Detection (branch1_train.csv) ...")
    ds = load_dataset("Jason-42195/VNU-SQLi-Detection", data_files="branch1_train.csv", split="train")
    logger.info("Total rows: %d", len(ds))

    normal = ds.filter(lambda r: r["label"] == 0)
    logger.info("Normal rows (label=0): %d", len(normal))

    rows: list[dict] = []
    for i, row in enumerate(normal):
        canonical = row["query_canonical"]
        feats_by_name = extract_statistical_features(canonical).as_dict()
        row_out = {
            "id": i,
            "query_raw": row["query_raw"],
            "query_canonical": canonical,
            "has_comment_marker": row["has_comment_marker"],
            **{name: round(feats_by_name[name], 6) for name in FEATURE_ORDER},
            "source": row["source"],
            "split": row["split"],
        }
        rows.append(row_out)

    train_count = sum(1 for r in rows if r["split"] == "train")
    test_count = sum(1 for r in rows if r["split"] == "test")
    logger.info("Train=%d  Test=%d  Total=%d", train_count, test_count, len(rows))

    out_path = processed_dir / "branch2_data.csv"
    fieldnames = [
        "id", "query_raw", "query_canonical", "has_comment_marker",
        *FEATURE_ORDER, "source", "split",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Saved %d rows to %s", len(rows), out_path)

    logger.info("Loading anomalous eval CSV from HF ...")
    try:
        anom_ds = load_dataset(
            "Jason-42195/VNU-SQLi-Detection", data_files="branch2_anomalous_eval.csv", split="train"
        )
        # Recompute features locally rather than trusting the HF-hosted columns:
        # that file predates newer entries in branch2_anomaly.features (e.g.
        # bigram_entropy), so its stat columns would otherwise be missing/stale.
        anom_rows: list[dict] = []
        for i, row in enumerate(anom_ds):
            feats_by_name = extract_statistical_features(row["query_canonical"]).as_dict()
            anom_rows.append({
                "id": i,
                "query_raw": row["query_raw"],
                "query_canonical": row["query_canonical"],
                "has_comment_marker": row["has_comment_marker"],
                **{name: round(feats_by_name[name], 6) for name in FEATURE_ORDER},
                "source": row["source"],
            })
        anom_out = processed_dir / "branch2_anomalous_eval.csv"
        with anom_out.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames[:-1])
            writer.writeheader()
            writer.writerows(anom_rows)
        logger.info("Saved %d anomalous eval rows to %s", len(anom_rows), anom_out)
    except Exception as exc:
        logger.warning("Could not load anomalous eval file: %s", exc)


if __name__ == "__main__":
    main()
