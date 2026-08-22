"""Figures for the real-class-holdout continual-learning scenario (paper-ready).

Reads the artifacts written by ``train/run_cl_scenario_experiment.py`` and
renders them at the same style as ``train/generate_metrics.py``.

Run:  uv run python train/plot_cl_scenario.py
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


def _plot_pour(ax, drift: dict, *, threshold: float, trigger_window: int | None, title: str) -> None:
    windows = drift["windows"]
    # A trailing fragment far short of a full window (e.g. 26 of 1,000 rows)
    # produces unstable, meaningless PSI via small-sample bin noise; drop it
    # from the plot rather than let it dominate the y-axis.
    full_window = max(w["n"] for w in windows)
    windows = [w for w in windows if w["n"] >= full_window * 0.5]
    indices = [w["index"] for w in windows]
    reference_end = max((w["index"] for w in windows if w.get("is_reference")), default=-1)

    for signal, label in SIGNAL_LABELS.items():
        ax.plot(indices, [w["psi"][signal] for w in windows], linewidth=1.2, label=label)
    ax.axhline(threshold, color="crimson", linestyle="--", linewidth=1.1)
    ax.set_ylim(0, max(threshold * 1.4, max(w["psi"][s] for w in windows for s in SIGNAL_LABELS) * 1.1))
    top = ax.get_ylim()[1]

    if reference_end >= 0:
        ax.axvspan(-0.5, reference_end, color="0.9", zorder=0)
        ax.text(reference_end / 2, top * 0.92, "reference", ha="center", fontsize=8, color="0.35")
    if trigger_window is not None:
        ax.axvline(trigger_window, color="0.35", linestyle=":", linewidth=1.1)
        ax.annotate(
            "retrain triggers",
            xy=(trigger_window, top * 0.80),
            xytext=(trigger_window + 0.15, top * 0.80),
            fontsize=8,
            color="0.35",
        )
    ax.set_title(title, fontsize=10)
    ax.set_ylabel("PSI")


def plot_drift(drift_q3: dict, drift_q4: dict, threshold: float, major_trigger_window: int, out: Path) -> None:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.2, 6.4), sharex=False)
    _plot_pour(
        ax1, drift_q3, threshold=threshold, trigger_window=major_trigger_window,
        title="Scenario 1 (Q3): held-out class enters, replayed against M0",
    )
    _plot_pour(
        ax2, drift_q4, threshold=threshold, trigger_window=None,
        title="Scenario 2 (Q4): known-class volume only, replayed against M1",
    )
    ax2.set_xlabel("Stream window (1,000 queries each)")
    ax1.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), frameon=False, ncol=2)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(out)
    plt.close(fig)
    logger.info("Wrote %s", out)


def plot_ablation(control: dict, held_out: str, out: Path) -> None:
    candidate_recall = control["candidate_recall_on_held_out"]
    control_recall = control["control_recall_on_held_out"]

    fig, ax = plt.subplots(figsize=(5.4, 3.6))
    bars = ax.bar(
        [f"Control\n(+{control['extra_rows']} rows,\nno {held_out})", f"Candidate\n(+{control['extra_rows']} rows,\nwith {held_out})"],
        [control_recall, candidate_recall],
        color=["#C44E52", "#55A868"],
        width=0.55,
    )
    for bar, value in zip(bars, [control_recall, candidate_recall]):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.02, f"{value:.4f}", ha="center", fontsize=10)
    ax.set_ylabel(f"Recall on {held_out}")
    ax.set_ylim(0, 1.05)
    ax.set_title(f"Ablation: identical +{control['extra_rows']} rows either way")
    fig.savefig(out)
    plt.close(fig)
    logger.info("Wrote %s", out)


def main() -> None:
    cfg = load_config()
    artifacts = Path(cfg.get_path("cl_scenario.artifacts_dir", "report/metrics/cl_scenario"))
    threshold = float(cfg.get_path("monitoring.psi_alert_threshold", 0.2))
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    with (artifacts / "experiment_results.json").open(encoding="utf-8") as handle:
        results = json.load(handle)

    window_size = int(cfg.get_path("cl_scenario.stream.window_size", 1000))
    major_trigger_window = results["act1_major_bump"]["trigger_position"] // window_size

    plot_drift(
        results["drift_q3"], results["drift_q4"], threshold, major_trigger_window,
        FIGURES_DIR / "cl_scenario_drift.png",
    )
    plot_ablation(
        results["act1_ablation_control"], results["pre_bump"]["held_out_class"],
        FIGURES_DIR / "cl_scenario_ablation.png",
    )
    logger.info("All CL-scenario figures written to %s", FIGURES_DIR)


if __name__ == "__main__":
    main()
