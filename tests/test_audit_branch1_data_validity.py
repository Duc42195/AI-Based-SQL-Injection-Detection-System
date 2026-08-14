# -*- coding: utf-8 -*-
"""Tests for the Branch 1 data-validity audit script."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_audit_path = ROOT / "train" / "audit_branch1_data_validity.py"
_spec = importlib.util.spec_from_file_location("audit_branch1", _audit_path)
audit = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(audit)


@pytest.fixture
def df() -> pd.DataFrame:
    rows = [
        # normal / benign
        ("normal", "SELECT * FROM users WHERE id=1", "train"),
        ("normal", "SELECT * FROM users WHERE id=1", "test"),  # duplicate text straddling
        ("normal", "SELECT name FROM cats", "train"),
        # SSRF rows
        ("normal", "GET http://owasp.org/x HTTP/1.1", "train"),     # benign-pool contamination
        ("boolean_blind", "sleep(5) OR cat /etc/passwd --", "train"),  # label noise
        # blog-format rows
        ("union_based", "/blog/index.php/2020/03/union select 1--", "train"),
        ("union_based", "/blog/index.php/2020/03/union select 2--", "train"),
        # clean sql classes
        ("time_blind", "id=1 AND SLEEP(5)", "train"),
        ("error_based", "1' AND extractvalue(1,concat(0x7e,version()))--", "test"),
    ]
    df = pd.DataFrame(rows, columns=["label_name", "query_canonical", "split"])
    df["query_raw"] = df["query_canonical"]
    df["has_comment_marker"] = 0
    df["source"] = "test"
    df["label"] = df["label_name"]
    df["id"] = [str(i) for i in range(len(df))]
    return df


def test_distributions(df: pd.DataFrame) -> None:
    out = audit.check_distributions(df)
    assert out["rows"] == 9
    assert out["split"] == {"train": 7, "test": 2}
    assert out["distinct_query_canonical"] == 8


def test_duplicate_leakage(df: pd.DataFrame) -> None:
    out = audit.check_duplicate_leakage(df)
    assert out["extra_copies"] == 1
    assert out["distinct_duplicate_texts"] == 1
    assert out["duplicate_texts_straddle_train_and_test"] == 1


def test_ssrf_mislabels(df: pd.DataFrame) -> None:
    out = audit.check_ssrf_mislabels(df)
    assert out["ssrf_rows_total"] == 2
    assert out["in_normal_benign_pool"] == 1
    assert out["in_boolean_blind_sqli"] == 1


def test_blog_duplication(df: pd.DataFrame) -> None:
    out = audit.check_blog_duplication(df)
    assert out["rows"] == 2
    assert out["by_label"]["union_based"] == 2
    assert out["distinct_canonicals"] == 2