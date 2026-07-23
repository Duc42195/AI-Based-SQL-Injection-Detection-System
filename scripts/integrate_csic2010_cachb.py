"""Integrate CSIC 2010 benign traffic into Cach B evaluation dataset.

Creates pseudo-sessions from CSIC 2010 normal requests (groups of 5-15)
and writes a NEW augmented CSV (does not mutate the original).

Usage:
    uv run python scripts/integrate_csic2010_cachb.py
"""

from __future__ import annotations

import csv
import random
from pathlib import Path
from typing import Any

from src.preprocessing.statistical_features import extract_statistical_features
from src.utils import get_logger, load_config

logger = get_logger(__name__)

NORMALS_PER_SESSION = (5, 15)
SESSIONS_TO_CREATE = 50


def load_csic_normals(path: Path) -> list[str]:
    from urllib.parse import unquote_plus
    import re
    _HTTP_REQUEST_LINE_RE = re.compile(r"^(GET|POST|PUT) (\S+)", re.MULTILINE)
    rows: list[str] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("label") != "normal":
                continue
            block = row.get("raw_request") or ""
            match = _HTTP_REQUEST_LINE_RE.search(block)
            if not match:
                continue
            url = match.group(2)
            parts = block.split("\n\n", 1)
            body = parts[1].strip() if len(parts) > 1 else ""
            text = unquote_plus(f"{url} {body}".strip())
            rows.append(text)
    return rows


def main() -> None:
    cfg = load_config()
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    raw_dir = Path(cfg.get_path("paths.data_raw", "data/raw"))

    csic_csv = raw_dir / "d3_csic2010_raw.csv"
    if not csic_csv.exists():
        logger.error("CSIC CSV not found at %s. Run scripts/fetch_and_wrap_d3_csic2010.py first.", csic_csv)
        return

    cachb_path = processed_dir / "nhanh3_session_data_cachb.csv"
    if not cachb_path.exists():
        logger.error("Cach B CSV not found at %s", cachb_path)
        return

    out_path = processed_dir / "nhanh3_session_data_cachb_with_csic.csv"
    if out_path.exists():
        logger.warning("Output %s already exists — delete it first to regenerate", out_path)
        return

    logger.info("Loading CSIC 2010 normal requests ...")
    normals = load_csic_normals(csic_csv)
    logger.info("Loaded %d CSIC 2010 normal queries", len(normals))

    rng = random.Random(cfg.get_path("project.random_seed", 42))
    rng.shuffle(normals)

    feature_names = cfg.get_path("branch3_session.step_features",
                                  ["length", "special_char_ratio", "sql_keyword_count", "entropy", "is_attack_query"])

    # Read original rows
    original_rows: list[dict[str, Any]] = []
    max_sid = -1
    with cachb_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            original_rows.append(row)
            sid = int(row["session_id"])
            if sid > max_sid:
                max_sid = sid
    last_sid = max_sid + 1

    # Generate CSIC pseudo-sessions
    csic_rows: list[dict[str, Any]] = []
    idx = 0
    created = 0
    while idx < len(normals) and created < SESSIONS_TO_CREATE:
        n = rng.randint(*NORMALS_PER_SESSION)
        batch = normals[idx:idx + n]
        idx += n
        if len(batch) < 3:
            continue
        sid = last_sid + created
        for step, q in enumerate(batch):
            feats = extract_statistical_features(q)
            csic_rows.append({
                "session_id": sid,
                "step": step,
                "split": "test",
                "query_raw": q,
                "query_canonical": q,
                "has_comment_marker": 0,
                "length": feats.length,
                "special_char_ratio": round(feats.special_char_ratio, 6),
                "sql_keyword_count": feats.sql_keyword_count,
                "entropy": round(feats.entropy, 6),
                "is_attack_query": 0,
                "per_query_label": -1,
                "per_query_label_name": "unknown",
                "session_label": 0,
                "session_label_name": "benign",
            })
        created += 1

    fieldnames = [
        "session_id", "step", "split",
        "query_raw", "query_canonical", "has_comment_marker",
        *[f for f in feature_names if f != "is_attack_query"],
        "is_attack_query",
        "per_query_label", "per_query_label_name",
        "session_label", "session_label_name",
    ]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(original_rows)
        writer.writerows(csic_rows)

    logger.info("Created %s with %d original + %d CSIC rows (%d CSIC sessions)",
                out_path, len(original_rows), len(csic_rows), created)


if __name__ == "__main__":
    main()
