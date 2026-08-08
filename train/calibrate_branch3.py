"""Calibrate and evaluate the Session Correlator (formerly "train Branch 3").

Not gradient training — SessionCorrelator (src/models/branch3_session.py)
re-uses the already-trained branch1_v1 classifier and branch2_v1 anomaly
detector as-is; this script only picks the 3 scalar behavior thresholds from
the TRAIN split of data/processed/branch3_sessions_cach_a.csv, then evaluates
(content-only / behavior-only / combined ablation) on the disjoint TEST
split. Writes:

  - models/branch3_v2/metadata.json (calibrated thresholds, no weights)
  - report/metrics/branch3_eval.json (ablation table, same consumers as the
    superseded GRU's eval report)

Replaces train/train_branch3.py after this project's diagnostic session
found the GRU sequence-model design didn't hold up (see
report/plan/data_contract.md §4.2 and src/models/branch3_session.py's module
docstring for the full story).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from build_session_dataset import _load_branch1, _load_branch2
from src.models.branch3_features import (
    class_names_from_config,
    evaluate_correlator_sessions,
    sessions_to_correlator_inputs,
)
from src.models.branch3_session import SessionCorrelator
from src.utils import get_logger, load_config

logger = get_logger(__name__)


def main() -> None:
    cfg = load_config()
    models_dir = Path(cfg.get_path("paths.models_dir", "models"))
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    reports_dir = Path(cfg.get_path("paths.reports_dir", "report/metrics"))

    data_path = processed_dir / "branch3_sessions_cach_a.csv"
    if not data_path.exists():
        raise FileNotFoundError(f"{data_path} not found. Run train/build_session_dataset.py first.")
    df = pd.read_csv(data_path)

    class_names = class_names_from_config(cfg)
    train_df, test_df = df[df["split"] == "train"], df[df["split"] == "test"]
    train_sessions = sessions_to_correlator_inputs(train_df)
    test_sessions = sessions_to_correlator_inputs(test_df)
    logger.info("Train sessions=%d  Test sessions=%d", len(train_sessions), len(test_sessions))

    vectorizer, clf = _load_branch1(models_dir, cfg.get_path("branch1_supervised.active_version", "branch1_v1"))
    b2_detector = _load_branch2(models_dir, cfg.get_path("branch2_anomaly.active_version", "branch2_v1"))
    content_threshold = float(cfg.get_path("branch1_supervised.decision_threshold", 0.5))
    percentile = float(cfg.get_path("branch3_session.aggregate.b2_benign_score_percentile", 0.90))
    max_decode = int(cfg.get_path("preprocessing.max_decode_iterations", 3))

    correlator = SessionCorrelator(
        b1_vectorizer=vectorizer, b1_clf=clf, b2_detector=b2_detector,
        content_threshold=content_threshold,
        max_decode_iterations=max_decode,
    )
    correlator.calibrate(train_sessions, percentile=percentile)

    metrics = evaluate_correlator_sessions(correlator, test_sessions, class_names)
    logger.info("=== Content-only ===  FPR=%s  DR=%s", metrics["content_only"]["fpr_benign"], metrics["content_only"]["detection_rate"])
    logger.info("=== Behavior-only === FPR=%s  DR=%s", metrics["behavior_only"]["fpr_benign"], metrics["behavior_only"]["detection_rate"])
    logger.info("=== Combined ===      FPR=%s  DR=%s", metrics["combined"]["fpr_benign"], metrics["combined"]["detection_rate"])

    version = "branch3_v2"
    out_dir = models_dir / version
    correlator.save(out_dir)

    eval_report = {
        "version": version,
        "branch": "branch3_session",
        "mechanism": "session_correlator",
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset": str(data_path),
        "dataset_source": {
            k: int(v) for k, v in df.drop_duplicates("session_id")["session_source"].value_counts().items()
        },
        "calibration": {
            "content_threshold": correlator.content_threshold,
            "per_query_threshold": correlator.per_query_threshold,
            "mean_threshold": correlator.mean_threshold,
            "fraction_threshold": correlator.fraction_threshold,
        },
        "train_sessions": len(train_sessions),
        "metrics": metrics,
        "caveat": (
            "Cach A sessions are self-generated (real bisection algorithm against a "
            "self-hosted demo DB), not independently-captured attacker traffic (Cach "
            "B, not started). Near-perfect detection rate here reflects that both "
            "branches were scoring data drawn from the same generation process they "
            "were built around, not evidence of generalization to novel evasive "
            "traffic — see report/plan/data_contract.md SS4.2."
        ),
    }

    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "branch3_eval.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(eval_report, f, indent=2)
    logger.info("Saved eval report to %s", report_path)
    logger.info("=== Done ===")


if __name__ == "__main__":
    main()
