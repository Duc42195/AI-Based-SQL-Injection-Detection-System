"""Unit tests for the synthetic stacked-query generator."""

from __future__ import annotations

from src.preprocessing.multiclass_tagger import LABEL_STACKED, tag_query
from src.preprocessing.synthetic_stacked import generate_synthetic_stacked


def test_generates_nonempty_list() -> None:
    payloads = generate_synthetic_stacked()
    assert len(payloads) > 0


def test_respects_limit() -> None:
    payloads = generate_synthetic_stacked(limit=10)
    assert len(payloads) == 10


def test_all_generated_payloads_tag_as_stacked() -> None:
    payloads = generate_synthetic_stacked()
    for p in payloads:
        assert tag_query(p, is_attack=True) == LABEL_STACKED, p


def test_payloads_are_unique() -> None:
    payloads = generate_synthetic_stacked()
    assert len(payloads) == len(set(payloads))
