"""Zero-shot compatibility check: Branch 1 + Branch 2 (as trained) against
the newly-found Kaggle dataset "Superviz25" (data/raw/superviz25/dataset.csv,
grgorqutel/superviz25-sql-injection-detection-dataset).

No retraining happens here — this answers "does the pattern in this new
dataset look compatible with what Branch 1/2 already learned?" before
deciding whether to fold it into training. Reuses the exact trained
artifacts (models/branch1_v1, models/branch2_v1) and the same
canonicalize -> feature-extraction path production inference uses
(src/models/branch3_features.py, already shared by train/calibrate_branch3.py
and train/eval_branch3_hard.py).

Dataset notes discovered while inspecting it (see report/plan/data_contract.md
for the eventual writeup once a decision is made):
- 3.69M rows, `label` (0/1) + `attack_technique` (boolean/error/union/time/
  stacked/inline/insider) + `tamper_method` (real sqlmap tamper scripts).
- The dataset's own `split` column is NOT usable for supervised training as-is:
  `train` = 100% label=0 rows, all label=1 rows sit in `test` — a 1-class/
  anomaly-style split, not a stratified supervised split. Ignored here; we
  draw our own stratified sample instead.
- `attack_technique="insider"` rows look mislabeled on inspection (content is
  plain session-init SQL like "SET NAMES utf8mb4") — sampled and reported
  separately, not folded into the "attack" aggregate.
- `attack_technique="inline"` doesn't map to any of the 5 current Branch-1
  classes (canary-probe-shaped payloads, not a SQL sub-technique) — reported
  separately, unmapped.
- Key hypothesis this script tests directly: some benign (label=0) rows are
  legitimate multi-table lookups written with a real `UNION SELECT` (e.g.
  searching two tables at once) — content Branch 1's training data (D1/D3/D7)
  never contained a benign counter-example for. Sampled as its own stratum
  (`benign_union_like`) to measure whether this alone inflates Branch 1's FPR.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.models.branch1_loader import load_branch1_artifacts
from src.models.branch2_anomaly import AnomalyDetector
from src.models.branch3_features import BRANCH1_LABEL_ORDER, branch1_probabilities, branch2_scores_for_texts
from src.preprocessing.canonicalize import canonicalize
from src.preprocessing.multiclass_tagger import LABEL_NAMES
from src.utils import get_logger, load_config

logger = get_logger(__name__)

_UNION_SELECT_RE = re.compile(r"UNION\s+(ALL\s+)?SELECT", re.IGNORECASE)

# attack_technique -> Branch-1 label id, for the classes that map 1:1 onto
# the project's existing 5-class schema. "inline"/"insider" deliberately
# excluded (see module docstring) and reported as their own unmapped strata.
_TECHNIQUE_TO_LABEL = {
    "union": 1,
    "error": 2,
    "boolean": 3,
    "time": 4,
    "stacked": 5,
}

# Per-stratum reservoir cap. Benign strata get more since FPR estimates need
# more samples to be stable at the low rates this system targets.
_STRATUM_CAPS = {
    "benign_plain": 3000,
    "benign_union_like": 2000,
    "union": 1500,
    "error": 1500,
    "boolean": 1500,
    "time": 1500,
    "stacked": 1500,
    "inline": 1000,
    "insider": 1089,  # small population (1,089 total) — take effectively all
}

_CHUNK_SIZE = 200_000


def _stratum_key(label: str, attack_technique: str | None, full_query: str) -> str:
    if label == "0":
        return "benign_union_like" if _UNION_SELECT_RE.search(full_query) else "benign_plain"
    return attack_technique or "unknown_attack"


def _sample_dataset(csv_path: Path, seed: int) -> dict[str, list[str]]:
    """Reservoir-sample up to _STRATUM_CAPS[stratum] raw queries per stratum.

    Streams the 3.69M-row / ~1GB file in chunks rather than loading it whole.
    """
    rng = random.Random(seed)
    reservoirs: dict[str, list[str]] = {k: [] for k in _STRATUM_CAPS}
    seen_counts: dict[str, int] = {k: 0 for k in _STRATUM_CAPS}

    cols = ["full_query", "label", "attack_technique"]
    n_rows = 0
    for chunk in pd.read_csv(csv_path, usecols=cols, dtype=str, chunksize=_CHUNK_SIZE):
        n_rows += len(chunk)
        for label, technique, text in zip(chunk["label"], chunk["attack_technique"], chunk["full_query"]):
            if not isinstance(text, str) or not text:
                continue
            key = _stratum_key(label, technique if isinstance(technique, str) else None, text)
            if key not in reservoirs:
                continue
            cap = _STRATUM_CAPS[key]
            seen_counts[key] += 1
            reservoir = reservoirs[key]
            if len(reservoir) < cap:
                reservoir.append(text)
            else:
                j = rng.randint(0, seen_counts[key] - 1)
                if j < cap:
                    reservoir[j] = text
        logger.info("Scanned %d rows so far...", n_rows)

    for key, reservoir in reservoirs.items():
        logger.info("Stratum %-18s: sampled %5d / %d seen", key, len(reservoir), seen_counts[key])
    return reservoirs


def main() -> None:
    cfg = load_config()
    models_dir = Path(cfg.get_path("paths.models_dir", "models"))
    reports_dir = Path(cfg.get_path("paths.reports_dir", "report/metrics"))
    data_raw_dir = Path(cfg.get_path("paths.data_raw", "data/raw"))
    max_decode = int(cfg.get_path("preprocessing.max_decode_iterations", 3))
    b1_threshold = float(cfg.get_path("branch1_supervised.decision_threshold", 0.5))
    seed = int(cfg.get_path("project.random_seed", 42))

    csv_path = data_raw_dir / "superviz25" / "dataset.csv"
    logger.info("Streaming + stratified-sampling %s", csv_path)
    reservoirs = _sample_dataset(csv_path, seed)

    b1_dir = models_dir / "branch1_v1"
    b2_dir = models_dir / "branch2_v1"
    vectorizer, clf = load_branch1_artifacts(b1_dir, cfg.get_path("branch1_supervised.distilbert", {}))
    detector = AnomalyDetector.load(b2_dir)

    label_names_by_col = [LABEL_NAMES[i] for i in BRANCH1_LABEL_ORDER]

    results: dict[str, dict] = {}
    for stratum, raw_texts in reservoirs.items():
        if not raw_texts:
            results[stratum] = {"n": 0}
            continue
        canonical_texts = [canonicalize(t, max_decode).query_canonical for t in raw_texts]

        b1_probs = branch1_probabilities(canonical_texts, vectorizer, clf)  # (n, 5)
        attack_prob = 1.0 - b1_probs[:, 0]
        is_sqli = attack_prob >= b1_threshold
        pred_label_idx = b1_probs.argmax(axis=1)
        pred_label_names = [label_names_by_col[i] for i in pred_label_idx]

        b2_scores = branch2_scores_for_texts(canonical_texts, detector)
        is_anomaly = _branch2_flags(canonical_texts, detector)

        pred_dist: dict[str, int] = {}
        for name in pred_label_names:
            pred_dist[name] = pred_dist.get(name, 0) + 1

        stratum_result = {
            "n": len(raw_texts),
            "branch1": {
                "mean_attack_probability": round(float(attack_prob.mean()), 6),
                "flag_rate": round(float(is_sqli.mean()), 6),
                "predicted_label_distribution": pred_dist,
            },
            "branch2": {
                "mean_anomaly_score": round(float(b2_scores.mean()), 6),
                "flag_rate": round(float(is_anomaly.mean()), 6),
            },
        }
        if stratum in ("benign_plain", "benign_union_like"):
            stratum_result["interpretation"] = "flag_rate here = false positive rate (ground truth is benign)"
        elif stratum in _TECHNIQUE_TO_LABEL:
            stratum_result["interpretation"] = "flag_rate here = detection rate (ground truth is attack)"
            stratum_result["mapped_branch1_label"] = LABEL_NAMES[_TECHNIQUE_TO_LABEL[stratum]]
        else:
            stratum_result["interpretation"] = (
                "unmapped attack_technique, not one of Branch 1's 5 classes — "
                "reported for reference only, not scored as detection rate"
            )
        results[stratum] = stratum_result
        logger.info(
            "%-18s n=%-5d B1 flag_rate=%.4f  B2 flag_rate=%.4f",
            stratum, len(raw_texts), stratum_result["branch1"]["flag_rate"], stratum_result["branch2"]["flag_rate"],
        )

    out = {
        "description": (
            "Zero-shot evaluation of models/branch1_v1 + models/branch2_v1 (no "
            "retraining) against a stratified sample of the newly-found Kaggle "
            "dataset data/raw/superviz25/dataset.csv. Purpose: decide whether "
            "this dataset's pattern is compatible enough to cite as an "
            "additional validation set, or whether it requires retraining."
        ),
        "caveats": [
            "Source dataset's own `split` column is unusable for supervised "
            "training as given (train split = 100% benign, all attacks in test) "
            "— ignored here in favor of our own stratified sample.",
            "attack_technique='insider' rows inspected by hand and look "
            "mislabeled (plain session-init SQL like 'SET NAMES utf8mb4' "
            "tagged as attack) — reported separately, not treated as ground truth.",
            "attack_technique='inline' does not map to any of Branch 1's 5 "
            "classes (canary/fuzz-probe payloads, not a SQLi sub-technique) — "
            "reported separately, unmapped.",
            "This is a stratified sample (reservoir sampling per stratum, seed "
                f"={seed}), not the full 3.69M-row dataset — sized for stable "
            "FPR/DR estimates, not exhaustive coverage.",
        ],
        "strata": results,
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / "superviz25_zeroshot_eval.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    logger.info("Saved to %s", out_path)


def _branch2_flags(texts: list[str], detector: AnomalyDetector) -> np.ndarray:
    from src.preprocessing.statistical_features import FEATURE_ORDER, extract_statistical_features

    feature_names = detector.feature_names or FEATURE_ORDER
    X = np.array([extract_statistical_features(t).as_list() for t in texts], dtype=np.float64)
    if feature_names != FEATURE_ORDER:
        idx = [FEATURE_ORDER.index(f) for f in feature_names]
        X = X[:, idx]
    return detector.anomaly_flags(X)


if __name__ == "__main__":
    main()
