"""Branch 2 ablation (26/8-27/8): which benign-SOURCE combination to actually
TRAIN on, tested for generalization against EVERY source (not just the ones
trained on) — plus which of the 12 statistical features discriminate.

Revised per explicit user direction: fewer training sources may be better
(simpler paper narrative, cleaner anomaly-score chart), BUT every candidate
combo must still be EVALUATED against all 4 sources' held-out benign test
rows to prove generalization — not just the sources it was trained on. This
fixes a real gap in the first version of this ablation: that version only
measured FPR on each combo's OWN (reduced) benign-test, so dropping a source
looked artificially "better" simply because that source's harder benign
traffic was no longer in the test set either (confirmed concretely: dropping
D6 looked like an improvement there purely because D6's own benign — the
thing that had 69-95% FPR zero-shot — wasn't being tested at all in that
combo).

Design:
  1. Clean + GLOBALLY dedup all 4 sources' benign candidates together (one
     dedup pass, not four independent ones, so a cross-source duplicate text
     isn't double-counted).
  2. Split EACH source's own deduped rows into train/test ONCE (fixed,
     independent of which combo is being trained) — so every combo is judged
     against the exact same 4 held-out test sets.
  3. For each candidate TRAINING combo: fit only on the TRAIN portion of the
     combo's included sources. Calibrate the matched-FPR=5% threshold from
     that combo's OWN test-benign (realistic — this is what you'd actually
     have to calibrate against in practice). Then apply that SAME threshold
     to EVERY source's test-benign (including sources the combo never
     trained on) to read off per-source generalization, plus DR on the fixed
     full-D1+D3+D6+D7 anomalous set.

Also reports the same per-feature Cohen's d analysis as before (attack-
discrimination vs D6-source-identity confound).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

# train/ isn't a regular package (no __init__.py) and every other script here
# only imports from src/, so cross-importing another train/*.py module (this
# script is the first to do so) needs the project root on sys.path first —
# same fix train/clean_branch2_data.py already uses for the same reason.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.preprocessing.data_sources import load_d1, load_d3, load_d6_superviz25, load_d7  # noqa: E402
from src.utils import get_logger, load_config  # noqa: E402
from train.build_branch2_dataset import _build_anomalous_rows, _clean_benign_rows  # noqa: E402
from train.train_branch2 import _build_detector, _get_feature_names  # noqa: E402

logger = get_logger(__name__)

ALL_SOURCES = ("d1", "d3", "d6", "d7")

# Candidate training combos to evaluate: all 4, each single source dropped,
# and dropping both D1+D3 together (the pair the earlier leave-one-out pass
# suggested moved the metrics least).
CANDIDATE_COMBOS: list[tuple[str, ...]] = [
    ALL_SOURCES,
    ("d3", "d6", "d7"),        # minus d1
    ("d1", "d6", "d7"),        # minus d3
    ("d1", "d3", "d7"),        # minus d6 (expected to generalize badly to D6 test)
    ("d1", "d3", "d6"),        # minus d7
    ("d6", "d7"),              # minus d1 AND d3
]


def _cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    """Cohen's d effect size between two 1-D samples."""
    n_a, n_b = len(a), len(b)
    if n_a < 2 or n_b < 2:
        return float("nan")
    pooled_std = np.sqrt(((n_a - 1) * a.var(ddof=1) + (n_b - 1) * b.var(ddof=1)) / (n_a + n_b - 2))
    if pooled_std == 0:
        return 0.0
    return float((a.mean() - b.mean()) / pooled_std)


def _combo_label(combo: tuple[str, ...]) -> str:
    if combo == ALL_SOURCES:
        return "all4"
    dropped = set(ALL_SOURCES) - set(combo)
    return "minus_" + "_".join(sorted(dropped))


def main() -> None:
    cfg = load_config()
    seed = cfg.get_path("project.random_seed", 42)
    max_decode = cfg.get_path("preprocessing.max_decode_iterations", 3)
    test_fraction = cfg.get_path("branch2_anomaly.test_fraction", 0.2)
    algorithm = cfg.get_path("branch2_anomaly.algorithm", "local_outlier_factor")
    feature_names = _get_feature_names(cfg)
    raw_dir = Path(cfg.get_path("paths.data_raw", "data/raw"))
    reports_dir = Path(cfg.get_path("paths.reports_dir", "report/metrics"))

    logger.info("=== Loading all 4 raw sources once ===")
    raw = {
        "d1": load_d1(raw_dir / "d1_sqliv3_raw.csv"),
        "d3": load_d3(raw_dir / "d3_csic2010_raw.csv"),
        "d7": load_d7(raw_dir / "sr_bh_2020" / "data_capec_multilabel.csv", normal_sample_size=None, seed=seed),
    }
    d6_cap_benign = cfg.get_path("branch2_anomaly.d6_benign_cap", 50000)
    d6_cap_attack = cfg.get_path("branch2_anomaly.d6_attack_technique_cap", 20000)
    d6_4tuple = load_d6_superviz25(
        raw_dir / "superviz25" / "dataset.csv", seed=seed, benign_cap=d6_cap_benign, attack_cap=d6_cap_attack,
    )
    raw["d6"] = [(t, a, "d6_superviz25") for t, a, _s, _l in d6_4tuple]
    for k, v in raw.items():
        logger.info("  %s: %d raw rows", k, len(v))

    logger.info("=== Building FIXED anomalous eval set (all 4 sources, same for every combo) ===")
    all_attack_rows = raw["d1"] + raw["d3"] + raw["d6"] + raw["d7"]
    anom_rows, _ = _build_anomalous_rows(all_attack_rows, max_decode)
    X_anom = np.array([[r[f] for f in feature_names] for r in anom_rows], dtype=np.float64)
    logger.info("Fixed anomalous eval: %d rows", len(X_anom))

    logger.info("=== Cleaning + GLOBAL dedup across all 4 sources' benign candidates ===")
    all_benign_rows = raw["d1"] + raw["d3"] + raw["d6"] + raw["d7"]
    clean_rows, rejected, empty = _clean_benign_rows(all_benign_rows, max_decode)
    seen: set[str] = set()
    deduped = []
    for r in clean_rows:
        if r["query_canonical"] in seen:
            continue
        seen.add(r["query_canonical"])
        deduped.append(r)
    logger.info("  candidates: %d -> clean %d -> globally deduped %d", len(all_benign_rows), len(clean_rows), len(deduped))

    source_name_map = {"d1_sqliv3": "d1", "d3_csic2010": "d3", "d6_superviz25": "d6",
                        "d7_srbh2020_normal": "d7"}
    rng = np.random.default_rng(seed)
    train_X_by_source: dict[str, np.ndarray] = {}
    test_X_by_source: dict[str, np.ndarray] = {}
    rows_by_source: dict[str, list[dict]] = {s: [] for s in ALL_SOURCES}
    for r in deduped:
        s = source_name_map.get(r["source"])
        if s:
            rows_by_source[s].append(r)

    for s, rows in rows_by_source.items():
        X = np.array([[r[f] for f in feature_names] for r in rows], dtype=np.float64)
        idx = rng.permutation(len(rows))
        n_test = int(round(test_fraction * len(rows)))
        test_X_by_source[s] = X[idx[:n_test]]
        train_X_by_source[s] = X[idx[n_test:]]
        logger.info("  %s: %d rows -> train=%d test=%d", s, len(rows), len(train_X_by_source[s]), len(test_X_by_source[s]))

    results: dict[str, dict] = {}
    for combo in CANDIDATE_COMBOS:
        label = _combo_label(combo)
        logger.info("=== Training combo: %s ===", label)

        X_train = np.concatenate([train_X_by_source[s] for s in combo], axis=0)
        X_test_combo = np.concatenate([test_X_by_source[s] for s in combo], axis=0)

        detector = _build_detector(cfg, algorithm, feature_names)
        detector.fit(X_train)

        scores_test_combo = detector.score(X_test_combo)
        matched_threshold = float(np.percentile(scores_test_combo, 95))
        scores_anom = detector.score(X_anom)
        dr = float((scores_anom > matched_threshold).mean())
        y_true = np.concatenate([np.zeros(len(X_test_combo)), np.ones(len(X_anom))])
        y_scores = np.concatenate([scores_test_combo, scores_anom])
        auc = float(roc_auc_score(y_true, y_scores))

        fpr_by_source = {}
        for s in ALL_SOURCES:
            scores_s = detector.score(test_X_by_source[s])
            fpr_by_source[s] = round(float((scores_s > matched_threshold).mean()), 6)

        eval_result = {
            "trained_on": list(combo),
            "n_train": int(len(X_train)),
            "matched_threshold": round(matched_threshold, 6),
            "own_test_fpr": round(float((scores_test_combo > matched_threshold).mean()), 6),
            "fpr_by_source_ALL_4": fpr_by_source,
            "detection_rate_fixed_anomalous": round(dr, 6),
            "auc_own_test_vs_anomalous": round(auc, 6),
        }
        logger.info(
            "  FPR by source: %s | DR=%.4f AUC=%.4f",
            fpr_by_source, dr, auc,
        )

        per_feature = {}
        for i, fname in enumerate(feature_names):
            d_vs_anom = _cohens_d(X_anom[:, i], X_test_combo[:, i])
            entry = {"cohens_d_vs_anomalous": round(d_vs_anom, 4)}
            if "d6" in combo:
                d6_vals = train_X_by_source["d6"][:, i]
                other_vals = np.concatenate([train_X_by_source[s][:, i] for s in combo if s != "d6"]) if len(combo) > 1 else np.array([])
                if len(other_vals) >= 2:
                    entry["cohens_d_d6_vs_other_benign"] = round(_cohens_d(d6_vals, other_vals), 4)
            per_feature[fname] = entry

        results[label] = {"eval": eval_result, "per_feature": per_feature}

    out = {
        "description": (
            "Branch 2 training-source ablation: for each candidate TRAINING "
            "combo (subset of D1/D3/D6/D7), reports FPR against EVERY source's "
            "held-out benign test set (fpr_by_source_ALL_4), not just the "
            "sources trained on — this is the corrected version of the first "
            "ablation pass, which only measured FPR on each combo's own "
            "(reduced) test set and so made dropping a hard source look "
            "artificially better. detection_rate_fixed_anomalous is measured "
            "against the same full D1+D3+D6+D7 attack set for every combo."
        ),
        "results": results,
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / "branch2_source_ablation.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    logger.info("Saved to %s", out_path)


if __name__ == "__main__":
    main()
