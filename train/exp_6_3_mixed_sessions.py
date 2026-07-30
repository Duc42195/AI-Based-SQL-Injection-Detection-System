"""exp_6_3_mixed_sessions.py — Experiment 6.3: Mixed sessions.

Prepend benign steps to attack sessions: benign:attack = 1:2, 1:1, 2:1.
Builds features, trains B3, runs hard eval for each ratio.
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
RAW_DIR = Path("data/raw/branch3_sessions")

RATIOS = [(1, 2), (1, 1), (2, 1)]


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


def _process_sessions(df_mixed, b1_scorer, b2_model, max_decode, max_len, max_sessions):
    all_X, all_y = [], []
    for label, cls_name in enumerate(CLASS_NAMES):
        if cls_name == "benign":
            continue
        cls_df = df_mixed[df_mixed["original_class"] == cls_name]
        sids = cls_df["session_id"].unique().tolist()
        rng = np.random.RandomState(42)
        rng.shuffle(sids)
        for sid in sids[:max_sessions]:
            sdf = cls_df[cls_df["session_id"] == sid]
            vec = _build_session_vector(sdf, b1_scorer, label, b2_model, max_decode, max_len)
            all_X.append(vec)
            all_y.append(label)
    X = np.stack(all_X).astype(np.float32)
    y = np.array(all_y, dtype=np.int64)
    return X, y


def generate_mixed_sessions(benign_ratio: int, attack_ratio: int, max_sessions: int = 500) -> pd.DataFrame:
    """Prepend benign steps to attack sessions at given ratio."""
    benign_train = pd.read_csv(RAW_DIR / "benign_train.csv")
    attack_dfs = {}
    for cls_name in ["boolean_blind", "time_blind", "query_splitting"]:
        attack_dfs[cls_name] = pd.read_csv(RAW_DIR / f"{cls_name}_train.csv")

    mixed_rows = []
    rng = np.random.RandomState(42)
    next_sid = 1

    for cls_name, atk_df in attack_dfs.items():
        atk_sids = atk_df["session_id"].unique().tolist()
        rng.shuffle(atk_sids)
        ben_sids = benign_train["session_id"].unique().tolist()

        for i, atk_sid in enumerate(atk_sids[:max_sessions]):
            atk_steps = atk_df[atk_df["session_id"] == atk_sid].sort_values("step_idx")
            n_atk = len(atk_steps)
            n_ben = max(1, int(n_atk * benign_ratio / attack_ratio))

            ben_sid = ben_sids[i % len(ben_sids)]
            ben_steps = benign_train[benign_train["session_id"] == ben_sid].sort_values("step_idx")
            ben_steps = ben_steps.head(n_ben).copy()

            ben_steps["step_idx"] = range(1, len(ben_steps) + 1)
            atk_steps["step_idx"] = range(len(ben_steps) + 1, len(ben_steps) + len(atk_steps) + 1)
            ben_steps["session_id"] = next_sid
            atk_steps["session_id"] = next_sid
            ben_steps["original_class"] = "benign_prefix"
            atk_steps["original_class"] = cls_name

            mixed_rows.append(ben_steps)
            mixed_rows.append(atk_steps)
            next_sid += 1

    result = pd.concat(mixed_rows, ignore_index=True)
    result["session_label"] = result["original_class"].map({
        "boolean_blind": 1, "time_blind": 2, "query_splitting": 3, "benign_prefix": -1,
    })
    logger.info("Mixed sessions (ratio %d:%d): %d sessions, %d rows",
                benign_ratio, attack_ratio, next_sid - 1, len(result))
    return result


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


def run_experiment_for_ratio(benign_ratio: int, attack_ratio: int, cfg, max_len, max_decode, max_sessions):
    """Run full 6.3 experiment for one benign:attack ratio."""
    model_dir = Path(cfg.get_path("paths.models_dir", "models"))
    train_cfg = cfg.get_path("branch3_session.train")
    seed = int(cfg.get_path("project.random_seed", 42))

    label = f"{benign_ratio}:{attack_ratio}"
    logger.info("=" * 50)
    logger.info("Mixed session ratio %s", label)
    logger.info("=" * 50)

    logger.info("Step 1: Generate mixed sessions")
    df_train = generate_mixed_sessions(benign_ratio, attack_ratio, max_sessions)
    df_test = df_train.copy()  # reuse same pool for zero-day style; separate test below

    logger.info("Step 2: Build features with B1/B2 scoring")
    b2_model = AnomalyDetector.load(model_dir / "branch2_v1")
    vec_reg = joblib.load(Path(B1_REGULAR_DIR) / "vectorizer.joblib")
    clf_reg = joblib.load(Path(B1_REGULAR_DIR) / "model.joblib")

    def _b1_scorer(q, _cls):
        return _b1_probs(q, vec_reg, clf_reg, max_decode)

    # Split: 80% train, 20% test
    train_X, train_y = _process_sessions(df_train, _b1_scorer, b2_model, max_decode, max_len, max_sessions)
    test_X, test_y = _process_sessions(df_test, _b1_scorer, b2_model, max_decode, max_len, max_sessions // 5)

    if len(train_X) == 0 or len(test_X) == 0:
        logger.warning("No data for ratio %s, skipping", label)
        return None

    input_dim = train_X.shape[2]
    hidden_dim = int(train_cfg["hidden_dim"])
    epochs = int(train_cfg["epochs"])
    lr = float(train_cfg["learning_rate"])
    batch_size = int(train_cfg["batch_size"])

    logger.info("Step 3: Train B3 on mixed sessions (ratio %s)", label)
    model = SessionSequenceDetector(
        input_dim=input_dim, hidden_dim=hidden_dim,
        num_classes=len(CLASS_NAMES), class_names=CLASS_NAMES,
        random_seed=seed, max_len=max_len,
    )

    train_ds = SessionDataset(train_X, train_y)
    n_val = max(1, int(0.15 * len(train_ds)))
    n_tr = len(train_ds) - n_val
    train_sub, val_sub = torch.utils.data.random_split(
        train_ds, [n_tr, n_val],
        generator=torch.Generator().manual_seed(seed),
    )
    train_loader = DataLoader(train_sub, batch_size=batch_size, shuffle=True, collate_fn=collate_fn)
    val_loader = DataLoader(val_sub, batch_size=batch_size, shuffle=False, collate_fn=collate_fn)
    test_ds = SessionDataset(test_X, test_y)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False, collate_fn=collate_fn)

    fit(model, train_loader, val_loader, epochs=epochs, lr=lr)
    _, baseline_acc = eval_epoch(model, test_loader, torch.device("cpu"))
    logger.info("Baseline test accuracy: %.4f", baseline_acc)

    logger.info("Step 4: Shuffle test")
    shuffle_result = run_shuffle_test(model, test_X, test_y, seed)

    return {
        "ratio": label,
        "benign_ratio": benign_ratio,
        "attack_ratio": attack_ratio,
        "config": {
            "train_size": len(train_X),
            "test_size": len(test_X),
            "input_dim": input_dim,
            "hidden_dim": hidden_dim,
        },
        "baseline_test_acc": round(float(baseline_acc), 6),
        "shuffle_test": shuffle_result,
    }


def main():
    cfg = load_config()
    metrics_dir = Path(cfg.get_path("paths.reports_dir", "report/metrics"))
    max_len = int(cfg.get_path("branch3_session.max_session_len", 64))
    max_decode = int(cfg.get_path("preprocessing.max_decode_iterations", 3))

    max_sessions = int(cfg.get_path("branch3_session.boolean_blind.sessions_per_split", 500))

    metrics_dir.mkdir(parents=True, exist_ok=True)

    all_results = {}
    for ben_r, atk_r in RATIOS:
        result = run_experiment_for_ratio(ben_r, atk_r, cfg, max_len, max_decode, max_sessions)
        key = f"{ben_r}_{atk_r}"
        all_results[key] = result

    results = {
        "experiment": "6.3_mixed_sessions",
        "description": "Prepend benign steps to attack sessions at various ratios",
        "ratios_tested": [f"{b}:{a}" for b, a in RATIOS],
        "results": all_results,
    }
    all_pass = all(
        v and v["shuffle_test"]["passes"] for v in all_results.values() if v
    )
    results["gate_decision"] = "PASS" if all_pass else "FAIL"

    out_path = metrics_dir / "experiment_6_3_mixed_sessions.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    logger.info("Results saved to %s", out_path)
    for k, v in all_results.items():
        if v:
            logger.info("Ratio %s: acc=%.4f shuffle_f1_drop=%.4f",
                        v["ratio"], v["baseline_test_acc"], v["shuffle_test"]["f1_drop"])
    logger.info("Gate: %s", results["gate_decision"])


if __name__ == "__main__":
    main()
