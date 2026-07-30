"""Figures for the continual-learning experiment (paper-ready).

Reads the artifacts written by ``train/run_continual_learning_experiment.py``
and renders them at the same style as ``train/generate_metrics.py``.

Run:  uv run python train/plot_continual_learning.py
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams

from src.utils import get_logger, load_config

warnings.filterwarnings("ignore")
logger = get_logger(__name__)

rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["DejaVu Serif", "Times New Roman"],
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "axes.grid": False,
    }
)

PROJECT = Path(__file__).resolve().parent.parent
FIGURES_DIR = PROJECT / "report" / "metrics" / "figures"

SIGNAL_LABELS = {
    "global": "Structural features (all traffic)",
    "attack_subpop": "Structural features (flagged only)",
    "prediction": "Predicted-class distribution",
    "confidence": "Confidence (all traffic)",
    "confidence_flagged": "Confidence (flagged only)",
}


def plot_drift(drift: dict, out: Path) -> None:
    """PSI per window for every signal, with the alert threshold and phases."""
    windows = drift["windows"]
    threshold = drift["threshold"]
    indices = [w["index"] for w in windows]
    phase_b_start = next((w["index"] for w in windows if w["phase"] == "B"), None)
    reference_end = max(
        (w["index"] for w in windows if w.get("is_reference")), default=-1
    )

    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    for signal, label in SIGNAL_LABELS.items():
        ax.plot(indices, [w["psi"][signal] for w in windows], linewidth=1.2, label=label)

    ax.axhline(
        threshold,
        color="crimson",
        linestyle="--",
        linewidth=1.1,
        label=f"Alert threshold (PSI = {threshold})",
    )
    # Headroom above the threshold line so the phase annotations have somewhere
    # to sit without landing on the series.
    ax.set_ylim(0, threshold * 1.25)
    top = ax.get_ylim()[1]

    if reference_end >= 0:
        ax.axvspan(0, reference_end, color="0.9", zorder=0)
        ax.text(
            reference_end / 2, top * 0.90, "reference", ha="center", fontsize=8, color="0.35"
        )
    if phase_b_start is not None:
        ax.axvline(phase_b_start, color="0.35", linestyle=":", linewidth=1.1)
        ax.annotate(
            "new class enters",
            xy=(phase_b_start, top * 0.83),
            xytext=(phase_b_start + 3, top * 0.83),
            fontsize=8,
            color="0.35",
        )

    ax.set_xlabel("Stream window (1,000 queries each)")
    ax.set_ylabel("PSI")
    ax.set_title("No drift signal breaches the alert threshold at a 0.9 % new-class rate")
    # Legend below the axes: the series occupy the lower half, and the upper
    # half is needed for the threshold line and annotations.
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.16),
        frameon=False,
        ncol=2,
    )
    fig.savefig(out)
    plt.close(fig)
    logger.info("Wrote %s", out)


def plot_per_class_recall(results: dict, out: Path) -> None:
    """Champion vs promoted candidate recall, per class."""
    champion = results["champion"]["per_class_recall"]
    promoted = results["acts"]["act2_minor"]["balanced"]["candidate"]["per_class_recall"]
    classes = sorted(set(champion) | set(promoted))
    positions = range(len(classes))
    width = 0.38

    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    ax.bar(
        [p - width / 2 for p in positions],
        [champion.get(c, 0.0) for c in classes],
        width,
        label="Champion (data 1.0)",
        color="#4C72B0",
    )
    ax.bar(
        [p + width / 2 for p in positions],
        [promoted.get(c, 0.0) for c in classes],
        width,
        label="Promoted candidate (data 2.1)",
        color="#55A868",
    )
    ax.set_xticks(list(positions))
    ax.set_xticklabels(classes, rotation=20, ha="right")
    ax.set_ylabel("Recall")
    ax.set_ylim(0, 1.05)
    ax.set_title("Per-class recall on the frozen golden set")
    ax.legend(frameon=False)
    fig.savefig(out)
    plt.close(fig)
    logger.info("Wrote %s", out)


def plot_control_ablation(results: dict, out: Path) -> None:
    """The ablation: was the gain the new class, or just more data?"""
    control = results["controls"]["volume_control"]
    candidate_recall = results["acts"]["act1_major"]["new_class_recall"] or 0.0
    control_recall = control["new_class_recall"] or 0.0

    fig, ax = plt.subplots(figsize=(5.4, 3.6))
    bars = ax.bar(
        ["Control\n(+same rows,\nno new class)", "Candidate\n(+same rows,\nwith new class)"],
        [control_recall, candidate_recall],
        color=["#C44E52", "#55A868"],
        width=0.55,
    )
    for bar, value in zip(bars, [control_recall, candidate_recall]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.02,
            f"{value:.3f}",
            ha="center",
            fontsize=10,
        )
    ax.set_ylabel("Recall on the new class")
    ax.set_ylim(0, 1.05)
    ax.set_title(f"Ablation: identical +{control['extra_rows']} rows either way")
    fig.savefig(out)
    plt.close(fig)
    logger.info("Wrote %s", out)


def plot_gate_outcomes(results: dict, out: Path) -> None:
    """F1 on the golden set for each candidate, annotated with the verdict."""
    act2 = results["acts"]["act2_minor"]
    entries = [
        ("Champion\n(data 2.0)", results["acts"]["act1_major"]["candidate"]["f1_macro"], "incumbent"),
        ("Naive pool\n(raw confirmed)", act2["naive"]["candidate"]["f1_macro"], act2["naive"]["decision"]["verdict"]),
        ("Balanced pool", act2["balanced"]["candidate"]["f1_macro"], act2["balanced"]["decision"]["verdict"]),
        (
            "Starved rehearsal",
            results["controls"]["starved_rehearsal"]["f1_macro"],
            results["controls"]["starved_rehearsal"]["decision"]["verdict"],
        ),
    ]
    colors = {
        "incumbent": "#4C72B0",
        "promote": "#55A868",
        "reject": "#C44E52",
        "direct_promote": "#55A868",
    }

    fig, ax = plt.subplots(figsize=(7.0, 3.8))
    bars = ax.bar(
        [e[0] for e in entries],
        [e[1] for e in entries],
        color=[colors.get(e[2], "0.6") for e in entries],
        width=0.6,
    )
    for bar, (_, value, verdict) in zip(bars, entries):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.008,
            f"{value:.4f}\n{verdict.upper()}",
            ha="center",
            fontsize=8.5,
        )
    ax.set_ylabel("F1-macro on golden@2")
    ax.set_ylim(0.75, 1.02)
    ax.set_title("The gate accepts one candidate and rejects two")
    fig.savefig(out)
    plt.close(fig)
    logger.info("Wrote %s", out)


def main() -> None:
    """Render every figure from the experiment artifacts."""
    cfg = load_config()
    artifacts = Path(cfg.get_path("mlops.artifacts_dir", "report/metrics/continual_learning"))
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    with (artifacts / "experiment_results.json").open(encoding="utf-8") as handle:
        results = json.load(handle)
    with (artifacts / "drift.json").open(encoding="utf-8") as handle:
        drift = json.load(handle)

    plot_drift(drift, FIGURES_DIR / "cl_drift_windows.png")
    plot_per_class_recall(results, FIGURES_DIR / "cl_per_class_recall.png")
    plot_control_ablation(results, FIGURES_DIR / "cl_control_ablation.png")
    plot_gate_outcomes(results, FIGURES_DIR / "cl_gate_outcomes.png")
    logger.info("All continual-learning figures written to %s", FIGURES_DIR)


if __name__ == "__main__":
    main()
