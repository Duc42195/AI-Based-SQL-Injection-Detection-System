"""Unit tests for Branch 2 statistical feature extraction."""

from __future__ import annotations

from src.preprocessing.statistical_features import FEATURE_ORDER, extract_statistical_features


def test_empty_string() -> None:
    f = extract_statistical_features("")
    assert f.length == 0
    assert f.special_char_ratio == 0.0
    assert f.sql_keyword_count == 0
    assert f.entropy == 0.0
    assert f.bigram_entropy == 0.0
    assert f.quote_imbalance == 0.0
    assert f.same_type_run_ratio == 0.0
    assert f.max_token_length == 0
    assert f.token_count == 0
    assert f.max_special_run == 0
    assert f.max_digit_run == 0
    assert f.paren_imbalance == 0.0


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


def test_bigram_entropy_zero_for_short_strings() -> None:
    assert extract_statistical_features("a").bigram_entropy == 0.0


def test_bigram_entropy_lower_for_repeated_bigrams() -> None:
    repeated = extract_statistical_features(")))))))))" * 3)
    varied = extract_statistical_features("select id from users where name='a'")
    assert repeated.bigram_entropy < varied.bigram_entropy


def test_quote_imbalance_even_quotes_is_zero() -> None:
    assert extract_statistical_features("select name from users where id='1'").quote_imbalance == 0.0


def test_quote_imbalance_one_unclosed_quote_type() -> None:
    assert extract_statistical_features("' OR 1=1--").quote_imbalance == 1.0


def test_quote_imbalance_both_quote_types_unclosed() -> None:
    assert extract_statistical_features("' OR \"1").quote_imbalance == 2.0


def test_as_list_returns_twelve_floats_in_feature_order() -> None:
    f = extract_statistical_features("select 1")
    values = f.as_list()
    assert len(values) == len(FEATURE_ORDER) == 12
    assert all(isinstance(v, float) for v in values)


def test_as_dict_keys_match_feature_order() -> None:
    f = extract_statistical_features("select 1")
    assert list(f.as_dict().keys()) == FEATURE_ORDER


def test_same_type_run_ratio_zero_for_short_strings() -> None:
    assert extract_statistical_features("a").same_type_run_ratio == 0.0


def test_same_type_run_ratio_one_for_uniform_class() -> None:
    assert extract_statistical_features("aaaa").same_type_run_ratio == 1.0


def test_same_type_run_ratio_lower_for_mixed_classes() -> None:
    mixed = extract_statistical_features("a1 b2!c3")
    uniform = extract_statistical_features("aaaaaaaa")
    assert mixed.same_type_run_ratio < uniform.same_type_run_ratio


def test_max_token_length_picks_longest_token() -> None:
    f = extract_statistical_features("id=1 verylongtoken123 x=2")
    assert f.max_token_length == len("verylongtoken123")


def test_max_token_length_zero_for_empty_string() -> None:
    assert extract_statistical_features("").max_token_length == 0


def test_token_count_counts_whitespace_delimited_tokens() -> None:
    assert extract_statistical_features("a b  c").token_count == 3


def test_max_special_run_finds_longest_special_char_run() -> None:
    f = extract_statistical_features("abc))))def")
    assert f.max_special_run == 4


def test_max_special_run_zero_for_alnum_only() -> None:
    assert extract_statistical_features("abc123").max_special_run == 0


def test_max_digit_run_finds_longest_digit_run() -> None:
    f = extract_statistical_features("id=12345&x=1")
    assert f.max_digit_run == 5


def test_paren_imbalance_zero_for_even_paren_counts() -> None:
    assert extract_statistical_features("f(1)+g(2)").paren_imbalance == 0.0


def test_paren_imbalance_one_for_unclosed_paren() -> None:
    assert extract_statistical_features("f(g(1)").paren_imbalance == 1.0
