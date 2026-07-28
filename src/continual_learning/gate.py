"""Validation gate: decide whether a candidate model may replace the champion.

Implements section 7 of ``report/plan/mlops_contract.md``.

The gate's first job is to know **when not to compare**. A model trained without
class *X* has never been given the chance to learn *X*; scoring it against a
model that has seen *X*, on a benchmark containing *X*, measures the label space
rather than model quality. So when the two models were trained on data of
different **major** versions, comparison is *refused* and the candidate is
promoted directly — a deliberate decision recorded as such, not a silent skip.

Within one major the benchmark is frozen and identical, so a comparison is
meaningful and the criteria apply:

- F1-macro must not fall
- FPR (normal misclassified as attack) must not rise
- no known class may lose more than ``max_per_class_recall_drop`` recall
- any newly-introduced class must reach ``min_new_class_recall``
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from src.continual_learning.versioning import major_of
from src.utils import get_logger

logger = get_logger(__name__)

Verdict = Literal["promote", "reject", "direct_promote"]
Comparison = Literal["same_major", "cross_major_refused", "no_champion"]

NORMAL_LABEL = "normal"


@dataclass
class ModelEvaluation:
    """A model's scores on a golden set, plus the versions that produced them."""

    model_version: str
    data_version: str
    f1_macro: float
    fpr: float
    per_class_recall: dict[str, float] = field(default_factory=dict)
    n_rows: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the decision record."""
        return {
            "model_version": self.model_version,
            "data_version": self.data_version,
            "f1_macro": round(self.f1_macro, 6),
            "fpr": round(self.fpr, 6),
            "per_class_recall": {k: round(v, 6) for k, v in self.per_class_recall.items()},
            "n_rows": self.n_rows,
        }


@dataclass
class GateDecision:
    """The gate's verdict and the evidence behind it."""

    verdict: Verdict
    comparison: Comparison
    reason: str
    candidate: ModelEvaluation
    champion: ModelEvaluation | None = None
    criteria: dict[str, Any] = field(default_factory=dict)
    golden_version: str | None = None
    ts: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    @property
    def promoted(self) -> bool:
        """True when the candidate should become the new champion."""
        return self.verdict in ("promote", "direct_promote")

    def to_dict(self) -> dict[str, Any]:
        """Serialise to the ``decisions.jsonl`` shape."""
        return {
            "ts": self.ts,
            "candidate": self.candidate.model_version,
            "champion": self.champion.model_version if self.champion else None,
            "candidate_data": self.candidate.data_version,
            "champion_data": self.champion.data_version if self.champion else None,
            "comparison": self.comparison,
            "golden_version": self.golden_version,
            "metrics": {
                "candidate": self.candidate.to_dict(),
                "champion": self.champion.to_dict() if self.champion else None,
            },
            "criteria": self.criteria,
            "verdict": self.verdict,
            "reason": self.reason,
        }


def compute_evaluation(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    *,
    model_version: str,
    data_version: str,
    normal_label: str = NORMAL_LABEL,
) -> ModelEvaluation:
    """Build a :class:`ModelEvaluation` from predictions on a golden set.

    FPR is defined operationally as the share of *normal* queries predicted as
    any attack class — the false-alarm rate a proxy operator actually feels.

    Args:
        y_true: Ground-truth label names.
        y_pred: Predicted label names.
        model_version: Model identifier for the record.
        data_version: Data version the model trained on.
        normal_label: Name of the benign class.

    Returns:
        The evaluation, with per-class recall for every class present in
        ``y_true``.

    Raises:
        ValueError: If the sequences differ in length or are empty.
    """
    if len(y_true) != len(y_pred):
        raise ValueError(f"y_true/y_pred length mismatch: {len(y_true)} vs {len(y_pred)}")
    if not y_true:
        raise ValueError("Cannot evaluate on an empty golden set")

    labels = sorted(set(y_true) | set(y_pred))
    per_class_recall: dict[str, float] = {}
    f1s: list[float] = []

    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        support = tp + fn

        recall = tp / support if support else 0.0
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

        # Only classes actually present in the truth contribute to macro-F1 and
        # to per-class recall; a class the model merely hallucinated has no
        # support to average over.
        if support:
            per_class_recall[label] = recall
            f1s.append(f1)

    normal_total = sum(1 for t in y_true if t == normal_label)
    normal_flagged = sum(
        1 for t, p in zip(y_true, y_pred) if t == normal_label and p != normal_label
    )
    fpr = normal_flagged / normal_total if normal_total else 0.0

    return ModelEvaluation(
        model_version=model_version,
        data_version=data_version,
        f1_macro=sum(f1s) / len(f1s) if f1s else 0.0,
        fpr=fpr,
        per_class_recall=per_class_recall,
        n_rows=len(y_true),
    )


def evaluate_gate(
    candidate: ModelEvaluation,
    champion: ModelEvaluation | None,
    *,
    max_per_class_recall_drop: float = 0.02,
    min_new_class_recall: float = 0.80,
    min_f1: float | None = None,
    max_fpr: float | None = None,
    golden_version: str | None = None,
) -> GateDecision:
    """Apply the promotion rules and return a decision.

    Args:
        candidate: The challenger's evaluation.
        champion: The incumbent's evaluation, or ``None`` if nothing is deployed.
        max_per_class_recall_drop: Largest tolerated recall loss on a known class.
        min_new_class_recall: Recall a newly-introduced class must reach.
        min_f1: Absolute F1 floor; ``None`` means "at least the champion's".
        max_fpr: Absolute FPR ceiling; ``None`` means "at most the champion's".
        golden_version: Benchmark version, recorded on the decision.

    Returns:
        A :class:`GateDecision`.
    """
    if champion is None:
        return GateDecision(
            verdict="direct_promote",
            comparison="no_champion",
            reason="No incumbent model to compare against.",
            candidate=candidate,
            golden_version=golden_version,
        )

    candidate_major = major_of(candidate.data_version)
    champion_major = major_of(champion.data_version)
    if candidate_major != champion_major:
        new_classes = sorted(
            set(candidate.per_class_recall) - set(champion.per_class_recall)
        )
        return GateDecision(
            verdict="direct_promote",
            comparison="cross_major_refused",
            reason=(
                f"Data major changed {champion.data_version} -> {candidate.data_version}"
                + (f" (new class: {', '.join(new_classes)})" if new_classes else "")
                + ". The label spaces differ, so a champion/challenger comparison would "
                "measure the benchmark rather than the models; promoting directly."
            ),
            candidate=candidate,
            champion=champion,
            criteria={"comparison_skipped": True, "new_classes": new_classes},
            golden_version=golden_version,
        )

    # --- same major: the benchmark is frozen and identical, so compare. ---
    f1_floor = champion.f1_macro if min_f1 is None else min_f1
    fpr_ceiling = champion.fpr if max_fpr is None else max_fpr

    f1_ok = candidate.f1_macro >= f1_floor
    fpr_ok = candidate.fpr <= fpr_ceiling

    regressions: dict[str, float] = {}
    for label, champion_recall in champion.per_class_recall.items():
        candidate_recall = candidate.per_class_recall.get(label, 0.0)
        drop = champion_recall - candidate_recall
        if drop > max_per_class_recall_drop:
            regressions[label] = round(drop, 6)
    per_class_ok = not regressions

    new_classes = sorted(set(candidate.per_class_recall) - set(champion.per_class_recall))
    weak_new = {
        label: round(candidate.per_class_recall[label], 6)
        for label in new_classes
        if candidate.per_class_recall[label] < min_new_class_recall
    }
    new_class_ok = not weak_new

    criteria = {
        "f1_macro_ok": f1_ok,
        "f1_macro": {"candidate": round(candidate.f1_macro, 6), "floor": round(f1_floor, 6)},
        "fpr_ok": fpr_ok,
        "fpr": {"candidate": round(candidate.fpr, 6), "ceiling": round(fpr_ceiling, 6)},
        "per_class_ok": per_class_ok,
        "failing_classes": sorted(regressions),
        "regressions": regressions,
        "new_class_ok": new_class_ok,
        "weak_new_classes": weak_new,
    }

    if f1_ok and fpr_ok and per_class_ok and new_class_ok:
        return GateDecision(
            verdict="promote",
            comparison="same_major",
            reason=(
                f"Candidate meets every criterion on golden@{golden_version or champion_major} "
                f"(F1 {candidate.f1_macro:.4f} >= {f1_floor:.4f}, "
                f"FPR {candidate.fpr:.4f} <= {fpr_ceiling:.4f}, no per-class regression)."
            ),
            candidate=candidate,
            champion=champion,
            criteria=criteria,
            golden_version=golden_version,
        )

    failures = []
    if not f1_ok:
        failures.append(f"F1-macro {candidate.f1_macro:.4f} < {f1_floor:.4f}")
    if not fpr_ok:
        failures.append(f"FPR {candidate.fpr:.4f} > {fpr_ceiling:.4f}")
    if not per_class_ok:
        failures.append(
            "recall regression on " + ", ".join(f"{k} (-{v:.4f})" for k, v in regressions.items())
        )
    if not new_class_ok:
        failures.append(
            "new class below floor: "
            + ", ".join(f"{k}={v:.4f} < {min_new_class_recall}" for k, v in weak_new.items())
        )

    return GateDecision(
        verdict="reject",
        comparison="same_major",
        reason="; ".join(failures),
        candidate=candidate,
        champion=champion,
        criteria=criteria,
        golden_version=golden_version,
    )


def append_decision(decision: GateDecision, path: str | Path) -> None:
    """Append a decision to the append-only decision log."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(decision.to_dict()) + "\n")
    logger.info("Recorded gate decision: %s (%s)", decision.verdict, decision.comparison)


def read_decisions(path: str | Path) -> list[dict[str, Any]]:
    """Read the decision log, skipping malformed lines."""
    path = Path(path)
    if not path.exists():
        return []
    decisions: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                decisions.append(json.loads(line))
            except ValueError:  # pragma: no cover - a truncated write
                logger.warning("Skipping malformed decision line in %s", path)
    return decisions
