"""Domain adaptation: fine-tune GRU on URL-encoded queries + Cach B.

Strategy:
1. Augment Cach A session data by URL-encoding the query_raw column
   (mimics the distribution shift seen in real sqlmap traffic)
2. Load the pre-trained GRU (Cach A only)
3. Fine-tune on augmented Cach A + Cach B session data
4. Save adapted model + evaluate
"""

from __future__ import annotations

import json
import time
import warnings
from pathlib import Path
from typing import Any
from urllib.parse import quote

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import (
    accuracy_score, auc, classification_report, confusion_matrix,
    f1_score, precision_recall_fscore_support, roc_auc_score, roc_curve,
)
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, Dataset

from src.utils import get_logger, load_config

warnings.filterwarnings("ignore")
logger = get_logger(__name__)

DEVICE = torch.device("cpu")


def url_encode_query(text: str, rng: np.random.Generator, p: float = 0.5) -> str:
    """Randomly URL-encode parts of a query string to mimic real sqlmap traffic."""
    chars = list(text)
    out: list[str] = []
    for ch in chars:
        if rng.random() < p and not ch.isalnum():
            out.append(quote(ch))
        else:
            out.append(ch)
    return "".join(out)


def augment_cacha(df: pd.DataFrame, frac: float = 1.0, seed: int = 42) -> pd.DataFrame:
    """Create augmented copy of Cach A with URL-encoded query_raw."""
    rng = np.random.default_rng(seed)
    mask = rng.random(len(df)) < frac
    aug = df[mask].copy()
    aug["query_raw"] = aug["query_raw"].apply(lambda q: url_encode_query(str(q), rng))
    aug["query_canonical"] = aug["query_raw"]
    for col in ["length", "special_char_ratio", "sql_keyword_count", "entropy"]:
        aug[col] = np.nan
    logger.info("Augmented %d rows with URL-encoded queries", len(aug))
    return aug


def recompute_features(df: pd.DataFrame) -> pd.DataFrame:
    from src.preprocessing.statistical_features import extract_statistical_features
    for idx in df.index:
        q = str(df.at[idx, "query_raw"])
        feats = extract_statistical_features(q)
        df.at[idx, "length"] = feats.length
        df.at[idx, "special_char_ratio"] = round(feats.special_char_ratio, 6)
        df.at[idx, "sql_keyword_count"] = feats.sql_keyword_count
        df.at[idx, "entropy"] = round(feats.entropy, 6)
    return df


def load_session_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in ["length", "special_char_ratio", "sql_keyword_count", "entropy"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["length", "special_char_ratio", "sql_keyword_count", "entropy"])
    return df


def build_sequences(df: pd.DataFrame, feature_cols: list[str], max_len: int):
    sequences, labels, lengths = [], [], []
    for sid, grp in df.groupby("session_id"):
        grp = grp.sort_values("step")
        seq = grp[feature_cols].values.astype(np.float32)
        label = int(grp["session_label"].iloc[0])
        if len(seq) > max_len:
            seq = seq[:max_len]
        seq_len = len(seq)
        padded = np.zeros((max_len, len(feature_cols)), dtype=np.float32)
        padded[:seq_len] = seq
        sequences.append(padded)
        labels.append(label)
        lengths.append(seq_len)
    return (
        torch.tensor(np.array(sequences)),
        torch.tensor(labels, dtype=torch.long),
        torch.tensor(lengths, dtype=torch.long),
    )


def evaluate_model(model, loader) -> dict[str, Any]:
    model.eval()
    all_preds, all_labels, all_probs = [], [], []
    with torch.no_grad():
        for batch_x, batch_y, batch_mask in loader:
            out = model(batch_x, batch_mask)
            probs = torch.softmax(out, dim=1)
            preds = out.argmax(dim=1)
            all_probs.append(probs[:, 1].cpu().numpy())
            all_preds.append(preds.cpu().numpy())
            all_labels.append(batch_y.cpu().numpy())
    y_true = np.concatenate(all_labels)
    y_pred = np.concatenate(all_preds)
    y_prob = np.concatenate(all_probs)
    cm = confusion_matrix(y_true, y_pred)
    f1 = f1_score(y_true, y_pred, average="binary", zero_division=0)
    try:
        auc_val = roc_auc_score(y_true, y_prob)
    except Exception:
        auc_val = 0.0
    fpr, tpr, _ = roc_curve(y_true, y_prob)
    return {
        "f1": round(f1, 4),
        "auc": round(auc_val, 4),
        "confusion_matrix": cm.tolist(),
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "roc_fpr": fpr.tolist(),
        "roc_tpr": tpr.tolist(),
    }


def main() -> None:
    cfg = load_config()
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    models_base = Path(cfg.get_path("paths.models_dir", "models"))
    reports_dir = Path(cfg.get_path("paths.reports_dir", "reports"))
    reports_dir.mkdir(parents=True, exist_ok=True)

    seed = cfg.get_path("project.random_seed", 42)
    torch.manual_seed(seed)
    np.random.seed(seed)

    feature_cols = ["length", "special_char_ratio", "sql_keyword_count", "entropy", "is_attack_query"]
    max_len = cfg.get_path("branch3_session.max_session_len", 64)
    batch_size = cfg.get_path("branch3_session.training.batch_size", 32)
    lr = cfg.get_path("branch3_session.training.learning_rate", 1e-3)
    epochs = cfg.get_path("branch3_session.training.epochs", 30)
    early_stop = cfg.get_path("branch3_session.training.early_stop_patience", 5)

    cachb_path = processed_dir / "nhanh3_session_data_cachb.csv"
    cacha_path = processed_dir / "nhanh3_session_data.csv"

    df_b = load_session_data(cachb_path)
    df_a = load_session_data(cacha_path)

    df_a["session_label"] = (df_a["session_label"] > 0).astype(int)
    df_b["session_label"] = (df_b["session_label"] > 0).astype(int)

    logger.info("Cach A: %d rows, Cach B: %d rows", len(df_a), len(df_b))

    aug = augment_cacha(df_a[df_a["split"] == "train"], frac=0.5, seed=seed)
    aug = recompute_features(aug)
    df_a_train = pd.concat([df_a[df_a["split"] == "train"], aug], ignore_index=True)
    df_a_test = df_a[df_a["split"] == "test"]

    X_a_train, y_a_train, m_a_train = build_sequences(df_a_train, feature_cols, max_len)
    X_a_test, y_a_test, m_a_test = build_sequences(df_a_test, feature_cols, max_len)
    X_b, y_b, m_b = build_sequences(df_b, feature_cols, max_len)

    scaler = StandardScaler()
    n_features = len(feature_cols)
    orig_shape = X_a_train.shape
    flat = X_a_train.reshape(-1, n_features)
    scaler.fit(flat)
    for X in [X_a_train, X_a_test, X_b]:
        flat_x = X.reshape(-1, n_features)
        flat_x[:] = torch.tensor(scaler.transform(flat_x.numpy()), dtype=torch.float32)

    train_ds = torch.utils.data.TensorDataset(X_a_train, y_a_train, m_a_train)
    test_ds = torch.utils.data.TensorDataset(X_a_test, y_a_test, m_a_test)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    test_loader = DataLoader(test_ds, batch_size=batch_size)

    from src.models.nhanh3_gru import GRUSessionClassifier
    model_dir = models_base / "nhanh3_gru_v1"
    model_path = model_dir / "session_gru.pt"

    input_dim = len(feature_cols)
    hidden_dim = cfg.get_path("branch3_session.gru.hidden_dim", 64)
    num_layers = cfg.get_path("branch3_session.gru.num_layers", 2)
    dropout = cfg.get_path("branch3_session.gru.dropout", 0.3)
    bidirectional = cfg.get_path("branch3_session.gru.bidirectional", False)

    model = GRUSessionClassifier(
        input_dim=input_dim,
        hidden_dim=hidden_dim,
        num_layers=num_layers,
        dropout=dropout,
        bidirectional=bidirectional,
    )

    if model_path.exists():
        model.load_state_dict(torch.load(model_path, map_location=DEVICE, weights_only=True))
        logger.info("Loaded pre-trained GRU from %s", model_path)
    else:
        logger.warning("No pre-trained model found; training from scratch")

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-5)
    criterion = nn.CrossEntropyLoss()
    best_f1, best_epoch, best_state = 0.0, 0, None
    train_t0 = time.time()

    for epoch in range(epochs):
        model.train()
        total_loss = 0.0
        for bx, by, bm in train_loader:
            optimizer.zero_grad()
            out = model(bx, bm)
            loss = criterion(out, by)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        avg_loss = total_loss / len(train_loader)
        metrics = evaluate_model(model, test_loader)
        logger.info("Epoch %2d | loss=%.4f | F1=%.4f AUC=%.4f", epoch + 1, avg_loss, metrics["f1"], metrics["auc"])
        if metrics["f1"] > best_f1:
            best_f1 = metrics["f1"]
            best_epoch = epoch
            best_state = model.state_dict()
        elif epoch - best_epoch >= early_stop:
            logger.info("Early stop at epoch %d", epoch + 1)
            break

    if best_state is not None:
        model.load_state_dict(best_state)
    logger.info("Best Cach A test F1=%.4f at epoch %d", best_f1, best_epoch + 1)

    eval_a = evaluate_model(model, test_loader)
    logger.info("Final Cach A: F1=%.4f AUC=%.4f", eval_a["f1"], eval_a["auc"])

    b_loader = DataLoader(torch.utils.data.TensorDataset(X_b, y_b, m_b), batch_size=batch_size)
    eval_b = evaluate_model(model, b_loader)
    logger.info("Cross-eval Cach B: F1=%.4f AUC=%.4f", eval_b["f1"], eval_b["auc"])

    adapted_dir = models_base / "nhanh3_gru_v2_adapted"
    adapted_dir.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), adapted_dir / "session_gru.pt")
    joblib.dump(scaler, adapted_dir / "session_scaler.joblib")
    logger.info("Saved adapted model to %s", adapted_dir)

    report = {
        "cach_a": eval_a,
        "cach_b_cross_eval": eval_b,
        "augmented_rows": len(aug),
        "best_epoch": best_epoch + 1,
    }
    report_path = reports_dir / "nhanh3_gru_adapted_eval.json"
    with report_path.open("w") as f:
        json.dump(report, f, indent=2)
    logger.info("Report saved to %s", report_path)
    logger.info("=== Done (%.1fs) ===", time.time() - train_t0)


if __name__ == "__main__":
    main()
