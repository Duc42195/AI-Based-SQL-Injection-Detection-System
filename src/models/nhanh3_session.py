"""Branch 3 — Session-level SQLi detection.

Aggregates per-query statistical features over a session window and classifies
the entire session as benign or attack using a pre-trained sklearn model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.preprocessing.statistical_features import extract_statistical_features, StatisticalFeatures
from src.utils import load_config, get_logger

logger = get_logger(__name__)

_FEATURE_NAMES = ["length", "special_char_ratio", "sql_keyword_count", "entropy"]


class SessionAggregator:
    """Accumulates per-query features for an active session, then classifies it."""

    def __init__(self, max_len: int = 64):
        self.max_len = max_len
        self._steps: list[dict[str, Any]] = []

    def add_step(self, query: str, is_attack: float = 0.0) -> None:
        f = extract_statistical_features(query)
        self._steps.append({
            "length": f.length,
            "special_char_ratio": f.special_char_ratio,
            "sql_keyword_count": f.sql_keyword_count,
            "entropy": f.entropy,
            "is_attack_query": is_attack,
        })
        if len(self._steps) > self.max_len:
            self._steps = self._steps[-self.max_len:]

    def reset(self) -> None:
        self._steps = []

    def aggregate(self) -> dict[str, float]:
        if not self._steps:
            return {f"{n}_{agg}": 0.0 for n in _FEATURE_NAMES for agg in ("mean", "std", "max", "min")}
        df = pd.DataFrame(self._steps)
        feats = {}
        for f in _FEATURE_NAMES:
            vals = df[f].values
            feats[f"{f}_mean"] = float(np.mean(vals))
            feats[f"{f}_std"] = float(np.std(vals)) if len(vals) > 1 else 0.0
            feats[f"{f}_max"] = float(np.max(vals))
            feats[f"{f}_min"] = float(np.min(vals))
        feats["n_queries"] = len(self._steps)
        feats["attack_ratio"] = float(df["is_attack_query"].mean())
        return feats


class SessionClassifier:
    """Session-level classifier that loads a trained model and predicts."""

    def __init__(self, version: str | None = None):
        cfg = load_config()
        v = version or cfg.get_path("branch3_session.active_version", "nhanh3_v1")
        models_dir = Path(cfg.get_path("paths.models_dir", "models"))
        model_path = models_dir / v / "session_rf.joblib"
        feat_path = models_dir / v / "session_feature_names.joblib"

        if not model_path.exists():
            logger.warning("Session model not found at %s – predictions will default to 'not_ready'", model_path)
            self._model = None
            return

        self._model = joblib.load(model_path)
        self._feat_names = joblib.load(feat_path)
        self._aggregator = SessionAggregator(max_len=cfg.get_path("branch3_session.max_session_len", 64))
        logger.info("Loaded Branch 3 session model: %s", model_path)

    def predict(self, query: str, is_attack: float = 0.0, reset: bool = False) -> dict[str, Any]:
        """Add a query to the current session and return session-level prediction.

        Args:
            query: Raw SQL query string.
            is_attack: Per-query attack flag from Branch 1 (0=benign, 1=attack, or float score).
            reset: If True, resets the session buffer first (new session).

        Returns:
            Dict with 'session_label' (0=benign, 1=attack), 'confidence', 'is_ready'.
        """
        if self._model is None:
            return {"session_label": -1, "confidence": 0.0, "is_ready": False}

        if reset:
            self._aggregator.reset()

        self._aggregator.add_step(query, is_attack=is_attack)
        feats = self._aggregator.aggregate()

        X = pd.DataFrame([feats])[self._feat_names]
        label = int(self._model.predict(X)[0])
        proba = self._model.predict_proba(X)[0]
        confidence = float(max(proba))

        return {
            "session_label": label,
            "confidence": round(confidence, 4),
            "is_ready": True,
        }
