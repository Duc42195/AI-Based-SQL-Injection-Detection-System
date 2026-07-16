"""Build data/processed/nhanh1_train.csv — the balanced Branch-1 dataset.

Combines all Day 1-2 sources (see data_contract.md Muc 2.1):
- D1 SQLiV3 raw (normal + attack rows, both used)
- D4 payload-box (attack only)
- D7 SR-BH 2020 (attack rows via "66 - SQL Injection"==1, plus a sample of
  "000 - Normal"==1 rows for benign diversity)
- Synthetic `stacked` payloads (no real source has this class)

Each row is canonicalized (src/preprocessing/canonicalize.py) and tagged
(src/preprocessing/multiclass_tagger.py) on the CANONICAL text, then each
class is undersampled down to `branch1_supervised.balance.target_per_class`
(classes with fewer rows are kept in full) before a stratified train/test
split.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

from sklearn.model_selection import train_test_split

from src.preprocessing.canonicalize import canonicalize
from src.preprocessing.data_sources import load_d1, load_d4, load_d7
from src.preprocessing.multiclass_tagger import LABEL_NAMES, matches_any_attack_signature, tag_query
from src.preprocessing.synthetic_stacked import generate_synthetic_stacked
from src.utils import get_logger, load_config

logger = get_logger(__name__)

csv.field_size_limit(10_000_000)


def _load_synthetic_stacked(limit: int) -> list[tuple[str, bool, str]]:
    """Generate the synthetic `stacked` payload batch.

    Returns:
        List of (raw_text, is_attack, source) tuples, all is_attack=True.
    """
    payloads = generate_synthetic_stacked(limit=limit)
    logger.info("Synthetic stacked: generated %d payloads", len(payloads))
    return [(p, True, "synthetic_stacked") for p in payloads]


def _undersample(rows: list[dict], target_per_class: int, seed: int) -> list[dict]:
    """Cap each label's row count at `target_per_class` via random sampling.

    Args:
        rows: All tagged rows (each a dict with a "label" key).
        target_per_class: Max rows to keep per label; smaller classes are
            kept in full.
        seed: Random seed for reproducible sampling.

    Returns:
        The balanced row list (order not preserved across labels).
    """
    rng = random.Random(seed)
    by_label: dict[int, list[dict]] = {}
    for r in rows:
        by_label.setdefault(r["label"], []).append(r)

    balanced: list[dict] = []
    for label, group in sorted(by_label.items()):
        if len(group) > target_per_class:
            sampled = rng.sample(group, target_per_class)
        else:
            sampled = group
        logger.info(
            "  label=%d (%s): %d available -> %d kept",
            label,
            LABEL_NAMES[label],
            len(group),
            len(sampled),
        )
        balanced.extend(sampled)
    return balanced


def main() -> None:
    """Build the balanced Nhanh 1 multiclass dataset and write it to CSV."""
    cfg = load_config()
    seed = cfg.get_path("project.random_seed", 42)
    max_decode = cfg.get_path("preprocessing.max_decode_iterations", 3)
    target_per_class = cfg.get_path("branch1_supervised.balance.target_per_class", 15000)
    synthetic_count = cfg.get_path("branch1_supervised.balance.synthetic_stacked_count", 363)
    test_fraction = cfg.get_path("branch1_supervised.balance.test_fraction", 0.2)

    raw_dir = Path(cfg.get_path("paths.data_raw", "data/raw"))
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    processed_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=== Loading raw sources ===")
    d1_rows = load_d1(raw_dir / "d1_sqliv3_raw.csv")
    logger.info("D1: loaded %d unique non-empty rows", len(d1_rows))
    d4_rows = load_d4(raw_dir / "payload_box")
    logger.info("D4: loaded %d unique payload lines", len(d4_rows))
    d7_rows = load_d7(
        raw_dir / "sr_bh_2020" / "data_capec_multilabel.csv", normal_sample_size=10000, seed=seed
    )
    logger.info("D7: loaded %d rows (attack + sampled normal)", len(d7_rows))
    synthetic_rows = _load_synthetic_stacked(limit=synthetic_count)

    all_rows = d1_rows + d4_rows + d7_rows + synthetic_rows
    logger.info("Total raw rows before canonicalize/tag: %d", len(all_rows))

    logger.info("=== Canonicalizing + tagging ===")
    tagged_rows: list[dict] = []
    rejected_mislabeled_normal = 0
    for i, (text, is_attack, source) in enumerate(all_rows):
        canonical = canonicalize(text, max_decode_iterations=max_decode)

        # Content-based safety net: a row an upstream source calls "normal"
        # is still rejected if it matches a known attack signature (found via
        # manual sanity-check: SR-BH "Normal=1" rows containing sleep() and
        # "cat /etc/passwd" - see data_contract.md Muc 3.1). We don't trust
        # the source's negative label blindly, only its positive one.
        if not is_attack and matches_any_attack_signature(canonical.query_canonical):
            rejected_mislabeled_normal += 1
            continue

        label = tag_query(canonical.query_canonical, is_attack=is_attack)
        tagged_rows.append(
            {
                "query_raw": text,
                "query_canonical": canonical.query_canonical,
                "has_comment_marker": canonical.has_comment_marker,
                "label": label,
                "label_name": LABEL_NAMES[label],
                "source": source,
            }
        )
        if (i + 1) % 100000 == 0:
            logger.info("  ... processed %d/%d rows", i + 1, len(all_rows))

    logger.info(
        "Rejected %d rows labeled 'normal' by source but matching an attack signature",
        rejected_mislabeled_normal,
    )

    logger.info("=== Undersampling to target_per_class=%d ===", target_per_class)
    balanced_rows = _undersample(tagged_rows, target_per_class, seed)
    logger.info("Balanced total: %d rows", len(balanced_rows))

    logger.info("=== Splitting train/test (test_fraction=%.2f, seed=%d) ===", test_fraction, seed)
    labels = [r["label"] for r in balanced_rows]
    train_rows, test_rows = train_test_split(
        balanced_rows, test_size=test_fraction, random_state=seed, stratify=labels
    )
    for r in train_rows:
        r["split"] = "train"
    for r in test_rows:
        r["split"] = "test"
    final_rows = train_rows + test_rows

    out_path = processed_dir / "nhanh1_train.csv"
    fieldnames = [
        "id",
        "query_raw",
        "query_canonical",
        "has_comment_marker",
        "label",
        "label_name",
        "source",
        "split",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, r in enumerate(final_rows):
            writer.writerow({"id": i, **r})

    logger.info("Wrote %d rows to %s (train=%d, test=%d)", len(final_rows), out_path, len(train_rows), len(test_rows))


if __name__ == "__main__":
    main()
