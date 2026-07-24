"""Model registry: version-aware, lazily-loaded model handles for the API.

This is the small "MLOps-lite" core behind the FastAPI service. Each branch's
production model lives under ``models/<active_version>/`` (see the per-branch
``active_version`` keys in ``configs/config.yaml``), so switching or rolling back
a model is a one-line config change — no code edit.

Only Branch 1 (``tfidf_logreg``) is trained today; Branch 2/3 have no weights
yet. The registry loads whatever is present and reports the rest as
*not ready* instead of crashing the app, so the frontend can be built against a
stable contract before those models land.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

import joblib

from src.preprocessing.canonicalize import canonicalize
from src.preprocessing.multiclass_tagger import LABEL_NAMES
from src.utils import get_logger, load_config

logger = get_logger(__name__)


@dataclass
class Nhanh1Prediction:
    """Structured output of a single Branch-1 (supervised multiclass) inference."""

    query_canonical: str
    label: int
    label_name: str
    is_sqli: bool
    confidence: float
    attack_probability: float
    probabilities: dict[str, float] = field(default_factory=dict)
    threshold: float = 0.5


class Nhanh1Model:
    """Loaded Branch-1 model: TF-IDF vectorizer + classifier + label map.

    Replicates the exact inference path used at training time
    (``scripts/train_nhanh1.py``): ``canonicalize(text).query_canonical`` ->
    ``vectorizer.transform`` -> ``clf.predict_proba``.
    """

    def __init__(
        self,
        vectorizer: Any,
        clf: Any,
        metadata: dict[str, Any],
        decision_threshold: float,
        max_decode_iterations: int,
    ) -> None:
        self._vectorizer = vectorizer
        self._clf = clf
        self.metadata = metadata
        self._threshold = decision_threshold
        self._max_decode_iterations = max_decode_iterations
        # The model only predicts the classes present at train time (e.g. the
        # synthetic `stacked` class was excluded), so map from clf.classes_.
        self._classes: list[int] = [int(c) for c in clf.classes_]

    def predict(self, query: str) -> Nhanh1Prediction:
        """Classify one raw query string.

        Args:
            query: Raw query/parameter string (canonicalized internally, exactly
                as done at training time).

        Returns:
            A :class:`Nhanh1Prediction` with label, confidence, per-class
            probabilities and the SQLi flag.
        """
        canonical = canonicalize(query, self._max_decode_iterations).query_canonical
        probs = self._clf.predict_proba(self._vectorizer.transform([canonical]))[0]
        prob_by_label = {
            self._classes[i]: float(probs[i]) for i in range(len(self._classes))
        }
        probabilities = {
            LABEL_NAMES.get(label, str(label)): prob
            for label, prob in prob_by_label.items()
        }

        best_label = max(prob_by_label, key=prob_by_label.get)
        best_prob = prob_by_label[best_label]
        # Any attack class = "not normal" (label 0). Flag as SQLi when the
        # combined attack probability clears the configured threshold. Note this
        # differs from `confidence` (the single top-class probability): a query
        # can be confidently an attack overall while the probability mass is
        # split across attack sub-classes.
        normal_prob = prob_by_label.get(0, 0.0)
        attack_prob = 1.0 - normal_prob
        is_sqli = attack_prob >= self._threshold

        return Nhanh1Prediction(
            query_canonical=canonical,
            label=int(best_label),
            label_name=LABEL_NAMES.get(best_label, str(best_label)),
            is_sqli=is_sqli,
            confidence=best_prob,
            attack_probability=attack_prob,
            probabilities=probabilities,
            threshold=self._threshold,
        )


class ModelRegistry:
    """Lazy, thread-safe holder of per-branch model handles.

    Loads each branch's model on first use from ``models/<active_version>/``.
    Missing weights are reported via :meth:`status` rather than raising, so the
    API stays up while Branch 2/3 are still being trained.
    """

    def __init__(self) -> None:
        self._cfg = load_config()
        self._lock = Lock()
        self._nhanh1: Nhanh1Model | None = None
        self._nhanh1_loaded = False  # True once a load has been attempted

    def _models_dir(self) -> Path:
        return Path(self._cfg.get_path("paths.models_dir", "models"))

    def _branch_version_dir(self, active_version_key: str, default: str) -> Path:
        version = self._cfg.get_path(active_version_key, default)
        return self._models_dir() / str(version)

    def nhanh1(self) -> Nhanh1Model | None:
        """Return the loaded Branch-1 model, or ``None`` if unavailable.

        Loads lazily on first call and caches the result (including a failed
        load, so we don't retry disk I/O on every request).
        """
        if self._nhanh1_loaded:
            return self._nhanh1
        with self._lock:
            if self._nhanh1_loaded:  # re-check inside the lock
                return self._nhanh1
            self._nhanh1 = self._load_nhanh1()
            self._nhanh1_loaded = True
        return self._nhanh1

    def _load_nhanh1(self) -> Nhanh1Model | None:
        model_dir = self._branch_version_dir(
            "branch1_supervised.active_version", "nhanh1_v1"
        )
        vec_path = model_dir / "vectorizer.joblib"
        clf_path = model_dir / "model.joblib"
        if not vec_path.exists() or not clf_path.exists():
            logger.warning(
                "Branch-1 model not found under %s — reporting not_ready", model_dir
            )
            return None
        try:
            vectorizer = joblib.load(vec_path)
            clf = joblib.load(clf_path)
        except Exception:  # pragma: no cover - corrupt artifact is unexpected
            logger.exception("Failed to load Branch-1 model from %s", model_dir)
            return None

        metadata = self._read_metadata(model_dir)
        threshold = float(
            self._cfg.get_path("branch1_supervised.decision_threshold", 0.5)
        )
        max_decode = int(self._cfg.get_path("preprocessing.max_decode_iterations", 3))
        logger.info("Loaded Branch-1 model from %s (threshold=%.2f)", model_dir, threshold)
        return Nhanh1Model(vectorizer, clf, metadata, threshold, max_decode)

    @staticmethod
    def _read_metadata(model_dir: Path) -> dict[str, Any]:
        import json

        meta_path = model_dir / "metadata.json"
        if not meta_path.exists():
            return {}
        try:
            with meta_path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):  # pragma: no cover
            logger.warning("Could not parse %s", meta_path)
            return {}

    def _branch_ready(self, active_version_key: str, default: str, marker: str) -> bool:
        """Return True if a branch's version dir has its expected weight file."""
        model_dir = self._branch_version_dir(active_version_key, default)
        return (model_dir / marker).exists()

    def status(self) -> dict[str, str]:
        """Return per-branch readiness for the health endpoint.

        Values are ``"ready"`` or ``"not_trained"``.
        """
        nhanh1_ready = self.nhanh1() is not None
        nhanh2_ready = self._branch_ready(
            "branch2_anomaly.active_version", "nhanh2_v1", "model.joblib"
        )
        nhanh3_ready = self._branch_ready(
            "branch3_session.active_version", "nhanh3_v1", "model.pt"
        )
        as_status = lambda ready: "ready" if ready else "not_trained"
        return {
            "nhanh1": as_status(nhanh1_ready),
            "nhanh2": as_status(nhanh2_ready),
            "nhanh3": as_status(nhanh3_ready),
        }


# Process-wide singleton reused across requests.
_registry: ModelRegistry | None = None


def get_registry() -> ModelRegistry:
    """Return the process-wide :class:`ModelRegistry` (created on first call)."""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
