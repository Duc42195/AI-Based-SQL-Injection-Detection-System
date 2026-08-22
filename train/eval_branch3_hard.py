"""Honest zero-day ablation for the Session Correlator's content check.

Re-scores `boolean_blind` test sessions' content check using
`models/branch1_no_boolean_blind` (a Branch-1 variant that has never seen
`boolean_blind` and misses 86.5% of it per-query, see
report/metrics/zeroday_experiment/summary.json) instead of the regular
`branch1_v1`.

This directly re-checks, on the real held-out TEST split, what this
project's diagnostic session (Experiment A2) already measured: concatenating
more session steps does NOT rescue a classifier that never learned the
attack class in the first place — attack_prob stayed 0.16-0.22 across
k=1..32 for the zero-day model, vs. 0.46-0.67 for the regular model. That
result should be reported as a stated LIMITATION of the content check (it
only helps when Branch 1 can recognize the class but the per-step signal is
weak — it is not a substitute for Branch 1 actually knowing the attack
type), not re-framed as a strength the way the superseded GRU's "still
F1=1.0 in hard mode" claim was (that claim was produced before two real bugs
in this evaluation pipeline were found and fixed — see
report/plan/data_contract.md §4.2 — and should not be re-cited).

The behavior check (Branch 2 aggregation) is UNCHANGED here on purpose:
Branch 2 never depended on Branch 1's class labels, so it isn't a zero-day
concern for Branch 1's classifier — it is evaluated in the regular
train/calibrate_branch3.py combined ablation instead.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd

from src.models.branch3_features import (
    branch1_probabilities,
    class_names_from_config,
)
from src.utils import get_logger, load_config

logger = get_logger(__name__)


def main() -> None:
    cfg = load_config()
    models_dir = Path(cfg.get_path("paths.models_dir", "models"))
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    reports_dir = Path(cfg.get_path("paths.reports_dir", "report/metrics"))
    # Use the session-level content_threshold actually calibrated for
    # SessionCorrelator (train/calibrate_branch3.py), not B1's single-query
    # decision_threshold — this ablation re-checks the SAME threshold the
    # live content check applies, just with a zero-day classifier swapped in.
    with (models_dir / "branch3_v2" / "metadata.json").open("r", encoding="utf-8") as f:
        content_threshold = float(json.load(f)["content_threshold"])

    data_path = processed_dir / "branch3_sessions_cach_a.csv"
    # keep_default_na=False: query_canonical can legitimately contain pandas'
    # default NA sentinel strings (e.g. a fragment literally reading "null" in
    # a query_splitting session) — see train/calibrate_branch3.py for the same fix.
    df = pd.read_csv(data_path, keep_default_na=False, na_values=[])
    class_names = class_names_from_config(cfg)
    test_df = df[(df["split"] == "test") & (df["session_label"] == 1)]  # boolean_blind only
    logger.info("Re-scoring %d boolean_blind TEST sessions with the zero-day content model",
                test_df["session_id"].nunique())

    hard_model_dir = models_dir / "branch1_no_boolean_blind"
    vectorizer = joblib.load(hard_model_dir / "vectorizer.joblib")
    clf = joblib.load(hard_model_dir / "model.joblib")

    rows = []
    for sid, group in test_df.sort_values("step_index").groupby("session_id", sort=False):
        texts = group["query_canonical"].tolist()
        concat_text = " ".join(texts)
        attack_prob = 1.0 - branch1_probabilities([concat_text], vectorizer, clf)[0, 0]
        rows.append({
            "session_id": sid,
            "n_steps": len(texts),
            "attack_prob": round(float(attack_prob), 4),
            "fires_content": bool(attack_prob >= content_threshold),
        })
    result = pd.DataFrame(rows)
    detection_rate = result["fires_content"].mean() if len(result) else None

    logger.info("=== HARD-MODE (content check, boolean_blind scored by branch1_no_boolean_blind) ===")
    logger.info("Content-check detection rate on boolean_blind: %.4f (n=%d)", detection_rate, len(result))
    logger.info("Mean attack_prob: %.4f (regular branch1_v1 content check on the same sessions "
                "measured 0.59-0.67 in Experiment A2 — see report/plan/data_contract.md §4.2)",
                result["attack_prob"].mean() if len(result) else float("nan"))

    out_path = reports_dir / "branch3_eval_hard.json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "description": (
                    "Zero-day ablation for the Session Correlator's content check: "
                    "boolean_blind TEST sessions re-scored with branch1_no_boolean_blind "
                    "(never seen boolean_blind, misses 86.5% of it per-query). Reported as "
                    "a stated limitation, not a strength — concatenation does not rescue a "
                    "classifier that never learned the class."
                ),
                "n_test_sessions": len(result),
                "content_check_detection_rate": round(float(detection_rate), 6) if detection_rate is not None else None,
                "mean_attack_prob": round(float(result["attack_prob"].mean()), 6) if len(result) else None,
                "per_session": result.to_dict(orient="records"),
            },
            f, indent=2,
        )
    logger.info("Saved to %s", out_path)


if __name__ == "__main__":
    main()
