"""Review queue: flagged queries awaiting human confirmation.

Implements sections 3.H, 3.I and 6 of ``report/plan/mlops_contract.md``.

The loop deliberately never asks a human to label from scratch. A queued item
arrives carrying the model's own prediction as ``ai_label``; the reviewer either
**approves** it, **corrects** it, or **rejects** the sample. Whether the label
was corrected is recorded, because the *pre-label acceptance rate* is a free
measure of model quality on live traffic.

Two stores, both already declared in ``configs/config.yaml``:

- **SQLite** (``decision.queue_path``) for the queue itself — rows are mutable
  (pending → decided) and need paging, which is what a database is for.
- **JSONL** (``continual_learning.new_data_path``) for confirmed labels — an
  append-only ledger that feeds the next data version.

``round_id`` tags everything produced by one demo round so a reset can roll back
exactly that round and nothing else.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Literal, Sequence

from src.utils import get_logger, load_config

logger = get_logger(__name__)

Status = Literal["pending", "approved", "corrected", "rejected"]
Action = Literal["approve", "correct", "reject"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS review_queue (
  id              TEXT PRIMARY KEY,
  created_at      TEXT NOT NULL,
  query_raw       TEXT NOT NULL,
  query_canonical TEXT NOT NULL,
  source          TEXT NOT NULL,
  ai_label        TEXT,
  ai_confidence   REAL,
  anomaly_score   REAL,
  status          TEXT NOT NULL DEFAULT 'pending',
  final_label     TEXT,
  decided_at      TEXT,
  decided_by      TEXT,
  round_id        TEXT
);
CREATE INDEX IF NOT EXISTS idx_review_status ON review_queue(status);
CREATE INDEX IF NOT EXISTS idx_review_round  ON review_queue(round_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ReviewItem:
    """One queued query, carrying the model's proposed label."""

    id: str
    query_raw: str
    query_canonical: str
    source: str
    ai_label: str | None = None
    ai_confidence: float | None = None
    anomaly_score: float | None = None
    status: Status = "pending"
    final_label: str | None = None
    created_at: str = field(default_factory=_now)
    decided_at: str | None = None
    decided_by: str | None = None
    round_id: str | None = None

    @property
    def was_corrected(self) -> bool:
        """True when the reviewer chose a label other than the AI's."""
        return self.status == "corrected"

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the API layer."""
        return {
            "id": self.id,
            "query_raw": self.query_raw,
            "query_canonical": self.query_canonical,
            "source": self.source,
            "ai_label": self.ai_label,
            "ai_confidence": self.ai_confidence,
            "anomaly_score": self.anomaly_score,
            "status": self.status,
            "final_label": self.final_label,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
            "decided_by": self.decided_by,
            "round_id": self.round_id,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ReviewItem:
        """Rebuild from a database row."""
        return cls(**{key: row[key] for key in row.keys()})


class ReviewQueue:
    """SQLite-backed queue of items awaiting human confirmation."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # -- writing ----------------------------------------------------------- #
    def enqueue(self, items: Iterable[ReviewItem]) -> int:
        """Add items to the queue, ignoring ids already present.

        Returns:
            The number of rows actually inserted.
        """
        rows = [
            (
                item.id,
                item.created_at,
                item.query_raw,
                item.query_canonical,
                item.source,
                item.ai_label,
                item.ai_confidence,
                item.anomaly_score,
                item.status,
                item.final_label,
                item.decided_at,
                item.decided_by,
                item.round_id,
            )
            for item in items
        ]
        if not rows:
            return 0
        with self._connect() as conn:
            before = conn.total_changes
            conn.executemany(
                "INSERT OR IGNORE INTO review_queue VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
            inserted = conn.total_changes - before
        logger.info("Enqueued %d/%d review items", inserted, len(rows))
        return inserted

    def decide(
        self,
        item_id: str,
        action: Action,
        *,
        label: str | None = None,
        decided_by: str = "admin",
    ) -> ReviewItem:
        """Record a review decision and return the updated item.

        Args:
            item_id: Queue row id.
            action: ``approve`` (accept ``ai_label``), ``correct`` (use ``label``)
                or ``reject`` (drop the sample).
            label: Required for ``correct``.
            decided_by: Reviewer identifier.

        Returns:
            The updated :class:`ReviewItem`.

        Raises:
            KeyError: If the id is unknown.
            ValueError: If the action is unknown, ``correct`` has no label, or
                ``approve`` is used on an item with no AI pre-label.
        """
        item = self.get(item_id)
        if item is None:
            raise KeyError(f"No review item {item_id!r}")

        if action == "approve":
            if item.ai_label is None:
                raise ValueError(f"Item {item_id!r} has no ai_label to approve")
            status, final_label = "approved", item.ai_label
        elif action == "correct":
            if not label:
                raise ValueError("A label is required when correcting an item")
            # Choosing the same label the model proposed is an approval, not a
            # correction — otherwise the acceptance-rate metric would be wrong.
            if label == item.ai_label:
                status, final_label = "approved", label
            else:
                status, final_label = "corrected", label
        elif action == "reject":
            status, final_label = "rejected", None
        else:
            raise ValueError(f"Unknown action {action!r}")

        with self._connect() as conn:
            conn.execute(
                "UPDATE review_queue SET status=?, final_label=?, decided_at=?, decided_by=? "
                "WHERE id=?",
                (status, final_label, _now(), decided_by, item_id),
            )
        updated = self.get(item_id)
        assert updated is not None  # just written
        return updated

    # -- reading ----------------------------------------------------------- #
    def get(self, item_id: str) -> ReviewItem | None:
        """Return one item by id, or ``None``."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM review_queue WHERE id=?", (item_id,)
            ).fetchone()
        return ReviewItem.from_row(row) if row else None

    def list(
        self,
        *,
        status: Status | None = "pending",
        limit: int = 20,
        offset: int = 0,
        round_id: str | None = None,
    ) -> list[ReviewItem]:
        """List items, optionally filtered by status and round."""
        clauses, params = [], []
        if status is not None:
            clauses.append("status=?")
            params.append(status)
        if round_id is not None:
            clauses.append("round_id=?")
            params.append(round_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM review_queue {where} ORDER BY created_at, id LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        return [ReviewItem.from_row(row) for row in rows]

    def counts(self) -> dict[str, int]:
        """Return row counts per status."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM review_queue GROUP BY status"
            ).fetchall()
        return {row["status"]: row["n"] for row in rows}

    def acceptance_rate(self) -> float | None:
        """Share of decided (non-rejected) items whose AI label was kept.

        Returns:
            The rate in ``[0, 1]``, or ``None`` if nothing has been decided.
        """
        counts = self.counts()
        approved = counts.get("approved", 0)
        corrected = counts.get("corrected", 0)
        total = approved + corrected
        return approved / total if total else None

    def purge_round(self, round_id: str) -> int:
        """Delete every row belonging to one round (used by the demo reset)."""
        with self._connect() as conn:
            before = conn.total_changes
            conn.execute("DELETE FROM review_queue WHERE round_id=?", (round_id,))
            deleted = conn.total_changes - before
        logger.info("Purged %d review items from round %s", deleted, round_id)
        return deleted


# --------------------------------------------------------------------------- #
# Confirmed labels (append-only JSONL)
# --------------------------------------------------------------------------- #
def append_confirmed(
    items: Sequence[ReviewItem], path: str | Path, *, label_ids: dict[str, int] | None = None
) -> int:
    """Append decided items to the confirmed-label ledger.

    Rejected and still-pending items are skipped — only confirmed labels feed
    the next data version.

    Args:
        items: Reviewed items.
        path: Destination JSONL.
        label_ids: Optional label-name → id map, recorded alongside the name.

    Returns:
        Number of records written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("a", encoding="utf-8") as handle:
        for item in items:
            if item.status not in ("approved", "corrected") or not item.final_label:
                continue
            record = {
                "id": item.id,
                "query_canonical": item.query_canonical,
                "label": item.final_label,
                "label_id": (label_ids or {}).get(item.final_label),
                "ai_label": item.ai_label,
                "was_corrected": item.was_corrected,
                "confirmed_at": item.decided_at or _now(),
                "round_id": item.round_id,
            }
            handle.write(json.dumps(record) + "\n")
            written += 1
    logger.info("Appended %d confirmed labels to %s", written, path)
    return written


def read_confirmed(path: str | Path, *, round_id: str | None = None) -> list[dict[str, Any]]:
    """Read the confirmed-label ledger, optionally filtered to one round."""
    path = Path(path)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:  # pragma: no cover - a truncated write
                logger.warning("Skipping malformed confirmed-label line in %s", path)
                continue
            if round_id is None or record.get("round_id") == round_id:
                records.append(record)
    return records


def drop_round(path: str | Path, round_id: str) -> int:
    """Rewrite the ledger without one round's records (demo reset).

    Returns:
        Number of records removed.
    """
    path = Path(path)
    if not path.exists():
        return 0
    kept = [r for r in read_confirmed(path) if r.get("round_id") != round_id]
    removed = len(read_confirmed(path)) - len(kept)
    with path.open("w", encoding="utf-8") as handle:
        for record in kept:
            handle.write(json.dumps(record) + "\n")
    logger.info("Dropped %d confirmed labels from round %s", removed, round_id)
    return removed


# --------------------------------------------------------------------------- #
# Config helpers
# --------------------------------------------------------------------------- #
def queue_path(cfg=None) -> Path:
    """Resolve the review-queue database path from config."""
    cfg = cfg or load_config()
    return Path(cfg.get_path("decision.queue_path", "data/overkill_queue.db"))


def confirmed_labels_path(cfg=None) -> Path:
    """Resolve the confirmed-label ledger path from config."""
    cfg = cfg or load_config()
    return Path(
        cfg.get_path("continual_learning.new_data_path", "data/processed/confirmed_labels.jsonl")
    )


def open_queue(cfg=None) -> ReviewQueue:
    """Open (creating if needed) the configured review queue."""
    return ReviewQueue(queue_path(cfg))
