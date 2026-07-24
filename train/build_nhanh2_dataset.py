"""Build data/processed/nhanh2_normal.csv — the Branch-2 benign pool.

Unlike Branch 1, Branch 2 (anomaly detection) trains on 100% benign data and
does NOT need class balance — more clean normal rows only helps it estimate
the "safe zone" boundary better. So this script does NOT cap the pool size;
it takes ALL available clean-normal rows from D1 + D3 (CSIC 2010 normal
split) + D7 (SR-BH 2020 Normal=1), after the same content-based safety-net
filter used for Branch 1 (src/preprocessing/multiclass_tagger.py) — Branch 2
is MORE sensitive to benign-pool noise than Branch 1, so this filter matters
even more here (see data_contract.md Muc 3.2).

A held-out anomalous sample (D3's "anomalous" split) is also carried through,
unlabeled for training but reserved for evaluating false-positive rate /
detection rate later (Day 5-6).
"""

from __future__ import annotations

import csv
from pathlib import Path

from sklearn.model_selection import train_test_split

from src.preprocessing.canonicalize import canonicalize
from src.preprocessing.data_sources import load_d1, load_d3, load_d7
from src.preprocessing.multiclass_tagger import matches_any_attack_signature
from src.preprocessing.statistical_features import extract_statistical_features
from src.utils import get_logger, load_config

logger = get_logger(__name__)

csv.field_size_limit(10_000_000)


def _clean_benign_rows(
    rows: list[tuple[str, bool, str]], max_decode: int
) -> tuple[list[dict], int]:
    """Canonicalize benign candidates and reject any matching an attack signature.

    Args:
        rows: (raw_text, is_attack, source) tuples; only is_attack=False rows
            are considered (attack rows from a source are skipped entirely -
            this builder only wants benign data).
        max_decode: Max URL-decode iterations for canonicalize().

    Returns:
        Tuple of (clean rows as dicts, count of rows rejected as mislabeled).
    """
    clean: list[dict] = []
    rejected = 0
    for text, is_attack, source in rows:
        if is_attack:
            continue
        canonical = canonicalize(text, max_decode_iterations=max_decode)
        if matches_any_attack_signature(canonical.query_canonical):
            rejected += 1
            continue
        features = extract_statistical_features(canonical.query_canonical)
        clean.append(
            {
                "query_raw": text,
                "query_canonical": canonical.query_canonical,
                "has_comment_marker": canonical.has_comment_marker,
                "length": features.length,
                "special_char_ratio": round(features.special_char_ratio, 6),
                "sql_keyword_count": features.sql_keyword_count,
                "entropy": round(features.entropy, 6),
                "source": source,
            }
        )
    return clean, rejected


def main() -> None:
    """Build the Branch-2 benign pool (+ held-out anomalous sample) and write CSVs."""
    cfg = load_config()
    seed = cfg.get_path("project.random_seed", 42)
    max_decode = cfg.get_path("preprocessing.max_decode_iterations", 3)
    test_fraction = cfg.get_path("branch2_anomaly.test_fraction", 0.2)

    raw_dir = Path(cfg.get_path("paths.data_raw", "data/raw"))
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    processed_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=== Loading raw sources (benign candidates, no cap) ===")
    d1_rows = load_d1(raw_dir / "d1_sqliv3_raw.csv")
    logger.info("D1: loaded %d rows", len(d1_rows))
    d3_rows = load_d3(raw_dir / "d3_csic2010_raw.csv")
    logger.info("D3: loaded %d rows", len(d3_rows))
    d7_rows = load_d7(
        raw_dir / "sr_bh_2020" / "data_capec_multilabel.csv", normal_sample_size=None, seed=seed
    )
    logger.info("D7: loaded %d rows", len(d7_rows))

    logger.info("=== Canonicalizing + content-filtering benign candidates ===")
    all_rows = d1_rows + d3_rows + d7_rows
    clean_rows, rejected = _clean_benign_rows(all_rows, max_decode)
    logger.info(
        "Clean benign rows: %d (rejected %d as mislabeled/attack-like, %.1f%%)",
        len(clean_rows),
        rejected,
        100 * rejected / max(1, len(all_rows)),
    )

    logger.info("=== Deduplicating ===")
    seen: set[str] = set()
    deduped: list[dict] = []
    for r in clean_rows:
        if r["query_canonical"] in seen:
            continue
        seen.add(r["query_canonical"])
        deduped.append(r)
    logger.info("After dedup: %d rows (removed %d duplicates)", len(deduped), len(clean_rows) - len(deduped))

    logger.info("=== Splitting train/test (test_fraction=%.2f, seed=%d) ===", test_fraction, seed)
    train_rows, test_rows = train_test_split(deduped, test_size=test_fraction, random_state=seed)
    for r in train_rows:
        r["split"] = "train"
    for r in test_rows:
        r["split"] = "test"
    final_rows = train_rows + test_rows

    out_path = processed_dir / "nhanh2_normal.csv"
    fieldnames = [
        "id",
        "query_raw",
        "query_canonical",
        "has_comment_marker",
        "length",
        "special_char_ratio",
        "sql_keyword_count",
        "entropy",
        "source",
        "split",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, r in enumerate(final_rows):
            writer.writerow({"id": i, **r})
    logger.info(
        "Wrote %d rows to %s (train=%d, test=%d)", len(final_rows), out_path, len(train_rows), len(test_rows)
    )

    logger.info("=== Building held-out anomalous evaluation sample (D3 only) ===")
    d3_anomalous = [(t, True, "d3_csic2010") for t, is_attack, s in d3_rows if is_attack]
    eval_rows = []
    for text, _, source in d3_anomalous:
        canonical = canonicalize(text, max_decode_iterations=max_decode)
        features = extract_statistical_features(canonical.query_canonical)
        eval_rows.append(
            {
                "query_raw": text,
                "query_canonical": canonical.query_canonical,
                "has_comment_marker": canonical.has_comment_marker,
                "length": features.length,
                "special_char_ratio": round(features.special_char_ratio, 6),
                "sql_keyword_count": features.sql_keyword_count,
                "entropy": round(features.entropy, 6),
                "source": source,
            }
        )

    eval_path = processed_dir / "nhanh2_anomalous_eval.csv"
    with eval_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "query_raw",
                "query_canonical",
                "has_comment_marker",
                "length",
                "special_char_ratio",
                "sql_keyword_count",
                "entropy",
                "source",
            ],
        )
        writer.writeheader()
        for i, r in enumerate(eval_rows):
            writer.writerow({"id": i, **r})
    logger.info("Wrote %d rows to %s (D3 anomalous, for FPR/detection-rate eval)", len(eval_rows), eval_path)


if __name__ == "__main__":
    main()
