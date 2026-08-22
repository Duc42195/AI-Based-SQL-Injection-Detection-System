"""Build the Base / golden / stream partitions for the real-class-holdout CL scenario.

Supersedes the synthetic-`stacked` design (``train/build_mlops_split.py``) for
the paper's reported continual-learning numbers. Three things happen here:

1. ``union_based`` (a real SQLi class, not a synthetic one) is entirely
   withheld from the initial training pool ("Base"), so a major-bump retrain
   later has to learn a genuinely new attack type, and its accuracy is a real
   detection result rather than a mechanism demo.
2. A two-pour replay stream is assembled: scenario 1 introduces the withheld
   class (a light trickle of known traffic first, for a quiet drift-monitor
   reference, then the held-out class interleaved in); scenario 2 is more
   volume of the 4 known classes only, no new class.
3. Every partition invariant is asserted and recorded before anything is
   written, matching ``build_mlops_split.py``'s discipline.

Run:  uv run python train/build_cl_scenario_split.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.utils import get_logger, load_config

logger = get_logger(__name__)

SPLIT_FILENAME = "cl_scenario_split.csv"
STREAM_FILENAME = "cl_scenario_stream.csv"
MANIFEST_FILENAME = "split_manifest.json"

COLUMNS = ["id", "query_raw", "query_canonical", "label", "label_name"]


@dataclass
class Invariant:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": bool(self.passed), "detail": self.detail}


@dataclass
class SplitReport:
    partitions: dict[str, int] = field(default_factory=dict)
    per_class: dict[str, dict[str, int]] = field(default_factory=dict)
    stream: dict[str, Any] = field(default_factory=dict)
    invariants: list[Invariant] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "partitions": self.partitions,
            "per_class": self.per_class,
            "stream": self.stream,
            "invariants": [i.to_dict() for i in self.invariants],
            "all_invariants_passed": all(bool(i.passed) for i in self.invariants),
        }


def load_dedup_branch1(processed: Path) -> pd.DataFrame:
    """Dedup ``branch1_train.csv`` by canonical text (same rule as build_mlops_split.py)."""
    raw = pd.read_csv(processed / "branch1_train.csv")
    raw["query_canonical"] = raw["query_canonical"].astype(str)
    label_counts = raw.groupby("query_canonical")["label"].nunique()
    conflicted = set(label_counts[label_counts > 1].index)
    df = raw[~raw["query_canonical"].isin(conflicted)].copy()
    df = df.drop_duplicates(subset="query_canonical", keep="first").reset_index(drop=True)
    logger.info("Deduplicated: %s -> %s rows", f"{len(raw):,}", f"{len(df):,}")
    return df


def load_benign_pool(processed: Path) -> pd.DataFrame:
    """Branch-2 normal pool, excluding rows Branch 1 or Branch 2 already trained on."""
    b1 = load_dedup_branch1(processed)
    b1_canon = set(b1["query_canonical"])

    b2 = pd.read_csv(processed / "branch2_data.csv")
    b2_train_canon = set(b2.loc[b2["split"] == "train", "query_canonical"].astype(str))

    pool = pd.read_csv(processed / "branch2_normal.csv")
    pool["query_canonical"] = pool["query_canonical"].astype(str)
    pool = pool.drop_duplicates(subset="query_canonical")
    usable = pool[~pool["query_canonical"].isin(b2_train_canon | b1_canon)].copy()
    usable["id"] = "b2n:" + usable["id"].astype(str)
    usable["label"] = 0
    usable["label_name"] = "normal"
    return usable[COLUMNS].reset_index(drop=True)


def main() -> None:
    cfg = load_config()
    processed = Path(cfg.get_path("paths.data_processed", "data/processed"))
    artifacts = Path(cfg.get_path("cl_scenario.artifacts_dir", "report/metrics/cl_scenario"))
    artifacts.mkdir(parents=True, exist_ok=True)

    seed = int(cfg.get_path("cl_scenario.seed", 42))
    held_out = str(cfg.get_path("cl_scenario.held_out_class", "union_based"))
    golden_fraction = float(cfg.get_path("cl_scenario.golden_fraction", 0.1))
    valid_fraction = float(cfg.get_path("cl_scenario.valid_fraction", 0.15))
    base_fraction = float(cfg.get_path("cl_scenario.base_fraction_of_known", 0.5))
    window_size = int(cfg.get_path("cl_scenario.stream.window_size", 1000))
    scenario1_new = int(cfg.get_path("cl_scenario.stream.scenario1_new_class_rows", 2000))
    scenario1_trickle = int(cfg.get_path("cl_scenario.stream.scenario1_trickle_rows", 300))
    quiet_head = int(cfg.get_path("cl_scenario.stream.quiet_head_rows", 2000))
    scenario2_known = int(cfg.get_path("cl_scenario.stream.scenario2_known_rows", 2000))

    rng = np.random.default_rng(seed)

    df = load_dedup_branch1(processed)
    known_classes = sorted(c for c in df["label_name"].unique() if c != held_out)
    logger.info("Held-out class: %s | known classes: %s", held_out, known_classes)

    # ── 1. Golden: 10% of every class, frozen for evaluation ──────────────
    partition = pd.Series("unused", index=df.index)
    for _, group in df.groupby("label_name", sort=True):
        idx = group.index.to_numpy().copy()
        rng.shuffle(idx)
        n_golden = int(round(len(idx) * golden_fraction))
        partition.loc[idx[:n_golden]] = "golden"
        remainder = idx[n_golden:]

        if group["label_name"].iloc[0] == held_out:
            # ALL of the held-out class's non-golden rows are reserved for
            # scenario 1 (Base must see none of it); only a sample streams.
            partition.loc[remainder] = "reserve_held_out"
        else:
            n_base = int(round(len(remainder) * base_fraction))
            partition.loc[remainder[:n_base]] = "base"
            partition.loc[remainder[n_base:]] = "reserve_known"
    df["partition"] = partition

    # Carve valid out of base.
    base_idx = df.index[df["partition"] == "base"].to_numpy().copy()
    rng.shuffle(base_idx)
    n_valid = int(round(len(base_idx) * valid_fraction))
    df.loc[base_idx[:n_valid], "partition"] = "base_valid"
    df.loc[base_idx[n_valid:], "partition"] = "base_train"

    # ── 2. Sample the two pours from the reserves ──────────────────────────
    reserve_known = df[df["partition"] == "reserve_known"]
    reserve_held_out = df[df["partition"] == "reserve_held_out"]

    trickle_idx = reserve_known.sample(n=scenario1_trickle, random_state=seed).index
    df.loc[trickle_idx, "partition"] = "stream_q3_trickle"

    remaining_known = df[df["partition"] == "reserve_known"]
    q4_idx = remaining_known.sample(n=scenario2_known, random_state=seed).index
    df.loc[q4_idx, "partition"] = "stream_q4"

    new_class_idx = reserve_held_out.sample(n=scenario1_new, random_state=seed).index
    df.loc[new_class_idx, "partition"] = "stream_q3_new_class"

    df.loc[df["partition"] == "reserve_known", "partition"] = "unused"
    df.loc[df["partition"] == "reserve_held_out", "partition"] = "unused"

    report = SplitReport()
    report.partitions = df["partition"].value_counts().to_dict()
    report.per_class = {
        str(name): group["partition"].value_counts().to_dict()
        for name, group in df.groupby("label_name", sort=True)
    }

    # ── 3. Assemble the ordered stream: quiet head -> scenario 1 -> scenario 2 ──
    benign_pool = load_benign_pool(processed)
    q3_attack_n = scenario1_trickle + scenario1_new
    q4_attack_n = scenario2_known
    total_attack = q3_attack_n + q4_attack_n
    benign_pool = benign_pool.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    n_benign_q3 = int(round(len(benign_pool) * q3_attack_n / total_attack))
    benign_q3 = benign_pool.iloc[:n_benign_q3]
    benign_q4 = benign_pool.iloc[n_benign_q3:]

    trickle_rows = df[df["partition"] == "stream_q3_trickle"][COLUMNS]
    new_class_rows = df[df["partition"] == "stream_q3_new_class"][COLUMNS]
    q4_rows = df[df["partition"] == "stream_q4"][COLUMNS]

    quiet_pool = pd.concat([trickle_rows, benign_q3], ignore_index=True).sample(
        frac=1.0, random_state=seed
    )
    quiet = quiet_pool.iloc[:quiet_head].copy()
    quiet["sub_phase"] = "quiet"
    scenario1_tail_pool = pd.concat(
        [quiet_pool.iloc[quiet_head:], new_class_rows], ignore_index=True
    ).sample(frac=1.0, random_state=seed + 1)
    scenario1_tail = scenario1_tail_pool.copy()
    scenario1_tail["sub_phase"] = "scenario1"

    q3 = pd.concat([quiet, scenario1_tail], ignore_index=True)
    q3["chunk"] = "q3"

    scenario2_pool = pd.concat([q4_rows, benign_q4], ignore_index=True).sample(
        frac=1.0, random_state=seed + 2
    )
    scenario2_pool["sub_phase"] = "scenario2"
    scenario2_pool["chunk"] = "q4"

    stream = pd.concat([q3, scenario2_pool], ignore_index=True)
    stream["position"] = np.arange(len(stream))
    stream["id"] = stream["id"].astype(str) + "#" + stream["position"].astype(str)

    report.stream = {
        "rows": len(stream),
        "windows": (len(stream) + window_size - 1) // window_size,
        "window_size": window_size,
        "q3_rows": int((stream["chunk"] == "q3").sum()),
        "q4_rows": int((stream["chunk"] == "q4").sum()),
        "quiet_head_rows": int((stream["sub_phase"] == "quiet").sum()),
        "q3_attack_rate": round(
            float((stream.loc[stream["chunk"] == "q3", "label_name"] != "normal").mean()), 4
        ),
        "q4_attack_rate": round(
            float((stream.loc[stream["chunk"] == "q4", "label_name"] != "normal").mean()), 4
        ),
        "benign_pool_available": len(benign_pool),
        "benign_pool_used": len(benign_q3) + len(benign_q4),
        "class_mix": stream["label_name"].value_counts().to_dict(),
        "unused_held_out_rows": int(
            (df["label_name"] == held_out).sum()
            - report.partitions.get("stream_q3_new_class", 0)
            - report.partitions.get("golden", 0)
        ),
    }

    # ── 4. Invariants ───────────────────────────────────────────────────────
    golden_canon = set(df.loc[df["partition"] == "golden", "query_canonical"])
    base_canon = set(
        df.loc[df["partition"].isin(["base_train", "base_valid"]), "query_canonical"]
    )
    stream_canon = set(stream["query_canonical"])

    report.invariants = [
        Invariant(
            "golden_disjoint_from_base",
            not (golden_canon & base_canon),
            f"overlap={len(golden_canon & base_canon)}",
        ),
        Invariant(
            "golden_disjoint_from_stream",
            not (golden_canon & stream_canon),
            f"overlap={len(golden_canon & stream_canon)}",
        ),
        Invariant(
            "base_has_zero_held_out_class",
            not (
                (df["partition"].isin(["base_train", "base_valid"]))
                & (df["label_name"] == held_out)
            ).any(),
            "Base must never see the held-out class",
        ),
        Invariant(
            "q4_has_zero_held_out_class",
            not ((stream["chunk"] == "q4") & (stream["label_name"] == held_out)).any(),
            "scenario 2 is volume-only, no new class",
        ),
        Invariant(
            "quiet_head_has_zero_held_out_class",
            not ((stream["sub_phase"] == "quiet") & (stream["label_name"] == held_out)).any(),
            "the drift reference period must be free of the held-out class",
        ),
        Invariant(
            "stream_benign_deduplicated",
            not stream.loc[stream["label_name"] == "normal", "query_canonical"].duplicated().any(),
            "no repeated benign padding rows",
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

    # ── 5. Write ─────────────────────────────────────────────────────────────
    df.to_csv(processed / SPLIT_FILENAME, index=False)
    stream.to_csv(processed / STREAM_FILENAME, index=False)
    with (artifacts / MANIFEST_FILENAME).open("w", encoding="utf-8") as handle:
        json.dump(report.to_dict(), handle, indent=2)

    logger.info("=== Split complete ===")
    for name, count in sorted(report.partitions.items()):
        logger.info("  %-22s %s", name, f"{count:,}")
    logger.info(
        "  stream  %s rows (%s windows): Q3=%s (attack %.1f%%) Q4=%s (attack %.1f%%)",
        f"{len(stream):,}",
        report.stream["windows"],
        f"{report.stream['q3_rows']:,}",
        report.stream["q3_attack_rate"] * 100,
        f"{report.stream['q4_rows']:,}",
        report.stream["q4_attack_rate"] * 100,
    )
    logger.info("Wrote %s, %s, %s", SPLIT_FILENAME, STREAM_FILENAME, MANIFEST_FILENAME)


if __name__ == "__main__":
    main()
