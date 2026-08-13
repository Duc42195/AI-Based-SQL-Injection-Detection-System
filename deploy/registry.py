"""Model registry: version-aware, lazily-loaded model handles for the API.

This is the small "MLOps-lite" core behind the FastAPI service. Each branch's
production model lives under ``models/<active_version>/`` (see the per-branch
``active_version`` keys in ``configs/config.yaml``), so switching or rolling back
a model is a one-line config change — no code edit.

Branch 1 (``tfidf_logreg``) and Branch 2 (One-Class SVM) are served from their
trained weights. Branch 3 (``SessionCorrelator``) is not a trained model — it
re-uses Branch 1's + Branch 2's already-loaded artifacts plus thresholds
calibrated by ``train/calibrate_branch3.py`` (see ``branch3()`` below). The
registry loads whatever is present and reports the rest as *not ready* instead
of crashing the app, so the frontend stays on a stable contract even if a
branch's artifacts are missing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

import joblib
import numpy as np

from src.continual_learning.model_registry import resolve_active
from src.models.branch2_anomaly import AnomalyDetector
from src.models.branch3_session import SessionCorrelator
from src.preprocessing.canonicalize import canonicalize
from src.preprocessing.multiclass_tagger import LABEL_NAMES
from src.preprocessing.statistical_features import extract_statistical_features
from src.utils import get_logger, load_config

logger = get_logger(__name__)

NORMAL_LABEL = "normal"
_LABEL_IDS = {name: label for label, name in LABEL_NAMES.items()}


def _is_int_like(value: Any) -> bool:
    """True if a class label is an integer id rather than a name."""
    return str(value).lstrip("-").isdigit()


@dataclass
class Branch1Prediction:
    """Structured output of a single Branch-1 (supervised multiclass) inference."""

    query_canonical: str
    label: int
    label_name: str
    is_sqli: bool
    confidence: float
    attack_probability: float
    probabilities: dict[str, float] = field(default_factory=dict)
    threshold: float = 0.5


class Branch1Model:
    """Loaded Branch-1 model: TF-IDF vectorizer + classifier + label map.

    Replicates the exact inference path used at training time
    (``train/train_branch1.py``): ``canonicalize(text).query_canonical`` ->
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
        #
        # Models are trained two ways in this repo: train/train_branch1.py fits
        # on integer label ids, while the continual-learning trainer fits on
        # label names. Normalise both to names here so either can be served.
        self._class_names: list[str] = [
            LABEL_NAMES.get(int(c), str(c)) if _is_int_like(c) else str(c)
            for c in clf.classes_
        ]

    def predict(self, query: str) -> Branch1Prediction:
        """Classify one raw query string.

        Args:
            query: Raw query/parameter string (canonicalized internally, exactly
                as done at training time).

        Returns:
            A :class:`Branch1Prediction` with label, confidence, per-class
            probabilities and the SQLi flag.
        """
        canonical = canonicalize(query, self._max_decode_iterations).query_canonical
        probs = self._clf.predict_proba(self._vectorizer.transform([canonical]))[0]
        probabilities = {
            self._class_names[i]: float(probs[i]) for i in range(len(self._class_names))
        }

        best_name = max(probabilities, key=probabilities.get)
        best_prob = probabilities[best_name]
        # Any attack class = "not normal". Flag as SQLi when the combined attack
        # probability clears the configured threshold. Note this differs from
        # `confidence` (the single top-class probability): a query can be
        # confidently an attack overall while the probability mass is split
        # across attack sub-classes.
        normal_prob = probabilities.get(NORMAL_LABEL, 0.0)
        attack_prob = 1.0 - normal_prob
        is_sqli = attack_prob >= self._threshold

        return Branch1Prediction(
            query_canonical=canonical,
            label=_LABEL_IDS.get(best_name, -1),
            label_name=best_name,
            is_sqli=is_sqli,
            confidence=best_prob,
            attack_probability=attack_prob,
            probabilities=probabilities,
            threshold=self._threshold,
        )


@dataclass
class Branch2Prediction:
    """Structured output of a single Branch-2 (anomaly) inference."""

    query_canonical: str
    anomaly_score: float
    is_anomaly: bool


class Branch2Model:
    """Loaded Branch-2 anomaly detector (One-Class SVM / Isolation Forest).

    Replicates the training feature path (``train/build_branch2_dataset.py``):
    ``canonicalize(text).query_canonical`` -> ``extract_statistical_features``
    -> ``AnomalyDetector`` (which applies log1p/scaling internally). Higher
    ``anomaly_score`` = more anomalous; ``is_anomaly`` uses the model's own
    inlier/outlier decision.
    """

    def __init__(self, detector: AnomalyDetector, max_decode_iterations: int) -> None:
        self._detector = detector
        self._max_decode_iterations = max_decode_iterations

    def predict(self, query: str) -> Branch2Prediction:
        """Score one raw query for anomalousness.

        Args:
            query: Raw query/parameter string (canonicalized internally, exactly
                as done when the Branch-2 training data was built).

        Returns:
            A :class:`Branch2Prediction` with the continuous score and flag.
        """
        canonical = canonicalize(query, self._max_decode_iterations).query_canonical
        features = extract_statistical_features(canonical).as_list()
        X = np.array([features], dtype=float)
        score = float(self._detector.score(X)[0])
        is_anomaly = bool(self._detector.anomaly_flags(X)[0])
        return Branch2Prediction(
            query_canonical=canonical,
            anomaly_score=score,
            is_anomaly=is_anomaly,
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
        self._branch1: Branch1Model | None = None
        self._branch1_loaded = False  # True once a load has been attempted
        self._branch2: Branch2Model | None = None
        self._branch2_loaded = False
        self._branch3: SessionCorrelator | None = None
        self._branch3_loaded = False

    def _models_dir(self) -> Path:
        return Path(self._cfg.get_path("paths.models_dir", "models"))

    def _branch_version_dir(
        self, active_version_key: str, default: str, branch: str | None = None
    ) -> Path:
        """Resolve a branch's model directory.

        A promoted version in the model registry wins; ``config.yaml`` holds the
        declared baseline and is the fallback, so a fresh clone with no registry
        serves exactly what config says.
        """
        if branch:
            version = resolve_active(branch, active_version_key, default, self._cfg)
        else:
            version = self._cfg.get_path(active_version_key, default)
        return self._models_dir() / str(version)

    def branch1(self) -> Branch1Model | None:
        """Return the loaded Branch-1 model, or ``None`` if unavailable.

        Loads lazily on first call and caches the result (including a failed
        load, so we don't retry disk I/O on every request).
        """
        if self._branch1_loaded:
            return self._branch1
        with self._lock:
            if self._branch1_loaded:  # re-check inside the lock
                return self._branch1
            self._branch1 = self._load_branch1()
            self._branch1_loaded = True
        return self._branch1

    def _load_branch1(self) -> Branch1Model | None:
        model_dir = self._branch_version_dir(
            "branch1_supervised.active_version", "branch1_v1", branch="branch1"
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
        return Branch1Model(vectorizer, clf, metadata, threshold, max_decode)

    def reload(self) -> None:
        """Re-read config and drop cached models.

        Promotion and rollback change ``<branch>.active_version`` in config, so
        the process must forget what it loaded or it would keep serving the
        previous model until restarted.
        """
        with self._lock:
            self._cfg = load_config()
            self._branch1 = None
            self._branch1_loaded = False
            self._branch2 = None
            self._branch2_loaded = False
            self._branch3 = None
            self._branch3_loaded = False
        logger.info("Model registry reloaded (active versions re-read from config)")

    def branch2(self) -> Branch2Model | None:
        """Return the loaded Branch-2 model, or ``None`` if unavailable."""
        if self._branch2_loaded:
            return self._branch2
        with self._lock:
            if self._branch2_loaded:  # re-check inside the lock
                return self._branch2
            self._branch2 = self._load_branch2()
            self._branch2_loaded = True
        return self._branch2

    def _load_branch2(self) -> Branch2Model | None:
        model_dir = self._branch_version_dir(
            "branch2_anomaly.active_version", "branch2_v1", branch="branch2"
        )
        if not (model_dir / "model.joblib").exists():
            logger.warning(
                "Branch-2 model not found under %s — reporting not_ready", model_dir
            )
            return None
        try:
            detector = AnomalyDetector.load(model_dir)
        except Exception:  # pragma: no cover - corrupt artifact is unexpected
            logger.exception("Failed to load Branch-2 model from %s", model_dir)
            return None
        max_decode = int(self._cfg.get_path("preprocessing.max_decode_iterations", 3))
        logger.info("Loaded Branch-2 model from %s", model_dir)
        return Branch2Model(detector, max_decode)

    def branch3(self) -> SessionCorrelator | None:
        """Return the loaded Session Correlator ("Branch 3"), or ``None`` if unavailable.

        Not a trained model — re-uses ``branch1()``/``branch2()``'s raw
        vectorizer/clf/detector plus thresholds calibrated by
        ``train/calibrate_branch3.py``. Loaded independently of the
        Branch1Model/Branch2Model wrappers (which don't expose their raw
        sklearn objects) via the same joblib paths those loaders use.
        """
        if self._branch3_loaded:
            return self._branch3
        with self._lock:
            if self._branch3_loaded:  # re-check inside the lock
                return self._branch3
            self._branch3 = self._load_branch3()
            self._branch3_loaded = True
        return self._branch3

    def _load_branch3(self) -> SessionCorrelator | None:
        correlator_dir = self._branch_version_dir("branch3_session.active_version", "branch3_v2")
        if not (correlator_dir / "metadata.json").exists():
            logger.warning(
                "Session Correlator thresholds not found under %s — reporting not_ready", correlator_dir
            )
            return None

        b1_dir = self._branch_version_dir("branch1_supervised.active_version", "branch1_v1")
        b2_dir = self._branch_version_dir("branch2_anomaly.active_version", "branch2_v1")
        if not (b1_dir / "vectorizer.joblib").exists() or not (b2_dir / "model.joblib").exists():
            logger.warning("Session Correlator needs Branch 1 + Branch 2 artifacts — reporting not_ready")
            return None
        try:
            vectorizer = joblib.load(b1_dir / "vectorizer.joblib")
            clf = joblib.load(b1_dir / "model.joblib")
            b2_detector = AnomalyDetector.load(b2_dir)
            correlator = SessionCorrelator.load(correlator_dir, vectorizer, clf, b2_detector)
        except Exception:  # pragma: no cover - corrupt artifact is unexpected
            logger.exception("Failed to load Session Correlator from %s", correlator_dir)
            return None
        logger.info("Loaded Session Correlator (thresholds from %s)", correlator_dir)
        return correlator

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
        branch1_ready = self.branch1() is not None
        branch2_ready = self.branch2() is not None
        branch3_ready = self.branch3() is not None
        as_status = lambda ready: "ready" if ready else "not_trained"
        return {
            "branch1": as_status(branch1_ready),
            "branch2": as_status(branch2_ready),
            "branch3": as_status(branch3_ready),
        }


# Process-wide singleton reused across requests.
_registry: ModelRegistry | None = None


def get_registry() -> ModelRegistry:
    """Return the process-wide :class:`ModelRegistry` (created on first call)."""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
