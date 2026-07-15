"""Tests for the Branch 2 feature extraction module."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.models.nhanh2_embed import (
    extract_numeric_features,
    build_tfidf_vectorizer,
    extract_features,
)


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "canonical_text": [
            "GET /index.jsp id=1",
            "POST /login.jsp user=admin",
        ],
        "path": ["/index.jsp", "/login.jsp"],
        "query": ["id=1", "user=admin"],
        "body": ["", "password=123"],
    })


def test_extract_numeric_features_shape():
    df = _sample_df()
    features = extract_numeric_features(df)
    assert features.shape[0] == 2
    assert features.shape[1] == 9  # 9 numeric features


def test_extract_numeric_features_dtype():
    df = _sample_df()
    features = extract_numeric_features(df)
    assert features.dtype == np.float32


def test_build_tfidf_vectorizer():
    vec = build_tfidf_vectorizer()
    assert vec.analyzer == "char_wb"
    assert vec.ngram_range == (2, 5)
    assert vec.max_features == 10000


def test_extract_features_fit():
    df = _sample_df()
    mat, vec = extract_features(df, fit=True)
    assert vec is not None
    assert mat.shape[0] == 2
    # combined = tfidf_features + 9 numeric features
    assert mat.shape[1] > 9


def test_extract_features_fit_then_transform():
    df = _sample_df()
    _, vec = extract_features(df, fit=True)
    mat2, _ = extract_features(df, vectorizer=vec)
    assert mat2.shape[0] == 2
