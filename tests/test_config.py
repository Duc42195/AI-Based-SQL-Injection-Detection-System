"""Smoke tests for config loading + env-var overrides."""

from __future__ import annotations

from src.utils.config import load_config


def test_config_loads_defaults() -> None:
    cfg = load_config()
    assert cfg.get_path("project.name") == "ai-sqli-detection"
    assert cfg.get_path("decision.overkill_timeout_seconds") == 300


def test_env_override(monkeypatch) -> None:
    monkeypatch.setenv("SQLIDS_API_PORT", "9999")
    cfg = load_config()
    assert cfg.get_path("api.port") == "9999"


def test_missing_key_returns_default() -> None:
    cfg = load_config()
    assert cfg.get_path("does.not.exist", default="fallback") == "fallback"
