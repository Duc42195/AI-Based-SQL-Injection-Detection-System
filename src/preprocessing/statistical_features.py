"""Statistical/structural feature extraction for Branch 2 (anomaly detection).

Branch 1 learns from content (TF-IDF over known attack syntax); Branch 2 must
generalize to SYNTAX IT HAS NEVER SEEN, so it deliberately avoids content-based
features. Instead it describes the *shape* of a query: length, ratio of
special characters, count of SQL keywords, character-level entropy, and
character-bigram entropy — a zero-day payload with unfamiliar syntax still
tends to look structurally different from benign traffic even if no keyword
matches anything known.

``bigram_entropy`` (added 15/08) turned out 16-17/08 to be a DOMAIN-SHIFT
artifact, not a genuine attack-structure signal: the benign training pool
used at the time was accidentally missing the `d3_csic2010` source entirely
(a data-loading bug in train/build_branch2_data.py — see that file's
docstring), while the anomalous eval set is 100% `d3_csic2010`. Bigram
entropy partly separated "which raw dataset is this text from" rather than
"is this an attack" — confirmed by comparing means: benign-d3_csic2010=6.90
vs attack-d3_csic2010=6.42 (barely different, the real in-domain task) vs
benign-d1_sqliv3+d7_srbh2020=5.35 vs attack-d3_csic2010=6.42 (much bigger
gap, but a cross-dataset-formatting gap, not an attack signal). Once the
data bug was fixed and d3_csic2010 benign rows were included in training,
bigram_entropy stopped helping (and started hurting) — see
configs/config.yaml branch2_anomaly for the full account and
report/metrics/branch2_feature_exploration.json for the re-run ablation.

``quote_imbalance`` (added 17/08, after the above) is the feature that
replaced it: count of unclosed single/double quotes
(`(count("'") odd) + (count('"') odd)` -> 0/1/2). Unlike bigram_entropy,
this is a direct structural signature of string-literal breakout (e.g.
`' OR '1'='1`) independent of which raw dataset a query happens to come
from, and held up as a genuine signal on the corrected, d3_csic2010-inclusive
benign pool.

``same_type_run_ratio``, ``max_token_length``, ``token_count``,
``max_special_run``, ``max_digit_run``, ``paren_imbalance`` (added 17/08):
a second finding the same day showed *why* D3/D7 are structurally harder
than D1 even with quote_imbalance added — D3/D7 rows are full HTTP
request/parameter strings (`key=value&key=value&...`), so a whole-string
RATIO feature (special_char_ratio, quote_imbalance) gets diluted by all the
legitimate `&`/`=`/`.` syntax surrounding a small injected payload (measured
effect size on special_char_ratio: |d|=1.69 on D1, only |d|=0.12 on D3 — see
report/plan/data_contract.md). These six features look for a *local peak*
(longest run of special/digit chars, longest single token) instead of a
whole-string average, so they don't get diluted the same way. Combined with
scoping D1+D3+D7 down to query-parameter text only (URL scheme/host/path
stripped — see train/build_branch2_dataset.py) and switching the estimator
to LocalOutlierFactor (local-density based, handles the resulting 3
structurally-distinct benign sub-populations far better than one global
OCSVM/IsolationForest boundary — see configs/config.yaml branch2_anomaly),
this raised DR@matched-FPR5% from 26.2% to 80.0% (AUC 0.79 -> 0.90) on a
combined D1+D3+D7 zero-day eval. Full account: report/plan/data_contract.md.
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
# New fields are APPENDED (never inserted) so any existing model trained on
# the earlier columns still gets those in the same positions. Consumers that
# need a specific subset/order (e.g. a model trained on
# branch2_anomaly.features = ["special_char_ratio", "entropy",
# "quote_imbalance"]) should select+reorder by name from this list rather
# than assuming as_list()'s order/length directly — see
# src/models/branch3_features.py::branch2_scores_for_texts and
# deploy/registry.py::Branch2Model.predict for the reference implementation.
FEATURE_ORDER = [
    "length", "special_char_ratio", "sql_keyword_count", "entropy",
    "bigram_entropy", "quote_imbalance",
    "same_type_run_ratio", "max_token_length", "token_count",
    "max_special_run", "max_digit_run", "paren_imbalance",
]


@dataclass(frozen=True)
class StatisticalFeatures:
    """Structural feature vector for one query/payload string."""

    length: int
    special_char_ratio: float
    sql_keyword_count: int
    entropy: float
    bigram_entropy: float
    quote_imbalance: float
    same_type_run_ratio: float
    max_token_length: int
    token_count: int
    max_special_run: int
    max_digit_run: int
    paren_imbalance: float

    def as_list(self) -> list[float]:
        """Return features as a plain list, in FEATURE_ORDER, for model input."""
        return [
            float(self.length),
            self.special_char_ratio,
            float(self.sql_keyword_count),
            self.entropy,
            self.bigram_entropy,
            self.quote_imbalance,
            self.same_type_run_ratio,
            float(self.max_token_length),
            float(self.token_count),
            float(self.max_special_run),
            float(self.max_digit_run),
            self.paren_imbalance,
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


def _quote_imbalance(text: str) -> float:
    """Count of unclosed single/double quotes: 0, 1, or 2.

    A direct structural signature of string-literal breakout (e.g.
    `' OR '1'='1`), independent of which raw dataset a query came from —
    unlike bigram_entropy, this held up as a genuine signal after the
    domain-shift confound was fixed (see module docstring).

    Args:
        text: Input string.

    Returns:
        `(count("'") is odd) + (count('"') is odd)`, i.e. 0.0, 1.0, or 2.0.
    """
    return float((text.count("'") % 2) + (text.count('"') % 2))


_CHAR_CLASS_SPECIAL_RE = re.compile(r"[^A-Za-z0-9\s]")
_CHAR_CLASS_DIGIT_RE = re.compile(r"[0-9]")
_CHAR_CLASS_SPACE_RE = re.compile(r"\s")
_SPECIAL_RUN_RE = re.compile(r"[^A-Za-z0-9\s]+")
_DIGIT_RUN_RE = re.compile(r"[0-9]+")


def _char_class(ch: str) -> str:
    if _CHAR_CLASS_SPACE_RE.match(ch):
        return "space"
    if _CHAR_CLASS_DIGIT_RE.match(ch):
        return "digit"
    if _CHAR_CLASS_SPECIAL_RE.match(ch):
        return "special"
    return "alpha"


def _same_type_run_ratio(text: str) -> float:
    """Fraction of adjacent character pairs sharing the same class.

    Long runs of one class (padding, repeated tokens, encoded/concatenated
    payloads) vs mixed natural text. 0.0 for strings shorter than 2 chars.
    """
    if len(text) < 2:
        return 0.0
    classes = [_char_class(ch) for ch in text]
    same = sum(1 for a, b in zip(classes, classes[1:]) if a == b)
    return same / (len(classes) - 1)


def _max_token_length(text: str) -> int:
    """Length of the longest whitespace-delimited token."""
    tokens = text.split()
    return max((len(t) for t in tokens), default=0)


def _token_count(text: str) -> int:
    """Number of whitespace-delimited tokens."""
    return len(text.split())


def _max_special_run(text: str) -> int:
    """Length of the longest consecutive run of non-alphanumeric, non-space chars.

    A LOCAL-peak feature, not a whole-string ratio: an injected payload
    embedded in a long, otherwise-legitimate parameter string (D3/D7 -- see
    module docstring) still produces a sharp local run of special characters
    even though it's a small fraction of the total string.
    """
    runs = _SPECIAL_RUN_RE.findall(text)
    return max((len(r) for r in runs), default=0)


def _max_digit_run(text: str) -> int:
    """Length of the longest consecutive run of digit characters."""
    runs = _DIGIT_RUN_RE.findall(text)
    return max((len(r) for r in runs), default=0)


def _paren_imbalance(text: str) -> float:
    """Count of unclosed parentheses: `(count('(') odd) + (count(')') odd)`.

    Same rationale as quote_imbalance but for parenthesis-heavy payloads
    (nested function calls: `dbms_pipe.receive_message(chr(76)||chr(116)...`).
    """
    return float((text.count("(") % 2) + (text.count(")") % 2))


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
    quote_imbalance = _quote_imbalance(text)
    same_type_run_ratio = _same_type_run_ratio(text)
    max_token_length = _max_token_length(text)
    token_count = _token_count(text)
    max_special_run = _max_special_run(text)
    max_digit_run = _max_digit_run(text)
    paren_imbalance = _paren_imbalance(text)

    return StatisticalFeatures(
        length=length,
        special_char_ratio=special_char_ratio,
        sql_keyword_count=sql_keyword_count,
        entropy=entropy,
        bigram_entropy=bigram_entropy,
        quote_imbalance=quote_imbalance,
        same_type_run_ratio=same_type_run_ratio,
        max_token_length=max_token_length,
        token_count=token_count,
        max_special_run=max_special_run,
        max_digit_run=max_digit_run,
        paren_imbalance=paren_imbalance,
    )
