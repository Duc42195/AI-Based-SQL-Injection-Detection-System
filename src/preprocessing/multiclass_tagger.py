"""Rule-based multi-class tagger for SQLi payloads.

Assigns one of the 6 Branch-1 labels (see ``configs/config.yaml: labels``) to
a raw SQL/payload string using regex signatures, applied in a fixed priority
order so a payload matching several signatures gets its most specific label:
``stacked > time_blind > error_based > union_based > boolean_blind``.

This is a heuristic tagger, not a ground-truth labeller — outputs must be
spot-checked by hand (see data_contract.md, Muc 3) before being trusted for
training.
"""

from __future__ import annotations

import re

LABEL_NORMAL = 0
LABEL_UNION_BASED = 1
LABEL_ERROR_BASED = 2
LABEL_BOOLEAN_BLIND = 3
LABEL_TIME_BLIND = 4
LABEL_STACKED = 5

LABEL_NAMES: dict[int, str] = {
    LABEL_NORMAL: "normal",
    LABEL_UNION_BASED: "union_based",
    LABEL_ERROR_BASED: "error_based",
    LABEL_BOOLEAN_BLIND: "boolean_blind",
    LABEL_TIME_BLIND: "time_blind",
    LABEL_STACKED: "stacked",
}

# Checked in this exact order; first match wins.
_RULES: list[tuple[int, re.Pattern[str]]] = [
    (
        LABEL_STACKED,
        re.compile(
            r";\s*(DROP|INSERT|UPDATE|DELETE|EXEC|TRUNCATE|CREATE|GRANT|ALTER)",
            re.IGNORECASE,
        ),
    ),
    (
        LABEL_TIME_BLIND,
        re.compile(r"SLEEP\(|BENCHMARK\(|WAITFOR\s+DELAY|PG_SLEEP\(", re.IGNORECASE),
    ),
    (
        LABEL_ERROR_BASED,
        re.compile(
            r"EXTRACTVALUE|UPDATEXML|FLOOR\(RAND|CAST\(.*AS|CONVERT\(",
            re.IGNORECASE,
        ),
    ),
    (LABEL_UNION_BASED, re.compile(r"UNION\s+(ALL\s+)?SELECT", re.IGNORECASE)),
    (
        LABEL_BOOLEAN_BLIND,
        re.compile(r"(OR|AND)\s+\d+\s*=\s*\d+|'\s*OR\s*'?1'?\s*=\s*'?1", re.IGNORECASE),
    ),
]


def tag_attack_payload(text: str) -> int:
    """Assign an attack sub-label (1-5) to a payload already known to be SQLi.

    Args:
        text: Raw attack payload/query text.

    Returns:
        One of ``LABEL_UNION_BASED``, ``LABEL_ERROR_BASED``,
        ``LABEL_BOOLEAN_BLIND``, ``LABEL_TIME_BLIND``, ``LABEL_STACKED``.
        Falls back to ``LABEL_BOOLEAN_BLIND`` (catch-all bucket) if no
        signature matches — see data_contract.md for the known limitation
        this causes (over-broad boolean_blind bucket).
    """
    for label, pattern in _RULES:
        if pattern.search(text):
            return label
    return LABEL_BOOLEAN_BLIND


def tag_query(text: str, is_attack: bool) -> int:
    """Assign a full 6-class Branch-1 label to a query.

    Args:
        text: Raw query/payload text.
        is_attack: Ground-truth binary label from the source dataset
            (``True`` = known SQLi, ``False`` = known normal).

    Returns:
        ``LABEL_NORMAL`` if ``is_attack`` is False, otherwise the result of
        :func:`tag_attack_payload`.
    """
    if not is_attack:
        return LABEL_NORMAL
    return tag_attack_payload(text)
