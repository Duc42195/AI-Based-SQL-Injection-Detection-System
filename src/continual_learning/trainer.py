"""Train, seal and promote a Branch-1 model from a versioned dataset.

Implements section 7 of ``report/plan/mlops_contract.md`` (sealing and
promotion) for the live service, so pressing *Train* in the UI does what the
offline experiment does rather than simulating it.

The order of operations is what makes a run reproducible and idempotent:

1. assemble the dataset — the version's training partition plus every confirmed
   label for the round;
2. infer the version bump from the label space (new class → major);
3. compute the ``run_id`` from *(config, data digest, seed)* and look it up —
   an identical run that already completed is reported, not repeated;
4. train, write ``model.joblib`` / ``vectorizer.joblib`` / ``metadata.json`` /
   ``run_manifest.json`` in the layout ``deploy.registry`` already loads;
5. leave promotion to the caller, which applies the gate first.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from src.continual_learning.gate import ModelEvaluation, compute_evaluation
from src.continual_learning.versioning import (
    compute_run_id,
    content_hash,
    git_sha,
    hash_ids,
    load_registry,
)
from src.decision.queue import confirmed_labels_path, read_confirmed
from src.utils import get_logger, load_config

logger = get_logger(__name__)

RUN_MANIFEST = "run_manifest.json"
RUNS_LOG = "runs.jsonl"


@dataclass
class TrainOutcome:
    """Result of a training request."""

    status: str  # "completed" | "exists" | "failed"
    run_id: str
    model_version: str | None = None
    data_version: str | None = None
    bump: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    duration_s: float = 0.0
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the API layer."""
        return {
            "status": self.status,
            "run_id": self.run_id,
            "model_version": self.model_version,
            "data_version": self.data_version,
            "bump": self.bump,
            "metrics": self.metrics,
            "duration_s": round(self.duration_s, 3),
            "detail": self.detail,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def find_run(run_id: str, runs_log: Path) -> dict[str, Any] | None:
    """Return a completed run with this id, or ``None``.

    This is the check that makes *Train* idempotent: the same configuration on
    the same data does not silently retrain.
    """
    if not runs_log.exists():
        return None
    with runs_log.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:  # pragma: no cover - truncated write
                continue
            if record.get("run_id") == run_id and record.get("status") == "completed":
                return record
    return None


def assemble_dataset(cfg=None, round_id: str | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Return the training rows for the next version, plus their label space.

    The next version is the current training partition plus every confirmed
    label — that is what "a new data version" means here, and it is why the
    bump can be inferred rather than chosen.
    """
    cfg = cfg or load_config()
    processed = Path(cfg.get_path("paths.data_processed", "data/processed"))
    split = pd.read_csv(processed / "branch1_mlops_split.csv")
    base = split[split["partition"] == "train"][
        ["id", "query_raw", "query_canonical", "label", "label_name"]
    ].copy()

    confirmed = read_confirmed(confirmed_labels_path(cfg), round_id=round_id)
    if confirmed:
        extra = pd.DataFrame(
            [
                {
                    "id": record["id"],
                    "query_raw": record.get("query_canonical", ""),
                    "query_canonical": record["query_canonical"],
                    "label": record.get("label_id"),
                    "label_name": record["label"],
                }
                for record in confirmed
            ]
        )
        base = pd.concat([base, extra], ignore_index=True).drop_duplicates(
            subset="query_canonical", keep="last"
        )
        logger.info("Added %d confirmed labels to the training pool", len(extra))

    return base, sorted(base["label_name"].astype(str).unique())


def train_and_seal(
    *,
    cfg=None,
    round_id: str | None = None,
    force: bool = False,
) -> TrainOutcome:
    """Seal the next data version and train a model on it.

    Args:
        cfg: Optional pre-loaded config.
        round_id: Restrict confirmed labels to one demo round.
        force: Retrain even if an identical run already completed.

    Returns:
        A :class:`TrainOutcome`; ``status="exists"`` means an identical run was
        found and nothing was retrained.
    """
    cfg = cfg or load_config()
    seed = int(cfg.get_path("mlops.split.seed", 42))
    tfidf_cfg = dict(cfg.get_path("branch1_supervised.tfidf"))
    models_dir = Path(cfg.get_path("paths.models_dir", "models"))
    artifacts = Path(cfg.get_path("mlops.artifacts_dir", "report/metrics/continual_learning"))
    artifacts.mkdir(parents=True, exist_ok=True)
    valid_fraction = float(cfg.get_path("mlops.split.valid_fraction", 0.15))

    data, label_space = assemble_dataset(cfg, round_id)
    digest = content_hash(zip(data["id"], data["label_name"]))
    run_id = compute_run_id(tfidf_cfg, digest, seed)

    existing = find_run(run_id, artifacts / RUNS_LOG)
    if existing and not force:
        logger.info("Run %s already completed — skipping retrain", run_id)
        return TrainOutcome(
            status="exists",
            run_id=run_id,
            model_version=existing.get("model_version"),
            data_version=existing.get("data_version"),
            metrics=existing.get("metrics", {}),
            detail=(
                "An identical run (same config, data and seed) already completed. "
                "Nothing was retrained."
            ),
        )

    # Seal the version; the bump follows from the label space.
    registry = load_registry("branch1", cfg)
    parent = registry.latest()
    try:
        version = registry.seal(
            label_space=label_space,
            n_rows=len(data),
            content_hash_value=digest,
            reason=f"train run {run_id}",
            partitions={"train": len(data)},
        )
    except ValueError:
        # Identical content is already sealed: reuse that version rather than
        # failing, since the data genuinely has not changed.
        version = next(v for v in registry.versions if v.content_hash == digest)
        logger.info("Data unchanged; reusing sealed version %s", version.version)
    else:
        registry.save()

    model_version = f"branch1_v{version.version.replace('.', '_')}"
    model_dir = models_dir / model_version
    model_dir.mkdir(parents=True, exist_ok=True)

    # Hold out a validation slice; `golden` is never touched by training.
    validation = data.sample(frac=valid_fraction, random_state=seed)
    training = data.drop(validation.index)

    started = time.perf_counter()
    vectorizer = TfidfVectorizer(
        analyzer=tfidf_cfg["analyzer"],
        ngram_range=(tfidf_cfg["ngram_min"], tfidf_cfg["ngram_max"]),
        max_features=tfidf_cfg["max_features"],
    )
    matrix = vectorizer.fit_transform(training["query_canonical"].astype(str))
    classifier = LogisticRegression(max_iter=1000, random_state=seed)
    classifier.fit(matrix, training["label_name"].to_numpy())
    duration = time.perf_counter() - started

    evaluation = compute_evaluation(
        validation["label_name"].tolist(),
        classifier.predict(
            vectorizer.transform(validation["query_canonical"].astype(str))
        ).tolist(),
        model_version=model_version,
        data_version=version.version,
    )

    joblib.dump(vectorizer, model_dir / "vectorizer.joblib")
    joblib.dump(classifier, model_dir / "model.joblib")
    metadata = {
        "version": model_version,
        "branch": "branch1_supervised_multiclass",
        "architecture": "tfidf_logreg",
        "trained_at": _now(),
        "data_version": version.version,
        "run_id": run_id,
        "state": "trained",
        "protected": False,
        "labels": label_space,
        "f1_macro": round(evaluation.f1_macro, 6),
    }
    with (model_dir / "metadata.json").open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)

    manifest = {
        "run_id": run_id,
        "git_sha": git_sha(),
        "created_at": _now(),
        "status": "completed",
        "model_version": model_version,
        "data_version": version.version,
        "data_content_hash": digest,
        "train_config": tfidf_cfg,
        "split": {
            "method": "random_holdout",
            "seed": seed,
            "train_rows": len(training),
            "valid_rows": len(validation),
            "train_ids_hash": hash_ids(training["id"]),
            "valid_ids_hash": hash_ids(validation["id"]),
        },
        "metrics": {
            "f1_macro": round(evaluation.f1_macro, 6),
            "fpr": round(evaluation.fpr, 6),
            "per_class_recall": {
                k: round(v, 6) for k, v in evaluation.per_class_recall.items()
            },
        },
        "duration_s": round(duration, 3),
    }
    with (model_dir / RUN_MANIFEST).open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    with (artifacts / RUNS_LOG).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(manifest) + "\n")

    logger.info(
        "Trained %s on data %s (%s rows) — F1-macro %.4f in %.1fs",
        model_version,
        version.version,
        f"{len(training):,}",
        evaluation.f1_macro,
        duration,
    )
    return TrainOutcome(
        status="completed",
        run_id=run_id,
        model_version=model_version,
        data_version=version.version,
        bump=version.bump,
        metrics=manifest["metrics"],
        duration_s=duration,
    )


def evaluate_on_golden(
    model_version: str, data_version: str, cfg=None
) -> ModelEvaluation | None:
    """Score a saved model on the frozen golden partition.

    Returns ``None`` if the model artifacts are missing.
    """
    cfg = cfg or load_config()
    models_dir = Path(cfg.get_path("paths.models_dir", "models"))
    processed = Path(cfg.get_path("paths.data_processed", "data/processed"))
    model_dir = models_dir / model_version
    if not (model_dir / "model.joblib").exists():
        return None

    vectorizer = joblib.load(model_dir / "vectorizer.joblib")
    classifier = joblib.load(model_dir / "model.joblib")
    split = pd.read_csv(processed / "branch1_mlops_split.csv")
    golden = split[split["partition"] == "golden"]

    stacked_path = processed / "mlops_stacked_pool.csv"
    if stacked_path.exists():
        # golden@2 is a superset: the same golden@1 rows plus the new class.
        stacked = pd.read_csv(stacked_path)
        golden = pd.concat(
            [golden, stacked[stacked["partition"] == "golden"]], ignore_index=True
        )

    predictions = classifier.predict(
        vectorizer.transform(golden["query_canonical"].astype(str))
    )
    # Models trained by train/train_branch1.py emit integer label ids, while
    # this module trains on label names. Normalise to names so per-class
    # regressions are comparable between the two.
    from src.preprocessing.multiclass_tagger import LABEL_NAMES

    normalised = [
        LABEL_NAMES.get(int(p), str(p)) if str(p).lstrip("-").isdigit() else str(p)
        for p in predictions
    ]
    return compute_evaluation(
        golden["label_name"].astype(str).tolist(),
        normalised,
        model_version=model_version,
        data_version=data_version,
    )


def promote(model_version: str, cfg=None) -> None:
    """Make a model the active one by updating config (promotion == one flip).

    ``deploy.registry`` resolves models through
    ``branch1_supervised.active_version``, so promotion and rollback are the
    same operation in opposite directions and touch no serving code.
    """
    cfg = cfg or load_config()
    config_path = Path("configs/config.yaml")
    text = config_path.read_text(encoding="utf-8")

    import re

    updated, count = re.subn(
        r'(branch1_supervised:(?:.|\n)*?\n  active_version: )"[^"]*"',
        rf'\1"{model_version}"',
        text,
        count=1,
    )
    if count != 1:  # pragma: no cover - config shape changed
        raise RuntimeError("Could not locate branch1_supervised.active_version in config")
    config_path.write_text(updated, encoding="utf-8")

    model_dir = Path(cfg.get_path("paths.models_dir", "models")) / model_version
    meta_path = model_dir / "metadata.json"
    if meta_path.exists():
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        metadata.update({"state": "promoted", "promoted_at": _now()})
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    logger.info("Promoted %s (branch1_supervised.active_version updated)", model_version)
