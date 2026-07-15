"""Tests for the canonicalization pipeline."""

from __future__ import annotations

import pandas as pd

from src.preprocessing.canonicalize import canonicalize_sql, canonicalize_request


def test_canonicalize_sql_url_decoded():
    result = canonicalize_sql("%27%3B+DROP+TABLE+usuarios%3B+SELECT+*+FROM+datos+WHERE+nombre+LIKE+%27%25",
                               lowercase_keywords=True, mark_comments=True)
    assert "drop" in result.lower()
    assert "select" in result.lower()
    assert "from" in result.lower()
    assert "like" in result.lower()


def test_canonicalize_sql_comment_removal():
    result = canonicalize_sql("SELECT * FROM users /* comment */ WHERE id=1",
                               lowercase_keywords=True, mark_comments=True)
    assert "comment" not in result
    assert "where" in result


def test_canonicalize_sql_empty():
    assert canonicalize_sql("") == ""


def test_canonicalize_sql_no_change():
    text = "hello world"
    result = canonicalize_sql(text, lowercase_keywords=False, mark_comments=False)
    assert result == text


def test_canonicalize_request_basic():
    cfg = {"preprocessing": {"lowercase_keywords": True, "mark_comments": True}}
    result = canonicalize_request("GET", "/test.jsp", "id=1", "", cfg)
    assert result["method"] == "GET"
    assert "/test.jsp" in result["path"]
    assert "id=1" in result["query"]
    assert result["canonical_text"] is not None


def test_canonicalize_request_no_cfg():
    result = canonicalize_request("post", "/path", "q=1", "")
    assert result["method"] == "POST"
