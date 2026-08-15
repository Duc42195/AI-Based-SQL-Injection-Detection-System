"""Statistical/structural feature extraction for Branch 2 (anomaly detection).

Branch 1 learns from content (TF-IDF over known attack syntax); Branch 2 must
generalize to SYNTAX IT HAS NEVER SEEN, so it deliberately avoids content-based
features. Instead it describes the *shape* of a query: length, ratio of
special characters, count of SQL keywords, character-level entropy, and
character-bigram entropy — a zero-day payload with unfamiliar syntax still
tends to look structurally different from benign traffic even if no keyword
matches anything known.

``bigram_entropy`` added 15/08 after the SSRF/short-string cleanup (see
report/plan/solution_branch2_cleanup.md) regressed separation: DR at matched
FPR=5% dropped 41.87%->31.19% because removing the short-string benign
cluster left only complex JOIN/subquery rows, which overlap attack payloads
in (length, special_char_ratio, sql_keyword_count, entropy) space. Bigram
entropy (Shannon entropy over adjacent-character pairs, not single chars)
captures local structural repetition (e.g. `))`, `--`, quote/paren runs) that
unigram entropy misses, and recovers/exceeds the pre-cleanup separation when
combined with sql_keyword_count + entropy — see
train/explore_branch2_new_features.py and report/metrics/branch2_feature_exploration.json
for the ablation that also found `length` and `special_char_ratio` now HURT
separation post-cleanup (their old discriminative power depended on the
short-string cluster that was removed) and dropped them from
configs/config.yaml branch2_anomaly.features.
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

# Canonical field order for StatisticalFeatures.as_list() / model input.
# `bigram_entropy` is APPENDED (not inserted) so any existing model trained
# on the first 4 columns still gets those in the same positions. Consumers
# that need a specific subset/order (e.g. a model trained on
# branch2_anomaly.features = ["sql_keyword_count", "entropy",
# "bigram_entropy"]) should select+reorder by name from this list rather
# than assuming as_list()'s order/length directly — see
# src/models/branch3_features.py::branch2_scores_for_texts and
# deploy/registry.py::Branch2Model.predict for the reference implementation.
FEATURE_ORDER = ["length", "special_char_ratio", "sql_keyword_count", "entropy", "bigram_entropy"]


@dataclass(frozen=True)
class StatisticalFeatures:
    """Structural feature vector for one query/payload string."""

    length: int
    special_char_ratio: float
    sql_keyword_count: int
    entropy: float
    bigram_entropy: float

    def as_list(self) -> list[float]:
        """Return features as a plain list, in FEATURE_ORDER, for model input."""
        return [
            float(self.length),
            self.special_char_ratio,
            float(self.sql_keyword_count),
            self.entropy,
            self.bigram_entropy,
        ]

    def as_dict(self) -> dict[str, float]:
        """Return features as a name -> value dict (for selecting a subset by name)."""
        return dict(zip(FEATURE_ORDER, self.as_list()))


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


def _bigram_entropy(text: str) -> float:
    """Compute Shannon entropy (bits/bigram) over adjacent-character pairs.

    Unlike unigram entropy, this is sensitive to local structural repetition
    (e.g. `))`, `--`, runs of quotes/parens) rather than just the overall
    character-frequency distribution.

    Args:
        text: Input string.

    Returns:
        Entropy in bits per bigram; 0.0 for strings shorter than 2 chars.
    """
    if len(text) < 2:
        return 0.0
    bigrams = [text[i:i + 2] for i in range(len(text) - 1)]
    counts = Counter(bigrams)
    n = len(bigrams)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


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
    bigram_entropy = _bigram_entropy(text)

    return StatisticalFeatures(
        length=length,
        special_char_ratio=special_char_ratio,
        sql_keyword_count=sql_keyword_count,
        entropy=entropy,
        bigram_entropy=bigram_entropy,
    )
