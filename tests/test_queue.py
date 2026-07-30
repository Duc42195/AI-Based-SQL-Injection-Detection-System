"""Tests for the review queue and the confirmed-label ledger."""

from __future__ import annotations

import pytest

from src.decision.queue import (
    ReviewItem,
    ReviewQueue,
    append_confirmed,
    drop_round,
    read_confirmed,
)


def _item(item_id: str, ai_label: str = "union_based", round_id: str = "r1") -> ReviewItem:
    return ReviewItem(
        id=item_id,
        query_raw="1' OR 1=1--",
        query_canonical="1' or 1=1--",
        source="overkill",
        ai_label=ai_label,
        ai_confidence=0.72,
        anomaly_score=1.5,
        round_id=round_id,
    )


@pytest.fixture()
def queue(tmp_path) -> ReviewQueue:
    return ReviewQueue(tmp_path / "queue.db")


# --------------------------------------------------------------------------- #
# Enqueue / list
# --------------------------------------------------------------------------- #
def test_enqueued_items_start_pending_with_their_ai_label(queue: ReviewQueue) -> None:
    queue.enqueue([_item("a"), _item("b")])
    pending = queue.list()
    assert len(pending) == 2
    assert all(i.status == "pending" for i in pending)
    assert pending[0].ai_label == "union_based"
    assert pending[0].ai_confidence == pytest.approx(0.72)


def test_enqueue_is_idempotent_on_id(queue: ReviewQueue) -> None:
    assert queue.enqueue([_item("a")]) == 1
    assert queue.enqueue([_item("a")]) == 0
    assert queue.counts()["pending"] == 1


def test_enqueue_of_nothing_is_a_noop(queue: ReviewQueue) -> None:
    assert queue.enqueue([]) == 0


def test_list_pages_and_filters_by_status(queue: ReviewQueue) -> None:
    queue.enqueue([_item(f"i{n}") for n in range(5)])
    assert len(queue.list(limit=2)) == 2
    assert len(queue.list(limit=2, offset=4)) == 1
    queue.decide("i0", "approve")
    assert len(queue.list(status="pending")) == 4
    assert len(queue.list(status="approved")) == 1


# --------------------------------------------------------------------------- #
# Decisions
# --------------------------------------------------------------------------- #
def test_approve_accepts_the_ai_label(queue: ReviewQueue) -> None:
    queue.enqueue([_item("a")])
    item = queue.decide("a", "approve")
    assert item.status == "approved"
    assert item.final_label == "union_based"
    assert item.was_corrected is False
    assert item.decided_at is not None


def test_correct_records_a_different_label(queue: ReviewQueue) -> None:
    queue.enqueue([_item("a")])
    item = queue.decide("a", "correct", label="boolean_blind")
    assert item.status == "corrected"
    assert item.final_label == "boolean_blind"
    assert item.was_corrected is True


def test_correcting_to_the_same_label_counts_as_approval(queue: ReviewQueue) -> None:
    """Otherwise the pre-label acceptance rate would understate agreement."""
    queue.enqueue([_item("a", ai_label="union_based")])
    item = queue.decide("a", "correct", label="union_based")
    assert item.status == "approved"
    assert item.was_corrected is False


def test_reject_clears_the_label(queue: ReviewQueue) -> None:
    queue.enqueue([_item("a")])
    item = queue.decide("a", "reject")
    assert item.status == "rejected"
    assert item.final_label is None


def test_correct_without_a_label_is_an_error(queue: ReviewQueue) -> None:
    queue.enqueue([_item("a")])
    with pytest.raises(ValueError, match="label is required"):
        queue.decide("a", "correct")


def test_approving_an_item_with_no_prelabel_is_an_error(queue: ReviewQueue) -> None:
    queue.enqueue([_item("a", ai_label=None)])
    with pytest.raises(ValueError, match="no ai_label"):
        queue.decide("a", "approve")


def test_unknown_action_is_an_error(queue: ReviewQueue) -> None:
    queue.enqueue([_item("a")])
    with pytest.raises(ValueError, match="Unknown action"):
        queue.decide("a", "explode")  # type: ignore[arg-type]


def test_deciding_an_unknown_item_is_an_error(queue: ReviewQueue) -> None:
    with pytest.raises(KeyError):
        queue.decide("missing", "approve")


# --------------------------------------------------------------------------- #
# Acceptance rate — the free model-quality metric
# --------------------------------------------------------------------------- #
def test_acceptance_rate_is_none_before_any_decision(queue: ReviewQueue) -> None:
    queue.enqueue([_item("a")])
    assert queue.acceptance_rate() is None


def test_acceptance_rate_counts_approvals_over_decisions(queue: ReviewQueue) -> None:
    queue.enqueue([_item(f"i{n}") for n in range(4)])
    queue.decide("i0", "approve")
    queue.decide("i1", "approve")
    queue.decide("i2", "approve")
    queue.decide("i3", "correct", label="time_blind")
    assert queue.acceptance_rate() == pytest.approx(0.75)


def test_rejections_are_excluded_from_the_acceptance_rate(queue: ReviewQueue) -> None:
    """A rejected sample says nothing about whether the label was right."""
    queue.enqueue([_item("a"), _item("b")])
    queue.decide("a", "approve")
    queue.decide("b", "reject")
    assert queue.acceptance_rate() == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Confirmed-label ledger
# --------------------------------------------------------------------------- #
def test_only_decided_items_reach_the_ledger(tmp_path, queue: ReviewQueue) -> None:
    queue.enqueue([_item("a"), _item("b"), _item("c")])
    queue.decide("a", "approve")
    queue.decide("b", "correct", label="time_blind")
    # "c" stays pending.
    path = tmp_path / "confirmed.jsonl"
    written = append_confirmed(
        [queue.get("a"), queue.get("b"), queue.get("c")],
        path,
        label_ids={"union_based": 1, "time_blind": 4},
    )
    assert written == 2

    records = read_confirmed(path)
    by_id = {r["id"]: r for r in records}
    assert by_id["a"]["label"] == "union_based"
    assert by_id["a"]["was_corrected"] is False
    assert by_id["a"]["label_id"] == 1
    assert by_id["b"]["label"] == "time_blind"
    assert by_id["b"]["was_corrected"] is True


def test_rejected_items_never_reach_the_ledger(tmp_path, queue: ReviewQueue) -> None:
    queue.enqueue([_item("a")])
    queue.decide("a", "reject")
    path = tmp_path / "confirmed.jsonl"
    assert append_confirmed([queue.get("a")], path) == 0
    assert read_confirmed(path) == []


def test_ledger_appends_rather_than_overwrites(tmp_path, queue: ReviewQueue) -> None:
    path = tmp_path / "confirmed.jsonl"
    queue.enqueue([_item("a"), _item("b")])
    queue.decide("a", "approve")
    append_confirmed([queue.get("a")], path)
    queue.decide("b", "approve")
    append_confirmed([queue.get("b")], path)
    assert len(read_confirmed(path)) == 2


def test_reading_a_missing_ledger_returns_empty(tmp_path) -> None:
    assert read_confirmed(tmp_path / "nope.jsonl") == []


# --------------------------------------------------------------------------- #
# Round isolation — what makes the demo reset safe
# --------------------------------------------------------------------------- #
def test_purging_a_round_leaves_other_rounds_intact(queue: ReviewQueue) -> None:
    queue.enqueue([_item("a", round_id="r1"), _item("b", round_id="r2")])
    assert queue.purge_round("r1") == 1
    remaining = queue.list()
    assert [i.id for i in remaining] == ["b"]


def test_dropping_a_round_from_the_ledger(tmp_path, queue: ReviewQueue) -> None:
    path = tmp_path / "confirmed.jsonl"
    queue.enqueue([_item("a", round_id="r1"), _item("b", round_id="r2")])
    queue.decide("a", "approve")
    queue.decide("b", "approve")
    append_confirmed([queue.get("a"), queue.get("b")], path)

    assert drop_round(path, "r1") == 1
    remaining = read_confirmed(path)
    assert [r["id"] for r in remaining] == ["b"]


def test_read_confirmed_filters_by_round(tmp_path, queue: ReviewQueue) -> None:
    path = tmp_path / "confirmed.jsonl"
    queue.enqueue([_item("a", round_id="r1"), _item("b", round_id="r2")])
    queue.decide("a", "approve")
    queue.decide("b", "approve")
    append_confirmed([queue.get("a"), queue.get("b")], path)
    assert [r["id"] for r in read_confirmed(path, round_id="r2")] == ["b"]


def test_queue_persists_across_reopen(tmp_path) -> None:
    path = tmp_path / "queue.db"
    first = ReviewQueue(path)
    first.enqueue([_item("a")])
    first.decide("a", "approve")

    reopened = ReviewQueue(path)
    item = reopened.get("a")
    assert item is not None and item.status == "approved"
