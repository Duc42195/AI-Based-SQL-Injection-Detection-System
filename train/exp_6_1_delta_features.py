"""exp_6_1_delta_features.py — Experiment 6.1: Delta features.

Transform absolute B1/B2 scores → per-step deltas.
Trains B3 from scratch, runs hard eval (shuffle + zero-day).
Extends existing code, does NOT edit it.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import f1_score
from torch.utils.data import DataLoader

from src.models.branch2_anomaly import AnomalyDetector
from src.models.branch3_session import (
    SessionDataset,
    SessionSequenceDetector,
    collate_fn,
    eval_epoch,
    fit,
)
from src.preprocessing.canonicalize import canonicalize
from src.preprocessing.statistical_features import extract_statistical_features
from src.utils import get_logger, load_config

logger = get_logger(__name__)

CLASS_NAMES = ["benign", "boolean_blind", "time_blind", "query_splitting"]
B1_FULL_CLASSES = 5
B1_REGULAR_DIR = "models/branch1_v1"
MAX_SESSIONS_PER_CLASS = 200


def compute_deltas(X: np.ndarray) -> np.ndarray:
    """Convert absolute features to per-step deltas.

    Only computes deltas over non-padded steps.  First non-padded step
    retains its original value (delta from zero).  Padded region stays 0.
    """
    mask = X.sum(axis=2) > 0
    D = np.zeros_like(X, dtype=np.float32)
    for i in range(X.shape[0]):
        nz = np.where(mask[i])[0]
        for j, idx in enumerate(nz):
            D[i, idx] = X[i, idx] if j == 0 else X[i, idx] - X[i, nz[j - 1]]
    return D


def load_and_transform(data_dir: Path):
    X_train = np.load(data_dir / "train_features.npy")
    y_train = np.load(data_dir / "train_labels.npy")
    X_test = np.load(data_dir / "test_features.npy")
    y_test = np.load(data_dir / "test_labels.npy")
    logger.info("Loaded features: train=%s test=%s", X_train.shape, X_test.shape)

    X_train_d = compute_deltas(X_train)
    X_test_d = compute_deltas(X_test)
    logger.info("Delta transform complete: train=%s test=%s", X_train_d.shape, X_test_d.shape)
    return X_train_d, y_train, X_test_d, y_test


def run_shuffle_test(model, X, y, seed=42):
    rng = np.random.RandomState(seed)
    X_shuf = X.copy()
    for i in range(X_shuf.shape[0]):
        mask = X_shuf[i].sum(axis=1) > 0
        nz = mask.sum()
        if nz > 1:
            X_shuf[i, :nz] = X_shuf[i, :nz][rng.permutation(nz)]

    def _nonzero_seqs(x):
        seqs = []
        for i in range(x.shape[0]):
            s = x[i][x[i].sum(axis=1) > 0]
            seqs.append(s if len(s) > 0 else x[i][:1])
        return seqs

    pred_orig, _ = model.predict(_nonzero_seqs(X))
    pred_shuf, _ = model.predict(_nonzero_seqs(X_shuf))

    f1_orig = float(f1_score(y, pred_orig, average="macro"))
    f1_shuf = float(f1_score(y, pred_shuf, average="macro"))
    acc_orig = float((y == pred_orig).mean())
    acc_shuf = float((y == pred_shuf).mean())

    return {
        "original_accuracy": round(acc_orig, 4),
        "shuffled_accuracy": round(acc_shuf, 4),
        "accuracy_drop": round(acc_orig - acc_shuf, 4),
        "original_f1_macro": round(f1_orig, 4),
        "shuffled_f1_macro": round(f1_shuf, 4),
        "f1_drop": round(f1_orig - f1_shuf, 4),
        "passes": bool(f1_shuf < f1_orig - 0.01),
    }


def _b1_probs(query, vectorizer, clf, max_decode):
    canonical = canonicalize(query, max_decode).query_canonical
    probs = clf.predict_proba(vectorizer.transform([canonical]))[0]
    full = [0.0] * B1_FULL_CLASSES
    for i, c in enumerate(clf.classes_):
        full[int(c)] = float(probs[i])
    return full


def _b2_score(query, b2_model, max_decode):
    canonical = canonicalize(query, max_decode).query_canonical
    feats = extract_statistical_features(canonical).as_list()
    return float(b2_model.score(np.array([feats], dtype=float))[0])


def _build_session_vector(df, b1_scorer, cls_label, b2_model, max_decode, max_len):
    df = df.sort_values("step_idx")
    steps = []
    for _, row in df.iterrows():
        b1 = b1_scorer(row["query"], cls_label)
        b2 = _b2_score(row["query"], b2_model, max_decode)
        gap = np.log1p(float(row.get("timing_seconds", 0)))
        steps.append(np.array(b1 + [b2, gap], dtype=np.float32))
    arr = np.stack(steps)
    if arr.shape[0] >= max_len:
        return arr[-max_len:]
    pad = np.zeros((max_len - arr.shape[0], arr.shape[1]), dtype=np.float32)
    return np.concatenate([pad, arr], axis=0)


def _process_sessions(raw_dir, split, b1_scorer, b2_model, max_decode, max_len, max_sessions):
    all_X, all_y = [], []
    rng = np.random.RandomState(42)
    for label, cls_name in enumerate(CLASS_NAMES):
        csv_path = Path(raw_dir) / f"{cls_name}_{split}.csv"
        if not csv_path.exists():
            continue
        df = pd.read_csv(csv_path)
        sids = df["session_id"].unique().tolist()
        rng.shuffle(sids)
        for sid in sids[:max_sessions]:
            sdf = df[df["session_id"] == sid]
            vec = _build_session_vector(sdf, b1_scorer, label, b2_model, max_decode, max_len)
            all_X.append(vec)
            all_y.append(label)
    X = np.stack(all_X).astype(np.float32)
    y = np.array(all_y, dtype=np.int64)
    return compute_deltas(X), y


def run_zero_day_test(b2_model, raw_dir, max_len=64, max_decode=3, max_sessions=MAX_SESSIONS_PER_CLASS):
    variants = {
        "no_boolean_blind": ("models/branch1_no_boolean_blind", 1),
        "no_time_blind": ("models/branch1_no_time_blind", 2),
    }
    cfg = load_config()
    train_cfg = cfg.get_path("branch3_session.train")
    seed = int(cfg.get_path("project.random_seed", 42))

    results = {}
    for var_name, (b1_dir, target_label) in variants.items():
        logger.info("Zero-day %s — building delta features", var_name)

        vec_var = joblib.load(Path(b1_dir) / "vectorizer.joblib")
        clf_var = joblib.load(Path(b1_dir) / "model.joblib")
        vec_reg = joblib.load(Path(B1_REGULAR_DIR) / "vectorizer.joblib")
        clf_reg = joblib.load(Path(B1_REGULAR_DIR) / "model.joblib")

        def _make_scorer(vv, cv, vr, cr, tgt):
            def scorer(q, cls_label):
                v, c = (vv, cv) if cls_label == tgt else (vr, cr)
                return _b1_probs(q, v, c, max_decode)
            return scorer

        scorer = _make_scorer(vec_var, clf_var, vec_reg, clf_reg, target_label)

        train_X, train_y = _process_sessions(raw_dir, "train", scorer, b2_model, max_decode, max_len, max_sessions)
        test_X, test_y = _process_sessions(raw_dir, "test", scorer, b2_model, max_decode, max_len, max_sessions)

        input_dim = train_X.shape[2]
        hidden_dim = int(train_cfg["hidden_dim"])
        epochs = int(train_cfg["epochs"])
        lr = float(train_cfg["learning_rate"])
        batch_size = int(train_cfg["batch_size"])

        model = SessionSequenceDetector(
            input_dim=input_dim, hidden_dim=hidden_dim,
            num_classes=len(CLASS_NAMES), class_names=CLASS_NAMES,
            random_seed=seed, max_len=max_len,
        )

        train_ds = SessionDataset(train_X, train_y)
        test_ds = SessionDataset(test_X, test_y)
        val_size = max(1, int(0.15 * len(train_ds)))
        train_sub, val_sub = torch.utils.data.random_split(
            train_ds, [len(train_ds) - val_size, val_size],
            generator=torch.Generator().manual_seed(seed),
        )
        train_loader = DataLoader(train_sub, batch_size=batch_size, shuffle=True, collate_fn=collate_fn)
        val_loader = DataLoader(val_sub, batch_size=batch_size, shuffle=False, collate_fn=collate_fn)
        test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False, collate_fn=collate_fn)

        fit(model, train_loader, val_loader, epochs=epochs, lr=lr)
        test_loss, test_acc = eval_epoch(model, test_loader, torch.device("cpu"))

        seqs = []
        for i in range(test_X.shape[0]):
            s = test_X[i][test_X[i].sum(axis=1) > 0]
            seqs.append(s if len(s) > 0 else test_X[i][:1])
        preds, _ = model.predict(seqs)

        target_idx = np.where(test_y == target_label)[0]
        recall_target = float((preds[target_idx] == target_label).mean()) if len(target_idx) > 0 else 0.0

        results[var_name] = {
            "b1_variant": b1_dir,
            "target_class": CLASS_NAMES[target_label],
            "test_acc": round(float(test_acc), 6),
            "test_loss": round(float(test_loss), 6),
            "target_recall": round(recall_target, 4),
            "passes": bool(recall_target > 0.90),
        }
        logger.info("Zero-day %s: test_acc=%.4f target_recall=%.4f", var_name, test_acc, recall_target)

    return results


def main():
    cfg = load_config()
    proc_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    metrics_dir = Path(cfg.get_path("paths.reports_dir", "report/metrics"))
    raw_dir = proc_dir.parent / "raw" / "branch3_sessions"
    data_dir = proc_dir / "branch3_session_features"
    model_dir = Path(cfg.get_path("paths.models_dir", "models"))
    max_len = int(cfg.get_path("branch3_session.max_session_len", 64))
    max_decode = int(cfg.get_path("preprocessing.max_decode_iterations", 3))
    seed = int(cfg.get_path("project.random_seed", 42))
    train_cfg = cfg.get_path("branch3_session.train")

    logger.info("=" * 50)
    logger.info("Experiment 6.1 — Delta Features")
    logger.info("=" * 50)

    logger.info("Step 1: Load & transform to delta features")
    X_train, y_train, X_test, y_test = load_and_transform(data_dir)

    logger.info("Step 2: Train B3 on delta features")
    input_dim = X_train.shape[2]
    hidden_dim = int(train_cfg["hidden_dim"])
    epochs = int(train_cfg["epochs"])
    lr = float(train_cfg["learning_rate"])
    batch_size = int(train_cfg["batch_size"])

    model = SessionSequenceDetector(
        input_dim=input_dim, hidden_dim=hidden_dim,
        num_classes=len(CLASS_NAMES), class_names=CLASS_NAMES,
        random_seed=seed, max_len=max_len,
    )

    train_ds = SessionDataset(X_train, y_train)
    n_val = int(0.15 * len(train_ds))
    n_train = len(train_ds) - n_val
    train_sub, val_sub = torch.utils.data.random_split(
        train_ds, [n_train, n_val],
        generator=torch.Generator().manual_seed(seed),
    )
    train_loader = DataLoader(train_sub, batch_size=batch_size, shuffle=True, collate_fn=collate_fn)
    val_loader = DataLoader(val_sub, batch_size=batch_size, shuffle=False, collate_fn=collate_fn)
    test_ds = SessionDataset(X_test, y_test)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False, collate_fn=collate_fn)

    fit(model, train_loader, val_loader, epochs=epochs, lr=lr)
    _, baseline_acc = eval_epoch(model, test_loader, torch.device("cpu"))
    logger.info("Baseline test accuracy on delta features: %.4f", baseline_acc)

    logger.info("Step 3: Shuffle test")
    shuffle_result = run_shuffle_test(model, X_test, y_test, seed)

    logger.info("Step 4: Zero-day test")
    b2_model = AnomalyDetector.load(model_dir / "branch2_v1")
    zero_day_result = run_zero_day_test(b2_model, raw_dir, max_len, max_decode)

    results = {
        "experiment": "6.1_delta_features",
        "description": "Replace absolute B1/B2 scores with per-step deltas",
        "config": {
            "train_size": len(X_train),
            "test_size": len(X_test),
            "input_dim": input_dim,
            "hidden_dim": hidden_dim,
            "epochs": epochs,
            "batch_size": batch_size,
            "max_len": max_len,
        },
        "baseline_test_acc": round(float(baseline_acc), 6),
        "shuffle_test": shuffle_result,
        "zero_day_test": zero_day_result,
    }
    all_pass = shuffle_result["passes"] and all(v["passes"] for v in zero_day_result.values())
    results["gate_decision"] = "PASS" if all_pass else "FAIL"

    metrics_dir.mkdir(parents=True, exist_ok=True)
    out_path = metrics_dir / "experiment_6_1_delta_features.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    logger.info("Results saved to %s", out_path)
    logger.info("Shuffle: f1_drop=%.4f passes=%s", shuffle_result["f1_drop"], shuffle_result["passes"])
    for vn, vr in zero_day_result.items():
        logger.info("Zero-day %s: recall=%.4f passes=%s", vn, vr["target_recall"], vr["passes"])
    logger.info("Gate: %s", results["gate_decision"])


if __name__ == "__main__":
    main()
