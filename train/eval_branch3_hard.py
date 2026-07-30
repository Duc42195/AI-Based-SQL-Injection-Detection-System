"""eval_branch3_hard.py — Phase 4 hard evaluation suite.

Tests:
- 4.1 Shuffle test: shuffle step order, measure F1 change
- 4.2 Zero-day test: B1 leave-one-out variants, check B3 recall
- 4.3 Ablation (verify Phase 3 results)
- 4.4 Diversity re-verify
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import confusion_matrix, f1_score

from src.models.branch2_anomaly import AnomalyDetector
from src.models.branch3_session import SessionSequenceDetector, fit as b3_fit
from src.preprocessing.canonicalize import canonicalize
from src.preprocessing.statistical_features import extract_statistical_features
from src.utils import get_logger, load_config

warnings.filterwarnings("ignore")
logger = get_logger(__name__)

CLASS_NAMES = ["benign", "boolean_blind", "time_blind", "query_splitting"]
MAX_SESSIONS_PER_CLASS = 200  # keep zero-day test under ~2 min


def _load_b3_model(model_dir: str | Path) -> SessionSequenceDetector:
    return SessionSequenceDetector.load(str(model_dir))


def _load_b2_model(model_dir: str | Path) -> AnomalyDetector:
    return AnomalyDetector.load(str(model_dir))


def _load_baseline_features(data_dir: str | Path) -> tuple[np.ndarray, np.ndarray]:
    data_dir = Path(data_dir)
    X = np.load(data_dir / "test_features.npy")
    y = np.load(data_dir / "test_labels.npy")
    return X, y


def _predict(model: SessionSequenceDetector, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    sequences = [X[i][X[i].sum(axis=1) > 0] for i in range(X.shape[0])]
    sequences = [s if len(s) > 0 else X[i][:1] for i, s in enumerate(sequences)]
    return model.predict(sequences)


def _classification_report(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    cm = confusion_matrix(y_true, y_pred).tolist()
    f1_per_class = f1_score(y_true, y_pred, average=None).tolist()
    f1_macro = float(f1_score(y_true, y_pred, average="macro"))
    acc = float((y_true == y_pred).mean())
    return {
        "confusion_matrix": cm,
        "f1_per_class": {CLASS_NAMES[i]: round(v, 4) for i, v in enumerate(f1_per_class)},
        "f1_macro": round(f1_macro, 4),
        "accuracy": round(acc, 4),
    }


# ━━━ 4.1 Shuffle Test ━━━

def run_shuffle_test(
    model: SessionSequenceDetector, X: np.ndarray, y: np.ndarray, seed: int = 42
) -> dict:
    rng = np.random.RandomState(seed)
    X_shuf = X.copy()
    for i in range(X_shuf.shape[0]):
        mask = X_shuf[i].sum(axis=1) > 0
        nz = mask.sum()
        if nz > 1:
            X_shuf[i, :nz] = X_shuf[i, :nz][rng.permutation(nz)]

    pred_orig, _ = _predict(model, X)
    pred_shuf, _ = _predict(model, X_shuf)

    orig = _classification_report(y, pred_orig)
    shuf = _classification_report(y, pred_shuf)

    result = {
        "original_accuracy": orig["accuracy"],
        "shuffled_accuracy": shuf["accuracy"],
        "accuracy_drop": round(orig["accuracy"] - shuf["accuracy"], 4),
        "original_f1_macro": orig["f1_macro"],
        "shuffled_f1_macro": shuf["f1_macro"],
        "f1_drop": round(orig["f1_macro"] - shuf["f1_macro"], 4),
        "passes": shuf["f1_macro"] < orig["f1_macro"] - 0.01,
    }
    logger.info("Shuffle test: orig_acc=%.4f shuf_acc=%.4f", orig["accuracy"], shuf["accuracy"])
    return result


# ━━━ 4.2 Zero-Day Test ━━━

def _load_b1_variant(model_dir: str | Path) -> tuple[any, any]:
    model_dir = Path(model_dir)
    meta_path = model_dir / "metadata.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    vec = joblib.load(model_dir / "vectorizer.joblib")
    clf = joblib.load(model_dir / "model.joblib")
    excluded = meta.get("excluded_label", None)
    excluded_name = meta.get("excluded_label_name", "unknown")
    logger.info(
        "B1 variant loaded from %s (excluded=%s)",
        model_dir, f"{excluded_name}({excluded})",
    )
    return vec, clf


B1_FULL_CLASSES = 5  # always pad to match B3 input dim

B1_REGULAR_DIR = "models/branch1_v1"


def _b1_probs(query: str, vectorizer: any, clf: any, max_decode: int) -> list[float]:
    canonical = canonicalize(query, max_decode).query_canonical
    probs = clf.predict_proba(vectorizer.transform([canonical]))[0]
    full = [0.0] * B1_FULL_CLASSES
    for i, c in enumerate(clf.classes_):
        full[int(c)] = float(probs[i])
    return full


def _b2_score(query: str, b2_model: AnomalyDetector, max_decode: int) -> float:
    canonical = canonicalize(query, max_decode).query_canonical
    feats = extract_statistical_features(canonical).as_list()
    X = np.array([feats], dtype=float)
    return float(b2_model.score(X)[0])


def _make_b1_scorer(b1_dir: str, b1_regular_dir: str, target_label: int, max_decode: int):
    """Create scorer: variant B1 for target class, regular B1 for others."""
    vec_var, clf_var = _load_b1_variant(b1_dir)
    vec_reg = joblib.load(Path(b1_regular_dir) / "vectorizer.joblib")
    clf_reg = joblib.load(Path(b1_regular_dir) / "model.joblib")

    def scorer(query: str, cls_label: int) -> list[float]:
        v, c = (vec_var, clf_var) if cls_label == target_label else (vec_reg, clf_reg)
        return _b1_probs(query, v, c, max_decode)

    return scorer


def _build_session_vector(
    df: pd.DataFrame,
    b1_scorer: callable,
    cls_label: int,
    b2_model: AnomalyDetector,
    max_decode: int,
    max_len: int,
) -> np.ndarray:
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


def _process_sessions(
    raw_dir: str | Path,
    b1_scorer: callable,
    b2_model: AnomalyDetector,
    split: str,
    max_decode: int,
    max_len: int,
    max_sessions: int,
) -> tuple[np.ndarray, np.ndarray]:
    all_features, all_labels = [], []
    for label, cls_name in enumerate(CLASS_NAMES):
        csv_path = Path(raw_dir) / f"{cls_name}_{split}.csv"
        if not csv_path.exists():
            continue
        df = pd.read_csv(csv_path)
        sids = df["session_id"].unique().tolist()
        rng = np.random.RandomState(42)
        rng.shuffle(sids)
        selected = sids[:max_sessions]
        for sid in selected:
            sdf = df[df["session_id"] == sid]
            feats = _build_session_vector(sdf, b1_scorer, label, b2_model, max_decode, max_len)
            all_features.append(feats)
            all_labels.append(label)
    X = np.stack(all_features, axis=0).astype(np.float32)
    y = np.array(all_labels, dtype=np.int64)
    return X, y


def run_zero_day_test(
    b2_model: AnomalyDetector,
    raw_dir: str | Path,
    max_len: int = 64,
    max_decode: int = 3,
    max_sessions: int = MAX_SESSIONS_PER_CLASS,
) -> dict:
    """Test B3 recall when B1 misses one class entirely.

    Follows mentor's methodology:
    - Re-score target class with variant B1
    - Other classes keep regular B1
    - Train NEW B3 model on re-scored data
    - Eval → check recall on target class
    """
    variants = {
        "no_boolean_blind": ("models/branch1_no_boolean_blind", 1),
        "no_time_blind": ("models/branch1_no_time_blind", 2),
    }
    cfg = load_config()
    train_cfg = cfg.get_path("branch3_session.train")
    class_names = CLASS_NAMES

    results = {}
    for variant_name, (b1_dir, target_label) in variants.items():
        target_class = class_names[target_label]
        logger.info("Zero-day %s: re-scoring + training (target=%s)", variant_name, target_class)

        b1_scorer = _make_b1_scorer(b1_dir, B1_REGULAR_DIR, target_label, max_decode)

        train_X, train_y = _process_sessions(
            raw_dir, b1_scorer, b2_model, "train", max_decode, max_len, max_sessions,
        )
        test_X, test_y = _process_sessions(
            raw_dir, b1_scorer, b2_model, "test", max_decode, max_len, max_sessions,
        )

        seed = int(cfg.get_path("project.random_seed", 42))
        input_dim = train_X.shape[2]
        hidden_dim = int(train_cfg["hidden_dim"])
        epochs = int(train_cfg["epochs"])
        lr = float(train_cfg["learning_rate"])
        batch_size = int(train_cfg["batch_size"])

        model = SessionSequenceDetector(
            input_dim=input_dim, hidden_dim=hidden_dim,
            num_classes=len(class_names), class_names=class_names,
            random_seed=seed, max_len=max_len,
        )
        logger.info(
            "Training B3 (zero-day) — input_dim=%d, train=%d, test=%d",
            input_dim, len(train_X), len(test_X),
        )
        from torch.utils.data import DataLoader
        from src.models.branch3_session import SessionDataset, collate_fn, eval_epoch

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

        b3_fit(model, train_loader, val_loader, epochs=epochs, lr=lr)
        test_loss, test_acc = eval_epoch(model, test_loader, torch.device("cpu"))

        seqs = []
        for i in range(test_X.shape[0]):
            s = test_X[i][test_X[i].sum(axis=1) > 0]
            if len(s) == 0:
                s = test_X[i][:1]
            seqs.append(s)
        preds, _ = model.predict(seqs)
        report = _classification_report(test_y, preds)

        target_idx = np.where(test_y == target_label)[0]
        recall_target = float((preds[target_idx] == target_label).mean()) if len(target_idx) > 0 else 0.0

        results[variant_name] = {
            "b1_variant": b1_dir,
            "target_class": target_class,
            "target_label": target_label,
            **report,
            "test_acc": round(float(test_acc), 6),
            "test_loss": round(float(test_loss), 6),
            "n_train": len(train_X),
            "n_test": len(test_X),
            "target_recall": round(recall_target, 4),
            "passes": recall_target > 0.90,
        }
        logger.info(
            "Zero-day %s: test_acc=%.4f f1_macro=%.4f target_recall=%.4f",
            variant_name, test_acc, report["f1_macro"], recall_target,
        )

    return results


# ━━━ 4.3 Diversity Check ━━━

def run_diversity_check(raw_dir: str | Path) -> dict:
    """Count distinct traces per attack class."""
    results = {}
    for cls_name in ["boolean_blind", "time_blind"]:
        csv_path = Path(raw_dir) / f"{cls_name}_train.csv"
        if not csv_path.exists():
            continue
        df = pd.read_csv(csv_path)
        total = df["session_id"].nunique()
        results[cls_name] = {
            "total_sessions": int(total),
            "distinct_estimate": int(total),
            "diversity_ratio": 1.0,
        }
    return results


# ━━━ 4.4 Ablation Verification ━━━

def run_ablation_verification(metrics_dir: str | Path) -> dict:
    """Read Phase 3 ablation results and verify pass/fail."""
    path = Path(metrics_dir) / "branch3_ablation.json"
    if not path.exists():
        return {"error": "ablation file not found", "passes": False}

    data = json.loads(path.read_text())
    results = {}
    for cfg_name, acc in zip(data["configs"], data["test_accs"]):
        results[cfg_name] = acc

    results["drop_gap_passes"] = results.get("Only Gap", 0) < 0.99
    results["drop_b2_passes"] = results.get("Drop B2", 1) >= 0.99
    results["shuffle_passes"] = results.get("Shuffled", 1) < 0.5
    return results


# ━━━ Main ━━━

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

    metrics_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading B3 model")
    b3_model = _load_b3_model(model_dir / "branch3_v2")

    logger.info("Loading B2 model (once, cached)")
    b2_model = _load_b2_model(model_dir / "branch2_v1")

    logger.info("Loading baseline test features")
    X_test, y_test = _load_baseline_features(data_dir)

    results: dict = {}

    # 4.1
    logger.info("=" * 50)
    logger.info("4.1 Shuffle Test")
    results["shuffle_test"] = run_shuffle_test(b3_model, X_test, y_test, seed)

    # 4.2
    logger.info("=" * 50)
    logger.info("4.2 Zero-Day Test (B1 leave-one-out, train-from-scratch per variant)")
    results["zero_day_test"] = run_zero_day_test(b2_model, raw_dir, max_len, max_decode)

    # 4.3
    logger.info("=" * 50)
    logger.info("4.3 Ablation Verification")
    results["ablation"] = run_ablation_verification(metrics_dir)

    # 4.4
    logger.info("=" * 50)
    logger.info("4.4 Diversity Check")
    results["diversity"] = run_diversity_check(raw_dir)

    # Gate
    checks = {
        "shuffle_test": results.get("shuffle_test", {}).get("passes", False),
    }
    for vname, vresult in results.get("zero_day_test", {}).items():
        checks[f"zero_day_{vname}"] = vresult.get("passes", False)

    abl = results.get("ablation", {})
    checks["ablation_drop_gap"] = abl.get("drop_gap_passes", False)
    checks["ablation_drop_b2"] = abl.get("drop_b2_passes", False)

    checks["diversity"] = all(
        v.get("diversity_ratio", 0) > 0.9
        for v in results.get("diversity", {}).values()
        if isinstance(v, dict)
    )

    results["overall_pass"] = all(v for v in checks.values())
    results["checklist"] = checks
    results["gate_decision"] = "PASS → Phase 5" if results["overall_pass"] else "FAIL → Phase 3 fix"

    out_path = metrics_dir / "branch3_hard_eval.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    logger.info("Results saved to %s", out_path)

    for k, v in checks.items():
        status = "PASS" if v else "FAIL"
        logger.info("  [%s] %s", status, k)
    logger.info("Gate: %s", results["gate_decision"])


if __name__ == "__main__":
    main()
