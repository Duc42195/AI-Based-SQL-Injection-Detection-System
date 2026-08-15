# -*- coding: utf-8 -*-
"""Shared SSRF-detection helpers for Branch-2 benign-pool cleanup.

Single source of truth for the SSRF / OS-cmd callback patterns and the CSV
reading convention (``keep_default_na=False``) used across the Branch-2 data
cleanup and impact-audit scripts, so the same patterns/parsing rules are not
copy-pasted between files.
"""

from __future__ import annotations

import pandas as pd
from pathlib import Path

# Callback / SSRF / OS-command rows that leaked into the "100% benign" pool but
# are in fact attacks (anchor filter targets SQLi + OS-cmd/SSI, not SSRF).
SSRF_PATTERNS: list[str] = ["owasp.org", "/etc/passwd", "shellshock"]


def is_leaky_row(row) -> bool:
    """True if a row's canonical query contains an SSRF/OS-cmd callback marker."""
    t = str(row["query_canonical"]).lower()
    return any(p in t for p in SSRF_PATTERNS)


def read_csv_keep_na(path: Path) -> pd.DataFrame:
    """Read a CSV preserving empty strings instead of converting them to NaN.

    Matches the convention used elsewhere in the Branch-2 pipeline so that a
    cell equal to pandas' NA token (e.g. "NA", "null") is never silently
    turned into NaN during cleanup.
    """
    return pd.read_csv(path, keep_default_na=False, na_values=[])


__all__ = ["SSRF_PATTERNS", "is_leaky_row", "read_csv_keep_na"]