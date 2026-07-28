"""Build the train / golden / stream partitions and the replay stream.

Implements section 4 of ``report/plan/mlops_contract.md``.

Three things happen here, and the third is the reason the script exists:

1. ``branch1_train.csv`` is split 40 / 10 / 50 into ``train`` / ``golden`` /
   ``stream``, stratified by class, with ``valid`` carved out of ``train``.
2. A replay stream is assembled at a **realistic ~5 % attack rate** — the
   balanced training file is ~78 % attack, which would make any FPR or drift
   number meaningless — by padding benign traffic from the Branch-2 benign pool.
3. Every partition invariant is **asserted and recorded**. A golden set
   contaminated by training or stream rows would silently invalidate every
   comparison downstream, so the assertions run before anything is written.

Run:  uv run python train/build_mlops_split.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.continual_learning.versioning import content_hash, load_registry
from src.preprocessing.synthetic_stacked import generate_synthetic_stacked
from src.utils import get_logger, load_config

logger = get_logger(__name__)

SPLIT_FILENAME = "branch1_mlops_split.csv"
STREAM_FILENAME = "mlops_stream.csv"
STACKED_FILENAME = "mlops_stacked_pool.csv"
MANIFEST_FILENAME = "split_manifest.json"

# Share of the synthetic new-class pool reserved for golden@2 (the rest goes
# into the stream). Keeps the frozen benchmark able to measure the new class.
NEW_CLASS_GOLDEN_SHARE = 0.2


@dataclass
class Invariant:
    """One asserted property of the split, recorded pass or fail."""

    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        # bool() coerces numpy's np.bool_, which json cannot serialise.
        return {"name": self.name, "passed": bool(self.passed), "detail": self.detail}


@dataclass
class SplitReport:
    """Everything the manifest records about one build."""

    partitions: dict[str, int] = field(default_factory=dict)
    per_class: dict[str, dict[str, int]] = field(default_factory=dict)
    stream: dict[str, Any] = field(default_factory=dict)
    new_class: dict[str, Any] = field(default_factory=dict)
    deduplication: dict[str, Any] = field(default_factory=dict)
    invariants: list[Invariant] = field(default_factory=list)
    content_hash: str = ""
    golden_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "deduplication": self.deduplication,
            "partitions": self.partitions,
            "per_class": self.per_class,
            "stream": self.stream,
            "new_class": self.new_class,
            "invariants": [i.to_dict() for i in self.invariants],
            "content_hash": self.content_hash,
            "golden_hash": self.golden_hash,
            "all_invariants_passed": all(bool(i.passed) for i in self.invariants),
        }


def stratified_partition(
    df: pd.DataFrame, fractions: dict[str, float], seed: int
) -> pd.Series:
    """Assign each row a partition, stratified within each class.

    Args:
        df: Rows with a ``label`` column.
        fractions: Partition name -> share (must sum to ~1).
        seed: Shuffle seed.

    Returns:
        A Series of partition names aligned to ``df.index``.
    """
    rng = np.random.default_rng(seed)
    assignment = pd.Series(index=df.index, dtype=object)
    names = list(fractions)

    for label, group in df.groupby("label", sort=True):
        idx = group.index.to_numpy().copy()  # to_numpy() can return a read-only view
        rng.shuffle(idx)
        # Cumulative cut points keep every row assigned exactly once, with
        # rounding drift absorbed by the last partition.
        bounds = np.cumsum([fractions[n] for n in names]) * len(idx)
        start = 0
        for name, bound in zip(names, bounds):
            stop = int(round(bound))
            assignment.loc[idx[start:stop]] = name
            start = stop
        if start < len(idx):
            assignment.loc[idx[start:]] = names[-1]
    return assignment


def build_new_class_pool(seed: int) -> pd.DataFrame:
    """Generate the synthetic new-class payloads and split them golden/stream.

    The class is 100 % synthetic (see the contract §8): it demonstrates the
    major-bump mechanism, and its accuracy must never be reported as a
    detection result.
    """
    payloads = generate_synthetic_stacked()
    rng = np.random.default_rng(seed)
    idx = np.arange(len(payloads))
    rng.shuffle(idx)

    n_golden = int(round(len(payloads) * NEW_CLASS_GOLDEN_SHARE))
    partitions = ["golden"] * n_golden + ["stream"] * (len(payloads) - n_golden)

    return pd.DataFrame(
        {
            "id": [f"stacked:{i}" for i in idx],
            "query_raw": [payloads[i] for i in idx],
            "query_canonical": [payloads[i].lower() for i in idx],
            "label": 5,
            "label_name": "stacked",
            "source": "synthetic_stacked",
            "partition": partitions,
        }
    )


def build_stream(
    attack_rows: pd.DataFrame,
    benign_rows: pd.DataFrame,
    new_class_rows: pd.DataFrame,
    *,
    attack_rate: float,
    phase_a_fraction: float,
    new_class_share: float,
    seed: int,
) -> pd.DataFrame:
    """Assemble the ordered replay stream.

    Phase A contains no new-class traffic so the drift monitor can be shown
    quiet before it is shown firing; phase B introduces it.

    Args:
        attack_rows: Attack rows from the stream partition.
        benign_rows: Benign rows (already excluded/deduplicated by the caller).
        new_class_rows: Synthetic new-class rows allocated to the stream.
        attack_rate: Target share of attack traffic (e.g. 0.05).
        phase_a_fraction: Share of the stream before the new class appears.
        new_class_share: Share of phase-B *attacks* that are the new class.
        seed: Shuffle seed.

    Returns:
        The stream as an ordered DataFrame with ``phase`` and ``position``.
    """
    rng = np.random.default_rng(seed)

    # Benign supply is the binding constraint: size the stream from it.
    n_benign = len(benign_rows)
    total = int(n_benign / (1.0 - attack_rate))
    n_attack = total - n_benign

    n_phase_a = int(round(total * phase_a_fraction))
    n_phase_b = total - n_phase_a
    attacks_a = int(round(n_attack * phase_a_fraction))
    attacks_b = n_attack - attacks_a

    # Phase B attacks are part known-class, part new-class. The synthetic pool
    # is small (a few hundred templates), so it is sampled with replacement —
    # an attacker reusing payloads is realistic, but it is recorded in the
    # manifest because it inflates the new class's apparent volume.
    n_new = min(int(round(attacks_b * new_class_share)), attacks_b)
    n_known_b = attacks_b - n_new

    known = attack_rows.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    take_a = known.iloc[:attacks_a]
    take_b = known.iloc[attacks_a : attacks_a + n_known_b]

    new_sample = new_class_rows.sample(
        n=n_new, replace=n_new > len(new_class_rows), random_state=seed
    )

    benign = benign_rows.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    benign_a = benign.iloc[: n_phase_a - len(take_a)]
    benign_b = benign.iloc[n_phase_a - len(take_a) :]

    phase_a = pd.concat([take_a, benign_a], ignore_index=True)
    phase_a = phase_a.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    phase_a["phase"] = "A"

    phase_b = pd.concat([take_b, new_sample, benign_b], ignore_index=True)
    phase_b = phase_b.sample(frac=1.0, random_state=seed + 1).reset_index(drop=True)
    phase_b["phase"] = "B"

    stream = pd.concat([phase_a, phase_b], ignore_index=True)
    stream["position"] = np.arange(len(stream))
    return stream


def main() -> None:
    """Build the partitions and the stream, asserting every invariant."""
    cfg = load_config()
    processed = Path(cfg.get_path("paths.data_processed", "data/processed"))
    artifacts = Path(cfg.get_path("mlops.artifacts_dir", "report/metrics/continual_learning"))
    artifacts.mkdir(parents=True, exist_ok=True)

    seed = int(cfg.get_path("mlops.split.seed", 42))
    fractions = {
        "train": float(cfg.get_path("mlops.split.train_fraction", 0.4)),
        "golden": float(cfg.get_path("mlops.split.golden_fraction", 0.1)),
        "stream": float(cfg.get_path("mlops.split.stream_fraction", 0.5)),
    }
    valid_fraction = float(cfg.get_path("mlops.split.valid_fraction", 0.15))
    attack_rate = float(cfg.get_path("mlops.stream.attack_rate", 0.05))
    phase_a_fraction = float(cfg.get_path("mlops.stream.phase_a_fraction", 0.4))
    new_class_share = float(cfg.get_path("mlops.stream.new_class_share_in_phase_b", 0.3))
    window_size = int(cfg.get_path("mlops.stream.window_size", 1000))

    # ── 1. Partition the labelled Branch-1 data ────────────────────────────
    raw = pd.read_csv(processed / "branch1_train.csv")
    logger.info("Loaded %s rows from branch1_train.csv", f"{len(raw):,}")

    # Deduplicate by canonical text BEFORE partitioning. The file holds 4,277
    # repeated texts; partitioning by row id would scatter copies of the same
    # query across train and golden, which is leakage — the model would be
    # scored on text it was trained on. Texts carrying conflicting labels are
    # dropped outright rather than arbitrarily resolved: they are genuine label
    # noise and would silently cap the achievable score.
    raw["query_canonical"] = raw["query_canonical"].astype(str)
    label_counts = raw.groupby("query_canonical")["label"].nunique()
    conflicted = set(label_counts[label_counts > 1].index)
    df = raw[~raw["query_canonical"].isin(conflicted)].copy()
    n_after_conflict = len(df)
    df = df.drop_duplicates(subset="query_canonical", keep="first").reset_index(drop=True)
    dedup_report = {
        "input_rows": len(raw),
        "conflicting_texts_dropped": len(conflicted),
        "rows_dropped_for_conflict": len(raw) - n_after_conflict,
        "duplicate_rows_dropped": n_after_conflict - len(df),
        "rows_kept": len(df),
    }
    logger.info(
        "Deduplicated: %s -> %s rows (%s duplicates, %s conflicting texts)",
        f"{len(raw):,}",
        f"{len(df):,}",
        f"{dedup_report['duplicate_rows_dropped']:,}",
        len(conflicted),
    )

    df["partition"] = stratified_partition(df, fractions, seed)

    # Carve `valid` out of `train`. `golden` is never touched by training.
    rng = np.random.default_rng(seed)
    train_idx = df.index[df["partition"] == "train"].to_numpy().copy()
    rng.shuffle(train_idx)
    n_valid = int(round(len(train_idx) * valid_fraction))
    df.loc[train_idx[:n_valid], "partition"] = "valid"

    report = SplitReport()
    report.deduplication = dedup_report
    report.partitions = df["partition"].value_counts().to_dict()
    report.per_class = {
        str(name): group["partition"].value_counts().to_dict()
        for name, group in df.groupby("label_name", sort=True)
    }

    # ── 2. Assemble the replay stream ─────────────────────────────────────
    canon = df["query_canonical"].astype(str)
    all_branch1_canon = set(canon)

    b2_train = pd.read_csv(processed / "branch2_data.csv")
    b2_train_canon = set(
        b2_train.loc[b2_train["split"] == "train", "query_canonical"].astype(str)
    )

    pool = pd.read_csv(processed / "branch2_normal.csv")
    pool["query_canonical"] = pool["query_canonical"].astype(str)
    pool = pool.drop_duplicates(subset="query_canonical")
    # Exclude Branch-2's own training rows (reusing them would leak into the
    # anomaly scores this loop depends on) and everything already in Branch 1
    # (its `normal` class comes from this same CSIC pool, so reuse would put
    # golden rows into the stream).
    usable = pool[
        ~pool["query_canonical"].isin(b2_train_canon | all_branch1_canon)
    ].copy()
    usable["id"] = "b2n:" + usable["id"].astype(str)
    usable["label"] = 0
    usable["label_name"] = "normal"
    usable["source"] = "branch2_normal_pool"
    logger.info("Usable stream benign after exclusions: %s", f"{len(usable):,}")

    stream_attacks = df[(df["partition"] == "stream") & (df["label"] != 0)].copy()
    stream_attacks["id"] = "b1:" + stream_attacks["id"].astype(str)

    new_class = build_new_class_pool(seed)
    new_class_stream = new_class[new_class["partition"] == "stream"]

    columns = ["id", "query_raw", "query_canonical", "label", "label_name", "source"]
    stream = build_stream(
        stream_attacks[columns],
        usable[columns],
        new_class_stream[columns],
        attack_rate=attack_rate,
        phase_a_fraction=phase_a_fraction,
        new_class_share=new_class_share,
        seed=seed,
    )

    actual_attack_rate = float((stream["label"] != 0).mean())
    report.stream = {
        "rows": len(stream),
        "windows": (len(stream) + window_size - 1) // window_size,
        "window_size": window_size,
        "target_attack_rate": attack_rate,
        "actual_attack_rate": round(actual_attack_rate, 5),
        "phase_a_rows": int((stream["phase"] == "A").sum()),
        "phase_b_rows": int((stream["phase"] == "B").sum()),
        "benign_source": "data/processed/branch2_normal.csv",
        "benign_available_after_exclusions": len(usable),
        "class_mix": stream["label_name"].value_counts().to_dict(),
    }
    report.new_class = {
        "name": "stacked",
        "unique_payloads": len(new_class),
        "golden_rows": int((new_class["partition"] == "golden").sum()),
        "stream_unique": len(new_class_stream),
        "stream_occurrences": int((stream["label_name"] == "stacked").sum()),
        "sampled_with_replacement": True,
        "caveat": (
            "100% synthetic templated payloads; demonstrates the major-bump "
            "mechanism only - accuracy on this class is not a detection result."
        ),
    }

    # ── 3. Assert the invariants BEFORE writing anything ──────────────────
    golden_canon = set(df.loc[df["partition"] == "golden", "query_canonical"].astype(str))
    trainish_canon = set(
        df.loc[df["partition"].isin(["train", "valid"]), "query_canonical"].astype(str)
    )
    stream_canon = set(stream["query_canonical"].astype(str))

    report.invariants = [
        Invariant(
            "golden_disjoint_from_train",
            not (golden_canon & trainish_canon),
            f"overlap={len(golden_canon & trainish_canon)}",
        ),
        Invariant(
            "golden_disjoint_from_stream",
            not (golden_canon & stream_canon),
            f"overlap={len(golden_canon & stream_canon)}",
        ),
        Invariant(
            "stream_benign_excludes_branch2_training",
            not (set(usable["query_canonical"]) & b2_train_canon),
            f"overlap={len(set(usable['query_canonical']) & b2_train_canon)}",
        ),
        Invariant(
            "stream_benign_deduplicated",
            not usable["query_canonical"].duplicated().any(),
            f"duplicates={int(usable['query_canonical'].duplicated().sum())}",
        ),
        Invariant(
            "phase_a_has_no_new_class",
            not ((stream["phase"] == "A") & (stream["label_name"] == "stacked")).any(),
            "phase A must be quiet so phase-B drift is attributable",
        ),
        Invariant(
            "attack_rate_within_tolerance",
            abs(actual_attack_rate - attack_rate) < 0.01,
            f"actual={actual_attack_rate:.4f} target={attack_rate}",
        ),
        Invariant(
            "every_row_assigned_one_partition",
            df["partition"].notna().all(),
            f"unassigned={int(df['partition'].isna().sum())}",
        ),
    ]

    for inv in report.invariants:
        (logger.info if inv.passed else logger.error)(
            "invariant %-40s %s  %s", inv.name, "PASS" if inv.passed else "FAIL", inv.detail
        )

    failed = [i.name for i in report.invariants if not i.passed]
    if failed:
        raise SystemExit(f"Split invariants failed: {', '.join(failed)}. Nothing written.")

    # ── 4. Write artifacts and seal data version 1.0 ──────────────────────
    report.content_hash = content_hash(zip(df["id"], df["label"]))
    golden = df[df["partition"] == "golden"]
    report.golden_hash = content_hash(zip(golden["id"], golden["label"]))

    df.to_csv(processed / SPLIT_FILENAME, index=False)
    stream.to_csv(processed / STREAM_FILENAME, index=False)
    new_class.to_csv(processed / STACKED_FILENAME, index=False)

    with (artifacts / MANIFEST_FILENAME).open("w", encoding="utf-8") as handle:
        json.dump(report.to_dict(), handle, indent=2)

    registry = load_registry("branch1", cfg)
    if registry.get("1.0") is None:
        registry.seal(
            label_space=sorted(df["label_name"].astype(str).unique()),
            n_rows=len(df),
            content_hash_value=report.content_hash,
            reason="baseline: 5-class Branch-1 data as trained into branch1_v1",
            partitions={k: int(v) for k, v in report.partitions.items()},
            golden_hash=report.golden_hash,
            protected=True,
        )
        registry.save()
    else:
        logger.info("Data version 1.0 already sealed; leaving the registry unchanged")

    logger.info("=== Split complete ===")
    for name, count in sorted(report.partitions.items()):
        logger.info("  %-7s %s", name, f"{count:,}")
    logger.info(
        "  stream  %s rows (%s windows) at %.2f%% attack",
        f"{len(stream):,}",
        report.stream["windows"],
        actual_attack_rate * 100,
    )
    logger.info("Wrote %s, %s, %s", SPLIT_FILENAME, STREAM_FILENAME, MANIFEST_FILENAME)


if __name__ == "__main__":
    main()
