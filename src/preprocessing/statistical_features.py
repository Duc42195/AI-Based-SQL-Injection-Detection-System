"""Statistical/structural feature extraction for Branch 2 (anomaly detection).

Branch 1 learns from content (TF-IDF over known attack syntax); Branch 2 must
generalize to SYNTAX IT HAS NEVER SEEN, so it deliberately avoids content-based
features. Instead it describes the *shape* of a query: length, ratio of
special characters, count of SQL keywords, and character-level entropy — a
zero-day payload with unfamiliar syntax still tends to look structurally
different from benign traffic even if no keyword matches anything known.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

_SPECIAL_CHARS_RE = re.compile(r"['\";#\-=<>()*|%]")

_SQL_KEYWORDS = (
    "select",
    "union",
    "insert",
    "update",
    "delete",
    "drop",
    "where",
    "from",
    "and",
    "or",
    "exec",
    "extractvalue",
    "sleep",
    "waitfor",
    "benchmark",
    "concat",
    "case",
    "cast",
    "convert",
    "having",
    "group by",
    "order by",
)
_SQL_KEYWORD_RE = re.compile(r"\b(" + "|".join(_SQL_KEYWORDS) + r")\b", re.IGNORECASE)


@dataclass(frozen=True)
class StatisticalFeatures:
    """Structural feature vector for one query/payload string."""

    length: int
    special_char_ratio: float
    sql_keyword_count: int
    entropy: float

    def as_list(self) -> list[float]:
        """Return features as a plain list, in a fixed order, for model input."""
        return [
            float(self.length),
            self.special_char_ratio,
            float(self.sql_keyword_count),
            self.entropy,
        ]


def _shannon_entropy(text: str) -> float:
    """Compute Shannon entropy (bits/char) of a string.

    Args:
        text: Input string.

    Returns:
        Entropy in bits per character; 0.0 for empty input.
    """
    if not text:
        return 0.0
    counts = Counter(text)
    length = len(text)
    return -sum((n / length) * math.log2(n / length) for n in counts.values())


def extract_statistical_features(text: str) -> StatisticalFeatures:
    """Extract the Branch 2 structural feature vector from canonicalized text.

    Args:
        text: Canonicalized query/payload text (see
            src/preprocessing/canonicalize.py).

    Returns:
        A :class:`StatisticalFeatures` instance.
    """
    length = len(text)
    special_count = len(_SPECIAL_CHARS_RE.findall(text))
    special_char_ratio = special_count / length if length > 0 else 0.0
    sql_keyword_count = len(_SQL_KEYWORD_RE.findall(text))
    entropy = _shannon_entropy(text)

    return StatisticalFeatures(
        length=length,
        special_char_ratio=special_char_ratio,
        sql_keyword_count=sql_keyword_count,
        entropy=entropy,
    )
