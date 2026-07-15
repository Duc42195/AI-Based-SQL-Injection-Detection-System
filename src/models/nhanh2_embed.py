"""Feature extraction for Branch 2 (Anomaly Detection).

Extracts both sparse TF-IDF features and dense numerical features from
canonicalised HTTP request data for training/evaluation with Isolation Forest
or One-Class SVM.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy.sparse import csr_array, hstack as sparse_hstack
from sklearn.feature_extraction.text import TfidfVectorizer

from src.utils import get_logger

logger = get_logger(__name__)


def _safe_len(text: str) -> int:
    return len(text) if text else 0


def _count_special_chars(text: str) -> int:
    return sum(not c.isalnum() and not c.isspace() for c in text) if text else 0


def _count_digits(text: str) -> int:
    return sum(c.isdigit() for c in text) if text else 0


def _count_hex_encoded(text: str) -> int:
    return text.count("%") if text else 0


def _entropy(text: str) -> float:
    if not text:
        return 0.0
    prob = [text.count(c) / len(text) for c in set(text)]
    return -sum(p * np.log2(p) for p in prob)


def extract_numeric_features(df: pd.DataFrame,
                             cfg: dict[str, Any] | None = None) -> npt.NDArray:
    """Extract dense numerical features from a canonicalised request DataFrame.

    Features per row:
    - path_len, query_len, body_len
    - path_special_ratio, query_special_ratio
    - num_special_chars, num_digits, num_hex_encoded
    - entropy (of canonical_text)

    Args:
        df: DataFrame with columns ``canonical_text``, ``path``, ``query``,
            ``body``.
        cfg: Optional config with ``branch2_anomaly.feature.numeric`` section.

    Returns:
        ``(n_samples, n_features)`` float32 array.
    """
    feat_cols = cfg.get("branch2_anomaly", {}).get("feature", {}).get("numeric", {}) if cfg else {}
    _max_path = feat_cols.get("path_max_len", 500)
    _max_query = feat_cols.get("query_max_len", 1000)
    _max_body = feat_cols.get("body_max_len", 2000)

    rows: list[npt.NDArray] = []
    for _, row in df.iterrows():
        path = row.get("path", "")[:_max_path]
        query = row.get("query", "")[:_max_query]
        body = row.get("body", "")[:_max_body]
        text = row.get("canonical_text", "")

        features = np.array([
            float(_safe_len(path)),
            float(_safe_len(query)),
            float(_safe_len(body)),
            _safe_len(path) / max(_safe_len(path) + 1, 1) * _count_special_chars(path),
            _safe_len(query) / max(_safe_len(query) + 1, 1) * _count_special_chars(query),
            float(_count_special_chars(text)),
            float(_count_digits(text)),
            float(_count_hex_encoded(text)),
            _entropy(text),
        ], dtype=np.float32)
        rows.append(features)

    return np.array(rows, dtype=np.float32)


def build_tfidf_vectorizer(cfg: dict[str, Any] | None = None) -> TfidfVectorizer:
    """Build a TF-IDF vectorizer configured for Branch 2.

    Args:
        cfg: Config dict; reads ``branch2_anomaly.feature.tfidf`` section.

    Returns:
        Configured (unfitted) ``TfidfVectorizer`` instance.
    """
    tfidf_cfg = cfg.get("branch2_anomaly", {}).get("feature", {}).get("tfidf", {}) if cfg else {}
    return TfidfVectorizer(
        analyzer=tfidf_cfg.get("analyzer", "char_wb"),
        ngram_range=(tfidf_cfg.get("ngram_min", 2), tfidf_cfg.get("ngram_max", 5)),
        max_features=tfidf_cfg.get("max_features", 10000),
        sublinear_tf=True,
        dtype=np.float32,
    )


def extract_features(df: pd.DataFrame,
                     vectorizer: TfidfVectorizer | None = None,
                     cfg: dict[str, Any] | None = None,
                     fit: bool = False,
                     ) -> tuple[csr_array | npt.NDArray, TfidfVectorizer | None]:
    """Extract combined TF-IDF + numeric features.

    Args:
        df: DataFrame with columns ``canonical_text``, ``path``, ``query``,
            ``body``.
        vectorizer: Pre-fitted ``TfidfVectorizer``. If ``None`` and ``fit`` is
            ``True``, a new vectorizer is fitted.
        cfg: Optional config dict.
        fit: If ``True``, fit the TF-IDF vectorizer.

    Returns:
        Tuple of ``(feature_matrix, fitted_vectorizer)``.

    Raises:
        ValueError: If ``vectorizer`` is ``None`` and ``fit`` is ``False``.
    """
    if vectorizer is None and not fit:
        raise ValueError("Must provide a fitted vectorizer or set fit=True")

    texts = df["canonical_text"].tolist() if "canonical_text" in df.columns else df["path"].fillna("").tolist()  # noqa: E501

    vec = vectorizer
    if fit:
        vec = build_tfidf_vectorizer(cfg)
        vec.fit(texts)
        logger.info("TfidfVectorizer fitted — %d features", len(vec.get_feature_names_out()))

    tfidf_mat: csr_array = vec.transform(texts)  # type: ignore[assignment]

    numeric_feat = extract_numeric_features(df, cfg)
    # Normalise numeric features to [0,1] range per column via min-max
    if fit:
        _numeric_min = numeric_feat.min(axis=0)
        _numeric_range = numeric_feat.max(axis=0) - _numeric_min
        _numeric_range[_numeric_range == 0] = 1.0
        vec._numeric_min = _numeric_min  # type: ignore[attr-defined]
        vec._numeric_range = _numeric_range  # type: ignore[attr-defined]

    num_min = getattr(vec, "_numeric_min", numeric_feat.min(axis=0))
    num_range = getattr(vec, "_numeric_range", numeric_feat.max(axis=0) - numeric_feat.min(axis=0))
    num_range[num_range == 0] = 1.0
    numeric_norm = (numeric_feat - num_min) / num_range

    combined = sparse_hstack([tfidf_mat, csr_array(numeric_norm, dtype=np.float32)])
    return combined, vec
