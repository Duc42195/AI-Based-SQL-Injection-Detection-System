"""Build Branch-2 benign pool from HF dataset.

Loads the dedicated, UNCAPPED Branch-2 benign pool (`branch2_normal.csv` on
the HF dataset repo — built by the original raw-source pipeline,
`train/build_branch2_dataset.py`, from D1+D3+D7 with no per-class cap; see
`report/plan/data_contract.md` §3.2), extracts statistical features, and
saves as a CSV for anomaly detection training.

BUG FIXED 16/08: this script previously loaded `branch1_train.csv` (Branch
1's dataset) and filtered to `label == 0`, which silently gives Branch 1's
PER-CLASS-UNDERSAMPLED "normal" rows (capped at `branch1_supervised.balance.
target_per_class`, 15,000 total) instead of Branch 2's own, deliberately
UNCAPPED pool (91,935 rows) — a design requirement stated explicitly in
data_contract.md §3.2 ("no count cap — Branch 2 doesn't need class balance;
more normal data is better"). `branch2_normal.csv` already existed on HF with
the correct data the whole time; the bug was which file this script read.
Every Branch 2 result from 16/07 through 16/08 (a month) was trained on 1/6th
of the benign data that was actually available.

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

    logger.info("Loading HF dataset Jason-42195/VNU-SQLi-Detection (branch2_normal.csv) ...")
    normal = load_dataset("Jason-42195/VNU-SQLi-Detection", data_files="branch2_normal.csv", split="train")
    logger.info("Normal rows: %d", len(normal))

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
