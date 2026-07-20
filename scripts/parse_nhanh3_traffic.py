"""Parse captured sqlmap traffic into Branch 3 session format (Cach B).
Split by endpoint prefix + idle gap to get multiple sessions.
Add random train/test split.
"""
from __future__ import annotations

import csv
import random
from pathlib import Path
from typing import Any

import pandas as pd

from src.preprocessing.statistical_features import extract_statistical_features
from src.utils import get_logger, load_config

logger = get_logger(__name__)

SESSION_LABEL_NAMES = ["benign", "sqlmap_attack"]


def _detect_attack(row: dict) -> int:
    body = str(row.get("request_body", "") or "").lower()
    url = str(row.get("url", "") or "").lower()
    combined = body + url
    sql_keywords = ["select", "union", "sleep", "waitfor", "delay"]
    for kw in sql_keywords:
        if kw in combined:
            return 1
    return 0


def _endpoint_group(path: str) -> str:
    # Strip query params before grouping by endpoint
    path = path.split("?")[0]
    p = path.lower().strip("/").split("/")[0]
    return p if p else "root"


def _label_session(rows: list[dict]) -> int:
    for r in rows:
        if r.get("_attack", 0) == 1:
            return 1
    return 0


def main() -> None:
    cfg = load_config()
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    processed_dir.mkdir(parents=True, exist_ok=True)

    raw_dir = Path(cfg.get_path("paths.data_raw", "data/raw"))
    traffic_csv = raw_dir / "nhanh3_sqlmap_sessions" / "nhanh3_raw_traffic.csv"

    if not traffic_csv.exists():
        logger.error("Traffic CSV not found at %s", traffic_csv)
        return

    df = pd.read_csv(traffic_csv)
    logger.info("Loaded %d raw HTTP requests", len(df))
    if df.empty:
        logger.warning("No traffic captured")
        return

    idle_gap = cfg.get_path("branch3_session.session_idle_gap_seconds", 1800)
    seed = cfg.get_path("project.random_seed", 42)
    rng = random.Random(seed)
    tf = cfg.get_path("branch3_session.simulation.test_fraction", 0.2)

    df["_attack"] = df.apply(_detect_attack, axis=1)
    df["_endpoint"] = df["path"].apply(_endpoint_group)
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Split by endpoint + idle gap -> multiple sessions
    sessions = []
    for ep in sorted(df["_endpoint"].unique()):
        ep_df = df[df["_endpoint"] == ep].sort_values("timestamp")
        if len(ep_df) == 0:
            continue
        start = 0
        for i in range(1, len(ep_df)):
            if ep_df.iloc[i]["timestamp"] - ep_df.iloc[i - 1]["timestamp"] > idle_gap:
                sessions.append(ep_df.iloc[start:i])
                start = i
        sessions.append(ep_df.iloc[start:])

    logger.info("Split into %d sessions (%d endpoints)",
                len(sessions), df["_endpoint"].nunique())

    feature_names = cfg.get_path(
        "branch3_session.step_features",
        ["length", "special_char_ratio", "sql_keyword_count", "entropy", "is_attack_query"],
    )

    session_rows: list[dict[str, Any]] = []
    for session_id, group in enumerate(sessions):
        group_rows = group.to_dict("records")
        session_label = _label_session(group_rows)
        label_name = SESSION_LABEL_NAMES[session_label]
        split = "test" if rng.random() < tf else "train"

        for step_idx, (_, step) in enumerate(group.iterrows()):
            query_text = str(step.get("url", "") or "")
            feats = extract_statistical_features(query_text)
            session_rows.append({
                "session_id": session_id,
                "step": step_idx,
                "split": split,
                "query_raw": query_text,
                "query_canonical": query_text,
                "has_comment_marker": 0,
                "length": feats.length,
                "special_char_ratio": round(feats.special_char_ratio, 6),
                "sql_keyword_count": feats.sql_keyword_count,
                "entropy": round(feats.entropy, 6),
                "is_attack_query": int(step.get("_attack", 0)),
                "per_query_label": -1,
                "per_query_label_name": "unknown",
                "session_label": session_label,
                "session_label_name": label_name,
            })

    fieldnames = [
        "session_id", "step", "split",
        "query_raw", "query_canonical", "has_comment_marker",
        *[f for f in feature_names if f != "is_attack_query"],
        "is_attack_query",
        "per_query_label", "per_query_label_name",
        "session_label", "session_label_name",
    ]
    out_path = processed_dir / "nhanh3_session_data_cachb.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(session_rows)

    class_dist = df.groupby("_attack").size().to_dict()
    logger.info("Class distribution: %s", class_dist)
    logger.info("Saved %d step-rows (%d sessions) to %s",
                len(session_rows), len(sessions), out_path)


if __name__ == "__main__":
    main()
