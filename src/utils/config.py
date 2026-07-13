"""Config loading.

Loads YAML config (thresholds, paths, timeouts) so nothing is hardcoded.
Environment variables of the form ``SQLIDS_<SECTION>_<KEY>`` override the
matching YAML value, allowing secrets/deploy-specific overrides via a ``.env``
file without editing the committed config.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "config.yaml"

_ENV_PREFIX = "SQLIDS_"


class Config(dict):
    """Dict-like config object supporting attribute and dotted-key access."""

    def get_path(self, dotted_key: str, default: Any = None) -> Any:
        """Return a value addressed by a dotted key, e.g. ``"decision.timeout"``.

        Args:
            dotted_key: Keys joined by ``.`` describing the nested path.
            default: Value returned when any key in the path is missing.

        Returns:
            The resolved value, or ``default`` if the path does not exist.
        """
        node: Any = self
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    """Override ``config[section][key]`` from ``SQLIDS_SECTION_KEY`` env vars.

    Args:
        config: Parsed config mapping (mutated in place).

    Returns:
        The same mapping, with any environment overrides applied.
    """
    for env_key, env_val in os.environ.items():
        if not env_key.startswith(_ENV_PREFIX):
            continue
        remainder = env_key[len(_ENV_PREFIX):].lower()
        section, _, key = remainder.partition("_")
        if not key:
            continue
        config.setdefault(section, {})
        if isinstance(config[section], dict):
            config[section][key] = env_val
    return config


def load_config(path: str | Path | None = None) -> Config:
    """Load and return the project configuration.

    Args:
        path: Optional path to a YAML config file. Falls back to
            ``configs/config.yaml`` at the repository root.

    Returns:
        A :class:`Config` populated from YAML with env-var overrides applied.

    Raises:
        FileNotFoundError: If the resolved config file does not exist.
    """
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle) or {}
    return Config(_apply_env_overrides(raw))
