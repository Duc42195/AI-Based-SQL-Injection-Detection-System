"""Branch 2 — Anomaly Detection model wrapper.

Trains on 100 % benign (normal) traffic using Isolation Forest or One-Class SVM.
Emits a continuous anomaly score per query, used both as a zero-day flag and as
an extra feature dimension for Branch 3 (session-level model).

Includes:
  - Optional log1p-transform for right-skewed features (e.g. length).
  - Optional StandardScaler scaling (critical for OCSVM RBF kernel).
  - Persistence of preprocessor alongside the sklearn estimator.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Literal

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from src.utils import get_logger

logger = get_logger(__name__)

Algorithm = Literal["isolation_forest", "one_class_svm"]


class AnomalyDetector:
    """Unsupervised anomaly detector for Branch 2.

    Wraps sklearn's IsolationForest or OneClassSVM with a consistent interface
    for fit / predict / score / save / load.

    Preprocessing (log-transform + scaling) is applied inside fit/score/predict
    and persisted together with the model.
    """

    def __init__(
        self,
        algorithm: Algorithm = "isolation_forest",
        contamination: float = 0.01,
        random_seed: int = 42,
        scale_features: bool = True,
        log_transform_features: list[str] | None = None,
        feature_names: list[str] | None = None,
        **kwargs,
    ) -> None:
        """Initialise the anomaly detector.

        Args:
            algorithm: ``"isolation_forest"`` or ``"one_class_svm"``.
            contamination: Expected fraction of anomalies in the training set.
                For IF: passed as ``contamination`` (use ``"auto"`` for data-driven).
                For OCSVM: passed as ``nu``.
                Training data is 100 % benign → set this very small (<0.001).
            random_seed: Seed for reproducibility.
            scale_features: If True, fit a ``StandardScaler`` on the training
                data and apply it before every predict/score call.
            log_transform_features: List of feature names to apply
                ``np.log1p`` to before scaling (e.g. ``["length"]``).
            feature_names: Ordered list of feature names (needed to resolve
                ``log_transform_features`` to column indices).
            **kwargs: Additional keyword arguments passed to the underlying
                sklearn estimator.
        """
        self.algorithm = algorithm
        self.contamination = contamination
        self.random_seed = random_seed
        self.scale_features = scale_features
        self.log_transform_features = log_transform_features or []
        self.feature_names = feature_names
        self._model: IsolationForest | OneClassSVM | None = None
        self._scaler: StandardScaler | None = None
        self._log_indices: np.ndarray | None = None
        self._n_features: int | None = None

        if algorithm == "isolation_forest":
            self._model = IsolationForest(
                n_estimators=kwargs.get("n_estimators", 100),
                contamination=contamination,
                random_state=random_seed,
                n_jobs=kwargs.get("n_jobs", -1),
            )
        elif algorithm == "one_class_svm":
            self._model = OneClassSVM(
                kernel=kwargs.get("kernel", "rbf"),
                gamma=kwargs.get("gamma", "scale"),
                nu=contamination,
            )
        else:
            raise ValueError(
                f"Unknown algorithm: {algorithm}. "
                f"Expected one of: isolation_forest, one_class_svm"
            )

    # ──────────────────────────────────────────────
    #  Internal preprocessing helpers
    # ──────────────────────────────────────────────

    def _resolve_log_indices(self) -> None:
        """Populate ``_log_indices`` from ``log_transform_features``."""
        if self.log_transform_features and self.feature_names:
            self._log_indices = np.array([
                i for i, f in enumerate(self.feature_names)
                if f in self.log_transform_features
            ], dtype=np.intp)

    def _apply_log_transform(self, X: np.ndarray) -> np.ndarray:
        """Apply log1p to selected columns (in-place copy)."""
        if self._log_indices is None or len(self._log_indices) == 0:
            return X
        X = X.copy()
        X[:, self._log_indices] = np.log1p(X[:, self._log_indices])
        return X

    def _preprocess(self, X: np.ndarray, *, fit_scaler: bool = False) -> np.ndarray:
        """Apply log-transform then (optionally) scale.

        Args:
            X: Raw feature matrix.
            fit_scaler: If True, fit the scaler on X; otherwise transform.

        Returns:
            Preprocessed feature matrix.
        """
        X = self._apply_log_transform(X)
        if self.scale_features:
            if fit_scaler:
                self._scaler = StandardScaler().fit(X)
            if self._scaler is not None:
                X = self._scaler.transform(X)
        return X

    # ──────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────

    def fit(self, X: np.ndarray) -> None:
        """Fit the anomaly detector on benign training data.

        Applies log-transform + scaling before fitting the sklearn model.

        Args:
            X: Feature matrix of shape ``(n_samples, n_features)``.
        """
        self._resolve_log_indices()
        self._n_features = X.shape[1]

        n = X.shape[0]
        logger.info("Fitting %s (dim=%d, n=%d, contamination=%s)", self.algorithm, self._n_features, n, str(self.contamination))

        Xpp = self._preprocess(X, fit_scaler=True)

        t0 = time.perf_counter()
        self._model.fit(Xpp)
        elapsed = time.perf_counter() - t0
        logger.info("Fit done in %.2fs", elapsed)

        # Summarise transformed feature ranges
        for i in range(Xpp.shape[1]):
            name = self.feature_names[i] if self.feature_names and i < len(self.feature_names) else str(i)
            logger.info("  [%s]  mean=%+.4f  std=%.4f  min=%.4f  max=%.4f", name, Xpp[:, i].mean(), Xpp[:, i].std(), Xpp[:, i].min(), Xpp[:, i].max())

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Return binary anomaly labels: 1 = normal, -1 = anomaly.

        Sklearn convention: IsolationForest/OneClassSVM return 1 for inliers
        and -1 for outliers.

        Args:
            X: Feature matrix of shape ``(n_samples, n_features)``.

        Returns:
            Array of shape ``(n_samples,)`` with values 1 (normal) or -1 (anomaly).
        """
        Xpp = self._preprocess(X)
        return self._model.predict(Xpp)

    def score(self, X: np.ndarray) -> np.ndarray:
        """Return anomaly score (higher = more anomalous).

        For Isolation Forest this is ``-decision_function`` (raw scores are
        negative for anomalies). For One-Class SVM we negate ``decision_function``
        so that higher = more anomalous in both cases.

        Args:
            X: Feature matrix of shape ``(n_samples, n_features)``.

        Returns:
            Anomaly scores of shape ``(n_samples,)`` — higher is more anomalous.
        """
        Xpp = self._preprocess(X)
        raw = self._model.decision_function(Xpp)
        return -raw

    def anomaly_flags(self, X: np.ndarray, threshold: float | None = None) -> np.ndarray:
        """Return 0/1 anomaly flags (1 = anomalous).

        Uses the model's ``predict`` result (not a custom threshold). For a
        custom decision threshold on the continuous score, call ``score()``
        and compare externally.

        Args:
            X: Feature matrix.
            threshold: If provided, threshold the score instead of predict.

        Returns:
            Array of shape ``(n_samples,)`` with 0 = normal, 1 = anomalous.
        """
        if threshold is not None:
            scores = self.score(X)
            return (scores > threshold).astype(np.int32)
        preds = self.predict(X)
        return (preds == -1).astype(np.int32)

    def save(self, path: str | Path) -> None:
        """Serialize the model and preprocessor to disk.

        Args:
            path: Directory path. Creates the directory if needed.
        """
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._model, path / "model.joblib")
        if self._scaler is not None:
            joblib.dump(self._scaler, path / "scaler.joblib")

        meta = {
            "algorithm": self.algorithm,
            "contamination": self.contamination,
            "random_seed": self.random_seed,
            "scale_features": self.scale_features,
            "log_transform_features": self.log_transform_features,
            "feature_names": self.feature_names,
        }
        with (path / "metadata.json").open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        logger.info("Model saved to %s", path)

    @classmethod
    def load(cls, path: str | Path) -> AnomalyDetector:
        """Deserialize a saved model and preprocessor.

        Args:
            path: Directory containing ``model.joblib``, ``metadata.json``,
                and optionally ``scaler.joblib``.

        Returns:
            A loaded :class:`AnomalyDetector` instance.
        """
        path = Path(path)
        meta_path = path / "metadata.json"
        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)

        detector = cls(
            algorithm=meta["algorithm"],
            contamination=meta["contamination"],
            random_seed=meta.get("random_seed", 42),
            scale_features=meta.get("scale_features", False),
            log_transform_features=meta.get("log_transform_features", []),
            feature_names=meta.get("feature_names"),
        )
        detector._model = joblib.load(path / "model.joblib")

        scaler_path = path / "scaler.joblib"
        if scaler_path.exists():
            detector._scaler = joblib.load(scaler_path)

        detector._resolve_log_indices()
        if detector._model:
            t = getattr(detector._model, "n_features_in_", None)
            if t is not None:
                detector._n_features = t

        logger.info("Model loaded from %s", path)
        return detector

    def get_params(self) -> dict:
        """Return the underlying sklearn estimator's parameters for logging."""
        return self._model.get_params()
