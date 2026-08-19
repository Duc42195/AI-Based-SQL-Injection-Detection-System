"""Build data/processed/branch2_normal.csv — the Branch-2 benign pool.

Unlike Branch 1, Branch 2 (anomaly detection) trains on 100% benign data and
does NOT need class balance — more clean normal rows only helps it estimate
the "safe zone" boundary better. So this script does NOT cap the pool size;
it takes ALL available clean-normal rows from D1 + D3 (CSIC 2010 normal
split) + D7 (SR-BH 2020 Normal=1), after the same content-based safety-net
filter used for Branch 1 (src/preprocessing/multiclass_tagger.py) — Branch 2
is MORE sensitive to benign-pool noise than Branch 1, so this filter matters
even more here (see data_contract.md Muc 3.2).

A held-out anomalous sample is also carried through, unlabeled for training
but reserved for evaluating false-positive rate / detection rate later.

UPDATED 19/08 — scope fix (report/conf/project_history.md §1/§3): the system
is deployed at "Position B" (DB proxy, receives the SQL statement AFTER the
backend has already built it — report/plan/De_xuat_SQLi_Detection_AI.md
§5.1) so production input is always query/parameter text, never a raw HTTP
request. D1 (SQLiV3) is already query-shaped. D3 (CSIC 2010) and D7
(SR-BH 2020) are captured as full HTTP requests (scheme/host/path + query
string/body) — the scheme/host/path portion is pure routing noise that
dilutes whole-string features (measured: special_char_ratio effect size
|d|=1.69 on D1 vs only |d|=0.12 on D3 — data_contract.md). `_strip_url_wrapper`
drops everything up to the first `?` or whitespace (the routing part),
keeping only the query-string/body parameters — the closest available proxy
to Position-B input for these two HTTP-captured sources. Rows with nothing
left after stripping (bare static-asset requests, no parameters at all) are
dropped: they carry no SQL-relevant content either way.

The anomalous eval set now also pulls D1 + D7 attack rows (previously D3
only) — D7's `load_d7` only extracts its "SQL Injection" CAPEC column, so
these are confirmed-SQLi, not the mixed-attack-type problem D3 alone has
(only ~9-15% of D3 "anomalous" rows match any known SQLi/XSS/OS-command
signature — see project_history.md §3).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from sklearn.model_selection import train_test_split

from src.preprocessing.canonicalize import canonicalize
from src.preprocessing.data_sources import load_d1, load_d3, load_d7
from src.preprocessing.multiclass_tagger import matches_any_attack_signature
from src.preprocessing.statistical_features import FEATURE_ORDER, extract_statistical_features
from src.utils import get_logger, load_config

logger = get_logger(__name__)

csv.field_size_limit(10_000_000)

# Sources captured as full HTTP requests rather than bare query/parameter
# text — these get the URL-wrapper strip; D1 is already query-shaped.
_HTTP_CAPTURED_SOURCES = {"d3_csic2010", "d7_srbh2020", "d7_srbh2020_normal"}
_URL_WRAPPER_SEP_RE = re.compile(r"[\s?]")


def _strip_url_wrapper(text: str) -> str:
    """Drop scheme/host/path (routing noise); keep only query-string+body params.

    Finds the first '?' or whitespace character and returns everything from
    there on (dropping a leading '?' if that was the separator) — see module
    docstring. Returns "" if the text has no query string / body at all.
    """
    m = _URL_WRAPPER_SEP_RE.search(text)
    if not m:
        return ""
    rest = text[m.start():]
    if text[m.start()] == "?":
        rest = rest[1:]
    return rest.strip()


def _clean_benign_rows(
    rows: list[tuple[str, bool, str]], max_decode: int
) -> tuple[list[dict], int, int]:
    """Canonicalize benign candidates and reject any matching an attack signature.

    Args:
        rows: (raw_text, is_attack, source) tuples; only is_attack=False rows
            are considered (attack rows from a source are skipped entirely -
            this builder only wants benign data).
        max_decode: Max URL-decode iterations for canonicalize().

    Returns:
        Tuple of (clean rows as dicts, count rejected as mislabeled, count
        dropped for having no query-string/body content after URL stripping).
    """
    clean: list[dict] = []
    rejected = 0
    empty_after_strip = 0
    for text, is_attack, source in rows:
        if is_attack:
            continue
        if source in _HTTP_CAPTURED_SOURCES:
            text = _strip_url_wrapper(text)
            if not text:
                empty_after_strip += 1
                continue
        canonical = canonicalize(text, max_decode_iterations=max_decode)
        if matches_any_attack_signature(canonical.query_canonical):
            rejected += 1
            continue
        feats = extract_statistical_features(canonical.query_canonical).as_dict()
        clean.append(
            {
                "query_raw": text,
                "query_canonical": canonical.query_canonical,
                "has_comment_marker": canonical.has_comment_marker,
                **{name: round(feats[name], 6) for name in FEATURE_ORDER},
                "source": source,
            }
        )
    return clean, rejected, empty_after_strip


def _build_anomalous_rows(
    rows: list[tuple[str, bool, str]], max_decode: int
) -> tuple[list[dict], int]:
    """Canonicalize attack rows (is_attack=True) into eval rows.

    Args:
        rows: (raw_text, is_attack, source) tuples.
        max_decode: Max URL-decode iterations for canonicalize().

    Returns:
        Tuple of (eval rows as dicts, count dropped for having no
        query-string/body content after URL stripping).
    """
    eval_rows: list[dict] = []
    empty_after_strip = 0
    for text, is_attack, source in rows:
        if not is_attack:
            continue
        if source in _HTTP_CAPTURED_SOURCES:
            text = _strip_url_wrapper(text)
            if not text:
                empty_after_strip += 1
                continue
        canonical = canonicalize(text, max_decode_iterations=max_decode)
        feats = extract_statistical_features(canonical.query_canonical).as_dict()
        eval_rows.append(
            {
                "query_raw": text,
                "query_canonical": canonical.query_canonical,
                "has_comment_marker": canonical.has_comment_marker,
                **{name: round(feats[name], 6) for name in FEATURE_ORDER},
                "source": source,
            }
        )
    return eval_rows, empty_after_strip


def main() -> None:
    """Build the Branch-2 benign pool (+ held-out anomalous sample) and write CSVs."""
    cfg = load_config()
    seed = cfg.get_path("project.random_seed", 42)
    max_decode = cfg.get_path("preprocessing.max_decode_iterations", 3)
    test_fraction = cfg.get_path("branch2_anomaly.test_fraction", 0.2)

    raw_dir = Path(cfg.get_path("paths.data_raw", "data/raw"))
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    processed_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=== Loading raw sources (benign + attack candidates, no cap) ===")
    d1_rows = load_d1(raw_dir / "d1_sqliv3_raw.csv")
    logger.info("D1: loaded %d rows", len(d1_rows))
    d3_rows = load_d3(raw_dir / "d3_csic2010_raw.csv")
    logger.info("D3: loaded %d rows", len(d3_rows))
    d7_rows = load_d7(
        raw_dir / "sr_bh_2020" / "data_capec_multilabel.csv", normal_sample_size=None, seed=seed
    )
    logger.info("D7: loaded %d rows", len(d7_rows))

    logger.info("=== Canonicalizing + content-filtering benign candidates (D3/D7 URL-stripped) ===")
    all_rows = d1_rows + d3_rows + d7_rows
    clean_rows, rejected, empty_benign = _clean_benign_rows(all_rows, max_decode)
    logger.info(
        "Clean benign rows: %d (rejected %d as mislabeled/attack-like [%.1f%%], "
        "dropped %d with no params after URL-strip)",
        len(clean_rows), rejected, 100 * rejected / max(1, len(all_rows)), empty_benign,
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

    out_path = processed_dir / "branch2_normal.csv"
    fieldnames = ["id", "query_raw", "query_canonical", "has_comment_marker", *FEATURE_ORDER, "source", "split"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, r in enumerate(final_rows):
            writer.writerow({"id": i, **r})
    logger.info(
        "Wrote %d rows to %s (train=%d, test=%d)", len(final_rows), out_path, len(train_rows), len(test_rows)
    )

    logger.info("=== Building held-out anomalous evaluation sample (D1 + D3 + D7, D3/D7 URL-stripped) ===")
    eval_rows, empty_anom = _build_anomalous_rows(d1_rows + d3_rows + d7_rows, max_decode)
    by_source: dict[str, int] = {}
    for r in eval_rows:
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1
    logger.info(
        "Anomalous eval rows: %d (dropped %d with no params after URL-strip) by source: %s",
        len(eval_rows), empty_anom, by_source,
    )

    eval_path = processed_dir / "branch2_anomalous_eval.csv"
    with eval_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["id", "query_raw", "query_canonical", "has_comment_marker", *FEATURE_ORDER, "source"],
        )
        writer.writeheader()
        for i, r in enumerate(eval_rows):
            writer.writerow({"id": i, **r})
    logger.info("Wrote %d rows to %s (D1+D3+D7 anomalous, for FPR/detection-rate eval)", len(eval_rows), eval_path)


if __name__ == "__main__":
    main()
