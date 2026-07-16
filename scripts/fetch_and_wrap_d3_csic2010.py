"""One-off script: wrap raw CSIC 2010 HTTP dumps into a single raw CSV.

Downloads the 3 official CSIC 2010 text files (normalTrafficTraining,
normalTrafficTest, anomalousTrafficTest) are expected to already exist under
``data/raw/csic2010/`` (see AGENTS.md — fetched from the GSI/UdelaR GitLab
mirror). This script performs NO cleaning/parsing of HTTP fields; it only
splits each dump on request boundaries and stores each raw HTTP request block
as one CSV row, preserving the "raw" stage of the data pipeline.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from src.utils import get_logger

logger = get_logger(__name__)

RAW_DIR = Path("data/raw/csic2010")
OUT_PATH = Path("data/raw/d3_csic2010_raw.csv")

_SOURCES = [
    ("normalTrafficTraining.txt", "train", "normal"),
    ("normalTrafficTest.txt", "test", "normal"),
    ("anomalousTrafficTest.txt", "test", "anomalous"),
]

_REQUEST_START_RE = re.compile(r"^(GET|POST|PUT) ", re.MULTILINE)


def split_requests(raw_text: str) -> list[str]:
    """Split a CSIC dump into individual raw HTTP request blocks.

    Args:
        raw_text: Full contents of a CSIC traffic dump file.

    Returns:
        List of raw request blocks (method line + headers + optional body),
        each stripped of leading/trailing blank lines.
    """
    starts = [m.start() for m in _REQUEST_START_RE.finditer(raw_text)]
    blocks = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(raw_text)
        blocks.append(raw_text[start:end].strip("\n"))
    return blocks


def main() -> None:
    """Wrap the 3 raw CSIC dumps into one CSV: split, label, raw_request."""
    if not RAW_DIR.exists():
        raise FileNotFoundError(
            f"{RAW_DIR} not found. Download the 3 CSIC 2010 files first "
            "(see data_contract.md for the source URL)."
        )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with OUT_PATH.open("w", newline="", encoding="utf-8") as out_f:
        writer = csv.writer(out_f)
        writer.writerow(["id", "split", "label", "raw_request"])
        row_id = 0
        for filename, split, label in _SOURCES:
            path = RAW_DIR / filename
            logger.info("Processing %s ...", path)
            text = path.read_text(encoding="utf-8")
            blocks = split_requests(text)
            logger.info("  -> %d requests found", len(blocks))
            for block in blocks:
                writer.writerow([row_id, split, label, block])
                row_id += 1
            total += len(blocks)
    logger.info("Wrote %d rows to %s", total, OUT_PATH)


if __name__ == "__main__":
    main()
