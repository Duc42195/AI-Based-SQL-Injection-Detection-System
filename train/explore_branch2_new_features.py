# -*- coding: utf-8 -*-
"""Exploration (NO code change to production) — candidate structural features
for Branch 2.

REWRITTEN 17/08 to remove a bias found in the previous version: the
multivariate ablation (sections B2/B3 below) hard-coded `bigram_entropy` into
EVERY combination it tried, so it could only ever re-confirm bigram_entropy
as a winner — it never gave the other 3 candidates (quote_imbalance,
same_type_run_ratio, max_token_length) the same fair power-set treatment.
That mattered: bigram_entropy turned out to be a DOMAIN-SHIFT artifact, not a
genuine attack-structure signal — see train/build_branch2_data.py's docstring
and configs/config.yaml (branch2_anomaly) for the full story of how that was
found (the benign pool used to be missing the d3_csic2010 source entirely,
which is 100% of the anomalous eval set, so bigram_entropy was partly
learning "is this D3-formatted text" rather than "is this an attack").

Now runs a genuinely neutral search: full power-set (16 subsets, including
empty) of the 4 original features, repeated independently for EACH of the 4
new candidates (64 combos total) plus baseline_4+candidate and
baseline_4+all_candidates, so no candidate gets a structural advantage over
the others in how thoroughly it's tested.

Uses ONE fixed evaluation methodology throughout (AUC + DR at FPR matched to
5% via the P95-of-benign-test threshold) to avoid the dual-threshold
reporting confusion found earlier (see report/plan/solution_branch2_cleanup.md).

Candidate features (Duc's suggestions, kept "shape not content"):
  - quote_imbalance:    (count(') odd) + (count(") odd) -> 0/1/2. An unclosed
                         quote is a structural signature of string-literal
                         breakout, independent of *which* SQL keyword follows.
  - bigram_entropy:     Shannon entropy over adjacent-character pairs (bigrams)
                         instead of single chars -> captures local repetition/
                         structure (e.g. "))))" or "--" runs) that unigram
                         entropy misses.
  - same_type_run_ratio: fraction of adjacent character pairs that share the
                         same char class (alpha/digit/special/space) -> long
                         runs of one class (padding, repeated tokens) vs mixed
                         natural text.
  - max_token_length:   length of the longest whitespace-delimited token ->
                         long unbroken tokens (encoded/concatenated payloads)
                         vs normal short words.

Usage:  uv run python train/explore_branch2_new_features.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.chdir(Path(__file__).resolve().parents[1])

from src.models.branch2_anomaly import AnomalyDetector  # noqa: E402
from src.utils import get_logger, load_config  # noqa: E402

logger = get_logger(__name__)

BASE_FEATURES = ["length", "special_char_ratio", "sql_keyword_count", "entropy"]

_CHAR_CLASS_RE = [
    ("alpha", re.compile(r"[A-Za-z]")),
    ("digit", re.compile(r"[0-9]")),
    ("space", re.compile(r"\s")),
]


def _char_class(ch: str) -> str:
    for name, pat in _CHAR_CLASS_RE:
        if pat.match(ch):
            return name
    return "special"


def quote_imbalance(text: str) -> float:
    return float((text.count("'") % 2) + (text.count('"') % 2))


def bigram_entropy(text: str) -> float:
    if len(text) < 2:
        return 0.0
    bigrams = [text[i:i + 2] for i in range(len(text) - 1)]
    counts = Counter(bigrams)
    n = len(bigrams)
    return -sum((c / n) * np.log2(c / n) for c in counts.values())


def same_type_run_ratio(text: str) -> float:
    if len(text) < 2:
        return 0.0
    classes = [_char_class(ch) for ch in text]
    same = sum(1 for a, b in zip(classes, classes[1:]) if a == b)
    return same / (len(classes) - 1)


def max_token_length(text: str) -> float:
    tokens = text.split()
    return float(max((len(t) for t in tokens), default=0))


NEW_FEATURE_FUNCS = {
    "quote_imbalance": quote_imbalance,
    "bigram_entropy": bigram_entropy,
    "same_type_run_ratio": same_type_run_ratio,
    "max_token_length": max_token_length,
}


def _add_new_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    text = df["query_canonical"].astype(str)
    for name, fn in NEW_FEATURE_FUNCS.items():
        df[name] = text.map(fn)
    return df


def _detector_params(cfg, feature_names: list[str], log_transform: list[str]) -> dict:
    b2 = cfg.get("branch2_anomaly")
    return dict(
        algorithm=b2["algorithm"],
        contamination=b2["ocsvm_nu"] if b2["algorithm"] == "one_class_svm" else b2["contamination"],
        gamma=b2["ocsvm_gamma"],
        scale_features=b2["scale_features"],
        log_transform_features=log_transform,
        feature_names=feature_names,
    )


def _p95_matched_eval(
    detector: AnomalyDetector, X_train, X_test_benign, X_anom,
) -> dict:
    """One fixed methodology: fit, then AUC (threshold-free) + DR at the
    threshold set so FPR on held-out benign TEST = 5% (P95 of its own scores).
    """
    detector.fit(X_train)
    s_benign = detector.score(X_test_benign)
    s_anom = detector.score(X_anom)

    thr = np.percentile(s_benign, 95)
    fpr = float((s_benign > thr).mean())
    dr = float((s_anom > thr).mean())

    y_true = np.concatenate([np.zeros(len(s_benign)), np.ones(len(s_anom))])
    y_score = np.concatenate([s_benign, s_anom])
    auc = float(roc_auc_score(y_true, y_score))
    ks = stats.ks_2samp(s_benign, s_anom).statistic

    return {"fpr_p95": round(fpr, 4), "dr_p95": round(dr, 4), "auc": round(auc, 4), "ks": round(float(ks), 4)}


def main() -> None:
    cfg = load_config()
    processed = Path(__file__).resolve().parents[1] / "data" / "processed"

    train_path = processed / "branch2_data_clean.csv"
    anom_path = processed / "branch2_anomalous_eval_clean.csv"
    if not train_path.exists() or not anom_path.exists():
        raise FileNotFoundError(
            f"{train_path} / {anom_path} not found. Run train/build_branch2_data.py "
            "then train/clean_branch2_data.py first."
        )

    df = pd.read_csv(train_path)
    anom_df = pd.read_csv(anom_path)
    train_df = df[df["split"] == "train"].reset_index(drop=True)
    test_df = df[df["split"] == "test"].reset_index(drop=True)

    logger.info("Clean data: train=%d test_benign=%d anomalous=%d", len(train_df), len(test_df), len(anom_df))

    train_df = _add_new_features(train_df)
    test_df = _add_new_features(test_df)
    anom_df = _add_new_features(anom_df)

    # ---- A. Univariate screen: does the new feature alone separate the groups? ----
    logger.info("=== Univariate KS (test-benign vs anomalous), higher = more separation ===")
    ks_results = {}
    for name in NEW_FEATURE_FUNCS:
        ks = stats.ks_2samp(test_df[name].to_numpy(), anom_df[name].to_numpy())
        ks_results[name] = round(float(ks.statistic), 4)
        logger.info("  %-20s KS=%.4f (p=%.3g)", name, ks.statistic, ks.pvalue)
    # Baseline univariate KS for the current best feature (length, log1p) for reference.
    ks_length = stats.ks_2samp(
        np.log1p(test_df["length"].to_numpy()), np.log1p(anom_df["length"].to_numpy())
    )
    logger.info("  %-20s KS=%.4f (reference: current top feature)", "length (log1p)", ks_length.statistic)

    # ---- B. Multivariate: baseline 4 features vs baseline+candidate(s), same OCSVM hyperparams ----
    logger.info("=== Multivariate: OCSVM (current tuned nu/gamma) — fixed P95-matched-FPR methodology ===")
    import itertools

    combos: dict[str, list[str]] = {"baseline_4": list(BASE_FEATURES)}
    for name in NEW_FEATURE_FUNCS:
        combos[f"baseline_4+{name}"] = list(BASE_FEATURES) + [name]
    combos["baseline_4+all_new"] = list(BASE_FEATURES) + list(NEW_FEATURE_FUNCS)

    # ---- B2. Full power-set of the 4 base features, repeated independently
    # for EACH candidate (not just one) — the neutral version of what used
    # to be a bigram_entropy-only ablation. 16 subsets x 4 candidates = 64
    # combos, so no candidate gets a structural advantage over the others.
    for candidate in NEW_FEATURE_FUNCS:
        for r in range(0, len(BASE_FEATURES) + 1):
            for subset in itertools.combinations(BASE_FEATURES, r):
                feat_list = list(subset) + [candidate]
                key = "subset[" + ",".join(subset) + f"]+{candidate}"
                combos[key] = feat_list

    all_results = {}
    for combo_name, feat_list in combos.items():
        log_transform = ["length"] + (["max_token_length"] if "max_token_length" in feat_list else [])
        params = _detector_params(cfg, feat_list, log_transform)
        detector = AnomalyDetector(**params)

        X_train = train_df[feat_list].to_numpy(dtype=np.float64)
        X_test = test_df[feat_list].to_numpy(dtype=np.float64)
        X_anom = anom_df[feat_list].to_numpy(dtype=np.float64)

        res = _p95_matched_eval(detector, X_train, X_test, X_anom)
        res["features"] = feat_list
        all_results[combo_name] = res
        logger.info(
            "  %-24s FPR=%.4f DR=%.4f AUC=%.4f KS=%.4f",
            combo_name, res["fpr_p95"], res["dr_p95"], res["auc"], res["ks"],
        )

    out_path = Path(__file__).resolve().parents[1] / "report" / "metrics" / "branch2_feature_exploration.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump({"univariate_ks": ks_results, "univariate_ks_length_log1p_reference": round(float(ks_length.statistic), 4),
                   "multivariate": all_results}, f, indent=2)
    logger.info("Saved to %s", out_path)


if __name__ == "__main__":
    main()
