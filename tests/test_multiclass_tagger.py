"""Unit tests for the rule-based multi-class SQLi tagger."""

from __future__ import annotations

from src.preprocessing.multiclass_tagger import (
    LABEL_BOOLEAN_BLIND,
    LABEL_ERROR_BASED,
    LABEL_NORMAL,
    LABEL_STACKED,
    LABEL_TIME_BLIND,
    LABEL_UNION_BASED,
    matches_any_attack_signature,
    tag_query,
)


def test_normal_query_gets_label_normal() -> None:
    assert tag_query("SELECT * FROM users WHERE id = 42", is_attack=False) == LABEL_NORMAL


def test_union_based() -> None:
    text = "1' UNION SELECT username,password FROM users-- "
    assert tag_query(text, is_attack=True) == LABEL_UNION_BASED


def test_error_based() -> None:
    text = "' AND extractvalue(1,concat(0x7e,version()))-- "
    assert tag_query(text, is_attack=True) == LABEL_ERROR_BASED


def test_time_blind() -> None:
    text = "' OR SLEEP(5)-- "
    assert tag_query(text, is_attack=True) == LABEL_TIME_BLIND


def test_stacked() -> None:
    text = "'; DROP TABLE users; --"
    assert tag_query(text, is_attack=True) == LABEL_STACKED


def test_boolean_blind_fallback() -> None:
    text = "' OR 1=1-- "
    assert tag_query(text, is_attack=True) == LABEL_BOOLEAN_BLIND


def test_priority_stacked_over_time_blind() -> None:
    text = "'; DROP TABLE users; -- and also SLEEP(5)"
    assert tag_query(text, is_attack=True) == LABEL_STACKED


def test_unmatched_attack_falls_back_to_boolean_blind() -> None:
    text = "create user name identified by pass123"
    assert tag_query(text, is_attack=True) == LABEL_BOOLEAN_BLIND


def test_stacked_with_ddl_and_privilege_keywords() -> None:
    for stmt in ["TRUNCATE TABLE users", "CREATE USER hacker", "GRANT ALL PRIVILEGES", "ALTER TABLE users"]:
        text = f"1; {stmt}--"
        assert tag_query(text, is_attack=True) == LABEL_STACKED, text


def test_matches_any_attack_signature_true_for_sqli() -> None:
    assert matches_any_attack_signature("/blog / sleep(15) /index.php")


def test_matches_any_attack_signature_true_for_os_command_injection() -> None:
    assert matches_any_attack_signature("/blog/wp-includes/js;cat /etc/passwd;/jquery")
    assert matches_any_attack_signature("test $(whoami) end")
    assert matches_any_attack_signature("test `whoami` end")


def test_matches_any_attack_signature_true_for_shellshock() -> None:
    assert matches_any_attack_signature("() { :;}; /bin/sleep 15")


def test_matches_any_attack_signature_false_for_benign_text() -> None:
    assert not matches_any_attack_signature("/blog/wp-content/uploads/2020/04/photo.png")
    assert not matches_any_attack_signature("select * from users where id = 1")
