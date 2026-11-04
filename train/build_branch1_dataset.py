"""Build data/processed/branch1_train.csv — the balanced Branch-1 dataset.

Combines sources (see data_contract.md Muc 2.1):
- D1 SQLiV3 raw (normal + attack rows, both used)
- D7 SR-BH 2020 (attack rows via "66 - SQL Injection"==1, plus a sample of
  "000 - Normal"==1 rows for benign diversity)
- D6 Superviz25 (26/8, see data_contract.md): real sqlmap-generated traffic —
  fills the "D6 Docker-lab/sqlmap traffic" slot this project always reserved
  for a real stacked-query source (configs/config.yaml previously said
  "re-enable [stacked] once real stacked-query examples are available (e.g.
  from D6 Docker-lab/sqlmap traffic)"). Unlike the other 3 sources, D6 rows
  are NOT re-tagged by the regex-based `tag_query` — see
  `load_d6_superviz25`'s docstring for why its own `attack_technique` is
  trusted directly instead.

Synthetic `stacked` payloads (src/preprocessing/synthetic_stacked.py) are no
longer loaded now that D6 provides ~20k REAL stacked examples — the original
reason they were excluded (100% synthetic template, trivially separable, see
reports/branch1_architecture_comparison.json) no longer applies once real
data exists, which is exactly the condition the exclusion was waiting on.

D4 (payload-box) DROPPED 27/8: only 124 raw payloads (union_based/boolean_
blind/time_blind only, no error_based/stacked), contributing 16 of 90,000
final rows after undersampling — negligible next to D6's per-class volume,
and its removal simplifies the paper's data section to exactly 4 sources
total across both branches (D1/D3/D6/D7 — D3/CSIC2010 is Branch 2-only, see
build_branch2_dataset.py) instead of 5. Verified this doesn't just get
hand-waved away: retrained tfidf_logreg with D4 removed and confirmed the
delta against the D4-included run is within noise (data_contract.md §6).

Each row is canonicalized (src/preprocessing/canonicalize.py) and tagged
(src/preprocessing/multiclass_tagger.py, except D6 - see above) on the
CANONICAL text, then any label in `exclude_labels` is dropped, then each
remaining class is undersampled down to
`branch1_supervised.balance.target_per_class` (classes with fewer rows are
kept in full) before a train/test split. D6's attack rows get a GROUP-aware
split (one sqlmap campaign/`attack_id` never straddles both sides — see
`_group_aware_split`); everything else keeps the original per-row stratified
split.
"""

from __future__ import annotations

import csv
import random
import re
from pathlib import Path

from sklearn.model_selection import train_test_split

from src.preprocessing.canonicalize import canonicalize
from src.preprocessing.data_sources import load_d1, load_d6_superviz25, load_d7
from src.preprocessing.multiclass_tagger import (
    LABEL_NAMES,
    LABEL_STACKED,
    matches_any_attack_signature,
    tag_query,
)
from src.utils import get_logger, load_config

logger = get_logger(__name__)

csv.field_size_limit(10_000_000)

# Control chars (C0/DEL, excluding the whitespace \t\n\r which are collapsed
# separately). canonicalize can leave these in query_canonical; a CSV round-trip
# silently strips them, so two texts that differ only by a control char are one
# text to the trained model yet look distinct in memory - which let duplicates
# slip across the train/test split. Strip them at build time so the stored text
# is byte-stable and dedup matches exactly what the model reads back.
_CTRL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean_canonical(text: str) -> str:
    """Strip control chars and collapse all whitespace runs to single spaces."""
    return " ".join(_CTRL_CHARS.sub("", text).split())


def _dedup_by_canonical(rows: list[dict]) -> list[dict]:
    """Drop duplicate rows sharing the same `query_canonical`, keeping the first.

    Deduplicating BEFORE the train/test split is what prevents cross-split
    leakage: if the same canonical text can appear in both train and test, the
    model can memorise it at train time and be handed it back at test time,
    inflating the eval F1 (Branch-1 audit Mảng 2: 949 texts straddled the
    splits, 4,277 extra copies). Order is preserved (source order d1+d4+d7), so
    the kept copy is deterministic; when duplicates disagree on label, the first
    label wins and the collision is logged.

    Args:
        rows: Tagged rows (each a dict with "query_canonical" and "label").

    Returns:
        Rows with a single copy per distinct `query_canonical`.
    """
    seen: dict[str, int] = {}
    deduped: list[dict] = []
    label_conflicts = 0
    for r in rows:
        # query_canonical is already control-char-stripped + whitespace-collapsed
        # by _clean_canonical at build time, so it is a byte-stable dedup key.
        key = r["query_canonical"]
        if key in seen:
            if seen[key] != r["label"]:
                label_conflicts += 1
            continue
        seen[key] = r["label"]
        deduped.append(r)
    logger.info(
        "Dedup by query_canonical: %d -> %d rows (%d duplicate copies removed, %d had a label conflict)",
        len(rows),
        len(deduped),
        len(rows) - len(deduped),
        label_conflicts,
    )
    return deduped


def _group_aware_split(
    rows: list[dict], test_fraction: float, seed: int
) -> tuple[list[dict], list[dict]]:
    """Split D6 attack rows so a whole sqlmap campaign (`attack_id`) lands on one side.

    Campaign id is recovered from `source` (encoded by `load_d6_superviz25`
    as ``"d6_superviz25:<attack_id>"``). Done per-label (roughly preserving
    class balance across the split) via a shuffled greedy fill rather than
    `sklearn.model_selection.GroupShuffleSplit`, since we also want the
    result close to `test_fraction` per class, not just "some random group
    split" - see module docstring for why this matters (near-duplicate
    successive bisection-probe queries from the same campaign must not
    straddle train/test).

    Args:
        rows: D6 attack rows only (each dict's "source" has a
            ``"d6_superviz25:"`` prefix).
        test_fraction: Target fraction of rows (per label) to place in test.
        seed: Random seed for shuffling campaign order.

    Returns:
        (train_rows, test_rows).
    """
    # Independent RNG per label (see _undersample's docstring for why a
    # single shared RNG across a sorted per-label loop is the wrong choice:
    # one label's shuffle would otherwise depend on how many campaigns every
    # OTHER label had, not just its own).
    by_label: dict[int, dict[str, list[dict]]] = {}
    for r in rows:
        campaign_id = r["source"].split(":", 1)[1]
        by_label.setdefault(r["label"], {}).setdefault(campaign_id, []).append(r)

    train: list[dict] = []
    test: list[dict] = []
    for label, campaigns in sorted(by_label.items()):
        rng = random.Random(f"{seed}:{label}")
        total = sum(len(v) for v in campaigns.values())
        target_test = round(test_fraction * total)
        campaign_ids = list(campaigns.keys())
        rng.shuffle(campaign_ids)
        test_count = 0
        for cid in campaign_ids:
            campaign_rows = campaigns[cid]
            if test_count < target_test:
                test.extend(campaign_rows)
                test_count += len(campaign_rows)
            else:
                train.extend(campaign_rows)
        logger.info(
            "  D6 group-split label=%d (%s): %d campaigns, %d rows -> train=%d test=%d",
            label, LABEL_NAMES[label], len(campaign_ids), total,
            total - test_count, test_count,
        )
    return train, test


def _undersample(rows: list[dict], target_per_class: int, seed: int) -> list[dict]:
    """Cap each label's row count at `target_per_class` via random sampling.

    Args:
        rows: All tagged rows (each a dict with a "label" key).
        target_per_class: Max rows to keep per label; smaller classes are
            kept in full.
        seed: Random seed for reproducible sampling.

    Returns:
        The balanced row list (order not preserved across labels).

    BUG FOUND AND FIXED 27/8: previously used ONE `random.Random(seed)`
    instance shared across every label's `.sample()` call, in a fixed
    per-label loop. `.sample()`'s number of internal draws depends on the
    input pool size, so changing an EARLIER label's pool size (e.g. removing
    D4/payload-box, which only ever touched union_based/boolean_blind/
    time_blind) shifted the shared RNG's state before it ever reached a
    LATER label - `stacked` (processed last, sorted by label id) swung from
    83.5% to 54.6% recall purely from this ordering artifact, even though
    D4 contributed zero stacked rows and stacked's own candidate pool barely
    changed. Confirmed by re-running with D4 removed and finding the delta
    concentrated entirely in stacked/time_blind confusion - the same class
    of "silently order/state-dependent, looks fine until something upstream
    changes" issue as the hardcoded-LABEL_ORDER F1-macro bug (data_contract.md
    Muc 3.3). Fixed: each label now gets its OWN independent RNG stream
    (seeded from `(seed, label)`), so one class's sample is invariant to
    every other class's pool size - required for the reported numbers to be
    reproducible in the face of upstream data changes, not just for a fixed
    input.
    """
    by_label: dict[int, list[dict]] = {}
    for r in rows:
        by_label.setdefault(r["label"], []).append(r)

    balanced: list[dict] = []
    for label, group in sorted(by_label.items()):
        rng = random.Random(f"{seed}:{label}")
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
    test_fraction = cfg.get_path("branch1_supervised.balance.test_fraction", 0.2)
    exclude_labels = set(cfg.get_path("branch1_supervised.balance.exclude_labels", []))
    dedup_canonical = cfg.get_path("branch1_supervised.balance.dedup_query_canonical", True)
    d6_benign_cap = cfg.get_path("branch1_supervised.balance.d6_benign_cap", 50000)
    d6_attack_cap = cfg.get_path("branch1_supervised.balance.d6_attack_technique_cap", 20000)

    raw_dir = Path(cfg.get_path("paths.data_raw", "data/raw"))
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    processed_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=== Loading raw sources ===")
    d1_rows = load_d1(raw_dir / "d1_sqliv3_raw.csv")
    logger.info("D1: loaded %d unique non-empty rows", len(d1_rows))
    d7_rows = load_d7(
        raw_dir / "sr_bh_2020" / "data_capec_multilabel.csv", normal_sample_size=10000, seed=seed
    )
    logger.info("D7: loaded %d rows (attack + sampled normal)", len(d7_rows))
    d6_rows = load_d6_superviz25(
        raw_dir / "superviz25" / "dataset.csv", seed=seed,
        benign_cap=d6_benign_cap, attack_cap=d6_attack_cap,
    )
    logger.info("D6: loaded %d rows (benign + 5 mapped attack_technique classes)", len(d6_rows))
    # D6 benign rows (label_override=None) behave identically to every other
    # source under tag_query (is_attack=False -> LABEL_NORMAL always) - safe
    # to fold into the plain 3-tuple pipeline below. Only D6's ATTACK rows
    # need the label_override/no-retag/group-split treatment - see
    # load_d6_superviz25's docstring.
    d6_benign_3tuples = [(text, False, source) for text, is_attack, source, _ in d6_rows if not is_attack]
    d6_attack_4tuples = [(text, source, label) for text, is_attack, source, label in d6_rows if is_attack]

    all_rows = d1_rows + d7_rows + d6_benign_3tuples
    logger.info(
        "Skipping synthetic_stacked source: D6 provides %d REAL stacked-technique rows "
        "(the original reason to exclude synthetic - 100%% templated, trivially separable "
        "- no longer applies once real data exists, which is exactly the condition "
        "configs/config.yaml's exclude_labels comment was waiting on)",
        sum(1 for _, source, label in d6_attack_4tuples if label == LABEL_STACKED),
    )
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
                "query_canonical": _clean_canonical(canonical.query_canonical),
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

    logger.info("=== Canonicalizing D6 attack rows (label trusted as-is, no regex re-tag) ===")
    for i, (text, source, label) in enumerate(d6_attack_4tuples):
        canonical = canonicalize(text, max_decode_iterations=max_decode)
        tagged_rows.append(
            {
                "query_raw": text,
                "query_canonical": _clean_canonical(canonical.query_canonical),
                "has_comment_marker": canonical.has_comment_marker,
                "label": label,
                "label_name": LABEL_NAMES[label],
                "source": source,  # "d6_superviz25:<attack_id>" - campaign for group-split
            }
        )
        if (i + 1) % 100000 == 0:
            logger.info("  ... processed %d/%d D6 attack rows", i + 1, len(d6_attack_4tuples))

    if exclude_labels:
        before = len(tagged_rows)
        tagged_rows = [r for r in tagged_rows if r["label"] not in exclude_labels]
        logger.info(
            "Excluded %d rows with label in %s (config: branch1_supervised.balance.exclude_labels)",
            before - len(tagged_rows),
            sorted(exclude_labels),
        )

    if dedup_canonical:
        logger.info("=== Deduplicating by query_canonical (pre-split, anti-leakage) ===")
        tagged_rows = _dedup_by_canonical(tagged_rows)

    logger.info("=== Undersampling to target_per_class=%d ===", target_per_class)
    balanced_rows = _undersample(tagged_rows, target_per_class, seed)
    logger.info("Balanced total: %d rows", len(balanced_rows))

    logger.info("=== Splitting train/test (test_fraction=%.2f, seed=%d) ===", test_fraction, seed)
    # D6 attack rows get a GROUP-aware split (whole sqlmap campaign on one
    # side - see _group_aware_split's docstring); everything else (D1/D4/D7 +
    # D6 benign, all i.i.d. per-row) keeps the original stratified split. A
    # plain row-level split here would let near-duplicate successive
    # bisection-probe queries from the same campaign straddle train/test -
    # the same leakage shape the Branch-1 audit already found and fixed for
    # exact duplicates (data_contract.md, Mảng 2), just for near-duplicates.
    groupable = [r for r in balanced_rows if r["source"].startswith("d6_superviz25:")]
    ungroupable = [r for r in balanced_rows if not r["source"].startswith("d6_superviz25:")]

    labels = [r["label"] for r in ungroupable]
    train_rows, test_rows = train_test_split(
        ungroupable, test_size=test_fraction, random_state=seed, stratify=labels
    )
    if groupable:
        group_train, group_test = _group_aware_split(groupable, test_fraction, seed)
        train_rows += group_train
        test_rows += group_test

    for r in train_rows:
        r["split"] = "train"
    for r in test_rows:
        r["split"] = "test"
    final_rows = train_rows + test_rows

    out_path = processed_dir / "branch1_train.csv"
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
