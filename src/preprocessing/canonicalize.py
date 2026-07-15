"""Canonicalization: normalise evasion-prone SQL/payload text before tagging.

Applied in this fixed order:
1. Iteratively URL-decode (handles nested/double encoding).
2. Decode hex literals (``0x4142...``) to their ASCII string form.
3. Decode ``CHAR(...)`` function calls to their literal string form.
4. Detect (but do NOT strip) ``/* */`` and ``--`` comments as a feature flag.
5. Lowercase the whole result (SQL keywords are case-insensitive).

Comments are preserved in the output text on purpose — evasion via comment
insertion should remain visible to the classifier, not be erased.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote_plus

_HEX_LITERAL_RE = re.compile(r"0x([0-9a-fA-F]{2,})")
_CHAR_FUNC_RE = re.compile(r"CHAR\s*\(\s*(\d+(?:\s*,\s*\d+)*)\s*\)", re.IGNORECASE)
_COMMENT_RE = re.compile(r"/\*.*?\*/|--", re.DOTALL)


@dataclass(frozen=True)
class CanonicalResult:
    """Result of canonicalizing one query/payload string."""

    query_canonical: str
    has_comment_marker: int


def _decode_url_iteratively(text: str, max_iterations: int) -> str:
    """Repeatedly URL-decode until stable or the iteration budget is spent.

    Args:
        text: Input text, possibly URL-encoded (single or nested).
        max_iterations: Maximum number of decode passes.

    Returns:
        The decoded text (fixed point reached, or budget exhausted).
    """
    for _ in range(max_iterations):
        decoded = unquote_plus(text)
        if decoded == text:
            break
        text = decoded
    return text


def _decode_hex_literals(text: str) -> str:
    """Replace ``0x...`` hex literals with their decoded ASCII form.

    Args:
        text: Input text possibly containing hex string literals.

    Returns:
        Text with decodable hex literals replaced by ``'<ascii>'``; literals
        that aren't valid printable ASCII are left untouched.
    """

    def repl(match: re.Match[str]) -> str:
        hex_digits = match.group(1)
        if len(hex_digits) % 2 != 0:
            return match.group(0)
        try:
            decoded = bytes.fromhex(hex_digits).decode("ascii")
        except (ValueError, UnicodeDecodeError):
            return match.group(0)
        if not decoded.isprintable():
            return match.group(0)
        return f"'{decoded}'"

    return _HEX_LITERAL_RE.sub(repl, text)


def _decode_char_function(text: str) -> str:
    """Replace ``CHAR(n1, n2, ...)`` calls with the literal string they encode.

    Args:
        text: Input text possibly containing ``CHAR()``/``CHR()``-style calls.

    Returns:
        Text with decodable ``CHAR(...)`` calls replaced by ``'<string>'``;
        calls containing out-of-range code points are left untouched.
    """

    def repl(match: re.Match[str]) -> str:
        codes = [int(n.strip()) for n in match.group(1).split(",")]
        if any(c > 0x10FFFF for c in codes):
            return match.group(0)
        try:
            decoded = "".join(chr(c) for c in codes)
        except ValueError:
            return match.group(0)
        return f"'{decoded}'"

    return _CHAR_FUNC_RE.sub(repl, text)


def canonicalize(text: str, max_decode_iterations: int = 3) -> CanonicalResult:
    """Canonicalize one query/payload string for tagging and modeling.

    Args:
        text: Raw query/payload text.
        max_decode_iterations: Max URL-decode passes (nested encoding).

    Returns:
        A :class:`CanonicalResult` with the canonicalized text and a
        ``has_comment_marker`` flag (1 if a ``/* */`` or ``--`` comment was
        found in the ORIGINAL text, before any decoding).
    """
    has_comment_marker = 1 if _COMMENT_RE.search(text) else 0

    result = _decode_url_iteratively(text, max_decode_iterations)
    result = _decode_hex_literals(result)
    result = _decode_char_function(result)
    result = result.lower()

    return CanonicalResult(query_canonical=result, has_comment_marker=has_comment_marker)
