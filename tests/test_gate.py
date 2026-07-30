"""Tests for the promotion gate — including when it must refuse to compare."""

from __future__ import annotations

import pytest

from src.continual_learning.gate import (
    ModelEvaluation,
    append_decision,
    compute_evaluation,
    evaluate_gate,
    read_decisions,
)

KNOWN = ["normal", "union_based", "error_based", "boolean_blind", "time_blind"]


def _eval(
    version: str = "v1",
    data: str = "2.0",
    f1: float = 0.98,
    fpr: float = 0.01,
    recalls: dict[str, float] | None = None,
) -> ModelEvaluation:
    return ModelEvaluation(
        model_version=version,
        data_version=data,
        f1_macro=f1,
        fpr=fpr,
        per_class_recall=recalls if recalls is not None else {k: 0.98 for k in KNOWN},
        n_rows=1000,
    )


# --------------------------------------------------------------------------- #
# compute_evaluation
# --------------------------------------------------------------------------- #
def test_perfect_predictions_score_one_with_no_false_alarms() -> None:
    truth = ["normal", "union_based", "normal", "time_blind"]
    result = compute_evaluation(truth, list(truth), model_version="v1", data_version="1.0")
    assert result.f1_macro == pytest.approx(1.0)
    assert result.fpr == pytest.approx(0.0)
    assert result.per_class_recall["normal"] == pytest.approx(1.0)


def test_fpr_counts_normal_flagged_as_any_attack() -> None:
    truth = ["normal", "normal", "normal", "normal"]
    pred = ["normal", "union_based", "time_blind", "normal"]
    result = compute_evaluation(truth, pred, model_version="v1", data_version="1.0")
    assert result.fpr == pytest.approx(0.5)


def test_recall_is_reported_per_class() -> None:
    truth = ["union_based"] * 10
    pred = ["union_based"] * 7 + ["normal"] * 3
    result = compute_evaluation(truth, pred, model_version="v1", data_version="1.0")
    assert result.per_class_recall["union_based"] == pytest.approx(0.7)


def test_hallucinated_class_does_not_enter_per_class_recall() -> None:
    """A class with no support in the truth has no recall to report."""
    truth = ["normal"] * 5
    pred = ["normal"] * 4 + ["stacked"]
    result = compute_evaluation(truth, pred, model_version="v1", data_version="1.0")
    assert "stacked" not in result.per_class_recall


def test_mismatched_lengths_are_rejected() -> None:
    with pytest.raises(ValueError, match="length mismatch"):
        compute_evaluation(["normal"], [], model_version="v1", data_version="1.0")


def test_empty_golden_set_is_rejected() -> None:
    with pytest.raises(ValueError, match="empty golden set"):
        compute_evaluation([], [], model_version="v1", data_version="1.0")


# --------------------------------------------------------------------------- #
# The major rule — the gate's most important behaviour
# --------------------------------------------------------------------------- #
def test_cross_major_comparison_is_refused_and_promotes_directly() -> None:
    champion = _eval("branch1_v1", data="1.0")
    candidate = _eval(
        "branch1_v2",
        data="2.0",
        recalls={**{k: 0.98 for k in KNOWN}, "stacked": 0.99},
    )
    decision = evaluate_gate(candidate, champion)
    assert decision.verdict == "direct_promote"
    assert decision.comparison == "cross_major_refused"
    assert decision.promoted is True
    assert "stacked" in decision.criteria["new_classes"]


def test_cross_major_refusal_holds_even_if_candidate_looks_worse() -> None:
    """The point of refusing is that the numbers aren't comparable at all."""
    champion = _eval("branch1_v1", data="1.0", f1=0.99, fpr=0.001)
    candidate = _eval("branch1_v2", data="2.0", f1=0.70, fpr=0.20)
    decision = evaluate_gate(candidate, champion)
    assert decision.verdict == "direct_promote"
    assert decision.comparison == "cross_major_refused"


def test_no_champion_promotes_directly() -> None:
    decision = evaluate_gate(_eval(), None)
    assert decision.verdict == "direct_promote"
    assert decision.comparison == "no_champion"


# --------------------------------------------------------------------------- #
# Same-major criteria
# --------------------------------------------------------------------------- #
def test_strictly_better_candidate_is_promoted() -> None:
    champion = _eval("v1", data="2.0", f1=0.95, fpr=0.02)
    candidate = _eval("v2", data="2.1", f1=0.97, fpr=0.01)
    decision = evaluate_gate(candidate, champion)
    assert decision.verdict == "promote"
    assert decision.comparison == "same_major"


def test_identical_candidate_is_promoted_at_the_boundary() -> None:
    """'>= champion' must accept an exact tie, not reject it."""
    champion = _eval("v1", data="2.0")
    candidate = _eval("v2", data="2.1")
    assert evaluate_gate(candidate, champion).verdict == "promote"


def test_f1_regression_is_rejected() -> None:
    champion = _eval("v1", data="2.0", f1=0.98)
    candidate = _eval("v2", data="2.1", f1=0.90)
    decision = evaluate_gate(candidate, champion)
    assert decision.verdict == "reject"
    assert decision.criteria["f1_macro_ok"] is False


def test_fpr_increase_is_rejected() -> None:
    champion = _eval("v1", data="2.0", fpr=0.01)
    candidate = _eval("v2", data="2.1", fpr=0.05)
    decision = evaluate_gate(candidate, champion)
    assert decision.verdict == "reject"
    assert decision.criteria["fpr_ok"] is False


def test_catastrophic_forgetting_is_rejected_despite_a_better_average() -> None:
    """The starved-rehearsal case: macro-F1 hides a collapsed class."""
    champion = _eval("v1", data="2.0", f1=0.95, recalls={k: 0.95 for k in KNOWN})
    candidate = _eval(
        "v2",
        data="2.1",
        f1=0.96,  # average looks fine...
        recalls={**{k: 0.99 for k in KNOWN}, "time_blind": 0.40},  # ...but this collapsed
    )
    decision = evaluate_gate(candidate, champion)
    assert decision.verdict == "reject"
    assert decision.criteria["per_class_ok"] is False
    assert "time_blind" in decision.criteria["failing_classes"]


def test_small_recall_dip_within_tolerance_is_accepted() -> None:
    champion = _eval("v1", data="2.0", recalls={k: 0.98 for k in KNOWN})
    candidate = _eval(
        "v2", data="2.1", recalls={**{k: 0.98 for k in KNOWN}, "time_blind": 0.97}
    )
    decision = evaluate_gate(candidate, champion, max_per_class_recall_drop=0.02)
    assert decision.verdict == "promote"


def test_weak_new_class_within_the_same_major_is_rejected() -> None:
    champion = _eval("v1", data="2.0", recalls={k: 0.98 for k in KNOWN})
    candidate = _eval(
        "v2", data="2.1", recalls={**{k: 0.98 for k in KNOWN}, "obfuscated": 0.30}
    )
    decision = evaluate_gate(candidate, champion, min_new_class_recall=0.80)
    assert decision.verdict == "reject"
    assert decision.criteria["new_class_ok"] is False


def test_absolute_thresholds_override_the_champion_baseline() -> None:
    champion = _eval("v1", data="2.0", f1=0.50, fpr=0.30)
    candidate = _eval("v2", data="2.1", f1=0.60, fpr=0.25)
    # Better than the (poor) champion, but still below an absolute floor.
    decision = evaluate_gate(candidate, champion, min_f1=0.90, max_fpr=0.05)
    assert decision.verdict == "reject"


# --------------------------------------------------------------------------- #
# Decision log
# --------------------------------------------------------------------------- #
def test_decisions_roundtrip_through_the_log(tmp_path) -> None:
    path = tmp_path / "decisions.jsonl"
    append_decision(evaluate_gate(_eval("v2", data="2.1"), _eval("v1", data="2.0")), path)
    append_decision(evaluate_gate(_eval("v3", data="3.0"), _eval("v2", data="2.1")), path)

    records = read_decisions(path)
    assert len(records) == 2
    assert records[0]["verdict"] == "promote"
    assert records[1]["comparison"] == "cross_major_refused"
    assert records[1]["metrics"]["candidate"]["model_version"] == "v3"


def test_reading_a_missing_log_returns_empty(tmp_path) -> None:
    assert read_decisions(tmp_path / "nope.jsonl") == []
