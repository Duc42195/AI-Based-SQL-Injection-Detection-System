"""Train the production Branch-1 model (chosen architecture) and version it.

Trains the architecture selected in configs/config.yaml
(branch1_supervised.architecture) on data/processed/nhanh1_train.csv and saves
it under models/<version>/ with a metadata.json describing the run — enabling
the simple date/version-based model versioning + rollback described in the
proposal (MLOps-lite). Currently supports the chosen "tfidf_logreg".
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report

from src.preprocessing.multiclass_tagger import LABEL_NAMES
from src.utils import get_logger, load_config

logger = get_logger(__name__)


def main() -> None:
    """Train and version the chosen Branch-1 model."""
    cfg = load_config()
    architecture = cfg.get_path("branch1_supervised.architecture")
    if architecture != "tfidf_logreg":
        raise NotImplementedError(
            f"train_nhanh1.py currently only supports 'tfidf_logreg', got '{architecture}'. "
            "See scripts/compare_nhanh1_architectures.py for the other candidates."
        )

    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    models_dir = Path(cfg.get_path("paths.models_dir", "models"))
    version = "nhanh1_v1"
    out_dir = models_dir / version
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(processed_dir / "nhanh1_train.csv")
    train_df = df[df["split"] == "train"].reset_index(drop=True)
    test_df = df[df["split"] == "test"].reset_index(drop=True)
    logger.info("Loaded train=%d test=%d", len(train_df), len(test_df))

    tfidf_cfg = cfg.get_path("branch1_supervised.tfidf")
    vectorizer = TfidfVectorizer(
        analyzer=tfidf_cfg["analyzer"],
        ngram_range=(tfidf_cfg["ngram_min"], tfidf_cfg["ngram_max"]),
        max_features=tfidf_cfg["max_features"],
    )
    logger.info("Fitting TF-IDF + Logistic Regression ...")
    X_train = vectorizer.fit_transform(train_df["query_canonical"].astype(str))
    clf = LogisticRegression(max_iter=1000)
    t0 = time.perf_counter()
    clf.fit(X_train, train_df["label"].to_numpy())
    train_time_s = time.perf_counter() - t0

    X_test = vectorizer.transform(test_df["query_canonical"].astype(str))
    # Labels actually present in this dataset (NOT the static full schema) -
    # excluding an unused label (e.g. `stacked`, currently disabled) avoids
    # scoring a phantom class with 0 support as f1=0, which silently corrupts
    # the macro average (caught 16/7: reported F1 dropped 0.985->0.82 purely
    # from this bug, real F1 was ~0.98).
    labels_present = sorted(set(train_df["label"]) | set(test_df["label"]))
    target_names = [LABEL_NAMES[i] for i in labels_present]
    report = classification_report(
        test_df["label"].to_numpy(),
        clf.predict(X_test),
        labels=labels_present,
        target_names=target_names,
        output_dict=True,
        zero_division=0,
    )
    f1_macro = report["macro avg"]["f1-score"]
    logger.info("Test F1-macro=%.4f (train_time=%.1fs)", f1_macro, train_time_s)

    joblib.dump(vectorizer, out_dir / "vectorizer.joblib")
    joblib.dump(clf, out_dir / "model.joblib")

    metadata = {
        "version": version,
        "branch": "nhanh1_supervised_multiclass",
        "architecture": architecture,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "f1_macro": f1_macro,
        "train_time_s": train_time_s,
        "labels": {str(i): LABEL_NAMES[i] for i in labels_present},
        "dataset": "data/processed/nhanh1_train.csv",
        "tfidf": dict(tfidf_cfg),
    }
    with (out_dir / "metadata.json").open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    logger.info("Saved model + metadata to %s", out_dir)


if __name__ == "__main__":
    main()
