"""Real-class-holdout continual-learning experiment: two pours, two bump types.

Supersedes ``train/run_continual_learning_experiment.py`` (the synthetic
`stacked`-class demo) for the paper's reported continual-learning numbers.
Runs against the split built by ``train/build_cl_scenario_split.py``.

Scenario:

* **Champion (M0)** trains on Base — the 4 known classes only, the held-out
  class entirely absent.
* **Scenario 1 pour (Q3)** replays a quiet head (no held-out class, the drift
  reference) followed by the held-out class interleaved into ordinary known
  traffic. Confirmed held-out samples accumulate in the review queue; once
  they cross ``retrain_threshold``, a major-bump candidate (M1) is trained
  and — if it clears an absolute quality floor — promoted directly. There is
  no working champion for the new class to be *compared* against, so no
  shadow phase applies to this path (see report §III.G for why).
* **Scenario 2 pour (Q4)** replays more volume of the 4 known classes only.
  Confirmed samples again accumulate; once they cross the same threshold, a
  minor-bump candidate (M2) is trained and put through the validation gate's
  full same-major comparison against M1. If it is promoted, it must then
  survive a shadow window (predictions logged, M1 still decides) before
  becoming champion; M1 is retired only at that point.
* A drift monitor replays each pour independently and in parallel (its
  finding does not gate anything): Q3 against M0 to see whether the held-out
  class's emergence is visible before it is ever labelled; Q4 against M1 to
  see whether ordinary volume growth alone ever looks like drift.

Why the gate's cross-major path needs an extra check here: ``evaluate_gate``
deliberately promotes unconditionally across a major-version change (see
``src/continual_learning/gate.py`` and ``tests/test_gate.py::
test_cross_major_refusal_holds_even_if_candidate_looks_worse``) — the
benchmark itself changes shape, so no champion/challenger comparison is
meaningful, and the module's own tested contract is that none is attempted.
That is the right contract for a reusable gate, but this experiment still
needs *some* backstop before a major-bump candidate goes live, so a
``quality_floor_check`` runs in this script, one layer above the gate: no
regression on the 4 known classes, and a minimum recall on the held-out one.

Run:  uv run python train/run_cl_scenario_experiment.py
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from src.continual_learning.gate import (
    ModelEvaluation,
    append_decision,
    compute_evaluation,
    evaluate_gate,
)
from src.models.branch2_anomaly import AnomalyDetector
from src.monitoring.drift import (
    ReferenceBins,
    detect_trigger,
    fit_reference_bins,
    iter_windows,
    psi_categorical,
    psi_from_reference,
)
from src.preprocessing.statistical_features import extract_statistical_features
from src.utils import get_logger, load_config

logger = get_logger(__name__)

FEATURES = ["length", "special_char_ratio", "entropy", "quote_imbalance"]
SIGNALS = ("global", "attack_subpop", "prediction", "confidence", "confidence_flagged")
COLUMNS = ["id", "query_raw", "query_canonical", "label", "label_name"]


# --------------------------------------------------------------------------- #
# Branch 1 model
# --------------------------------------------------------------------------- #
class Classifier:
    """TF-IDF + logistic regression, matching the production Branch-1 path."""

    def __init__(self, tfidf_cfg: dict, seed: int) -> None:
        self._vectorizer = TfidfVectorizer(
            analyzer=tfidf_cfg["analyzer"],
            ngram_range=(tfidf_cfg["ngram_min"], tfidf_cfg["ngram_max"]),
            max_features=tfidf_cfg["max_features"],
        )
        self._clf = LogisticRegression(max_iter=1000, random_state=seed)

    def fit(self, texts: pd.Series, labels: pd.Series) -> float:
        started = time.perf_counter()
        matrix = self._vectorizer.fit_transform(texts.astype(str))
        self._clf.fit(matrix, labels.to_numpy())
        return time.perf_counter() - started

    def predict(self, texts: pd.Series) -> np.ndarray:
        return self._clf.predict(self._vectorizer.transform(texts.astype(str)))

    def predict_with_confidence(self, texts: pd.Series) -> tuple[np.ndarray, np.ndarray]:
        matrix = self._vectorizer.transform(texts.astype(str))
        probabilities = self._clf.predict_proba(matrix)
        indices = probabilities.argmax(axis=1)
        return self._clf.classes_[indices], probabilities.max(axis=1)


def train_model(data: pd.DataFrame, tfidf_cfg: dict, seed: int, *, name: str) -> Classifier:
    model = Classifier(tfidf_cfg, seed)
    duration = model.fit(data["query_canonical"], data["label_name"])
    logger.info(
        "Trained %-22s on %s rows (%d classes) in %.1fs",
        name,
        f"{len(data):,}",
        data["label_name"].nunique(),
        duration,
    )
    return model


def evaluate_on(
    model: Classifier, golden: pd.DataFrame, *, model_version: str, data_version: str
) -> ModelEvaluation:
    return compute_evaluation(
        golden["label_name"].tolist(),
        model.predict(golden["query_canonical"]).tolist(),
        model_version=model_version,
        data_version=data_version,
    )


# --------------------------------------------------------------------------- #
# Branch 2 (fixed for the whole experiment — benign-only, never retrained)
# --------------------------------------------------------------------------- #
def train_branch2(cfg) -> tuple[AnomalyDetector, list[str]]:
    processed = Path(cfg.get_path("paths.data_processed", "data/processed"))
    feature_names = list(cfg.get_path("branch2_anomaly.features"))
    data_file = cfg.get_path("branch2_anomaly.data_file", "branch2_data_clean.csv")
    df = pd.read_csv(processed / data_file)
    train = df[df["split"] == "train"].reset_index(drop=True)

    algorithm = cfg.get_path("branch2_anomaly.algorithm", "local_outlier_factor")
    scale = cfg.get_path("branch2_anomaly.scale_features", True)
    log_transform = cfg.get_path("branch2_anomaly.log_transform_features", [])
    kwargs: dict = {}
    if algorithm == "local_outlier_factor":
        contamination = cfg.get_path("branch2_anomaly.lof_contamination", 0.05)
        kwargs["n_neighbors"] = cfg.get_path("branch2_anomaly.lof_n_neighbors", 5)
    elif algorithm == "one_class_svm":
        contamination = cfg.get_path("branch2_anomaly.ocsvm_nu", 0.001)
    else:
        contamination = cfg.get_path("branch2_anomaly.contamination", 0.01)

    detector = AnomalyDetector(
        algorithm=algorithm,
        contamination=contamination,
        scale_features=scale,
        log_transform_features=log_transform,
        feature_names=feature_names,
        **kwargs,
    )
    detector.fit(train[feature_names].to_numpy(dtype=np.float64))
    logger.info("Trained Branch 2 (%s) on %s benign rows", algorithm, f"{len(train):,}")
    return detector, feature_names


def branch2_features(texts: pd.Series, feature_names: list[str]) -> np.ndarray:
    rows = [extract_statistical_features(str(t)).as_dict() for t in texts]
    return pd.DataFrame(rows)[feature_names].to_numpy(dtype=np.float64)


# --------------------------------------------------------------------------- #
# Quality floor check — the experiment's own backstop for the major-bump path
# --------------------------------------------------------------------------- #
@dataclass
class FloorCheck:
    passed: bool
    known_class_regressions: dict[str, float]
    new_class_recall: float
    min_new_class_recall: float
    max_per_class_recall_drop: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "known_class_regressions": self.known_class_regressions,
            "new_class_recall": round(self.new_class_recall, 6),
            "min_new_class_recall": self.min_new_class_recall,
            "max_per_class_recall_drop": self.max_per_class_recall_drop,
        }


def quality_floor_check(
    candidate: ModelEvaluation,
    prior: ModelEvaluation,
    new_class: str,
    *,
    max_per_class_recall_drop: float,
    min_new_class_recall: float,
) -> FloorCheck:
    """The experiment's backstop for cross-major promotion (see module docstring)."""
    regressions = {}
    for label, prior_recall in prior.per_class_recall.items():
        drop = prior_recall - candidate.per_class_recall.get(label, 0.0)
        if drop > max_per_class_recall_drop:
            regressions[label] = round(drop, 6)
    new_recall = candidate.per_class_recall.get(new_class, 0.0)
    passed = not regressions and new_recall >= min_new_class_recall
    return FloorCheck(
        passed=passed,
        known_class_regressions=regressions,
        new_class_recall=new_recall,
        min_new_class_recall=min_new_class_recall,
        max_per_class_recall_drop=max_per_class_recall_drop,
    )


# --------------------------------------------------------------------------- #
# Drift monitor (independent of the retrain mechanism — see module docstring)
# --------------------------------------------------------------------------- #
def feature_frame(texts: pd.Series) -> pd.DataFrame:
    rows = [extract_statistical_features(str(t)).as_dict() for t in texts]
    return pd.DataFrame(rows, columns=FEATURES)


def monitor_drift(
    chunk: pd.DataFrame,
    model: Classifier,
    *,
    label: str,
    reference_mask: np.ndarray,
    window_size: int,
    psi_bins: int,
    threshold: float,
    sustained: int,
) -> dict[str, Any]:
    """Replay one pour window by window, scoring PSI against its own reference.

    Args:
        chunk: The pour's rows, in stream order.
        model: The champion serving traffic during this pour.
        label: Human-readable name for logging (e.g. "Q3 (major-bump pour)").
        reference_mask: True for rows that form the drift reference. Must be a
            prefix of the pour (a quiet head) for the "windows since reference"
            framing to make sense.
        window_size, psi_bins, threshold, sustained: As in ``monitoring.psi_*``.
    """
    logger.info("[drift %s] scoring %s queries…", label, f"{len(chunk):,}")
    predictions, confidences = model.predict_with_confidence(chunk["query_canonical"])
    chunk = chunk.assign(predicted=predictions, confidence=confidences)
    features = feature_frame(chunk["query_canonical"])

    reference = chunk[reference_mask]
    reference_features = features[reference_mask]
    if len(reference) < psi_bins:
        raise ValueError(f"[{label}] reference has only {len(reference)} rows, need >= {psi_bins}")

    reference_bins = {
        name: fit_reference_bins(reference_features[name], feature=name, n_bins=psi_bins)
        for name in FEATURES
    }
    flagged_reference_mask = (reference["predicted"] != "normal").to_numpy()
    flagged_reference = reference_features[flagged_reference_mask]
    attack_bins: dict[str, ReferenceBins] = {}
    if len(flagged_reference) >= psi_bins:
        attack_bins = {
            name: fit_reference_bins(flagged_reference[name], feature=name, n_bins=psi_bins)
            for name in FEATURES
        }
    confidence_bins = fit_reference_bins(reference["confidence"], feature="confidence", n_bins=psi_bins)
    flagged_confidence_bins = (
        fit_reference_bins(
            reference.loc[flagged_reference_mask, "confidence"],
            feature="confidence_flagged",
            n_bins=psi_bins,
        )
        if flagged_reference_mask.sum() >= psi_bins
        else confidence_bins
    )
    reference_predictions = reference["predicted"].tolist()
    n_reference = int(reference_mask.sum())

    windows: list[dict[str, Any]] = []
    for index, start, stop in iter_windows(len(chunk), window_size):
        window = chunk.iloc[start:stop]
        window_features = features.iloc[start:stop]
        flagged = window["predicted"] != "normal"

        global_psi = float(
            np.mean([psi_from_reference(window_features[f], reference_bins[f]) for f in FEATURES])
        )
        if attack_bins and flagged.sum() >= 5:
            attack_features = window_features[flagged.to_numpy()]
            attack_psi = float(
                np.mean([psi_from_reference(attack_features[f], attack_bins[f]) for f in FEATURES])
            )
        else:
            attack_psi = 0.0
        prediction_psi = psi_categorical(reference_predictions, window["predicted"].tolist())
        confidence_psi = psi_from_reference(window["confidence"], confidence_bins)
        if flagged.sum() >= 5:
            flagged_confidence_psi = psi_from_reference(
                window.loc[flagged, "confidence"], flagged_confidence_bins
            )
        else:
            flagged_confidence_psi = 0.0

        signals = {
            "global": round(global_psi, 6),
            "attack_subpop": round(attack_psi, 6),
            "prediction": round(prediction_psi, 6),
            "confidence": round(confidence_psi, 6),
            "confidence_flagged": round(flagged_confidence_psi, 6),
        }
        windows.append(
            {
                "index": index,
                "is_reference": stop <= n_reference,
                "n": len(window),
                "n_held_out_class": int((window["label_name"] == HELD_OUT_CLASS_NAME).sum())
                if "label_name" in window
                else None,
                "psi": signals,
                "block_rate": round(float(flagged.mean()), 6),
                "alert": bool(max(signals.values()) >= threshold),
            }
        )

    trigger = detect_trigger(windows, threshold=threshold, sustained=sustained, signals=SIGNALS)
    logger.info(
        "[drift %s] trigger=%s at window %s",
        label,
        trigger.fired,
        trigger.window_index,
    )
    return {"windows": windows, "trigger": trigger.to_dict()}


HELD_OUT_CLASS_NAME = ""  # set in main() before monitor_drift is called


# --------------------------------------------------------------------------- #
# Experiment
# --------------------------------------------------------------------------- #
def main() -> None:
    global HELD_OUT_CLASS_NAME
    cfg = load_config()
    processed = Path(cfg.get_path("paths.data_processed", "data/processed"))
    artifacts = Path(cfg.get_path("cl_scenario.artifacts_dir", "report/metrics/cl_scenario"))
    artifacts.mkdir(parents=True, exist_ok=True)

    seed = int(cfg.get_path("cl_scenario.seed", 42))
    held_out = str(cfg.get_path("cl_scenario.held_out_class", "union_based"))
    HELD_OUT_CLASS_NAME = held_out
    tfidf_cfg = dict(cfg.get_path("branch1_supervised.tfidf"))
    window_size = int(cfg.get_path("cl_scenario.stream.window_size", 1000))
    psi_bins = int(cfg.get_path("mlops.drift.psi_bins", 10))
    threshold = float(cfg.get_path("monitoring.psi_alert_threshold", 0.2))
    sustained = int(cfg.get_path("mlops.drift.sustained_windows", 2))
    low_confidence = float(cfg.get_path("mlops.queue.low_confidence_below", 0.6))
    retrain_threshold = int(cfg.get_path("cl_scenario.retrain_threshold", 500))
    shadow_window = int(cfg.get_path("cl_scenario.shadow_window_queries", 2000))
    shadow_fpr_tolerance = float(cfg.get_path("cl_scenario.shadow_fpr_tolerance", 0.005))
    max_drop = float(cfg.get_path("cl_scenario.gate.max_per_class_recall_drop", 0.02))
    min_new_recall = float(cfg.get_path("cl_scenario.gate.min_new_class_recall", 0.80))

    split = pd.read_csv(processed / "cl_scenario_split.csv")
    stream = pd.read_csv(processed / "cl_scenario_stream.csv")
    q3 = stream[stream["chunk"] == "q3"].reset_index(drop=True)
    q4 = stream[stream["chunk"] == "q4"].reset_index(drop=True)

    base_train = split[split["partition"] == "base_train"]
    golden = split[split["partition"] == "golden"]
    golden_known = golden[golden["label_name"] != held_out]
    golden_held = golden[golden["label_name"] == held_out]

    results: dict[str, Any] = {"config": {
        "held_out_class": held_out,
        "retrain_threshold": retrain_threshold,
        "shadow_window_queries": shadow_window,
        "shadow_fpr_tolerance": shadow_fpr_tolerance,
    }}

    # ── Champion M0: trained on Base, never sees the held-out class ────────
    m0 = train_model(base_train, tfidf_cfg, seed, name="M0 (champion@1.0)")
    eval_m0_known = evaluate_on(
        m0, golden_known, model_version="M0", data_version="1.0"
    )
    logger.info(
        "M0 on golden (known classes only): F1-macro=%.4f FPR=%.4f",
        eval_m0_known.f1_macro,
        eval_m0_known.fpr,
    )

    # ── Branch 2: trained once, fixed for the whole experiment ─────────────
    detector, b2_features = train_branch2(cfg)

    # ── Pre-bump dual metric on the held-out class (zero-day-style) ────────
    preds_held = m0.predict(golden_held["query_canonical"])
    miss_rate = float((preds_held == "normal").mean())
    X_held = branch2_features(golden_held["query_canonical"], b2_features)
    b2_flags_held = detector.anomaly_flags(X_held)
    b2_dr_held = float(b2_flags_held.mean())
    combined_coverage = float(((preds_held != "normal") | (b2_flags_held == 1)).mean())
    results["pre_bump"] = {
        "f1_macro_known_classes": round(eval_m0_known.f1_macro, 4),
        "fpr": round(eval_m0_known.fpr, 4),
        "held_out_class": held_out,
        "held_out_n": len(golden_held),
        "branch1_miss_rate": round(miss_rate, 4),
        "branch2_detection_rate": round(b2_dr_held, 4),
        "combined_coverage": round(combined_coverage, 4),
    }
    logger.info(
        "Pre-bump on held-out '%s' (n=%d): B1 miss=%.4f B2 DR=%.4f combined=%.4f",
        held_out, len(golden_held), miss_rate, b2_dr_held, combined_coverage,
    )

    # ── Drift monitor over Q3, against M0, quiet head as reference ─────────
    q3_reference_mask = (q3["sub_phase"] == "quiet").to_numpy()
    drift_q3 = monitor_drift(
        q3, m0, label="Q3 (major-bump pour, vs M0)", reference_mask=q3_reference_mask,
        window_size=window_size, psi_bins=psi_bins, threshold=threshold, sustained=sustained,
    )
    results["drift_q3"] = drift_q3

    # ── Scenario 1: threshold-triggered major bump ──────────────────────────
    preds_m0, conf_m0 = m0.predict_with_confidence(q3["query_canonical"])
    q3 = q3.assign(predicted=preds_m0, confidence=conf_m0)
    flagged_q3 = (q3["predicted"] != "normal") | (q3["confidence"] < low_confidence)
    confirmed_held_out = flagged_q3 & (q3["label_name"] == held_out)
    cumulative = confirmed_held_out.cumsum()
    trigger_positions = np.flatnonzero((cumulative >= retrain_threshold).to_numpy())
    if len(trigger_positions) == 0:
        raise SystemExit(
            f"Only {int(cumulative.iloc[-1])} confirmed '{held_out}' samples reached in Q3 "
            f"(need {retrain_threshold}); widen cl_scenario.stream.scenario1_new_class_rows."
        )
    trigger_pos = int(trigger_positions[0])
    confirmed_pool = q3.iloc[: trigger_pos + 1][flagged_q3.iloc[: trigger_pos + 1]][COLUMNS]
    logger.info(
        "Major-bump trigger at Q3 position %d/%d (%.1f%% through the pour), pool=%d rows",
        trigger_pos, len(q3), 100 * (trigger_pos + 1) / len(q3), len(confirmed_pool),
    )

    pool_v2 = pd.concat([base_train[COLUMNS], confirmed_pool], ignore_index=True).drop_duplicates(
        subset="query_canonical"
    )
    m1 = train_model(pool_v2, tfidf_cfg, seed, name="M1 (candidate@2.0, major bump)")
    eval_m1 = evaluate_on(m1, golden, model_version="M1", data_version="2.0")
    logger.info(
        "M1 on full golden: F1-macro=%.4f FPR=%.4f recall[%s]=%.4f",
        eval_m1.f1_macro, eval_m1.fpr, held_out, eval_m1.per_class_recall.get(held_out, 0.0),
    )

    decision_major = evaluate_gate(
        eval_m1, eval_m0_known, max_per_class_recall_drop=max_drop,
        min_new_class_recall=min_new_recall, golden_version="1->2",
    )
    append_decision(decision_major, artifacts / "decisions.jsonl")
    floor = quality_floor_check(
        eval_m1, eval_m0_known, held_out,
        max_per_class_recall_drop=max_drop, min_new_class_recall=min_new_recall,
    )
    logger.info(
        "Major bump: gate=%s (%s) | experiment floor check=%s",
        decision_major.verdict, decision_major.comparison, "PASS" if floor.passed else "FAIL",
    )

    m1_is_champion = floor.passed
    results["act1_major_bump"] = {
        "trigger_position": trigger_pos,
        "trigger_fraction_of_pour": round((trigger_pos + 1) / len(q3), 4),
        "confirmed_pool_rows": len(confirmed_pool),
        "confirmed_pool_class_mix": confirmed_pool["label_name"].value_counts().to_dict(),
        "candidate": eval_m1.to_dict(),
        "gate_decision": decision_major.to_dict(),
        "quality_floor_check": floor.to_dict(),
        "promoted_direct": m1_is_champion,
        "lifecycle": (
            f"M0 retired, M1 champion at Q3 position {trigger_pos}"
            if m1_is_champion else "M1 rejected by floor check; M0 remains champion"
        ),
    }

    # ── Ablation: is the recall gain from the class, or just from more rows? ──
    # Same base pool, same NUMBER of extra rows, but resampled from the known
    # classes only (no union_based at all) — isolates whether M1's recall on
    # the held-out class came from learning it or from having more data.
    control_extra = base_train[COLUMNS].sample(
        n=min(len(confirmed_pool), len(base_train)), random_state=seed
    )
    pool_control = pd.concat([base_train[COLUMNS], control_extra], ignore_index=True)
    m_control = train_model(pool_control, tfidf_cfg, seed, name="control (same rows, no new class)")
    eval_control = evaluate_on(m_control, golden, model_version="control", data_version="1.1")
    results["act1_ablation_control"] = {
        "extra_rows": len(control_extra),
        "candidate_recall_on_held_out": eval_m1.per_class_recall.get(held_out, 0.0),
        "control_recall_on_held_out": eval_control.per_class_recall.get(held_out, 0.0),
        "interpretation": (
            "Same base pool, same number of extra rows either way; the control's "
            "extra rows are resampled from known classes only. If the control also "
            "recalled the held-out class, the gain would be attributable to row count "
            "rather than to learning the class."
        ),
    }
    logger.info(
        "Ablation: candidate recall[%s]=%.4f vs control (same +%d rows, no new class) recall=%.4f",
        held_out, eval_m1.per_class_recall.get(held_out, 0.0), len(control_extra),
        eval_control.per_class_recall.get(held_out, 0.0),
    )

    # ── Post-trigger tail of Q3: does the (now-champion) model catch it? ───
    champion_after_q3 = m1 if m1_is_champion else m0
    tail = q3.iloc[trigger_pos + 1 :]
    tail_held = tail[tail["label_name"] == held_out]
    if len(tail_held):
        tail_preds = champion_after_q3.predict(tail_held["query_canonical"])
        results["act1_major_bump"]["post_trigger_tail_recall"] = round(
            float((tail_preds == held_out).mean()), 4
        )
        results["act1_major_bump"]["post_trigger_tail_n"] = len(tail_held)

    # ── Scenario 2: threshold-triggered minor bump ──────────────────────────
    preds_champ, conf_champ = champion_after_q3.predict_with_confidence(q4["query_canonical"])
    q4 = q4.assign(predicted=preds_champ, confidence=conf_champ)
    flagged_q4 = (q4["predicted"] != "normal") | (q4["confidence"] < low_confidence)
    cumulative_q4 = flagged_q4.cumsum()
    trigger_positions_q4 = np.flatnonzero((cumulative_q4 >= retrain_threshold).to_numpy())
    if len(trigger_positions_q4) == 0:
        raise SystemExit(
            f"Only {int(cumulative_q4.iloc[-1])} confirmed samples reached in Q4 "
            f"(need {retrain_threshold}); widen cl_scenario.stream.scenario2_known_rows."
        )
    trigger_pos_q4 = int(trigger_positions_q4[0])
    confirmed_q4 = q4.iloc[: trigger_pos_q4 + 1][flagged_q4.iloc[: trigger_pos_q4 + 1]][COLUMNS]
    counts = confirmed_q4["label_name"].value_counts()
    balance_target = int(counts.min())
    balanced_q4 = pd.concat(
        [g.sample(n=balance_target, random_state=seed) for _, g in confirmed_q4.groupby("label_name")],
        ignore_index=True,
    )
    logger.info(
        "Minor-bump trigger at Q4 position %d/%d, confirmed=%d rows, balanced pool=%d rows",
        trigger_pos_q4, len(q4), len(confirmed_q4), len(balanced_q4),
    )

    pool_v21 = pd.concat([pool_v2, balanced_q4], ignore_index=True).drop_duplicates(
        subset="query_canonical"
    )
    m2 = train_model(pool_v21, tfidf_cfg, seed, name="M2 (candidate@2.1, minor bump)")
    eval_m2 = evaluate_on(m2, golden, model_version="M2", data_version="2.1")
    champion_eval_for_minor = eval_m1 if m1_is_champion else evaluate_on(
        champion_after_q3, golden, model_version="M0", data_version="2.0"
    )
    decision_minor = evaluate_gate(
        eval_m2, champion_eval_for_minor, max_per_class_recall_drop=max_drop,
        min_new_class_recall=min_new_recall, golden_version="2",
    )
    append_decision(decision_minor, artifacts / "decisions.jsonl")
    logger.info("Minor bump: gate=%s — %s", decision_minor.verdict, decision_minor.reason)

    minor_result: dict[str, Any] = {
        "trigger_position": trigger_pos_q4,
        "confirmed_pool_rows": len(confirmed_q4),
        "confirmed_pool_class_mix": confirmed_q4["label_name"].value_counts().to_dict(),
        "balanced_pool_rows": len(balanced_q4),
        "candidate": eval_m2.to_dict(),
        "gate_decision": decision_minor.to_dict(),
    }

    m2_is_champion = False
    if decision_minor.promoted:
        shadow_tail = q4.iloc[trigger_pos_q4 + 1 : trigger_pos_q4 + 1 + shadow_window]
        if len(shadow_tail) == 0:
            minor_result["shadow"] = {"note": "no remaining Q4 traffic to shadow on"}
        else:
            shadow_preds = m2.predict(shadow_tail["query_canonical"])
            shadow_eval = compute_evaluation(
                shadow_tail["label_name"].tolist(), shadow_preds.tolist(),
                model_version="M2-shadow", data_version="2.1",
            )
            fpr_ok = shadow_eval.fpr <= champion_eval_for_minor.fpr + shadow_fpr_tolerance
            f1_ok = shadow_eval.f1_macro >= eval_m2.f1_macro - 0.02
            m2_is_champion = fpr_ok and f1_ok
            minor_result["shadow"] = {
                "n": len(shadow_tail),
                "fpr": round(shadow_eval.fpr, 6),
                "fpr_tolerance_ceiling": round(champion_eval_for_minor.fpr + shadow_fpr_tolerance, 6),
                "f1_macro": round(shadow_eval.f1_macro, 6),
                "passed": m2_is_champion,
            }
    minor_result["lifecycle"] = (
        f"{'M1' if m1_is_champion else 'M0'} retired, M2 champion after shadow"
        if m2_is_champion
        else f"M2 {'discarded after shadow' if decision_minor.promoted else 'rejected by gate'}; "
        f"{'M1' if m1_is_champion else 'M0'} remains champion"
    )
    results["act2_minor_bump"] = minor_result

    # ── Drift monitor over Q4, against the champion after Q3 ────────────────
    q4_reference_mask = np.zeros(len(q4), dtype=bool)
    q4_reference_mask[: min(len(q4), int(2 * window_size))] = True
    drift_q4 = monitor_drift(
        q4, champion_after_q3, label="Q4 (minor-bump pour, vs post-Q3 champion)",
        reference_mask=q4_reference_mask, window_size=window_size, psi_bins=psi_bins,
        threshold=threshold, sustained=sustained,
    )
    results["drift_q4"] = drift_q4

    results["final_champion"] = "M2" if m2_is_champion else ("M1" if m1_is_champion else "M0")
    results["caveats"] = [
        f"'{held_out}' is a real SQLi class, subsampled to {len(golden_held) + (results['act1_major_bump']['confirmed_pool_class_mix'].get(held_out, 0))}"
        " rows for this experiment's stream given the ~8.7K-row usable benign-padding budget"
        " (data/processed/branch2_normal.csv minus Branch-1/Branch-2 training overlap);"
        " its full corpus (15,000 rows) is not exhausted.",
        "Labelling is simulated: ground truth stands in for a human reviewer, as in the"
        " original mlops_contract.md design.",
        "Traffic composition (attack rate per pour) is set by the available benign-padding"
        " budget, not by an attempt to match a specific real-world attack rate.",
        "Branch 2 is trained once and never retrained, matching the zero-day study"
        " (report/metrics/zeroday_experiment): it is benign-only and blind to attack labels.",
    ]

    with (artifacts / "experiment_results.json").open("w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
    logger.info("=== Experiment complete — artifacts in %s ===", artifacts)
    logger.info("Final champion: %s", results["final_champion"])


if __name__ == "__main__":
    main()
