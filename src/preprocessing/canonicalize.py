"""Canonicalization pipeline for raw HTTP requests.

Normalises and cleans raw HTTP request fields (path, query, body) before
feature extraction. Handles URL decoding, comment removal, and keyword
lowercasing.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

from src.utils import get_logger

logger = get_logger(__name__)

_COMMENT_PATTERN = re.compile(r"/\*.*?\*/", re.DOTALL)

_MAX_DECODE_ITERATIONS = 3


def canonicalize_sql(text: str | None, lowercase_keywords: bool = True,
                     mark_comments: bool = True) -> str:
    """Normalise a SQL payload string.

    Steps:
    1. URL-decode repeatedly (up to ``_MAX_DECODE_ITERATIONS`` passes).
    2. Remove multi-line SQL comments ``/* ... */``.
    3. Optionally lowercases recognised SQL keywords.

    Args:
        text: Raw payload (possibly URL-encoded).
        lowercase_keywords: Lowercase SQL keywords if ``True``.
        mark_comments: If ``True``, remove ``/* ... */`` comments.

    Returns:
        Normalised text.
    """
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text) if text is not None else ""

    # 1. Iterative URL decode
    for _ in range(_MAX_DECODE_ITERATIONS):
        prev = text
        try:
            text = urllib.parse.unquote_plus(text)
        except Exception:
            break
        if text == prev:
            break

    # 2. Remove multi-line comments
    if mark_comments:
        text = _COMMENT_PATTERN.sub(" ", text)

    # 3. Lowercase known SQL keywords
    if lowercase_keywords:
        text = _lowercase_sql_keywords(text)

    return text.strip()


def canonicalize_request(method: str, path: str | None, query: str | None, body: str | None,
                         cfg: dict[str, Any] | None = None) -> dict[str, str]:
    """Canonicalise a single HTTP request into a clean feature string.

    Concatenates ``method /path ?query [body]`` after applying SQL
    canonicalization to all text fields.

    Args:
        method: HTTP method (GET, POST, …).
        path: URL path.
        query: URL query string.
        body: Request body.
        cfg: Config dict with ``preprocessing`` section. If ``None``, uses
            default settings (lowercase + remove comments).

    Returns:
        Dict with keys ``method``, ``path``, ``query``, ``body``, and
        ``canonical_text`` (space-joined concatenation).
    """
    pre = cfg.get("preprocessing", {}) if cfg else {}
    lc = pre.get("lowercase_keywords", True)
    mc = pre.get("mark_comments", True)

    path_c = canonicalize_sql(path, lc, mc)
    query_c = canonicalize_sql(query, lc, mc)
    body_c = canonicalize_sql(body, lc, mc)
    method_c = method.upper()

    parts = [method_c, path_c]
    if query_c:
        parts.append("?" + query_c)
    if body_c:
        parts.append(body_c)

    return {
        "method": method_c,
        "path": path_c,
        "query": query_c,
        "body": body_c,
        "canonical_text": " ".join(parts),
    }


def _lowercase_sql_keywords(text: str) -> str:
    """Lowercase recognised SQL keywords (heuristic word-boundary replace)."""
    _SQL_KEYWORDS = {
        "SELECT", "INSERT", "UPDATE", "DELETE", "DROP", "UNION", "FROM",
        "WHERE", "AND", "OR", "NOT", "NULL", "TRUE", "FALSE", "LIKE",
        "IN", "BETWEEN", "IS", "HAVING", "GROUP", "ORDER", "BY", "ASC",
        "DESC", "LIMIT", "OFFSET", "INTO", "VALUES", "SET", "CREATE",
        "ALTER", "TABLE", "INDEX", "VIEW", "JOIN", "INNER", "LEFT",
        "RIGHT", "OUTER", "ON", "AS", "DISTINCT", "ALL", "ANY", "EXISTS",
        "CASE", "WHEN", "THEN", "ELSE", "END", "CAST", "CONVERT", "SUBSTRING",
        "CHAR", "NCHAR", "UNION", "ALL", "EXEC", "EXECUTE", "WAITFOR",
        "DELAY", "SLEEP", "BENCHMARK", "IF", "ELSE", "BEGIN", "END",
        "DECLARE", "PRINT", "RAISERROR", "THROW", "FETCH", "NEXT",
        "OPEN", "CLOSE", "DEALLOCATE", "CURSOR", "INTO", "PROCEDURE",
        "FUNCTION", "TRIGGER", "EVENT", "SCHEMA", "DATABASE", "USE",
        "SHOW", "DESCRIBE", "EXPLAIN", "LOAD", "FILE", "INFILE",
        "OUTFILE", "DUMPFILE", "INTO", "CONCAT", "GROUP_CONCAT",
        "VERSION", "USER", "DATABASE", "CURRENT_USER", "SESSION_USER",
    }
    pattern = re.compile(r"\b(" + "|".join(re.escape(kw) for kw in sorted(_SQL_KEYWORDS, key=len, reverse=True)) + r")\b", re.IGNORECASE)  # noqa: E501
    return pattern.sub(lambda m: m.group(1).lower(), text)
