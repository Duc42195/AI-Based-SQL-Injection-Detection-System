"""Grid search over TF-IDF + Logistic Regression hyperparameters for Branch 1.

Directly requested: the chosen production config (char_wb, ngram (2,4),
max_features=50000, C=1, class_weight=None — configs/config.yaml
branch1_supervised.tfidf) was picked back when all 4 candidate architectures
scored ~0.99 (data_contract.md, pre-D6). Now that D6/Superviz25 widened the
gap between tfidf_logreg (0.8352) and the other architectures (up to 0.970
for DistilBERT), it's worth checking whether the TF-IDF config itself was
ever tuned for THIS harder, evasion-heavy dataset, or just carried over
un-tuned from the earlier all-models-were-0.99 era. It was carried over
un-tuned — this script actually tunes it.

Curated grid (not a full cartesian product — kept to ~16 runs, a few
minutes total): analyzer (char_wb/char/word), ngram_range, max_features,
and LogisticRegression's C / class_weight, varied one or two at a time
around the current production config rather than every combination.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report

from src.utils import get_logger, load_config

logger = get_logger(__name__)

# (name, analyzer, ngram_range, max_features, C, class_weight)
GRID: list[tuple[str, str, tuple[int, int], int, float, str | None]] = [
    ("baseline (current prod)", "char_wb", (2, 4), 50000, 1.0, None),
    ("ngram(2,5)", "char_wb", (2, 5), 50000, 1.0, None),
    ("ngram(2,6)", "char_wb", (2, 6), 50000, 1.0, None),
    ("ngram(3,6)", "char_wb", (3, 6), 50000, 1.0, None),
    ("ngram(1,4)", "char_wb", (1, 4), 50000, 1.0, None),
    ("max_features=100k", "char_wb", (2, 4), 100000, 1.0, None),
    ("ngram(2,5)+100k", "char_wb", (2, 5), 100000, 1.0, None),
    ("analyzer=char", "char", (2, 4), 50000, 1.0, None),
    ("analyzer=char,ngram(2,5)", "char", (2, 5), 50000, 1.0, None),
    ("analyzer=word", "word", (1, 2), 50000, 1.0, None),
    ("C=10", "char_wb", (2, 4), 50000, 10.0, None),
    ("C=0.1", "char_wb", (2, 4), 50000, 0.1, None),
    ("class_weight=balanced", "char_wb", (2, 4), 50000, 1.0, "balanced"),
    ("ngram(2,5)+100k+C=10", "char_wb", (2, 5), 100000, 10.0, None),
    ("ngram(2,5)+100k+C=10+balanced", "char_wb", (2, 5), 100000, 10.0, "balanced"),
    ("ngram(2,6)+100k+C=10", "char_wb", (2, 6), 100000, 10.0, None),
]


def main() -> None:
    cfg = load_config()
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    reports_dir = Path(cfg.get_path("paths.reports_dir", "report/metrics"))

    df = pd.read_csv(processed_dir / "branch1_train.csv", keep_default_na=False, na_values=[])
    train_df = df[df["split"] == "train"].reset_index(drop=True)
    test_df = df[df["split"] == "test"].reset_index(drop=True)
    logger.info("Loaded train=%d test=%d", len(train_df), len(test_df))

    results = []
    for name, analyzer, ngram_range, max_features, C, class_weight in GRID:
        t0 = time.perf_counter()
        vectorizer = TfidfVectorizer(analyzer=analyzer, ngram_range=ngram_range, max_features=max_features)
        X_train = vectorizer.fit_transform(train_df["query_canonical"].astype(str))
        X_test = vectorizer.transform(test_df["query_canonical"].astype(str))
        clf = LogisticRegression(max_iter=1000, C=C, class_weight=class_weight)
        clf.fit(X_train, train_df["label"].to_numpy())
        fit_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        y_pred = clf.predict(X_test)
        pred_time_ms = (time.perf_counter() - t0) * 1000 / len(test_df)

        report = classification_report(
            test_df["label"].to_numpy(), y_pred, output_dict=True, zero_division=0
        )
        f1_macro = report["macro avg"]["f1-score"]
        stacked_f1 = report.get("5", {}).get("f1-score")
        time_blind_f1 = report.get("4", {}).get("f1-score")

        entry = {
            "name": name,
            "analyzer": analyzer,
            "ngram_range": list(ngram_range),
            "max_features": max_features,
            "C": C,
            "class_weight": class_weight,
            "f1_macro": round(f1_macro, 4),
            "stacked_f1": round(stacked_f1, 4) if stacked_f1 is not None else None,
            "time_blind_f1": round(time_blind_f1, 4) if time_blind_f1 is not None else None,
            "vocab_size": len(vectorizer.vocabulary_),
            "fit_time_s": round(fit_time, 1),
            "pred_p50_est_ms": round(pred_time_ms, 3),
        }
        results.append(entry)
        logger.info(
            "%-32s F1=%.4f stacked=%.4f time_blind=%.4f vocab=%d fit=%.1fs",
            name, f1_macro, stacked_f1 or -1, time_blind_f1 or -1, entry["vocab_size"], fit_time,
        )

    results.sort(key=lambda r: -r["f1_macro"])
    out_path = reports_dir / "branch1_tfidf_grid_search.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump({"results": results}, f, indent=2)
    logger.info("Saved to %s", out_path)

    logger.info("=== TOP 5 BY F1-MACRO ===")
    for r in results[:5]:
        logger.info("%-32s F1=%.4f", r["name"], r["f1_macro"])


if __name__ == "__main__":
    main()
