"""Tests for the runtime model registry (which version is served)."""

from __future__ import annotations

import pytest

from src.continual_learning.model_registry import ModelRegistry, resolve_active


@pytest.fixture()
def registry(tmp_path) -> ModelRegistry:
    return ModelRegistry(tmp_path / "registry.json")


def test_empty_registry_has_no_active_model(registry: ModelRegistry) -> None:
    assert registry.active("branch1") is None


def test_promote_sets_production(registry: ModelRegistry) -> None:
    entry = registry.promote(
        "branch1", "branch1_v2", data_version="2.0", run_id="abc", metrics={"f1": 0.9}
    )
    assert entry.stage == "production"
    assert entry.promoted_at is not None
    assert registry.active("branch1") == "branch1_v2"
    assert registry.active_entry("branch1").data_version == "2.0"


def test_promoting_archives_the_previous_production(registry: ModelRegistry) -> None:
    registry.promote("branch1", "v1")
    registry.promote("branch1", "v2")
    assert registry.active("branch1") == "v2"
    assert registry.get("branch1", "v1").stage == "archived"
    assert registry.get("branch1", "v1").archived_at is not None
    # Exactly one production entry at any time.
    assert sum(e.stage == "production" for e in registry.history("branch1")) == 1


def test_branches_are_independent(registry: ModelRegistry) -> None:
    registry.promote("branch1", "b1_v2")
    assert registry.active("branch1") == "b1_v2"
    assert registry.active("branch2") is None


def test_rollback_restores_the_previous_model(registry: ModelRegistry) -> None:
    registry.promote("branch1", "v1")
    registry.promote("branch1", "v2")
    restored = registry.rollback("branch1")
    assert restored is not None and restored.version == "v1"
    assert registry.active("branch1") == "v1"
    assert registry.get("branch1", "v2").stage == "archived"


def test_rollback_with_nothing_archived_returns_none(registry: ModelRegistry) -> None:
    registry.promote("branch1", "v1")
    assert registry.rollback("branch1") is None
    assert registry.active("branch1") == "v1"


def test_rollback_twice_returns_to_the_newer_model(registry: ModelRegistry) -> None:
    """Rollback picks the most recently archived, so it toggles rather than walks back."""
    registry.promote("branch1", "v1")
    registry.promote("branch1", "v2")
    registry.rollback("branch1")  # -> v1, archives v2
    registry.rollback("branch1")  # -> v2, the most recently archived
    assert registry.active("branch1") == "v2"


def test_clear_one_branch_leaves_others(registry: ModelRegistry) -> None:
    registry.promote("branch1", "b1")
    registry.promote("branch2", "b2")
    registry.clear("branch1")
    assert registry.active("branch1") is None
    assert registry.active("branch2") == "b2"


def test_clear_all(registry: ModelRegistry) -> None:
    registry.promote("branch1", "b1")
    registry.clear()
    assert registry.active("branch1") is None


def test_state_survives_reopen(tmp_path) -> None:
    path = tmp_path / "registry.json"
    first = ModelRegistry(path)
    first.promote("branch1", "v2", data_version="2.0", run_id="abc")
    first.save()

    reopened = ModelRegistry(path)
    assert reopened.active("branch1") == "v2"
    assert reopened.active_entry("branch1").run_id == "abc"


def test_corrupt_state_file_does_not_crash(tmp_path) -> None:
    """A truncated write must degrade to the config baseline, not take the API down."""
    path = tmp_path / "registry.json"
    path.write_text("{not json")
    assert ModelRegistry(path).active("branch1") is None


# --------------------------------------------------------------------------- #
# Resolution order: registry wins, config is the fallback baseline
# --------------------------------------------------------------------------- #
def test_resolve_falls_back_to_config_when_nothing_promoted(tmp_path, monkeypatch) -> None:
    from src.continual_learning import model_registry as mod

    monkeypatch.setattr(mod, "registry_path", lambda cfg=None: tmp_path / "registry.json")
    resolved = resolve_active("branch1", "branch1_supervised.active_version", "fallback")
    # The committed config declares the baseline.
    assert resolved == "branch1_v1"


def test_resolve_prefers_a_promoted_version(tmp_path, monkeypatch) -> None:
    from src.continual_learning import model_registry as mod

    path = tmp_path / "registry.json"
    monkeypatch.setattr(mod, "registry_path", lambda cfg=None: path)
    registry = ModelRegistry(path)
    registry.promote("branch1", "branch1_v9")
    registry.save()

    assert resolve_active("branch1", "branch1_supervised.active_version", "x") == "branch1_v9"


def test_resolve_uses_the_default_when_config_key_is_missing(tmp_path, monkeypatch) -> None:
    from src.continual_learning import model_registry as mod

    monkeypatch.setattr(mod, "registry_path", lambda cfg=None: tmp_path / "registry.json")
    assert resolve_active("branch1", "does.not.exist", "the_default") == "the_default"


# --------------------------------------------------------------------------- #
# The bug this module exists to fix
# --------------------------------------------------------------------------- #
def test_promotion_never_modifies_the_committed_config(tmp_path, monkeypatch) -> None:
    """Promotion must leave `configs/config.yaml` byte-identical.

    It used to rewrite `branch1_supervised.active_version` in place, so every
    promotion dirtied the git working tree and rollback was a regex substitution
    on a tracked file. Config declares the baseline; the registry holds runtime
    state. This pins that separation.
    """
    from pathlib import Path

    from src.continual_learning import model_registry as mod
    from src.continual_learning import trainer

    config_path = Path("configs/config.yaml")
    before = config_path.read_bytes()

    monkeypatch.setattr(mod, "registry_path", lambda cfg=None: tmp_path / "registry.json")
    # promote() also stamps the model's metadata.json; point it at an empty dir
    # so this test writes nothing into models/.
    monkeypatch.setattr(
        trainer, "load_model_registry", lambda cfg=None: ModelRegistry(tmp_path / "registry.json")
    )

    trainer.promote("branch1_v9", data_version="9.0", run_id="deadbeef")
    assert config_path.read_bytes() == before, "promote() rewrote configs/config.yaml"

    trainer.rollback("branch1")
    assert config_path.read_bytes() == before, "rollback() rewrote configs/config.yaml"
