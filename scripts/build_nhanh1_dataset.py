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
from urllib.parse import unquote_plus

from sklearn.model_selection import train_test_split

from src.preprocessing.canonicalize import canonicalize
from src.preprocessing.multiclass_tagger import LABEL_NAMES, tag_query
from src.preprocessing.synthetic_stacked import generate_synthetic_stacked
from src.utils import get_logger, load_config

logger = get_logger(__name__)

csv.field_size_limit(10_000_000)


def _load_d1(path: Path) -> list[tuple[str, bool, str]]:
    """Load D1 SQLiV3 raw rows, dropping null/empty text.

    Returns:
        List of (raw_text, is_attack, source) tuples.
    """
    rows: list[tuple[str, bool, str]] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for r in csv.reader(f):
            if len(r) < 2 or r[1] not in ("0", "1"):
                continue
            text = r[0].strip()
            if not text or text in seen:
                continue
            seen.add(text)
            rows.append((text, r[1] == "1", "d1_sqliv3"))
    logger.info("D1: loaded %d unique non-empty rows from %s", len(rows), path)
    return rows


def _load_d4(dir_path: Path) -> list[tuple[str, bool, str]]:
    """Load D4 payload-box lines (all treated as attack payloads).

    Returns:
        List of (raw_text, is_attack, source) tuples.
    """
    rows: list[tuple[str, bool, str]] = []
    seen: set[str] = set()
    for file in sorted(dir_path.glob("*.txt")):
        for line in file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line in seen:
                continue
            seen.add(line)
            rows.append((line, True, "d4_payloadbox"))
    logger.info("D4: loaded %d unique payload lines from %s", len(rows), dir_path)
    return rows


def _load_d7(path: Path, normal_sample_size: int, seed: int) -> list[tuple[str, bool, str]]:
    """Load D7 SR-BH 2020 attack rows (full) + a sampled subset of normal rows.

    Args:
        path: Path to data_capec_multilabel.csv.
        normal_sample_size: Max number of Normal==1 rows to sample for
            benign diversity (source dataset has 152,587 such rows).
        seed: Random seed for the normal-row reservoir sample.

    Returns:
        List of (raw_text, is_attack, source) tuples.
    """
    attack_rows: list[tuple[str, bool, str]] = []
    normal_pool: list[str] = []
    rng = random.Random(seed)
    normal_seen = 0

    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        sqli_col = next(c for c in reader.fieldnames if "SQL Injection" in c)
        normal_col = next(c for c in reader.fieldnames if "Normal" in c)
        for row in reader:
            text = (row.get("request_http_request") or "") + " " + (row.get("request_body") or "")
            text = unquote_plus(text).strip()
            if not text:
                continue
            if row.get(sqli_col) == "1":
                attack_rows.append((text, True, "d7_srbh2020"))
            elif row.get(normal_col) == "1":
                normal_seen += 1
                # reservoir sampling to get an unbiased sample without loading all 152K
                if len(normal_pool) < normal_sample_size:
                    normal_pool.append(text)
                else:
                    j = rng.randint(0, normal_seen - 1)
                    if j < normal_sample_size:
                        normal_pool[j] = text

    logger.info(
        "D7: loaded %d attack rows, sampled %d/%d normal rows from %s",
        len(attack_rows),
        len(normal_pool),
        normal_seen,
        path,
    )
    normal_rows = [(t, False, "d7_srbh2020_normal") for t in normal_pool]
    return attack_rows + normal_rows


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
    all_rows = (
        _load_d1(raw_dir / "d1_sqliv3_raw.csv")
        + _load_d4(raw_dir / "payload_box")
        + _load_d7(raw_dir / "sr_bh_2020" / "data_capec_multilabel.csv", normal_sample_size=10000, seed=seed)
        + _load_synthetic_stacked(limit=synthetic_count)
    )
    logger.info("Total raw rows before canonicalize/tag: %d", len(all_rows))

    logger.info("=== Canonicalizing + tagging ===")
    tagged_rows: list[dict] = []
    for i, (text, is_attack, source) in enumerate(all_rows):
        canonical = canonicalize(text, max_decode_iterations=max_decode)
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
