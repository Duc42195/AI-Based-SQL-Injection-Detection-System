# -*- coding: utf-8 -*-
"""Figure: Branch-2 normal vs. anomaly score distribution across the full
cleanup + feature-engineering journey (15-16/08).

Three stages, same eval protocol throughout (fit OCSVM, threshold = P95 of
benign-test scores => matched FPR=5%, so DR is directly comparable across
stages — see the note in train/train_branch2.py::_eval_detector about why a
fixed methodology matters here):

  1. "Before cleanup"        - dirty data,  4 features (length, special_char_ratio,
                                sql_keyword_count, entropy), nu=0.005/gamma=0.01
  2. "After cleanup"         - clean data (SSRF removed, short-strings
                                rebalanced), SAME 4 features/hyperparams as (1)
                                -> regressed (DR 41.87%->31.19%): removing the
                                short-string cluster left `length` unable to
                                separate complex-benign from complex-attack.
  3. "Final (this session)"  - clean data, 3 features (sql_keyword_count,
                                entropy, bigram_entropy — length and
                                special_char_ratio dropped), retuned
                                nu=0.001/gamma=0.01, scale_features=True
                                -> recovers and exceeds stage 1.

Stages 1-2 reproduce report/plan/plan_next_branch2_cleanup.md's own numbers
(DR 41.87%/31.19%) as a sanity check that this script's methodology matches
what was reported there. Stage 3 uses the CURRENT configs/config.yaml
(branch2_anomaly), i.e. whatever is checked in right now.

Usage:  uv run python train/plot_branch2_final_dist.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.chdir(Path(__file__).resolve().parents[1])

from src.models.branch2_anomaly import AnomalyDetector  # noqa: E402
from src.utils import get_logger, load_config  # noqa: E402

logger = get_logger(__name__)

IEEE_BLUE = "#0072B2"
IEEE_ORANGE = "#E69F00"
IEEE_RED = "#D55E00"
IEEE_GREEN = "#009E73"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "axes.linewidth": 0.8,
    "legend.frameon": True,
    "legend.edgecolor": "0.7",
    "legend.fancybox": False,
    "axes.grid": True,
    "grid.color": "0.85",
    "grid.linewidth": 0.6,
    "figure.dpi": 120,
})

OLD_4_FEATURES = ["length", "special_char_ratio", "sql_keyword_count", "entropy"]


def _fit_score(params: dict, train: pd.DataFrame, test: pd.DataFrame, anom: pd.DataFrame, feats: list[str]):
    det = AnomalyDetector(**{**params, "feature_names": feats})
    det.fit(train[feats].to_numpy(np.float64))
    s_test = det.score(test[feats].to_numpy(np.float64))
    s_anom = det.score(anom[feats].to_numpy(np.float64))
    return s_test, s_anom


def _p95_metrics(s_test: np.ndarray, s_anom: np.ndarray) -> dict:
    thr = float(np.percentile(s_test, 95))
    fpr = float((s_test > thr).mean())
    dr = float((s_anom > thr).mean())
    ks = float(stats.ks_2samp(s_test, s_anom).statistic)
    return {"threshold": thr, "fpr": fpr, "dr": dr, "ks": ks}


def main() -> None:
    cfg = load_config()
    processed = Path("data/processed")

    dirty = pd.read_csv(processed / "branch2_data.csv")
    dirty_train = dirty[dirty.split == "train"].reset_index(drop=True)
    dirty_test = dirty[dirty.split == "test"].reset_index(drop=True)
    dirty_anom = pd.read_csv(processed / "branch2_anomalous_eval.csv")

    clean = pd.read_csv(processed / "branch2_data_clean.csv")
    clean_train = clean[clean.split == "train"].reset_index(drop=True)
    clean_test = clean[clean.split == "test"].reset_index(drop=True)
    clean_anom = pd.read_csv(processed / "branch2_anomalous_eval_clean.csv")

    old_params = dict(algorithm="one_class_svm", contamination=0.005, gamma=0.01,
                       scale_features=False, log_transform_features=["length"])
    b2 = cfg.get("branch2_anomaly")
    final_features = list(b2["features"])
    final_params = dict(
        algorithm=b2["algorithm"],
        contamination=b2["ocsvm_nu"] if b2["algorithm"] == "one_class_svm" else b2["contamination"],
        gamma=b2["ocsvm_gamma"],
        scale_features=b2["scale_features"],
        log_transform_features=list(b2["log_transform_features"]),
    )

    stages = {}
    s_test, s_anom = _fit_score(old_params, dirty_train, dirty_test, dirty_anom, OLD_4_FEATURES)
    stages["Before cleanup\n(dirty, 4 features)"] = (s_test, s_anom, _p95_metrics(s_test, s_anom))

    s_test, s_anom = _fit_score(old_params, clean_train, clean_test, clean_anom, OLD_4_FEATURES)
    stages["After cleanup\n(clean, 4 features)"] = (s_test, s_anom, _p95_metrics(s_test, s_anom))

    s_test, s_anom = _fit_score(final_params, clean_train, clean_test, clean_anom, final_features)
    stages[f"Final\n(clean, {len(final_features)} features + bigram_entropy)"] = (
        s_test, s_anom, _p95_metrics(s_test, s_anom)
    )

    for name, (_, _, m) in stages.items():
        logger.info("%s: FPR=%.4f DR=%.4f KS=%.4f", name.replace("\n", " "), m["fpr"], m["dr"], m["ks"])

    # ---- Fig — 3-panel score distributions ----
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4), sharey=False)
    for ax, (name, (s_test, s_anom, m)) in zip(axes, stages.items()):
        lo, hi = min(s_test.min(), s_anom.min()), max(s_test.max(), s_anom.max())
        grid = np.linspace(lo, hi, 300)

        def kde(x):
            if len(x) > 1 and x.std() > 0:
                return stats.gaussian_kde(x)(grid)
            return np.zeros_like(grid)

        ax.fill_between(grid, kde(s_test), color=IEEE_BLUE, alpha=0.30, label="Normal (test)")
        ax.fill_between(grid, kde(s_anom), color=IEEE_ORANGE, alpha=0.45, label="Anomaly")
        ax.plot(grid, kde(s_test), color=IEEE_BLUE, lw=1.3)
        ax.plot(grid, kde(s_anom), color=IEEE_ORANGE, lw=1.3)
        ax.axvline(m["threshold"], color=IEEE_RED, ls="--", lw=1.2, label="P95 normal (FPR=5%)")
        ax.set_title(f"{name}\nDR={m['dr']:.1%}  KS={m['ks']:.3f}", fontsize=9.5)
        ax.set_xlabel("Anomaly score")
    axes[0].set_ylabel("Density")
    axes[0].legend(loc="upper right", fontsize=7.5)
    fig.suptitle("Fig. Branch 2 — normal vs. anomaly score distribution "
                 "(cleanup + feature-engineering journey, matched FPR=5%)", y=1.04, fontsize=10.5)
    fig.tight_layout()

    out_dir = Path("report/metrics/zeroday_experiment")
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_path = out_dir / "branch2_dist_final.png"
    fig.savefig(fig_path, bbox_inches="tight")
    logger.info("Saved %s", fig_path)

    # ---- Fig — DR-at-matched-FPR bar chart across stages ----
    fig2, ax2 = plt.subplots(figsize=(5.5, 3.6))
    names = list(stages.keys())
    drs = [stages[n][2]["dr"] for n in names]
    colors = [IEEE_RED, IEEE_ORANGE, IEEE_GREEN]
    bars = ax2.bar([n.replace("\n", " ") for n in names], drs, color=colors, edgecolor="black", linewidth=0.6)
    for bar, v in zip(bars, drs):
        ax2.text(bar.get_x() + bar.get_width() / 2, v + 0.01, f"{v:.1%}", ha="center", va="bottom", fontsize=9)
    ax2.set_ylabel("Detection rate @ matched FPR=5%")
    ax2.set_ylim(0, max(drs) * 1.25)
    ax2.set_title("Fig. Branch 2 — DR at matched FPR=5% across the journey")
    plt.setp(ax2.get_xticklabels(), rotation=12, ha="right", fontsize=8)
    fig2.tight_layout()
    fig2_path = out_dir / "branch2_dr_journey.png"
    fig2.savefig(fig2_path, bbox_inches="tight")
    logger.info("Saved %s", fig2_path)


if __name__ == "__main__":
    main()
