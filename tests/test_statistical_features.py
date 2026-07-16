"""Unit tests for Branch 2 statistical feature extraction."""

from __future__ import annotations

from src.preprocessing.statistical_features import extract_statistical_features


def test_empty_string() -> None:
    f = extract_statistical_features("")
    assert f.length == 0
    assert f.special_char_ratio == 0.0
    assert f.sql_keyword_count == 0
    assert f.entropy == 0.0


def test_length_matches_input() -> None:
    f = extract_statistical_features("select * from users")
    assert f.length == len("select * from users")


def test_special_char_ratio_higher_for_attack_like_text() -> None:
    benign = extract_statistical_features("select name from users where id=1")
    attack = extract_statistical_features("' or 1=1-- ' and '1'='1'--")
    assert attack.special_char_ratio > benign.special_char_ratio


def test_sql_keyword_count() -> None:
    f = extract_statistical_features("select * from users union select null")
    assert f.sql_keyword_count >= 3  # select, from, union, select


def test_entropy_higher_for_more_varied_text() -> None:
    uniform = extract_statistical_features("aaaaaaaaaa")
    varied = extract_statistical_features("a1b2c3d4e5")
    assert varied.entropy > uniform.entropy


def test_as_list_returns_four_floats() -> None:
    f = extract_statistical_features("select 1")
    values = f.as_list()
    assert len(values) == 4
    assert all(isinstance(v, float) for v in values)
