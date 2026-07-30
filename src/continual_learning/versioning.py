"""Data-version registry, content hashing and training-run identity.

Implements sections 1–3 of ``report/plan/mlops_contract.md``.

Two ideas carry the whole module:

1. **A data version is identified by its content**, not its name — a sha256 over
   its sorted ``(id, label)`` pairs. That makes "model X was trained on data Y"
   provable rather than asserted, and makes a sealed version immutable in
   practice: change a row and the hash no longer matches.

2. **The bump is a consequence, not a choice.** Adding rows within the same
   label space is a *minor* bump; introducing a class changes the label space
   and is a *major* one. Major matters because a model that never saw class *X*
   cannot be fairly compared against one that did — see :mod:`.gate`.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Sequence

from src.utils import get_logger, load_config

logger = get_logger(__name__)

Bump = Literal["major", "minor"]
REGISTRY_FILENAME = "registry.json"


# --------------------------------------------------------------------------- #
# Hashing
# --------------------------------------------------------------------------- #
def content_hash(pairs: Iterable[tuple[Any, Any]]) -> str:
    """Hash a dataset by its ``(id, label)`` pairs, order-independently.

    Args:
        pairs: Iterable of ``(row_id, label)``. Sorted internally, so the caller
            need not care about row order.

    Returns:
        ``"sha256:<hex>"``.
    """
    digest = hashlib.sha256()
    for row_id, label in sorted((str(i), str(l)) for i, l in pairs):
        digest.update(row_id.encode())
        digest.update(b"\x1f")  # unit separator: keeps fields unambiguous
        digest.update(label.encode())
        digest.update(b"\x1e")  # record separator
    return f"sha256:{digest.hexdigest()}"


def hash_ids(ids: Iterable[Any]) -> str:
    """Hash a set of row ids (used to seal a train/valid split)."""
    digest = hashlib.sha256()
    for row_id in sorted(str(i) for i in ids):
        digest.update(row_id.encode())
        digest.update(b"\x1e")
    return f"sha256:{digest.hexdigest()}"


def git_sha() -> str:
    """Return the current commit sha, or ``"unknown"`` outside a git checkout."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):  # pragma: no cover
        return "unknown"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Version arithmetic
# --------------------------------------------------------------------------- #
def parse_version(version: str) -> tuple[int, int]:
    """Split ``"2.1"`` into ``(2, 1)``.

    Raises:
        ValueError: If the version is not ``<int>.<int>``.
    """
    try:
        major, minor = version.split(".")
        return int(major), int(minor)
    except ValueError as exc:
        raise ValueError(f"Bad data version {version!r}; expected '<major>.<minor>'") from exc


def major_of(version: str) -> int:
    """Return just the major component of a version string."""
    return parse_version(version)[0]


def infer_bump(old_labels: Sequence[str], new_labels: Sequence[str]) -> Bump:
    """Decide the bump from how the label space changed.

    Args:
        old_labels: Label space of the parent version.
        new_labels: Label space of the new data.

    Returns:
        ``"major"`` if any label is new, else ``"minor"``.
    """
    return "major" if set(new_labels) - set(old_labels) else "minor"


def next_version(parent: str, bump: Bump) -> str:
    """Return the version that follows ``parent`` under ``bump``."""
    major, minor = parse_version(parent)
    return f"{major + 1}.0" if bump == "major" else f"{major}.{minor + 1}"


# --------------------------------------------------------------------------- #
# Run identity
# --------------------------------------------------------------------------- #
def compute_run_id(train_config: dict, data_content_hash: str, seed: int) -> str:
    """Return the idempotency key for a training run.

    Identical ``(config, data, seed)`` must yield an identical id, so a repeated
    run can be recognised and skipped rather than silently redone.

    Args:
        train_config: The training configuration snapshot.
        data_content_hash: Hash of the data version being trained on.
        seed: Random seed for the run.

    Returns:
        A 12-character hex digest.
    """
    payload = json.dumps(
        {"config": train_config, "data": data_content_hash, "seed": seed},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
@dataclass
class DataVersion:
    """One sealed (or draft) data version."""

    version: str
    label_space: list[str]
    n_rows: int
    content_hash: str
    state: Literal["draft", "sealed"] = "sealed"
    protected: bool = False
    parent: str | None = None
    bump: Bump | None = None
    created_at: str = field(default_factory=_now)
    reason: str = ""
    partitions: dict[str, int] = field(default_factory=dict)
    golden_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise to the registry's JSON shape."""
        return {
            "version": self.version,
            "state": self.state,
            "protected": self.protected,
            "parent": self.parent,
            "bump": self.bump,
            "created_at": self.created_at,
            "reason": self.reason,
            "label_space": list(self.label_space),
            "n_rows": self.n_rows,
            "content_hash": self.content_hash,
            "partitions": dict(self.partitions),
            "golden_hash": self.golden_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DataVersion:
        """Rebuild from the registry's JSON shape."""
        return cls(
            version=raw["version"],
            label_space=list(raw.get("label_space", [])),
            n_rows=int(raw.get("n_rows", 0)),
            content_hash=raw.get("content_hash", ""),
            state=raw.get("state", "sealed"),
            protected=bool(raw.get("protected", False)),
            parent=raw.get("parent"),
            bump=raw.get("bump"),
            created_at=raw.get("created_at", ""),
            reason=raw.get("reason", ""),
            partitions=dict(raw.get("partitions", {})),
            golden_hash=raw.get("golden_hash"),
        )


class VersionRegistry:
    """JSON-backed registry of data versions for one dataset.

    Deliberately a file and not a database: tens of records, append-mostly, and
    far more useful diffable in git next to the artifacts it describes.
    """

    def __init__(self, path: Path, dataset: str = "branch1") -> None:
        self.path = Path(path)
        self.dataset = dataset
        self._versions: list[DataVersion] = []
        if self.path.exists():
            self._load()

    # -- persistence ------------------------------------------------------- #
    def _load(self) -> None:
        with self.path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        self.dataset = raw.get("dataset", self.dataset)
        self._versions = [DataVersion.from_dict(v) for v in raw.get("versions", [])]

    def save(self) -> None:
        """Write the registry to disk (creating parent directories)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "dataset": self.dataset,
            "versions": [v.to_dict() for v in self._versions],
        }
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        logger.info("Wrote version registry %s (%d versions)", self.path, len(self._versions))

    # -- queries ----------------------------------------------------------- #
    @property
    def versions(self) -> list[DataVersion]:
        """All known versions, in insertion order."""
        return list(self._versions)

    def get(self, version: str) -> DataVersion | None:
        """Return a version by name, or ``None``."""
        return next((v for v in self._versions if v.version == version), None)

    def latest(self) -> DataVersion | None:
        """Return the highest version by ``(major, minor)``."""
        if not self._versions:
            return None
        return max(self._versions, key=lambda v: parse_version(v.version))

    def latest_in_major(self, major: int) -> DataVersion | None:
        """Return the highest version within one major, or ``None``."""
        candidates = [v for v in self._versions if major_of(v.version) == major]
        if not candidates:
            return None
        return max(candidates, key=lambda v: parse_version(v.version))

    # -- mutation ---------------------------------------------------------- #
    def seal(
        self,
        *,
        label_space: Sequence[str],
        n_rows: int,
        content_hash_value: str,
        parent: str | None = None,
        reason: str = "",
        partitions: dict[str, int] | None = None,
        golden_hash: str | None = None,
        protected: bool = False,
    ) -> DataVersion:
        """Seal a new data version, inferring its number from the label space.

        Args:
            label_space: Label names present in the new data.
            n_rows: Row count.
            content_hash_value: Result of :func:`content_hash`.
            parent: Version this derives from; defaults to the latest.
            reason: Human-readable note stored in the registry.
            partitions: Row counts per partition.
            golden_hash: Hash of the golden partition (frozen within a major).
            protected: Mark as un-resettable (the baseline).

        Returns:
            The newly sealed :class:`DataVersion`.

        Raises:
            ValueError: If a version with this content hash is already sealed,
                or the parent is unknown.
        """
        existing = next(
            (v for v in self._versions if v.content_hash == content_hash_value), None
        )
        if existing is not None:
            raise ValueError(
                f"Identical content already sealed as version {existing.version}"
            )

        parent_version = self.get(parent) if parent else self.latest()
        if parent and parent_version is None:
            raise ValueError(f"Unknown parent version {parent!r}")

        if parent_version is None:
            version, bump = "1.0", None
        else:
            bump = infer_bump(parent_version.label_space, label_space)
            version = next_version(parent_version.version, bump)

        entry = DataVersion(
            version=version,
            label_space=list(label_space),
            n_rows=n_rows,
            content_hash=content_hash_value,
            parent=parent_version.version if parent_version else None,
            bump=bump,
            reason=reason,
            partitions=dict(partitions or {}),
            golden_hash=golden_hash,
            protected=protected,
        )
        self._versions.append(entry)
        logger.info(
            "Sealed data version %s (bump=%s, rows=%d, labels=%d)",
            version,
            bump,
            n_rows,
            len(entry.label_space),
        )
        return entry

    def remove(self, version: str) -> bool:
        """Drop a version from the registry unless it is protected.

        Returns:
            True if it was removed.

        Raises:
            PermissionError: If the version is protected.
        """
        entry = self.get(version)
        if entry is None:
            return False
        if entry.protected:
            raise PermissionError(f"Version {version} is protected and cannot be removed")
        self._versions.remove(entry)
        return True


def registry_path(dataset: str = "branch1", cfg=None) -> Path:
    """Resolve the registry path for a dataset from config."""
    cfg = cfg or load_config()
    base = Path(cfg.get_path("mlops.data_versions_dir", "data/versions"))
    return base / dataset / REGISTRY_FILENAME


def load_registry(dataset: str = "branch1", cfg=None) -> VersionRegistry:
    """Load (or create) the registry for a dataset."""
    return VersionRegistry(registry_path(dataset, cfg), dataset=dataset)
