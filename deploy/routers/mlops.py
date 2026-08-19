"""MLOps lifecycle endpoints: versions, runs, decisions, replay and reset.

Implements section 1.7 of ``report/plan/mlops_contract.md``.

``/replay`` is what makes the demo self-contained: it pushes a slice of the
held-out stream through the live detection path, writes a real drift record and
fills the review queue with AI pre-labelled items. ``/reset`` returns the system
to its protected baseline so the demo can be run again.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException

from deploy.registry import get_registry
from deploy.schemas import (
    MlopsResetResponse,
    ReplayRequest,
    ReplayResponse,
    RollbackResponse,
    VersionsResponse,
)
from src.continual_learning.gate import read_decisions
from src.continual_learning.model_registry import load_model_registry, resolve_active
from src.continual_learning.trainer import RUNS_LOG, rollback
from src.continual_learning.versioning import load_registry
from src.decision.queue import (
    ReviewItem,
    confirmed_labels_path,
    drop_round,
    open_queue,
)
from src.monitoring.drift import (
    detect_trigger,
    fit_reference_bins,
    iter_windows,
    psi_categorical,
    psi_from_reference,
)
from src.preprocessing.statistical_features import extract_statistical_features
from src.utils import get_logger, load_config

logger = get_logger(__name__)

router = APIRouter(prefix="/mlops", tags=["mlops"])

# Kept intentionally SEPARATE from branch2_anomaly.features (the anomaly
# model's own feature set, now all 12 of statistical_features.FEATURE_ORDER
# as of 19/08) — this is what the drift monitor tracks over general traffic
# characteristics, not tied to whichever features the current anomaly model
# happens to use, and deliberately kept to a small, easily-interpreted
# subset rather than mirroring the full engineered feature set (the newer
# "local peak" features — max_special_run etc. — are specific fixes for the
# D3/D7 whole-string-dilution problem, not general drift signals). Update by
# hand, in sync with train/run_continual_learning_experiment.py's identical
# constant, whenever this subset should change.
FEATURES = ["length", "special_char_ratio", "entropy", "quote_imbalance"]
DEMO_ROUND = "demo"


def _artifacts(cfg) -> Path:
    path = Path(cfg.get_path("mlops.artifacts_dir", "report/metrics/continual_learning"))
    path.mkdir(parents=True, exist_ok=True)
    return path


@router.get("/versions", response_model=VersionsResponse)
def versions() -> VersionsResponse:
    """Return the data-version registry plus the served model and its history."""
    cfg = load_config()
    registry = load_registry("branch1", cfg)
    models = load_model_registry(cfg)
    return VersionsResponse(
        dataset="branch1",
        active_model=resolve_active(
            "branch1", "branch1_supervised.active_version", "branch1_v1", cfg
        ),
        baseline_model=str(cfg.get_path("branch1_supervised.active_version", "")),
        versions=[v.to_dict() for v in registry.versions],
        models=[e.to_dict() for e in models.history("branch1")],
    )


@router.post("/rollback", response_model=RollbackResponse)
def rollback_model() -> RollbackResponse:
    """Restore the previously-served model.

    With no archived model there is nothing to restore; clearing the registry
    (which ``/reset`` does) reverts to the config baseline instead.
    """
    cfg = load_config()
    restored = rollback("branch1", cfg)
    if restored is None:
        return RollbackResponse(
            ok=False,
            active=resolve_active(
                "branch1", "branch1_supervised.active_version", "branch1_v1", cfg
            ),
            detail="No previously-served model to roll back to.",
        )
    get_registry().reload()
    return RollbackResponse(ok=True, active=restored, detail=f"Rolled back to {restored}.")


@router.get("/runs")
def runs() -> dict[str, Any]:
    """Return every recorded training run, newest first."""
    cfg = load_config()
    path = _artifacts(cfg) / RUNS_LOG
    records: list[dict[str, Any]] = []
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except ValueError:  # pragma: no cover
                        continue
    return {"count": len(records), "runs": list(reversed(records))}


@router.get("/decisions")
def decisions() -> dict[str, Any]:
    """Return the promotion decision log, newest first."""
    cfg = load_config()
    records = read_decisions(_artifacts(cfg) / "decisions.jsonl")
    return {"count": len(records), "decisions": list(reversed(records))}


@router.post("/replay", response_model=ReplayResponse)
def replay(request: ReplayRequest) -> ReplayResponse:
    """Replay a slice of the held-out stream through the live model.

    Produces a real drift record and fills the review queue with pre-labelled
    items, so the Monitor and Data pages have genuine data to show.
    """
    cfg = load_config()
    processed = Path(cfg.get_path("paths.data_processed", "data/processed"))
    stream_path = processed / "mlops_stream.csv"
    if not stream_path.exists():
        raise HTTPException(
            status_code=409,
            detail="No replay stream found. Run: uv run python train/build_mlops_split.py",
        )

    model = get_registry().branch1()
    if model is None:
        raise HTTPException(status_code=409, detail="Branch-1 model is not loaded.")

    window_size = int(cfg.get_path("mlops.stream.window_size", 1000))
    psi_bins = int(cfg.get_path("mlops.drift.psi_bins", 10))
    threshold = float(cfg.get_path("monitoring.psi_alert_threshold", 0.2))
    sustained = int(cfg.get_path("mlops.drift.sustained_windows", 2))
    baseline_windows = int(cfg.get_path("mlops.drift.baseline_windows", 10))
    low_confidence = float(cfg.get_path("mlops.queue.low_confidence_below", 0.6))

    stream = pd.read_csv(stream_path)
    if request.limit:
        stream = stream.iloc[: request.limit].copy()

    # Score every query through the same path the API serves.
    predictions, confidences, canonicals = [], [], []
    for text in stream["query_raw"].astype(str):
        result = model.predict(text)
        predictions.append(result.label_name)
        confidences.append(result.confidence)
        canonicals.append(result.query_canonical)
    stream = stream.assign(
        predicted=predictions, confidence=confidences, canonical=canonicals
    )

    # Selects by name (FEATURES may be a different subset than
    # StatisticalFeatures.as_list()'s full FEATURE_ORDER — see FEATURES'
    # definition above for why they're kept separate).
    features = pd.DataFrame(
        [extract_statistical_features(t).as_dict() for t in stream["canonical"]],
        columns=FEATURES,
    )

    n_reference = min(baseline_windows * window_size, len(stream))
    reference = stream.iloc[:n_reference]
    reference_features = features.iloc[:n_reference]
    bins = {
        name: fit_reference_bins(reference_features[name], feature=name, n_bins=psi_bins)
        for name in FEATURES
    }
    flagged_mask = (reference["predicted"] != "normal").to_numpy()
    confidence_bins = fit_reference_bins(
        reference.loc[flagged_mask, "confidence"]
        if flagged_mask.sum() >= psi_bins
        else reference["confidence"],
        feature="confidence",
        n_bins=psi_bins,
    )
    reference_predictions = reference["predicted"].tolist()

    windows: list[dict[str, Any]] = []
    for index, start, stop in iter_windows(len(stream), window_size):
        chunk = stream.iloc[start:stop]
        chunk_features = features.iloc[start:stop]
        flagged = chunk["predicted"] != "normal"
        global_psi = float(
            sum(psi_from_reference(chunk_features[f], bins[f]) for f in FEATURES) / len(FEATURES)
        )
        prediction_psi = psi_categorical(reference_predictions, chunk["predicted"].tolist())
        confidence_psi = (
            psi_from_reference(chunk.loc[flagged, "confidence"], confidence_bins)
            if flagged.sum() >= 5
            else 0.0
        )
        signals = {
            "global": round(global_psi, 6),
            "prediction": round(prediction_psi, 6),
            "confidence_flagged": round(confidence_psi, 6),
        }
        windows.append(
            {
                "index": index,
                "phase": str(chunk["phase"].iloc[0]),
                "is_reference": stop <= n_reference,
                "n": len(chunk),
                "psi": signals,
                "rates": {
                    "block": round(float(flagged.mean()), 6),
                    "low_confidence": round(
                        float((chunk["confidence"] < low_confidence).mean()), 6
                    ),
                },
                "alert": bool(max(signals.values()) >= threshold),
            }
        )

    trigger = detect_trigger(
        windows,
        threshold=threshold,
        sustained=sustained,
        signals=("global", "prediction", "confidence_flagged"),
    )
    drift_record = {
        "data_version": str(cfg.get_path("mlops.baseline.data_version", "1.0")),
        "reference": f"stream baseline: first {baseline_windows} windows",
        "baseline_windows": baseline_windows,
        "psi_bins": psi_bins,
        "threshold": threshold,
        "sustained_windows": sustained,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "windows": windows,
        "trigger": trigger.to_dict(),
    }
    with (_artifacts(cfg) / "drift.json").open("w", encoding="utf-8") as handle:
        json.dump(drift_record, handle, indent=2)

    # Fill the review queue with AI-pre-labelled items.
    queue = open_queue(cfg)
    sources = set(cfg.get_path("mlops.queue.sources", ["overkill", "anomaly", "low_confidence"]))
    flagged_rows = stream[
        (stream["predicted"] != "normal") | (stream["confidence"] < low_confidence)
    ]
    if request.max_queue:
        flagged_rows = flagged_rows.head(request.max_queue)
    items = [
        ReviewItem(
            id=str(row.id),
            query_raw=str(row.query_raw),
            query_canonical=str(row.canonical),
            source="block" if row.predicted != "normal" else "low_confidence",
            ai_label=str(row.predicted),
            ai_confidence=float(row.confidence),
            round_id=DEMO_ROUND,
        )
        for row in flagged_rows.itertuples()
    ]
    queued = queue.enqueue(items)

    logger.info(
        "Replayed %s queries over %d windows; queued %d items for review",
        f"{len(stream):,}",
        len(windows),
        queued,
    )
    return ReplayResponse(
        replayed=len(stream),
        windows=len(windows),
        queued=queued,
        alert=trigger.fired,
        trigger=trigger.to_dict(),
        sources=sorted(sources),
    )


@router.post("/reset", response_model=MlopsResetResponse)
def reset() -> MlopsResetResponse:
    """Restore the protected baseline so the demo can be run again.

    Archives (never deletes) models created during the round, drops the round's
    queue rows, confirmed labels and drift record, and restores the baseline
    active version. Anything marked ``protected`` is left untouched.
    """
    cfg = load_config()
    models_dir = Path(cfg.get_path("paths.models_dir", "models"))
    archive_dir = Path(cfg.get_path("mlops.archive_dir", "models/_archive"))
    baseline_model = str(cfg.get_path("mlops.baseline.model_version", "branch1_v1"))
    baseline_data = str(cfg.get_path("mlops.baseline.data_version", "1.0"))
    artifacts = _artifacts(cfg)

    # 1. Archive non-baseline models produced by the demo.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    archived: list[str] = []
    for path in sorted(models_dir.glob("branch1_v*")):
        if not path.is_dir() or path.name == baseline_model:
            continue
        meta_path = path / "metadata.json"
        if meta_path.exists():
            try:
                if json.loads(meta_path.read_text(encoding="utf-8")).get("protected"):
                    continue
            except ValueError:  # pragma: no cover
                pass
        destination = archive_dir / stamp / path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(destination))
        archived.append(path.name)

    # 2. Drop the round's queue rows and confirmed labels.
    queue = open_queue(cfg)
    purged = queue.purge_round(DEMO_ROUND)
    labels_dropped = drop_round(confirmed_labels_path(cfg), DEMO_ROUND)

    # 3. Remove non-protected data versions.
    registry = load_registry("branch1", cfg)
    removed_versions = []
    for version in list(registry.versions):
        if version.protected or version.version == baseline_data:
            continue
        registry.remove(version.version)
        removed_versions.append(version.version)
    registry.save()

    # 4. Drop the round's drift record and runs log.
    for name in ("drift.json", RUNS_LOG):
        (artifacts / name).unlink(missing_ok=True)

    # 5. Clear the model registry so resolution falls back to the config
    #    baseline. Clearing (rather than promoting the baseline) is what makes a
    #    reset return the system to the state a fresh clone would be in.
    models = load_model_registry(cfg)
    models.clear()
    models.save()
    get_registry().reload()

    logger.info(
        "Demo reset: archived %d models, purged %d queue rows, dropped %d labels",
        len(archived),
        purged,
        labels_dropped,
    )
    return MlopsResetResponse(
        ok=True,
        baseline_model=baseline_model,
        baseline_data_version=baseline_data,
        archived_models=archived,
        purged_queue_rows=purged,
        dropped_labels=labels_dropped,
        removed_versions=removed_versions,
    )
