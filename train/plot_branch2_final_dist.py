# -*- coding: utf-8 -*-
"""Figure: Branch-2 normal vs. anomaly score distribution across the
bug-fix journey (16-17/08).

REWRITTEN 17/08: the previous version of this figure ("Before cleanup" /
"After cleanup" / "Final") compared SSRF-cleanup stages, all three computed
on the SAME accidentally-capped benign pool (see train/build_branch2_data.py
docstring — that pool was missing the d3_csic2010 source entirely, which is
100% of the anomalous eval set, a domain-shift confound). That comparison is
now superseded. This version tells the actually-current story:

  1. "Bug (missing D3)"       - the pool build_branch2_data.py produced before
                                the 16/08 fix: branch1_train.csv filtered to
                                label==0 (Branch 1's per-class-undersampled
                                "normal" rows, d1_sqliv3+d7_srbh2020 only),
                                cleaned the same way (SSRF removed,
                                short-strings rebalanced), scored with the
                                bigram_entropy feature set that was live on
                                `main` (nu=0.001/gamma=0.01/scaled).
                                Reproduced ON DEMAND here (not read from a
                                CSV — the original buggy branch2_data.csv was
                                gitignored and got overwritten when the data
                                was rebuilt correctly) since it's fully
                                deterministic from branch1_train.csv.
  2. "Fixed pool, old feature" - the CORRECTED pool (branch2_normal.csv, all
                                of D1+D3+D7, no cap) with the SAME old
                                bigram_entropy feature set/hyperparams as (1)
                                -> exposes the confound: DR collapses because
                                bigram_entropy was largely measuring "which
                                raw dataset is this" rather than "is this an
                                attack".
  3. "Fixed pool, new feature" - CORRECTED pool with the new feature set
                                (special_char_ratio + entropy +
                                quote_imbalance, retuned nu/gamma) — the
                                honest, current result.

Same eval protocol throughout (fit OCSVM, threshold = P95 of benign-test
scores => matched FPR=5%, so DR is directly comparable across panels — see
the note in train/train_branch2.py::_eval_detector about why a fixed
methodology matters here).

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
from src.preprocessing.statistical_features import extract_statistical_features  # noqa: E402
from src.utils import get_logger, load_config  # noqa: E402
from src.utils.ssrf import is_leaky_row  # noqa: E402
from train.clean_branch2_data import SHORT_LEN, _rebalance_short  # noqa: E402

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

OLD_FEATURES = ["sql_keyword_count", "entropy", "bigram_entropy"]
OLD_PARAMS = dict(algorithm="one_class_svm", contamination=0.001, gamma=0.01,
                   scale_features=True, log_transform_features=[])

# The 17/08-committed state (special_char_ratio+entropy+quote_imbalance,
# OCSVM, D3-only eval) — superseded 19/08 by the scope-fix + LOF switch (see
# `final_params`/`final_features` in main(), built live from config), kept
# hardcoded here so panel 3 still reproduces that historical state exactly
# regardless of later config changes.
QUOTE_FEATURES = ["special_char_ratio", "entropy", "quote_imbalance"]
QUOTE_PARAMS = dict(algorithm="one_class_svm", contamination=0.001, gamma=0.01,
                     scale_features=True, log_transform_features=[])


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


def _reproduce_buggy_pool(processed: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rebuild the pre-16/08-fix benign pool on demand: branch1_train.csv
    filtered to label==0 (d1_sqliv3+d7_srbh2020 only, no d3_csic2010),
    cleaned the same way clean_branch2_data.py cleans the real pool (SSRF
    removed, short-strings rebalanced to 3%). Deterministic — not read from
    a CSV, since the original buggy branch2_data.csv was gitignored and is
    gone.

    Returns:
        (train_df, test_df) with the same feature columns as the real
        pipeline, computed via extract_statistical_features.
    """
    b1 = pd.read_csv(processed / "branch1_train.csv")
    normal = b1[b1["label"] == 0].reset_index(drop=True)
    feats = normal["query_canonical"].astype(str).map(
        lambda t: extract_statistical_features(t).as_dict()
    )
    feats_df = pd.DataFrame(list(feats))
    normal = pd.concat([normal, feats_df], axis=1)

    train_df = normal[normal["split"] == "train"].reset_index(drop=True)
    test_df = normal[normal["split"] == "test"].reset_index(drop=True)

    leaky_train = train_df.apply(is_leaky_row, axis=1)
    leaky_test = test_df.apply(is_leaky_row, axis=1)
    clean_train = train_df[~leaky_train].reset_index(drop=True)
    clean_test = test_df[~leaky_test].reset_index(drop=True)

    rng = np.random.default_rng(42)
    clean_train = _rebalance_short(clean_train, 0.03, rng)
    logger.info("Reproduced buggy pool: train=%d test=%d (source=%s)",
                len(clean_train), len(clean_test), sorted(clean_train["source"].unique()))
    return clean_train, clean_test


def main() -> None:
    cfg = load_config()
    processed = Path("data/processed")

    buggy_train, buggy_test = _reproduce_buggy_pool(processed)

    # Panels 1-3 reproduce historical states, all measured against a D3-only
    # anomalous eval — the original scope before 19/08's fix also folded
    # D1/D7 attacks + URL-wrapper-stripped D3/D7 text into
    # branch2_anomalous_eval(_clean).csv (see build_branch2_dataset.py),
    # which would silently change what these historical panels represent.
    full_anom = pd.read_csv(processed / "branch2_anomalous_eval.csv")
    buggy_anom = full_anom[full_anom.source == "d3_csic2010"].reset_index(drop=True)

    fixed = pd.read_csv(processed / "branch2_data_clean.csv")
    fixed_train = fixed[fixed.split == "train"].reset_index(drop=True)
    fixed_test = fixed[fixed.split == "test"].reset_index(drop=True)
    full_anom_clean = pd.read_csv(processed / "branch2_anomalous_eval_clean.csv")
    d3_only_anom_clean = full_anom_clean[full_anom_clean.source == "d3_csic2010"].reset_index(drop=True)

    b2 = cfg.get("branch2_anomaly")
    final_features = list(b2["features"])
    if b2["algorithm"] == "one_class_svm":
        final_params = dict(algorithm="one_class_svm", contamination=b2["ocsvm_nu"], gamma=b2["ocsvm_gamma"],
                             scale_features=b2["scale_features"], log_transform_features=list(b2["log_transform_features"]))
    elif b2["algorithm"] == "local_outlier_factor":
        final_params = dict(algorithm="local_outlier_factor", contamination=b2["lof_contamination"],
                             n_neighbors=b2["lof_n_neighbors"], scale_features=b2["scale_features"],
                             log_transform_features=list(b2["log_transform_features"]))
    else:
        final_params = dict(algorithm=b2["algorithm"], contamination=b2["contamination"],
                             scale_features=b2["scale_features"], log_transform_features=list(b2["log_transform_features"]))

    stages = {}
    s_test, s_anom = _fit_score(OLD_PARAMS, buggy_train, buggy_test, buggy_anom, OLD_FEATURES)
    stages["Bug (missing D3)\nold feature (bigram_entropy)"] = (s_test, s_anom, _p95_metrics(s_test, s_anom))

    s_test, s_anom = _fit_score(OLD_PARAMS, fixed_train, fixed_test, d3_only_anom_clean, OLD_FEATURES)
    stages["Fixed pool (D1+D3+D7)\nold feature (bigram_entropy)"] = (s_test, s_anom, _p95_metrics(s_test, s_anom))

    # NOTE: d3_only_anom_clean is D3 rows from the CURRENT (19/08,
    # URL-wrapper-stripped) eval file, not a byte-for-byte replay of the
    # original 17/08 D3 text (that raw file was overwritten on HF when the
    # scope fix shipped) -- so this reproduces the 17/08 feature/algorithm
    # choice, not necessarily its exact historical DR number.
    s_test, s_anom = _fit_score(QUOTE_PARAMS, fixed_train, fixed_test, d3_only_anom_clean, QUOTE_FEATURES)
    stages["17/08 approach: quote_imbalance\n(OCSVM, D3-only, URL-stripped)"] = (s_test, s_anom, _p95_metrics(s_test, s_anom))

    # Panel 4 (current, 19/08): scope-fixed data (D3/D7 URL-wrapper
    # stripped) + D1/D7 attacks folded into eval + 12 features + LOF.
    s_test, s_anom = _fit_score(final_params, fixed_train, fixed_test, full_anom_clean, final_features)
    stages["19/08: scope fix + LOF\n(D1+D3+D7 eval)"] = (s_test, s_anom, _p95_metrics(s_test, s_anom))

    for name, (_, _, m) in stages.items():
        logger.info("%s: FPR=%.4f DR=%.4f KS=%.4f", name.replace("\n", " "), m["fpr"], m["dr"], m["ks"])

    # ---- Fig — 4-panel score distributions ----
    fig, axes = plt.subplots(1, 4, figsize=(14, 3.4), sharey=False)
    for ax, (name, (s_test, s_anom, m)) in zip(axes, stages.items()):
        # Display range clipped to the 0.5-95th percentile of each panel's
        # own combined scores (not full min/max) — LOF's density-ratio score
        # can have a small (~1-5%) extreme-outlier tail (near-duplicate
        # training points blow up the ratio) that otherwise squashes the
        # informative bulk of the distribution into a sliver near 0; DR/AUC/
        # KS reported in the title are still computed on the FULL data.
        combined = np.concatenate([s_test, s_anom])
        lo, hi = np.percentile(combined, 0.5), np.percentile(combined, 95)
        grid = np.linspace(lo, hi, 300)

        def kde(x):
            # Fit on only the in-range points too (not just clip the display
            # grid) — otherwise a heavy outlier tail still dominates the
            # bandwidth estimate and flattens the visible curve.
            x = x[(x >= lo) & (x <= hi)]
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
                 "(domain-confound bug fix journey, matched FPR=5%)", y=1.04, fontsize=10.5)
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
    colors = [IEEE_RED, IEEE_ORANGE, IEEE_BLUE, IEEE_GREEN]
    bars = ax2.bar([n.replace("\n", " ") for n in names], drs, color=colors, edgecolor="black", linewidth=0.6)
    for bar, v in zip(bars, drs):
        ax2.text(bar.get_x() + bar.get_width() / 2, v + 0.01, f"{v:.1%}", ha="center", va="bottom", fontsize=9)
    ax2.set_ylabel("Detection rate @ matched FPR=5%")
    ax2.set_ylim(0, max(drs) * 1.4)
    ax2.set_title("Fig. Branch 2 — DR at matched FPR=5% across the bug-fix journey")
    plt.setp(ax2.get_xticklabels(), rotation=12, ha="right", fontsize=8)
    fig2.tight_layout()
    fig2_path = out_dir / "branch2_dr_journey.png"
    fig2.savefig(fig2_path, bbox_inches="tight")
    logger.info("Saved %s", fig2_path)


if __name__ == "__main__":
    main()
