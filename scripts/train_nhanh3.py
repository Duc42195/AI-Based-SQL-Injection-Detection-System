"""Train and evaluate Branch 3 session classifier using sklearn.

Loads Cách A (simulated) or Cách B (sqlmap-captured) session data,
aggregates per-step features into session-level vectors, and trains a
Random Forest classifier for session-level binary classification
(benign vs attack).

Usage:
    python scripts/train_nhanh3.py                     # uses Cách A by default
    python scripts/train_nhanh3.py --cach B             # uses Cách B data
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split

from src.preprocessing.statistical_features import extract_statistical_features
from src.utils import get_logger, load_config

logger = get_logger(__name__)

FEATURE_NAMES = ["length", "special_char_ratio", "sql_keyword_count", "entropy"]
_SESSION_LABEL_NAMES = ["benign", "attack"]

def _session_features(group: pd.DataFrame) -> dict:
    """Aggregate per-step features into session-level statistics."""
    feats = {}
    for f in FEATURE_NAMES:
        vals = group[f].values
        feats[f"{f}_mean"] = float(np.mean(vals))
        feats[f"{f}_std"] = float(np.std(vals))
        feats[f"{f}_max"] = float(np.max(vals))
        feats[f"{f}_min"] = float(np.min(vals))
    feats["n_queries"] = len(group)
    feats["attack_ratio"] = float(group["is_attack_query"].mean())
    return feats


def _load_data(path: Path) -> pd.DataFrame:
    if not path.exists():
        logger.error("File not found: %s", path)
        sys.exit(1)
    df = pd.read_csv(path)
    logger.info("Loaded %d step-rows from %s", len(df), path)
    return df


def main():
    cfg = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--cach", choices=["A", "B"], default="A")
    args = parser.parse_args()

    pd_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    models_dir = Path(cfg.get_path("paths.models_dir", "models"))
    version = cfg.get_path("branch3_session.active_version", "nhanh3_v1")
    out_dir = models_dir / version
    out_dir.mkdir(parents=True, exist_ok=True)
    seed = cfg.get_path("project.random_seed", 42)

    if args.cach == "A":
        data_path = pd_dir / "nhanh3_session_data.csv"
        label_name = "session_label"
        # Cách A has 4 classes: 0=benign, 1=boolean_blind, 2=time_blind, 3=query_splitting
        # Convert to binary: 0=benign, 1=attack (any non-zero)
        binary = True
    else:
        data_path = pd_dir / "nhanh3_session_data_cachb.csv"
        label_name = "session_label"
        binary = True

    df = _load_data(data_path)
    if binary:
        df["label_binary"] = (df[label_name] > 0).astype(int)
        target = "label_binary"
        class_names = _SESSION_LABEL_NAMES
    else:
        target = label_name
        class_names = sorted(df[target].unique())

    # Aggregate session-level features
    sessions = df.groupby("session_id")
    X_rows = []
    y_rows = []
    for sid, group in sessions:
        X_rows.append(_session_features(group))
        y_rows.append(group[target].iloc[0])

    X = pd.DataFrame(X_rows)
    y = np.array(y_rows)
    logger.info("Session-level features: %s", list(X.columns))
    logger.info("Class distribution: benign=%d  attack=%d", int((y == 0).sum()), int((y > 0).sum()))

    # Train/test split (by session)
    if args.cach == "A":
        # Cách A already has split column
        train_ids = set(df[df["split"] == "train"]["session_id"].unique())
        test_ids = set(df[df["split"] == "test"]["session_id"].unique())
        X_train = X[X.index.isin(train_ids)]
        y_train = y[X.index.isin(train_ids)]
        X_test = X[X.index.isin(test_ids)]
        y_test = y[X.index.isin(test_ids)]
    else:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=seed, stratify=y,
        )

    logger.info("Train sessions: %d  Test sessions: %d", len(X_train), len(X_test))

    # Train
    clf = RandomForestClassifier(
        n_estimators=200, max_depth=12, random_state=seed,
        class_weight="balanced", n_jobs=-1,
    )
    clf.fit(X_train, y_train)

    # Evaluate
    y_pred = clf.predict(X_test)
    y_proba = clf.predict_proba(X_test)[:, 1] if len(clf.classes_) == 2 else clf.predict_proba(X_test)

    report = classification_report(y_test, y_pred, target_names=class_names, output_dict=True, digits=4)
    cm = confusion_matrix(y_test, y_pred)
    wf1 = f1_score(y_test, y_pred, average="weighted")

    logger.info("\n" + classification_report(y_test, y_pred, target_names=class_names, digits=4))
    logger.info("Confusion matrix:\n%s", cm)

    if len(np.unique(y_test)) == 2:
        auc = roc_auc_score(y_test, y_proba)
        logger.info("ROC AUC: %.4f", auc)
    else:
        auc = None

    # Save model
    import joblib
    joblib.dump(clf, out_dir / "session_rf.joblib")
    joblib.dump(X.columns.tolist(), out_dir / "session_feature_names.joblib")

    # Save eval report
    eval_report = {
        "version": version,
        "branch": "nhanh3_session",
        "data_source": f"Cách {args.cach}",
        "feature_names": X.columns.tolist(),
        "model": "RandomForest(n_estimators=200, max_depth=12)",
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "class_distribution_train": {str(k): int(v) for k, v in zip(*np.unique(y_train, return_counts=True))},
        "class_distribution_test": {str(k): int(v) for k, v in zip(*np.unique(y_test, return_counts=True))},
        "test_metrics": {
            "weighted_f1": round(wf1, 4),
            "classification_report": report,
            "confusion_matrix": cm.tolist(),
        },
    }
    if auc is not None:
        eval_report["test_metrics"]["roc_auc"] = round(auc, 4)

    report_path = Path(__file__).resolve().parent.parent / "reports" / f"nhanh3_eval_cach{args.cach}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(eval_report, f, indent=2)
    logger.info("Saved eval report to %s", report_path)
    logger.info("=== Done ===")


if __name__ == "__main__":
    main()
