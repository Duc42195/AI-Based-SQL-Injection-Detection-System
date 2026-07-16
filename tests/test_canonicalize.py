"""Unit tests for canonicalization (URL/hex/CHAR decode, comment marker, case fold)."""

from __future__ import annotations

from src.preprocessing.canonicalize import canonicalize


def test_url_decode_single_pass() -> None:
    result = canonicalize("id=1%20OR%201=1")
    assert result.query_canonical == "id=1 or 1=1"


def test_url_decode_nested_double_encoding() -> None:
    # %2520 -> %20 -> " " requires 2 decode passes
    result = canonicalize("1%2520OR%25201=1", max_decode_iterations=3)
    assert result.query_canonical == "1 or 1=1"


def test_url_decode_plus_as_space() -> None:
    result = canonicalize("UNION+ALL+SELECT+NULL")
    assert result.query_canonical == "union all select null"


def test_hex_literal_decoded() -> None:
    # 0x61646d696e -> "admin"
    result = canonicalize("SELECT * FROM users WHERE name=0x61646d696e")
    assert "'admin'" in result.query_canonical


def test_hex_literal_odd_length_left_untouched() -> None:
    result = canonicalize("0xABC")
    assert result.query_canonical == "0xabc"


def test_char_function_decoded() -> None:
    result = canonicalize("CHAR(65,66,67)")
    assert result.query_canonical == "'abc'"


def test_comment_marker_detected_for_block_comment() -> None:
    result = canonicalize("SELECT 1 /* comment */ FROM users")
    assert result.has_comment_marker == 1
    # comment is preserved, not stripped
    assert "comment" in result.query_canonical


def test_comment_marker_detected_for_dash_dash() -> None:
    result = canonicalize("admin'--")
    assert result.has_comment_marker == 1
    assert "--" in result.query_canonical


def test_no_comment_marker_when_absent() -> None:
    result = canonicalize("SELECT * FROM users WHERE id=1")
    assert result.has_comment_marker == 0


def test_case_folded_to_lowercase() -> None:
    result = canonicalize("SELECT * FROM Users WHERE Id=1")
    assert result.query_canonical == "select * from users where id=1"
