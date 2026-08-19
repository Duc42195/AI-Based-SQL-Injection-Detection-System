"""End-to-end continual-learning experiment: drift → label → retrain → gate.

Implements Part 2 of ``report/plan/mlops_contract.md``.

The run has two acts and two controls:

* **Act 1 — major bump.** A new class (`stacked`) appears mid-stream. The label
  space changes, so no comparable predecessor exists and the gate promotes
  directly rather than producing a meaningless comparison.
* **Act 2 — minor bump.** More samples of *known* classes are confirmed. The
  label space is unchanged, so the candidate is compared against the champion
  on the frozen golden set and must earn promotion.
* **Control arm.** A candidate retrained on the same *number* of extra samples
  but containing no new class. If it closes the gap too, the improvement came
  from data volume rather than from learning the class.
* **Negative control.** A candidate trained with rehearsal starved, which must
  be *rejected* for per-class regression. A gate that only ever approves
  demonstrates nothing.

Run:  uv run python train/run_continual_learning_experiment.py
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
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
from src.continual_learning.versioning import (
    compute_run_id,
    content_hash,
    git_sha,
    hash_ids,
    load_registry,
)
from src.decision.queue import ReviewItem, ReviewQueue, append_confirmed
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

ROUND_ID = "experiment"
# Kept intentionally SEPARATE from branch2_anomaly.features — see
# deploy/routers/mlops.py's identical constant for why, and keep both in
# sync by hand when the model's feature set changes.
FEATURES = ["length", "special_char_ratio", "entropy", "quote_imbalance"]

# Drift signals compared side by side. The point of running all five is to find
# out which, if any, notices a new attack class that is only ~1 % of traffic.
SIGNALS = (
    "global",  # structural features, all traffic
    "attack_subpop",  # structural features, flagged traffic only
    "prediction",  # predicted-class distribution
    "confidence",  # top-class confidence, all traffic
    "confidence_flagged",  # top-class confidence, flagged traffic only
)


# --------------------------------------------------------------------------- #
# Model
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
        """Fit and return the training duration in seconds."""
        started = time.perf_counter()
        matrix = self._vectorizer.fit_transform(texts.astype(str))
        self._clf.fit(matrix, labels.to_numpy())
        return time.perf_counter() - started

    def predict(self, texts: pd.Series) -> np.ndarray:
        """Predict label names."""
        return self._clf.predict(self._vectorizer.transform(texts.astype(str)))

    def predict_with_confidence(self, texts: pd.Series) -> tuple[np.ndarray, np.ndarray]:
        """Predict label names plus the top-class probability."""
        matrix = self._vectorizer.transform(texts.astype(str))
        probabilities = self._clf.predict_proba(matrix)
        indices = probabilities.argmax(axis=1)
        return self._clf.classes_[indices], probabilities.max(axis=1)


def train_model(
    data: pd.DataFrame, tfidf_cfg: dict, seed: int, *, name: str
) -> tuple[Classifier, float]:
    """Train a classifier on ``query_canonical`` → ``label_name``."""
    model = Classifier(tfidf_cfg, seed)
    duration = model.fit(data["query_canonical"], data["label_name"])
    logger.info(
        "Trained %-22s on %s rows (%d classes) in %.1fs",
        name,
        f"{len(data):,}",
        data["label_name"].nunique(),
        duration,
    )
    return model, duration


def evaluate_on(
    model: Classifier, golden: pd.DataFrame, *, model_version: str, data_version: str
) -> ModelEvaluation:
    """Score a model on a golden set."""
    return compute_evaluation(
        golden["label_name"].tolist(),
        model.predict(golden["query_canonical"]).tolist(),
        model_version=model_version,
        data_version=data_version,
    )


# --------------------------------------------------------------------------- #
# Drift over the replay stream
# --------------------------------------------------------------------------- #
def feature_frame(texts: pd.Series) -> pd.DataFrame:
    """Extract the drift-monitored structural features for a set of queries.

    Selects by name (FEATURES may be a different subset than
    StatisticalFeatures.as_list()'s full FEATURE_ORDER — see FEATURES'
    definition above for why they're kept separate).
    """
    rows = [extract_statistical_features(str(t)).as_dict() for t in texts]
    return pd.DataFrame(rows, columns=FEATURES)


def replay_stream(
    stream: pd.DataFrame,
    champion: Classifier,
    *,
    window_size: int,
    baseline_windows: int,
    psi_bins: int,
    threshold: float,
    sustained: int,
) -> dict[str, Any]:
    """Replay the stream window by window, computing drift on three populations.

    The reference is the **first ``baseline_windows`` windows of the stream
    itself**, not the training set. The training file is class-balanced (~78 %
    attack) while the stream is ~95 % benign, so scoring against it would report
    that construction difference as drift from window 0. Baselining on an
    initial stable production period is also what a real deployment does.

    Global feature PSI, attack-subpopulation PSI and prediction PSI are computed
    side by side precisely so their disagreement can be reported: at a 5 %
    attack rate a new class is ~1 % of traffic, which global monitoring may
    never see.
    """
    logger.info("Scoring %s stream queries…", f"{len(stream):,}")
    predictions, confidences = champion.predict_with_confidence(stream["query_canonical"])
    stream = stream.assign(predicted=predictions, confidence=confidences)
    features = feature_frame(stream["query_canonical"])

    n_reference = min(baseline_windows * window_size, len(stream))
    reference = stream.iloc[:n_reference]
    reference_features = features.iloc[:n_reference]
    reference_predictions = reference["predicted"].tolist()
    if (reference["phase"] != "A").any():  # pragma: no cover - config sanity
        logger.warning(
            "Baseline period reaches into phase B; drift will be understated. "
            "Reduce mlops.drift.baseline_windows."
        )
    logger.info(
        "Drift reference: first %d windows (%s queries, %.1f%% attack)",
        baseline_windows,
        f"{n_reference:,}",
        float((reference["label_name"] != "normal").mean()) * 100,
    )

    reference_bins = {
        name: fit_reference_bins(reference_features[name], feature=name, n_bins=psi_bins)
        for name in FEATURES
    }
    flagged_reference = reference_features[
        (reference["predicted"] != "normal").to_numpy()
    ]
    attack_bins: dict[str, ReferenceBins] = {}
    if len(flagged_reference) >= psi_bins:
        attack_bins = {
            name: fit_reference_bins(flagged_reference[name], feature=name, n_bins=psi_bins)
            for name in FEATURES
        }
    # Confidence is the signal with a mechanism behind it: a classifier meeting a
    # class it was never trained on has no good answer and should hedge. Unlike
    # the feature signals it needs no labels, so it is deployable as-is.
    #
    # Each population gets its OWN reference. Scoring flagged confidence against
    # all-traffic confidence bins compares two different populations and reports
    # that mismatch as permanent drift.
    confidence_bins = fit_reference_bins(
        reference["confidence"], feature="confidence", n_bins=psi_bins
    )
    flagged_reference_mask = (reference["predicted"] != "normal").to_numpy()
    flagged_confidence_bins = (
        fit_reference_bins(
            reference.loc[flagged_reference_mask, "confidence"],
            feature="confidence_flagged",
            n_bins=psi_bins,
        )
        if flagged_reference_mask.sum() >= psi_bins
        else confidence_bins
    )

    windows: list[dict[str, Any]] = []
    for index, start, stop in iter_windows(len(stream), window_size):
        chunk = stream.iloc[start:stop]
        chunk_features = features.iloc[start:stop]
        flagged = chunk["predicted"] != "normal"

        global_psi = float(
            np.mean([psi_from_reference(chunk_features[f], reference_bins[f]) for f in FEATURES])
        )

        if attack_bins and flagged.sum() >= 5:
            attack_features = chunk_features[flagged.to_numpy()]
            attack_psi = float(
                np.mean(
                    [psi_from_reference(attack_features[f], attack_bins[f]) for f in FEATURES]
                )
            )
        else:
            attack_psi = 0.0

        prediction_psi = psi_categorical(reference_predictions, chunk["predicted"].tolist())
        confidence_psi = psi_from_reference(chunk["confidence"], confidence_bins)
        # Confidence restricted to flagged traffic: a novel attack class hides
        # inside the 5% of traffic that is attacks, so the whole-stream view
        # dilutes it ~20x.
        if flagged.sum() >= 5:
            flagged_confidence_psi = psi_from_reference(
                chunk.loc[flagged, "confidence"], flagged_confidence_bins
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
                "phase": chunk["phase"].iloc[0],
                "is_reference": stop <= n_reference,
                "n": len(chunk),
                "psi": signals,
                "rates": {
                    "block": round(float(flagged.mean()), 6),
                    "low_confidence": round(float((chunk["confidence"] < 0.6).mean()), 6),
                    "mean_confidence": round(float(chunk["confidence"].mean()), 6),
                },
                "alert": bool(max(signals.values()) >= threshold),
            }
        )

    trigger = detect_trigger(
        windows, threshold=threshold, sustained=sustained, signals=tuple(SIGNALS)
    )
    return {"stream": stream, "windows": windows, "trigger": trigger}


# --------------------------------------------------------------------------- #
# Labelling (simulated at experiment scale — see contract §6)
# --------------------------------------------------------------------------- #
def harvest_and_confirm(
    stream: pd.DataFrame, queue: ReviewQueue, confirmed_path: Path, *, low_confidence: float
) -> pd.DataFrame:
    """Queue flagged queries with their AI pre-label, then auto-confirm them.

    At 80k queries no human can review every item, so ground truth stands in for
    the reviewer. This is *simulated labelling* and is reported as such; the UI
    exercises the identical path with a real human on a sample.
    """
    flagged = stream[
        (stream["predicted"] != "normal") | (stream["confidence"] < low_confidence)
    ]
    items = [
        ReviewItem(
            id=str(row.id),
            query_raw=str(row.query_raw),
            query_canonical=str(row.query_canonical),
            source="block" if row.predicted != "normal" else "low_confidence",
            ai_label=str(row.predicted),
            ai_confidence=float(row.confidence),
            round_id=ROUND_ID,
        )
        for row in flagged.itertuples()
    ]
    queue.enqueue(items)

    # The "reviewer" accepts the pre-label when it matches ground truth and
    # corrects it otherwise — which is what makes the acceptance rate a real
    # measure of model quality rather than a formality.
    truth = dict(zip(flagged["id"].astype(str), flagged["label_name"].astype(str)))
    decided: list[ReviewItem] = []
    for item in items:
        actual = truth[item.id]
        decided.append(
            queue.decide(item.id, "correct", label=actual, decided_by="ground_truth")
        )
    append_confirmed(decided, confirmed_path)

    logger.info(
        "Harvested %s flagged queries; pre-label acceptance rate %.1f%%",
        f"{len(items):,}",
        (queue.acceptance_rate() or 0.0) * 100,
    )
    return flagged


def build_retrain_pool(
    base: pd.DataFrame, new_rows: pd.DataFrame, rehearsal_fraction: float, seed: int
) -> pd.DataFrame:
    """Mix newly confirmed rows with a rehearsal sample of the original data."""
    if rehearsal_fraction <= 0:
        return new_rows.copy()
    n_old = int(len(base) * rehearsal_fraction)
    rehearsal = base.sample(n=min(n_old, len(base)), random_state=seed)
    return pd.concat([rehearsal, new_rows], ignore_index=True)


def balance_by_class(data: pd.DataFrame, seed: int, cap: int | None = None) -> pd.DataFrame:
    """Down-sample every class to the size of the smallest (or ``cap``).

    Confirmed traffic is heavily skewed — most flagged queries are benign false
    positives — so feeding it in raw shifts the decision boundary toward
    ``normal`` and costs attack recall. Balancing is the obvious engineering
    fix, and the experiment reports both so the difference is visible.
    """
    counts = data["label_name"].value_counts()
    target = int(counts.min() if cap is None else min(counts.min(), cap))
    # Built by explicit concatenation rather than groupby().apply(), which in
    # pandas 2.x can drop the grouping column and yield NaN labels.
    parts = [
        group.sample(n=min(len(group), target), random_state=seed)
        for _, group in data.groupby("label_name", sort=True)
    ]
    return pd.concat(parts, ignore_index=True)


# --------------------------------------------------------------------------- #
# Experiment
# --------------------------------------------------------------------------- #
def main() -> None:
    """Run both acts plus the control arms and write every artifact."""
    cfg = load_config()
    processed = Path(cfg.get_path("paths.data_processed", "data/processed"))
    artifacts = Path(cfg.get_path("mlops.artifacts_dir", "report/metrics/continual_learning"))
    artifacts.mkdir(parents=True, exist_ok=True)

    seed = int(cfg.get_path("mlops.split.seed", 42))
    tfidf_cfg = dict(cfg.get_path("branch1_supervised.tfidf"))
    window_size = int(cfg.get_path("mlops.stream.window_size", 1000))
    psi_bins = int(cfg.get_path("mlops.drift.psi_bins", 10))
    baseline_windows = int(cfg.get_path("mlops.drift.baseline_windows", 10))
    threshold = float(cfg.get_path("monitoring.psi_alert_threshold", 0.2))
    sustained = int(cfg.get_path("mlops.drift.sustained_windows", 2))
    rehearsal = float(cfg.get_path("continual_learning.rehearsal_old_fraction", 0.5))
    low_confidence = float(cfg.get_path("mlops.queue.low_confidence_below", 0.6))
    max_drop = float(cfg.get_path("mlops.gate.max_per_class_recall_drop", 0.02))
    min_new_recall = float(cfg.get_path("mlops.gate.min_new_class_recall", 0.80))

    df = pd.read_csv(processed / "branch1_mlops_split.csv")
    stream = pd.read_csv(processed / "mlops_stream.csv")
    stacked_pool = pd.read_csv(processed / "mlops_stacked_pool.csv")

    train_df = df[df["partition"] == "train"]
    valid_df = df[df["partition"] == "valid"]
    golden_v1 = df[df["partition"] == "golden"]
    # golden@2 is a SUPERSET: identical golden@1 rows plus the new class, so
    # "no regression on known classes" stays an exact comparison (contract §1).
    golden_v2 = pd.concat(
        [golden_v1, stacked_pool[stacked_pool["partition"] == "golden"]], ignore_index=True
    )

    # The experiment keeps its own lineage under the artifacts directory. Writing
    # into the service's registry would mix offline experiment versions with the
    # versions actually deployed, and the gate would then compare a live model
    # against a version no deployed model was ever trained on.
    from src.continual_learning.versioning import VersionRegistry

    registry = VersionRegistry(artifacts / "version_registry.json", dataset="branch1")
    if registry.get("1.0") is None:
        service_registry = load_registry("branch1", cfg)
        baseline = service_registry.get("1.0")
        if baseline is not None:
            registry.seal(
                label_space=baseline.label_space,
                n_rows=baseline.n_rows,
                content_hash_value=baseline.content_hash,
                reason="baseline copied from the service registry",
                partitions=baseline.partitions,
                golden_hash=baseline.golden_hash,
                protected=True,
            )
    results: dict[str, Any] = {"acts": {}, "controls": {}}

    # ── Champion: trained on train@1.0 ─────────────────────────────────────
    # NOT models/branch1_v1 — that model saw rows now in golden (contract §4.0).
    champion, duration = train_model(train_df, tfidf_cfg, seed, name="champion@1.0")
    champion_eval = evaluate_on(
        champion, golden_v1, model_version="champion", data_version="1.0"
    )
    logger.info(
        "champion on golden@1: F1-macro=%.4f FPR=%.4f",
        champion_eval.f1_macro,
        champion_eval.fpr,
    )

    run_id = compute_run_id(
        tfidf_cfg, content_hash(zip(train_df["id"], train_df["label"])), seed
    )
    results["champion"] = {
        **champion_eval.to_dict(),
        "run_id": run_id,
        "git_sha": git_sha(),
        "train_rows": len(train_df),
        "valid_rows": len(valid_df),
        "valid_ids_hash": hash_ids(valid_df["id"]),
        "duration_s": round(duration, 2),
    }

    # ── Drift: replay the stream against the champion ──────────────────────
    replay = replay_stream(
        stream,
        champion,
        window_size=window_size,
        baseline_windows=baseline_windows,
        psi_bins=psi_bins,
        threshold=threshold,
        sustained=sustained,
    )
    scored_stream, windows, trigger = replay["stream"], replay["windows"], replay["trigger"]

    # Reference windows score ~0 against themselves by construction, so the
    # honest "quiet period" is phase A *after* the baseline.
    phase_a = [w for w in windows if w["phase"] == "A" and not w["is_reference"]]
    phase_b = [w for w in windows if w["phase"] == "B"]
    drift_summary = {
        signal: {
            "phase_a_mean": round(float(np.mean([w["psi"][signal] for w in phase_a])), 6),
            "phase_a_max": round(float(np.max([w["psi"][signal] for w in phase_a])), 6),
            "phase_b_mean": round(float(np.mean([w["psi"][signal] for w in phase_b])), 6),
            "phase_b_max": round(float(np.max([w["psi"][signal] for w in phase_b])), 6),
            "quiet_in_phase_a": all(w["psi"][signal] < threshold for w in phase_a),
            "fired_in_phase_b": any(w["psi"][signal] >= threshold for w in phase_b),
            "phase_b_over_phase_a": round(
                float(
                    np.mean([w["psi"][signal] for w in phase_b])
                    / max(np.mean([w["psi"][signal] for w in phase_a]), 1e-9)
                ),
                3,
            ),
        }
        for signal in SIGNALS
    }
    for signal, stats in drift_summary.items():
        logger.info(
            "drift %-19s A mean=%.4f | B mean=%.4f max=%.4f | B/A=%.1fx | fired=%s",
            signal,
            stats["phase_a_mean"],
            stats["phase_b_mean"],
            stats["phase_b_max"],
            stats["phase_b_over_phase_a"],
            stats["fired_in_phase_b"],
        )

    with (artifacts / "drift.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "data_version": "1.0",
                "reference": f"stream baseline: first {baseline_windows} windows",
                "baseline_windows": baseline_windows,
                "psi_bins": psi_bins,
                "threshold": threshold,
                "sustained_windows": sustained,
                "summary": drift_summary,
                "windows": windows,
                "trigger": trigger.to_dict(),
            },
            handle,
            indent=2,
        )

    # ── Labelling: harvest flagged queries, confirm them ───────────────────
    queue_path = artifacts / "experiment_queue.db"
    queue_path.unlink(missing_ok=True)
    queue = ReviewQueue(queue_path)
    confirmed_path = artifacts / "experiment_confirmed_labels.jsonl"
    confirmed_path.unlink(missing_ok=True)
    flagged = harvest_and_confirm(
        scored_stream, queue, confirmed_path, low_confidence=low_confidence
    )
    acceptance_rate = queue.acceptance_rate()

    columns = ["id", "query_raw", "query_canonical", "label", "label_name"]
    confirmed_new_class = flagged[flagged["label_name"] == "stacked"][columns]
    confirmed_known = flagged[flagged["label_name"] != "stacked"][columns]

    # ── ACT 1: major bump → direct promotion ───────────────────────────────
    # A data version is the accumulated dataset: version 2.0 is everything 1.0
    # held plus the newly confirmed class. (Rehearsal-style sub-sampling is what
    # the negative control uses to show forgetting; using it here would make
    # every round discard half its history, which degrades the model by
    # construction rather than by any property of continual learning.)
    logger.info("=== ACT 1 — major bump (new class '%s') ===", "stacked")
    pool_v2 = pd.concat(
        [train_df[columns], confirmed_new_class], ignore_index=True
    ).drop_duplicates(subset="query_canonical")
    model_v2, _ = train_model(pool_v2, tfidf_cfg, seed, name="candidate@2.0")
    eval_v2 = evaluate_on(model_v2, golden_v2, model_version="branch1_v2", data_version="2.0")

    decision_1 = evaluate_gate(
        eval_v2,
        champion_eval,
        max_per_class_recall_drop=max_drop,
        min_new_class_recall=min_new_recall,
        golden_version="2",
    )
    append_decision(decision_1, artifacts / "decisions.jsonl")
    logger.info("ACT 1 verdict: %s (%s)", decision_1.verdict, decision_1.comparison)

    registry.seal(
        label_space=sorted(pool_v2["label_name"].astype(str).unique()),
        n_rows=len(pool_v2),
        content_hash_value=content_hash(zip(pool_v2["id"], pool_v2["label"])),
        reason="new class 'stacked' confirmed from the stream",
        partitions={"train": len(pool_v2), "golden": len(golden_v2)},
        golden_hash=content_hash(zip(golden_v2["id"], golden_v2["label"])),
    )
    results["acts"]["act1_major"] = {
        "candidate": eval_v2.to_dict(),
        "decision": decision_1.to_dict(),
        "new_class_recall": eval_v2.per_class_recall.get("stacked"),
    }

    # ── ACT 2: minor bump → full gate, two ways of building the pool ───────
    # Confirmed traffic is dominated by benign false positives, so feeding it in
    # raw is the obvious-but-wrong thing to do. Both variants are run so the
    # gate can be seen distinguishing them.
    logger.info("=== ACT 2 — minor bump (more of the known classes) ===")
    act2: dict[str, Any] = {}

    for variant, extra in (
        ("naive", confirmed_known.sample(frac=1.0, random_state=seed)),
        ("balanced", balance_by_class(confirmed_known, seed)),
    ):
        pool = pd.concat([pool_v2, extra], ignore_index=True).drop_duplicates(
            subset="query_canonical"
        )
        model, _ = train_model(pool, tfidf_cfg, seed, name=f"candidate@2.1 ({variant})")
        evaluation = evaluate_on(
            model,
            golden_v2,
            model_version=f"branch1_v2_1_{variant}",
            data_version="2.1",
        )
        decision = evaluate_gate(
            evaluation,
            eval_v2,
            max_per_class_recall_drop=max_drop,
            min_new_class_recall=min_new_recall,
            golden_version="2",
        )
        append_decision(decision, artifacts / "decisions.jsonl")
        logger.info(
            "ACT 2 [%s] verdict: %s — %s", variant, decision.verdict, decision.reason
        )
        act2[variant] = {
            "pool_rows": len(pool),
            "extra_rows": len(extra),
            "extra_class_mix": extra["label_name"].value_counts().to_dict(),
            "candidate": evaluation.to_dict(),
            "decision": decision.to_dict(),
        }
        if variant == "balanced" and decision.promoted:
            model_v2_1 = model

    act2["interpretation"] = (
        "Retraining on raw confirmed traffic skews the class balance toward "
        "`normal` (most flagged queries are false positives) and costs attack "
        "recall; the gate rejects it. Balancing the confirmed pool first is "
        "what earns promotion."
    )
    results["acts"]["act2_minor"] = act2

    # ── CONTROL: same extra volume, no new class ───────────────────────────
    logger.info("=== CONTROL — same sample count, no new class ===")
    control_extra = confirmed_known.sample(
        n=min(len(confirmed_new_class), len(confirmed_known)), random_state=seed
    )
    pool_control = build_retrain_pool(train_df[columns], control_extra, rehearsal, seed)
    model_control, _ = train_model(pool_control, tfidf_cfg, seed, name="control (no new class)")
    eval_control = evaluate_on(
        model_control, golden_v2, model_version="control", data_version="1.1"
    )
    results["controls"]["volume_control"] = {
        **eval_control.to_dict(),
        "new_class_recall": eval_control.per_class_recall.get("stacked", 0.0),
        "extra_rows": len(control_extra),
        "interpretation": (
            "If this closes the new-class gap, the gain came from data volume "
            "rather than from learning the class."
        ),
    }

    # ── NEGATIVE CONTROL: starved rehearsal must be rejected ───────────────
    # A token amount of old data rather than none: with none the pool is a
    # single class and cannot be fitted at all, which would demonstrate nothing
    # about forgetting.
    starved_fraction = 0.01
    logger.info(
        "=== NEGATIVE CONTROL — rehearsal starved (%.0f%% of old data) ===",
        starved_fraction * 100,
    )
    pool_starved = build_retrain_pool(
        train_df[columns], confirmed_new_class, starved_fraction, seed
    )
    model_starved, _ = train_model(pool_starved, tfidf_cfg, seed, name="starved (no rehearsal)")
    eval_starved = evaluate_on(
        model_starved, golden_v2, model_version="starved", data_version="2.1"
    )
    decision_starved = evaluate_gate(
        eval_starved,
        eval_v2,
        max_per_class_recall_drop=max_drop,
        min_new_class_recall=min_new_recall,
        golden_version="2",
    )
    append_decision(decision_starved, artifacts / "decisions.jsonl")
    logger.info(
        "NEGATIVE CONTROL verdict: %s — %s", decision_starved.verdict, decision_starved.reason
    )
    results["controls"]["starved_rehearsal"] = {
        **eval_starved.to_dict(),
        "rehearsal_fraction": starved_fraction,
        "decision": decision_starved.to_dict(),
        "interpretation": (
            "Retraining almost entirely on the new class makes the model forget "
            "the old ones; the gate must reject it on per-class regression."
        ),
    }

    # ── Shadow: champion enforced, candidate logged ────────────────────────
    logger.info("=== SHADOW — champion enforced, candidate logged ===")
    phase_b_stream = scored_stream[scored_stream["phase"] == "B"]
    champion_pred = phase_b_stream["predicted"].to_numpy()
    started = time.perf_counter()
    candidate_pred = model_v2.predict(phase_b_stream["query_canonical"])
    latency_ms = (time.perf_counter() - started) / max(len(phase_b_stream), 1) * 1000

    agreement = float((champion_pred == candidate_pred).mean())
    champion_blocks = champion_pred != "normal"
    candidate_blocks = candidate_pred != "normal"
    shadow = {
        "rows": len(phase_b_stream),
        "agreement_rate": round(agreement, 6),
        "candidate_allows_champion_blocks": int((champion_blocks & ~candidate_blocks).sum()),
        "candidate_blocks_champion_allows": int((~champion_blocks & candidate_blocks).sum()),
        "champion_block_rate": round(float(champion_blocks.mean()), 6),
        "candidate_block_rate": round(float(candidate_blocks.mean()), 6),
        "mean_latency_ms_per_query": round(latency_ms, 4),
    }
    logger.info(
        "shadow: agreement=%.2f%% | candidate allows %d that champion blocked",
        agreement * 100,
        shadow["candidate_allows_champion_blocks"],
    )
    with (artifacts / "shadow.json").open("w", encoding="utf-8") as handle:
        json.dump(shadow, handle, indent=2)

    # ── Persist ────────────────────────────────────────────────────────────
    registry.save()
    results["labelling"] = {
        "flagged_queries": len(flagged),
        "pre_label_acceptance_rate": round(acceptance_rate or 0.0, 6),
        "confirmed_new_class": len(confirmed_new_class),
        "confirmed_known_classes": len(confirmed_known),
        "note": "Labelling is simulated at this scale: ground truth stands in for a reviewer.",
    }
    results["drift"] = {"summary": drift_summary, "trigger": trigger.to_dict()}
    results["shadow"] = shadow
    results["caveats"] = [
        "'stacked' is 100% synthetic (363 templated payloads): the major-bump "
        "mechanism is demonstrated, its accuracy is not a detection result.",
        "Labelling is simulated; the UI exercises the same path with a human.",
        "Traffic is a replay of held-out data, not live production traffic.",
        "~13% label noise in boolean_blind (report/plan/data_contract.md).",
    ]

    with (artifacts / "experiment_results.json").open("w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)

    logger.info("=== Experiment complete — artifacts in %s ===", artifacts)


if __name__ == "__main__":
    main()
