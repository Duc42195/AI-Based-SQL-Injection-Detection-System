from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.models.branch2_anomaly import AnomalyDetector
from src.preprocessing.canonicalize import canonicalize
from src.preprocessing.statistical_features import extract_statistical_features
from src.utils import get_logger, load_config

logger = get_logger(__name__)


def _load_branch1(model_dir: str | Path) -> tuple[Any, Any, list[int]]:
    model_dir = Path(model_dir)
    vectorizer = joblib.load(model_dir / "vectorizer.joblib")
    clf = joblib.load(model_dir / "model.joblib")
    classes = [int(c) for c in clf.classes_]
    logger.info("B1 loaded from %s (n_classes=%d)", model_dir, len(classes))
    return vectorizer, clf, classes


def _b1_probs(
    query: str, vectorizer: Any, clf: Any, n_classes: int, max_decode: int
) -> list[float]:
    canonical = canonicalize(query, max_decode).query_canonical
    probs = clf.predict_proba(vectorizer.transform([canonical]))[0]
    full = [0.0] * n_classes
    for i, c in enumerate(clf.classes_):
        full[int(c)] = float(probs[i])
    return full


def _b2_score(query: str, detector: AnomalyDetector, max_decode: int) -> float:
    canonical = canonicalize(query, max_decode).query_canonical
    feats = extract_statistical_features(canonical).as_list()
    X = np.array([feats], dtype=float)
    return float(detector.score(X)[0])


def _process_session_df(
    df: pd.DataFrame,
    vectorizer: Any,
    clf: Any,
    n_b1_classes: int,
    detector: AnomalyDetector,
    max_decode: int,
    max_len: int,
) -> np.ndarray:
    df = df.sort_values("step_idx")
    steps: list[np.ndarray] = []
    for _, row in df.iterrows():
        q = row["query"]
        b1 = _b1_probs(q, vectorizer, clf, n_b1_classes, max_decode)
        b2 = _b2_score(q, detector, max_decode)
        gap = np.log1p(float(row.get("timing_seconds", 0)))
        vec = np.array(b1 + [b2, gap], dtype=np.float32)
        steps.append(vec)
    arr = np.stack(steps)
    if arr.shape[0] >= max_len:
        return arr[-max_len:]
    pad = np.zeros((max_len - arr.shape[0], arr.shape[1]), dtype=np.float32)
    return np.concatenate([pad, arr], axis=0)


def build_session_features(
    raw_dir: str | Path,
    output_dir: str | Path,
    model_dir: str | Path,
    max_decode: int = 3,
    max_len: int = 64,
    random_seed: int = 42,
) -> dict[str, Any]:
    raw_dir = Path(raw_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    b1_dir = Path(model_dir) / "branch1_v1"
    b2_dir = Path(model_dir) / "branch2_v1"

    vectorizer, clf, b1_classes = _load_branch1(b1_dir)
    n_b1 = int(max(b1_classes)) + 1
    if n_b1 != len(b1_classes):
        logger.warning(
            "B1 classes not contiguous (have %s), using n=%d",
            b1_classes, n_b1
        )

    detector = AnomalyDetector.load(b2_dir)
    logger.info("B2 loaded from %s (algorithm=%s)", b2_dir, detector.algorithm)

    class_names = ["benign", "boolean_blind", "time_blind", "query_splitting"]
    splits = ["train", "test"]

    rng = np.random.RandomState(random_seed)
    results: dict[str, Any] = {}

    for split in splits:
        all_features: list[np.ndarray] = []
        all_labels: list[int] = []
        for label, cls_name in enumerate(class_names):
            csv_path = raw_dir / f"{cls_name}_{split}.csv"
            if not csv_path.exists():
                logger.warning("Missing %s, skipping", csv_path)
                continue
            df = pd.read_csv(csv_path)
            session_ids = df["session_id"].unique()
            for sid in session_ids:
                sdf = df[df["session_id"] == sid]
                feats = _process_session_df(
                    sdf, vectorizer, clf, n_b1, detector, max_decode, max_len
                )
                all_features.append(feats)
                all_labels.append(label)
            logger.info(
                "  %s/%s: %d sessions", cls_name, split, len(session_ids)
            )

        n = len(all_features)
        perm = rng.permutation(n)
        X = np.stack([all_features[i] for i in perm], axis=0).astype(np.float32)
        y = np.array([all_labels[i] for i in perm], dtype=np.int64)

        np.save(output_dir / f"{split}_features.npy", X)
        np.save(output_dir / f"{split}_labels.npy", y)
        logger.info(
            "Saved %s: X %s, y %s (n=%d)", split, X.shape, y.shape, n
        )
        results[f"{split}_shape"] = list(X.shape)
        results[f"{split}_label_dist"] = {
            str(k): int(v) for k, v in enumerate(np.bincount(y))
        }

    meta = {
        "input_dim": n_b1 + 2,
        "max_len": max_len,
        "b1_n_classes": n_b1,
        "class_names": class_names,
        "label_map": {name: i for i, name in enumerate(class_names)},
        "feature_schema": {
            "b1_probs": {
                "indices": list(range(n_b1)),
                "classes": ["normal", "union_based", "error_based", "boolean_blind", "time_blind"],
            },
            "b2_anomaly_score": {"index": n_b1},
            "gap_log1p": {"index": n_b1 + 1},
        },
        "random_seed": random_seed,
    }
    meta_path = output_dir / "metadata.json"
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    logger.info("Metadata saved to %s", meta_path)

    results["metadata"] = meta
    return results


if __name__ == "__main__":
    cfg = load_config()
    raw_dir = Path(cfg.get_path("paths.data_raw", "data/raw")) / "branch3_sessions"
    proc_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    out_dir = proc_dir / "branch3_session_features"
    model_dir = Path(cfg.get_path("paths.models_dir", "models"))
    max_decode = int(cfg.get_path("preprocessing.max_decode_iterations", 3))
    max_len = int(cfg.get_path("branch3_session.max_len", 64))
    seed = int(cfg.get_path("project.random_seed", 42))

    report = build_session_features(
        raw_dir=raw_dir,
        output_dir=out_dir,
        model_dir=model_dir,
        max_decode=max_decode,
        max_len=max_len,
        random_seed=seed,
    )
    for k, v in report.items():
        if k == "metadata":
            continue
        print(f"  {k}: {v}")
    print(f"\nDone. Output: {out_dir}")
