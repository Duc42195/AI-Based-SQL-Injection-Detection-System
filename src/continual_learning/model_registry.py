"""Which model version is live — runtime state, not committed configuration.

Promotion used to rewrite ``branch1_supervised.active_version`` inside
``configs/config.yaml``. That conflated two different things: config is a
*committed declaration* of the intended baseline, while "what is serving right
now" is *runtime state* that changes as models are promoted and rolled back.
Editing a tracked YAML file at runtime made every demo dirty the git working
tree and made rollback a text substitution.

This module keeps that state in its own file (``models/registry.json``,
gitignored) with explicit stages, borrowing the idea from MLflow's Model
Registry without taking the dependency:

    production  — currently served
    staging     — trained and evaluated, not serving
    archived    — previously served, retained for rollback

Resolution order for "which model do I load":

1. the ``production`` entry in this registry, if there is one;
2. otherwise ``<branch>.active_version`` from config — the declared baseline.

So a fresh clone with no registry serves exactly what config says, and clearing
the registry is a complete rollback to that baseline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from src.utils import get_logger, load_config

logger = get_logger(__name__)

Stage = Literal["production", "staging", "archived"]

REGISTRY_FILENAME = "registry.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ModelEntry:
    """One model version and the stage it currently occupies."""

    version: str
    stage: Stage = "staging"
    data_version: str | None = None
    run_id: str | None = None
    promoted_at: str | None = None
    archived_at: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialise to the registry's JSON shape."""
        return {
            "version": self.version,
            "stage": self.stage,
            "data_version": self.data_version,
            "run_id": self.run_id,
            "promoted_at": self.promoted_at,
            "archived_at": self.archived_at,
            "metrics": self.metrics,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ModelEntry:
        """Rebuild from the registry's JSON shape."""
        return cls(
            version=raw["version"],
            stage=raw.get("stage", "staging"),
            data_version=raw.get("data_version"),
            run_id=raw.get("run_id"),
            promoted_at=raw.get("promoted_at"),
            archived_at=raw.get("archived_at"),
            metrics=dict(raw.get("metrics", {})),
            note=raw.get("note", ""),
        )


class ModelRegistry:
    """Per-branch record of which model is serving, with rollback history."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._branches: dict[str, list[ModelEntry]] = {}
        if self.path.exists():
            self._load()

    # -- persistence ------------------------------------------------------- #
    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):  # pragma: no cover - corrupt state file
            logger.warning("Could not parse %s; starting from empty state", self.path)
            return
        self._branches = {
            branch: [ModelEntry.from_dict(e) for e in entries]
            for branch, entries in raw.get("branches", {}).items()
        }

    def save(self) -> None:
        """Write the registry to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": _now(),
            "branches": {
                branch: [e.to_dict() for e in entries]
                for branch, entries in self._branches.items()
            },
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # -- queries ----------------------------------------------------------- #
    def active(self, branch: str) -> str | None:
        """Return the version in ``production`` for a branch, or ``None``."""
        entry = self.active_entry(branch)
        return entry.version if entry else None

    def active_entry(self, branch: str) -> ModelEntry | None:
        """Return the full ``production`` entry for a branch, or ``None``."""
        return next(
            (e for e in self._branches.get(branch, []) if e.stage == "production"), None
        )

    def history(self, branch: str) -> list[ModelEntry]:
        """Return every recorded entry for a branch, newest first."""
        return list(reversed(self._branches.get(branch, [])))

    def get(self, branch: str, version: str) -> ModelEntry | None:
        """Return one entry by version."""
        return next(
            (e for e in self._branches.get(branch, []) if e.version == version), None
        )

    # -- mutation ---------------------------------------------------------- #
    def promote(
        self,
        branch: str,
        version: str,
        *,
        data_version: str | None = None,
        run_id: str | None = None,
        metrics: dict[str, Any] | None = None,
        note: str = "",
    ) -> ModelEntry:
        """Make ``version`` the production model, archiving whatever was serving.

        Returns:
            The promoted :class:`ModelEntry`.
        """
        entries = self._branches.setdefault(branch, [])
        for entry in entries:
            if entry.stage == "production":
                entry.stage = "archived"
                entry.archived_at = _now()

        promoted = self.get(branch, version)
        if promoted is None:
            promoted = ModelEntry(version=version)
            entries.append(promoted)
        promoted.stage = "production"
        promoted.promoted_at = _now()
        promoted.archived_at = None
        if data_version is not None:
            promoted.data_version = data_version
        if run_id is not None:
            promoted.run_id = run_id
        if metrics:
            promoted.metrics = dict(metrics)
        if note:
            promoted.note = note

        logger.info("Promoted %s to production for %s", version, branch)
        return promoted

    def rollback(self, branch: str) -> ModelEntry | None:
        """Return to the most recently archived model.

        Returns:
            The restored entry, or ``None`` if there is nothing to roll back to
            (in which case clearing the branch falls back to the config
            baseline).
        """
        entries = self._branches.get(branch, [])
        archived = [e for e in entries if e.stage == "archived" and e.archived_at]
        if not archived:
            logger.warning("No archived model to roll back to for %s", branch)
            return None
        previous = max(archived, key=lambda e: e.archived_at or "")
        return self.promote(branch, previous.version, note="rollback")

    def clear(self, branch: str | None = None) -> None:
        """Forget registry state, so resolution falls back to config.

        Args:
            branch: Clear one branch, or every branch when ``None``.
        """
        if branch is None:
            self._branches = {}
        else:
            self._branches.pop(branch, None)
        logger.info("Cleared model registry state for %s", branch or "all branches")

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the API layer."""
        return {
            branch: [e.to_dict() for e in entries]
            for branch, entries in self._branches.items()
        }


def registry_path(cfg=None) -> Path:
    """Resolve the model-registry state file from config."""
    cfg = cfg or load_config()
    return Path(cfg.get_path("paths.models_dir", "models")) / REGISTRY_FILENAME


def load_model_registry(cfg=None) -> ModelRegistry:
    """Load (or create) the model registry."""
    return ModelRegistry(registry_path(cfg))


def resolve_active(branch: str, config_key: str, default: str, cfg=None) -> str:
    """Return the version to serve for a branch.

    Registry state wins; config is the declared baseline and the fallback.

    Args:
        branch: Branch name, e.g. ``"branch1"``.
        config_key: Dotted config key holding the baseline, e.g.
            ``"branch1_supervised.active_version"``.
        default: Value if neither registry nor config has one.
        cfg: Optional pre-loaded config.

    Returns:
        The model version directory name to load.
    """
    cfg = cfg or load_config()
    promoted = load_model_registry(cfg).active(branch)
    if promoted:
        return promoted
    return str(cfg.get_path(config_key, default))
