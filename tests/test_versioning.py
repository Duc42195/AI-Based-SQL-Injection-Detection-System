"""Tests for data-version identity, bump inference and the registry."""

from __future__ import annotations

import pytest

from src.continual_learning.versioning import (
    VersionRegistry,
    compute_run_id,
    content_hash,
    hash_ids,
    infer_bump,
    major_of,
    next_version,
    parse_version,
)

LABELS_V1 = ["normal", "union_based", "error_based", "boolean_blind", "time_blind"]


# --------------------------------------------------------------------------- #
# Hashing
# --------------------------------------------------------------------------- #
def test_content_hash_is_order_independent() -> None:
    a = content_hash([(1, "normal"), (2, "union_based")])
    b = content_hash([(2, "union_based"), (1, "normal")])
    assert a == b


def test_content_hash_detects_a_changed_label() -> None:
    before = content_hash([(1, "normal"), (2, "union_based")])
    after = content_hash([(1, "normal"), (2, "error_based")])
    assert before != after


def test_content_hash_detects_an_added_row() -> None:
    before = content_hash([(1, "normal")])
    after = content_hash([(1, "normal"), (2, "normal")])
    assert before != after


def test_content_hash_separators_prevent_field_collisions() -> None:
    """('a','bc') and ('ab','c') must not hash alike."""
    assert content_hash([("a", "bc")]) != content_hash([("ab", "c")])


def test_hash_ids_is_order_independent() -> None:
    assert hash_ids([3, 1, 2]) == hash_ids([1, 2, 3])


# --------------------------------------------------------------------------- #
# Version arithmetic
# --------------------------------------------------------------------------- #
def test_parse_and_major() -> None:
    assert parse_version("2.1") == (2, 1)
    assert major_of("13.4") == 13


def test_parse_version_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_version("v2")


def test_infer_bump_minor_when_label_space_unchanged() -> None:
    assert infer_bump(LABELS_V1, LABELS_V1) == "minor"
    # A subset is still not a *new* label -> minor.
    assert infer_bump(LABELS_V1, LABELS_V1[:3]) == "minor"


def test_infer_bump_major_when_a_class_appears() -> None:
    assert infer_bump(LABELS_V1, [*LABELS_V1, "stacked"]) == "major"


def test_next_version() -> None:
    assert next_version("1.0", "minor") == "1.1"
    assert next_version("1.7", "major") == "2.0"


# --------------------------------------------------------------------------- #
# Run identity
# --------------------------------------------------------------------------- #
def test_run_id_is_stable_for_identical_inputs() -> None:
    cfg = {"architecture": "tfidf_logreg", "tfidf": {"ngram_min": 2}}
    assert compute_run_id(cfg, "sha256:abc", 42) == compute_run_id(cfg, "sha256:abc", 42)


def test_run_id_ignores_key_order() -> None:
    a = compute_run_id({"a": 1, "b": 2}, "sha256:abc", 42)
    b = compute_run_id({"b": 2, "a": 1}, "sha256:abc", 42)
    assert a == b


@pytest.mark.parametrize(
    "cfg,data,seed",
    [
        ({"architecture": "cnn_sqltok"}, "sha256:abc", 42),  # config changed
        ({"architecture": "tfidf_logreg"}, "sha256:def", 42),  # data changed
        ({"architecture": "tfidf_logreg"}, "sha256:abc", 7),  # seed changed
    ],
)
def test_run_id_changes_when_any_input_changes(cfg, data, seed) -> None:
    baseline = compute_run_id({"architecture": "tfidf_logreg"}, "sha256:abc", 42)
    assert compute_run_id(cfg, data, seed) != baseline


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def _registry(tmp_path) -> VersionRegistry:
    return VersionRegistry(tmp_path / "registry.json")


def test_first_seal_is_1_0_with_no_bump(tmp_path) -> None:
    reg = _registry(tmp_path)
    v = reg.seal(
        label_space=LABELS_V1, n_rows=10, content_hash_value="sha256:a", reason="baseline"
    )
    assert v.version == "1.0"
    assert v.bump is None
    assert v.parent is None


def test_adding_rows_gives_a_minor_bump(tmp_path) -> None:
    reg = _registry(tmp_path)
    reg.seal(label_space=LABELS_V1, n_rows=10, content_hash_value="sha256:a")
    v = reg.seal(label_space=LABELS_V1, n_rows=20, content_hash_value="sha256:b")
    assert v.version == "1.1"
    assert v.bump == "minor"
    assert v.parent == "1.0"


def test_new_class_gives_a_major_bump(tmp_path) -> None:
    reg = _registry(tmp_path)
    reg.seal(label_space=LABELS_V1, n_rows=10, content_hash_value="sha256:a")
    v = reg.seal(
        label_space=[*LABELS_V1, "stacked"], n_rows=11, content_hash_value="sha256:b"
    )
    assert v.version == "2.0"
    assert v.bump == "major"


def test_sealing_identical_content_twice_is_refused(tmp_path) -> None:
    reg = _registry(tmp_path)
    reg.seal(label_space=LABELS_V1, n_rows=10, content_hash_value="sha256:a")
    with pytest.raises(ValueError, match="already sealed"):
        reg.seal(label_space=LABELS_V1, n_rows=10, content_hash_value="sha256:a")


def test_unknown_parent_is_refused(tmp_path) -> None:
    reg = _registry(tmp_path)
    reg.seal(label_space=LABELS_V1, n_rows=10, content_hash_value="sha256:a")
    with pytest.raises(ValueError, match="Unknown parent"):
        reg.seal(
            label_space=LABELS_V1,
            n_rows=11,
            content_hash_value="sha256:b",
            parent="9.9",
        )


def test_latest_and_latest_in_major(tmp_path) -> None:
    reg = _registry(tmp_path)
    reg.seal(label_space=LABELS_V1, n_rows=10, content_hash_value="sha256:a")  # 1.0
    reg.seal(label_space=LABELS_V1, n_rows=11, content_hash_value="sha256:b")  # 1.1
    reg.seal(
        label_space=[*LABELS_V1, "stacked"], n_rows=12, content_hash_value="sha256:c"
    )  # 2.0
    assert reg.latest().version == "2.0"
    assert reg.latest_in_major(1).version == "1.1"
    assert reg.latest_in_major(9) is None


def test_protected_version_cannot_be_removed(tmp_path) -> None:
    reg = _registry(tmp_path)
    reg.seal(
        label_space=LABELS_V1,
        n_rows=10,
        content_hash_value="sha256:a",
        protected=True,
    )
    with pytest.raises(PermissionError):
        reg.remove("1.0")


def test_registry_roundtrips_through_disk(tmp_path) -> None:
    path = tmp_path / "registry.json"
    reg = VersionRegistry(path)
    reg.seal(
        label_space=LABELS_V1,
        n_rows=10,
        content_hash_value="sha256:a",
        partitions={"train": 4, "golden": 1, "stream": 5},
        golden_hash="sha256:g",
        protected=True,
    )
    reg.save()

    reloaded = VersionRegistry(path)
    v = reloaded.get("1.0")
    assert v is not None
    assert v.protected is True
    assert v.partitions == {"train": 4, "golden": 1, "stream": 5}
    assert v.golden_hash == "sha256:g"
    assert v.label_space == LABELS_V1
