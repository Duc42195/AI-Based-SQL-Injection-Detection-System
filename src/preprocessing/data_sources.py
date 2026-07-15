"""Shared raw-data loaders for D1/D3/D4/D7, reused by both the Nhanh 1
(multiclass supervised) and Nhanh 2 (anomaly, benign-only) dataset builders.

Keeping loading logic in one place means both branches see the exact same
row-level content for a given source — important since Nhanh 2 is far more
sensitive to benign-pool noise than Nhanh 1 (see data_contract.md Muc 3.1/3.2).
"""

from __future__ import annotations

import csv
import random
import re
from pathlib import Path
from urllib.parse import unquote_plus

csv.field_size_limit(10_000_000)

_HTTP_REQUEST_LINE_RE = re.compile(r"^(GET|POST|PUT)\s+(\S+)\s+HTTP", re.MULTILINE)


def load_d1(path: Path) -> list[tuple[str, bool, str]]:
    """Load D1 SQLiV3 raw rows, dropping null/empty text and duplicates.

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
    return rows


def load_d4(dir_path: Path) -> list[tuple[str, bool, str]]:
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
    return rows


def load_d7(
    path: Path, normal_sample_size: int | None, seed: int
) -> list[tuple[str, bool, str]]:
    """Load D7 SR-BH 2020 attack rows (full) + a sample/all of the normal rows.

    Args:
        path: Path to data_capec_multilabel.csv.
        normal_sample_size: Max number of Normal==1 rows to sample for
            benign diversity (source dataset has 152,587 such rows). Pass
            ``None`` to keep all of them (used by the Nhanh 2 builder).
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
                if normal_sample_size is None:
                    normal_pool.append(text)
                elif len(normal_pool) < normal_sample_size:
                    normal_pool.append(text)
                else:
                    j = rng.randint(0, normal_seen - 1)
                    if j < normal_sample_size:
                        normal_pool[j] = text

    normal_rows = [(t, False, "d7_srbh2020_normal") for t in normal_pool]
    return attack_rows + normal_rows


def load_d3(path: Path, split_filter: str | None = None) -> list[tuple[str, bool, str]]:
    """Load D3 CSIC 2010 rows (wrapped raw HTTP requests) as (url, is_attack).

    Args:
        path: Path to d3_csic2010_raw.csv (see scripts/fetch_and_wrap_d3_csic2010.py).
        split_filter: If given, only load rows whose ``split`` column equals
            this value (e.g. ``"train"``). ``None`` loads all rows.

    Returns:
        List of (raw_text, is_attack, source) tuples. ``raw_text`` is the
        request line (method + URL) extracted from the raw HTTP block; the
        POST body, if any, is appended.
    """
    rows: list[tuple[str, bool, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if split_filter is not None and row.get("split") != split_filter:
                continue
            block = row.get("raw_request") or ""
            match = _HTTP_REQUEST_LINE_RE.search(block)
            if not match:
                continue
            url = match.group(2)
            # Body is whatever follows the blank-line-separated header section.
            parts = block.split("\n\n", 1)
            body = parts[1].strip() if len(parts) > 1 else ""
            text = unquote_plus(f"{url} {body}".strip())
            is_attack = row.get("label") == "anomalous"
            rows.append((text, is_attack, "d3_csic2010"))
    return rows
