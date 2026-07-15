"""Build normal traffic baseline for Branch 2 (Anomaly Detection).

Reads the raw D3 CSV, filters normal requests, canonicalises, extracts
features (TF-IDF + numerical), then saves:
- ``data/processed/nhanh2_normal.csv`` — cleaned & feature-enriched normal data
- ``models/nhanh2_v1/normal_baseline_profile.joblib`` — fitted vectorizer +
  numeric feature min/range for later transformations

Usage::

    python scripts/build_normal_baseline.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is importable
_proj_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_proj_root))

import pandas as pd
import joblib

from src.utils import get_logger, load_config
from src.preprocessing.canonicalize import canonicalize_request
from src.models.nhanh2_embed import extract_features, extract_numeric_features

logger = get_logger(__name__)


def main() -> None:
    cfg = load_config()

    # Paths
    raw_path = Path(cfg.get_path("paths.data_raw")) / "d3_csic2010_raw.csv"
    proc_dir = Path(cfg.get_path("paths.data_processed"))
    models_dir = Path(cfg.get_path("paths.models_dir")) / cfg.get_path("paths.active_version", "v0")

    proc_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load
    logger.info("Loading raw data from %s", raw_path)
    df = pd.read_csv(raw_path)
    logger.info("Total rows: %d", len(df))

    # 2. Filter normal
    df_norm = df[df["label"] == "normal"].copy()
    logger.info("Normal rows: %d", len(df_norm))

    # 3. Canonicalise
    logger.info("Canonicalising %d requests ...", len(df_norm))
    canon = []
    for _, row in df_norm.iterrows():
        canon.append(canonicalize_request(
            row["method"], row["path"], row["query"], row["body"], cfg,
        ))
    df_canon = pd.DataFrame(canon)

    # 4. Extract features (fit mode)
    logger.info("Extracting features ...")
    X, vectorizer = extract_features(df_canon, cfg=cfg, fit=True)

    # Also compute numeric-only min/range (needed because extract_features
    # already stores them on the vectorizer object)
    numeric_feat = extract_numeric_features(df_canon, cfg)
    num_min = numeric_feat.min(axis=0)
    num_range = numeric_feat.max(axis=0) - num_min
    num_range[num_range == 0] = 1.0

    # 5. Save cleaned CSV (canonicalised text + features metadata)
    df_canon["label"] = "normal"
    out_csv = proc_dir / "nhanh2_normal.csv"
    df_canon.to_csv(out_csv, index=False)
    logger.info("Saved cleaned normal data → %s (%d rows)", out_csv, len(df_canon))

    # 6. Save baseline profile (vectorizer + normalisation params)
    profile = {
        "vectorizer": vectorizer,
        "numeric_min": num_min,
        "numeric_range": num_range,
        "n_samples": len(df_norm),
        "feature_names": {
            "tfidf": list(vectorizer.get_feature_names_out()),
            "numeric": [
                "path_len", "query_len", "body_len",
                "path_special_score", "query_special_score",
                "num_special_chars", "num_digits", "num_hex_encoded", "entropy",
            ],
        },
    }
    profile_path = models_dir / "normal_baseline_profile.joblib"
    joblib.dump(profile, profile_path)
    logger.info("Saved baseline profile → %s", profile_path)

    logger.info("Done. Normal baseline ready.")


if __name__ == "__main__":
    main()
