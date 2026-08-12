# -*- coding: utf-8 -*-
"""Day 1 / Sprint 1 audit — Branch 3 validity (Bach).

Verifies the pipeline feeding `train/calibrate_branch3.py` so the numbers in
`report/metrics/branch3_eval.json` are trustworthy. KEPT in the repo.

Usage:  uv run python train/audit_branch3_data_validity.py
Requires: data/processed/branch3_sessions_cach_a.csv
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

_bml_path = ROOT / "train" / "build_mlops_split.py"
_spec = importlib.util.spec_from_file_location("build_mlops_split", _bml_path)
_bml = importlib.util.module_from_spec(_spec)
sys.modules["build_mlops_split"] = _bml  # register before exec (dataclass resolves __module__)
assert _spec.loader is not None
_spec.loader.exec_module(_bml)
NEW_CLASS_GOLDEN_SHARE = _bml.NEW_CLASS_GOLDEN_SHARE
build_new_class_pool = _bml.build_new_class_pool

from src.utils import get_logger, load_config  # noqa: E402

logger = get_logger(__name__)

_TARGET_RE = re.compile(r"username\s*=\s*'([^']+)'")


def _target(q: str) -> str | None:
    m = _TARGET_RE.search(q)
    return m.group(1) if m else None


def _session_seq(df: pd.DataFrame, sid: str) -> tuple:
    g = df[df["session_id"] == sid].sort_values("step_index")
    return tuple(g["query_canonical"].tolist())


def check_branch3_leakage(csv_path: Path) -> dict:
    df = pd.read_csv(csv_path, keep_default_na=False, na_values=[])
    train_ids = set(df[df["split"] == "train"]["session_id"])
    test_ids = set(df[df["split"] == "test"]["session_id"])

    info = {}
    for sid in train_ids | test_ids:
        seq = _session_seq(df, sid)
        tgs = {_target(t) for t in seq}
        tgs.discard(None)
        info[sid] = {
            "label": int(df[df["session_id"] == sid]["session_label"].iloc[0]),
            "seq": seq,
            "targets": tgs,
        }

    train_seq_set = set(info[s]["seq"] for s in train_ids)
    train_targ: dict[tuple, list] = defaultdict(list)
    for sid in train_ids:
        for t in info[sid]["targets"]:
            train_targ[(info[sid]["label"], t)].append(sid)

    same_target: dict = defaultdict(set)
    byte_identical: dict = defaultdict(set)
    for sid in test_ids:
        l = info[sid]["label"]
        for t in info[sid]["targets"]:
            if (l, t) in train_targ:
                same_target[l].add(sid)
                for tsid in train_targ[(l, t)]:
                    if info[tsid]["seq"] == info[sid]["seq"]:
                        byte_identical[l].add(sid)
                        break
        if info[sid]["seq"] in train_seq_set:
            byte_identical[l].add(sid)

    labels = {0: "benign", 1: "boolean_blind", 2: "time_blind", 3: "query_splitting"}
    out = {"rows": int(len(df)), "n_sessions": int(df["session_id"].nunique()), "by_label": {}}
    for l in labels:
        n_test = sum(1 for sid in test_ids if info[sid]["label"] == l)
        out["by_label"][labels[l]] = {
            "test_sessions": n_test,
            "test_share_target_with_train": len(same_target[l]),
            "test_byte_identical_to_train": len(byte_identical[l]),
        }
    return out


def check_stacked_leakage() -> dict:
    pool = build_new_class_pool(seed=42)
    golden = set(pool[pool["partition"] == "golden"]["query_canonical"])
    st = pool[pool["partition"] == "stream"]
    sampled = st.sample(n=727, replace=len(st) < 727, random_state=42)
    return {
        "n_templates": int(len(pool)),
        "golden": int(len(golden)),
        "stream": int(len(st)),
        "golden_x_stream_overlap": int(len(golden & set(st["query_canonical"]))),
        "stream_sampled_to": int(len(sampled)),
        "distinct_templates_in_727": int(sampled["query_canonical"].nunique()),
        "sampled_collides_with_golden": bool(set(sampled["query_canonical"]) & golden),
    }


def check_zeroday_report() -> dict:
    rd = ROOT / "report/metrics/zeroday_experiment"
    with (rd / "summary.json").open("r", encoding="utf-8") as f:
        summary = json.load(f)
    return {
        "summary_loaded": True,
        "branch1_miss_rate": {k: round(summary["results"][k]["branch1_miss_rate"], 4)
                              for k in summary["results"]},
        "branch2_dr": {k: round(summary["results"][k]["branch2_detection_rate"], 4)
                       for k in summary["results"]},
    }


def main() -> None:
    cfg = load_config()
    csv_path = Path(cfg.get_path("paths.data_processed", "data/processed")) / "branch3_sessions_cach_a.csv"
    if not csv_path.exists():
        logger.error("Missing input: %s", csv_path)
        return

    findings = {
        "mang1_branch3_leakage": check_branch3_leakage(csv_path),
        "mang2_stacked_leakage": check_stacked_leakage(),
        "mang3_zeroday_report": check_zeroday_report(),
    }
    out_dir = ROOT / "report/metrics/audit_branch3"
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "findings.json").open("w", encoding="utf-8") as f:
        json.dump(findings, f, indent=2, ensure_ascii=False)
    logger.info("Audit written to %s", out_dir / "findings.json")


if __name__ == "__main__":
    main()