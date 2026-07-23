"""Train GRU sequence model for Branch 3 session-level SQLi detection.

Usage:
    uv run python scripts/train_nhanh3_gru.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn, optim
from torch.utils.data import DataLoader
from sklearn.metrics import classification_report, confusion_matrix, f1_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

from src.models.nhanh3_gru import (
    GRUSessionClassifier,
    SessionSequenceDataset,
    _pad_collate,
    FEATURE_NAMES,
)
from src.utils import get_logger, load_config

logger = get_logger(__name__)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _prepare_data(
    df: pd.DataFrame, scaler: StandardScaler | None = None, fit_scaler: bool = False,
) -> tuple[SessionSequenceDataset, StandardScaler]:
    if fit_scaler:
        all_feats = df[FEATURE_NAMES].values.astype(np.float32)
        scaler = StandardScaler()
        scaler.fit(all_feats)
    sessions = []
    for _, group in df.groupby("session_id"):
        group = group.sort_values("step")
        feats = group[FEATURE_NAMES].values.astype(np.float32)
        feats_scaled = scaler.transform(feats)
        group[FEATURE_NAMES] = feats_scaled
        sessions.append(group)
    scaled_df = pd.concat(sessions)
    dataset = SessionSequenceDataset(scaled_df, max_len=64, label_binary=True)
    return dataset, scaler


def main():
    cfg = load_config()
    pd_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    models_dir = Path(cfg.get_path("paths.models_dir", "models"))
    report_dir = Path(cfg.get_path("paths.reports_dir", "reports"))

    version = "nhanh3_gru_v1"
    out_dir = models_dir / version
    out_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    seed = cfg.get_path("project.random_seed", 42)
    torch.manual_seed(seed)
    np.random.seed(seed)

    gru_cfg = cfg.get_path("branch3_session.gru", {})
    train_cfg = cfg.get_path("branch3_session.training", {})
    batch_size = train_cfg.get("batch_size", 32)
    epochs = train_cfg.get("epochs", 30)
    lr = train_cfg.get("learning_rate", 1e-3)
    weight_decay = train_cfg.get("weight_decay", 1e-5)
    patience = train_cfg.get("early_stop_patience", 5)
    max_len = cfg.get_path("branch3_session.max_session_len", 64)
    test_frac = cfg.get_path("branch3_session.simulation.test_fraction", 0.2)

    data_path = pd_dir / "nhanh3_session_data.csv"
    if not data_path.exists():
        logger.error("Data not found at %s", data_path)
        return

    df = pd.read_csv(data_path)
    df["label_binary"] = (df["session_label"] > 0).astype(int)
    logger.info("Loaded %d step-rows from %s", len(df), data_path)

    train_ids = set(df[df["split"] == "train"]["session_id"].unique())
    test_ids = set(df[df["split"] == "test"]["session_id"].unique())
    df_train = df[df["session_id"].isin(train_ids)]
    df_test = df[df["session_id"].isin(test_ids)]
    logger.info("Train sessions: %d  Test sessions: %d", len(train_ids), len(test_ids))

    train_ds, scaler = _prepare_data(df_train, fit_scaler=True)
    test_ds, _ = _prepare_data(df_test, scaler=scaler, fit_scaler=False)

    train_loader = DataLoader(
        train_ds, batch_size=batch_size, shuffle=True,
        collate_fn=_pad_collate, num_workers=0,
    )
    test_loader = DataLoader(
        test_ds, batch_size=batch_size, shuffle=False,
        collate_fn=_pad_collate, num_workers=0,
    )

    model = GRUSessionClassifier(
        input_dim=len(FEATURE_NAMES),
        hidden_dim=gru_cfg.get("hidden_dim", 64),
        num_layers=gru_cfg.get("num_layers", 2),
        dropout=gru_cfg.get("dropout", 0.3),
        bidirectional=gru_cfg.get("bidirectional", False),
    ).to(DEVICE)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

    logger.info("Training GRU on %s", DEVICE)
    logger.info("Model: %s", model)
    n_params = sum(p.numel() for p in model.parameters())
    logger.info("Parameters: %d", n_params)

    best_f1 = 0.0
    best_state = None
    no_improve = 0

    for epoch in range(1, epochs + 1):
        model.train()
        train_loss = 0.0
        for x_batch, lengths, y_batch in train_loader:
            x_batch = x_batch.to(DEVICE)
            lengths = lengths.to(DEVICE)
            y_batch = y_batch.to(DEVICE)

            optimizer.zero_grad()
            logits = model(x_batch, lengths)
            loss = criterion(logits, y_batch)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_loss += loss.item()

        model.eval()
        all_preds, all_labels = [], []
        with torch.no_grad():
            for x_batch, lengths, y_batch in test_loader:
                x_batch = x_batch.to(DEVICE)
                lengths = lengths.to(DEVICE)
                logits = model(x_batch, lengths)
                preds = torch.argmax(logits, dim=1)
                all_preds.extend(preds.cpu().numpy())
                all_labels.extend(y_batch.numpy())

        wf1 = f1_score(all_labels, all_preds, average="weighted")
        logger.info(
            "Epoch %2d/%d  train_loss=%.4f  val_weighted_f1=%.4f",
            epoch, epochs, train_loss / len(train_loader), wf1,
        )

        if wf1 > best_f1:
            best_f1 = wf1
            best_state = model.state_dict()
            no_improve = 0
        else:
            no_improve += 1
            if no_improve >= patience:
                logger.info("Early stopping at epoch %d", epoch)
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    model.eval()
    all_preds, all_probas, all_labels = [], [], []
    with torch.no_grad():
        for x_batch, lengths, y_batch in test_loader:
            x_batch = x_batch.to(DEVICE)
            lengths = lengths.to(DEVICE)
            logits = model(x_batch, lengths)
            probs = torch.softmax(logits, dim=1)
            preds = torch.argmax(logits, dim=1)
            all_preds.extend(preds.cpu().numpy())
            all_probas.extend(probs.cpu().numpy())
            all_labels.extend(y_batch.numpy())

    y_true = np.array(all_labels)
    y_pred = np.array(all_preds)
    y_proba = np.array(all_probas)[:, 1]

    report = classification_report(y_true, y_pred, target_names=["benign", "attack"], output_dict=True, digits=4)
    cm = confusion_matrix(y_true, y_pred)
    wf1 = f1_score(y_true, y_pred, average="weighted")
    auc = roc_auc_score(y_true, y_proba)

    logger.info("\n" + classification_report(y_true, y_pred, target_names=["benign", "attack"], digits=4))
    logger.info("Confusion matrix:\n%s", cm)
    logger.info("ROC AUC: %.4f", auc)

    torch.save(model.state_dict(), out_dir / "session_gru.pt")
    import joblib
    joblib.dump(scaler, out_dir / "session_scaler.joblib")
    logger.info("Saved model to %s", out_dir / "session_gru.pt")

    eval_report = {
        "version": version,
        "branch": "nhanh3_session",
        "model": "GRU",
        "model_params": n_params,
        "config": {
            "hidden_dim": gru_cfg.get("hidden_dim", 64),
            "num_layers": gru_cfg.get("num_layers", 2),
            "dropout": gru_cfg.get("dropout", 0.3),
            "bidirectional": gru_cfg.get("bidirectional", False),
            "epochs_trained": epoch,
            "batch_size": batch_size,
            "learning_rate": lr,
        },
        "device": str(DEVICE),
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_train": len(train_ds),
        "n_test": len(test_ds),
        "test_metrics": {
            "weighted_f1": round(wf1, 4),
            "roc_auc": round(auc, 4),
            "classification_report": report,
            "confusion_matrix": cm.tolist(),
        },
    }

    report_path = report_dir / "nhanh3_eval_gru.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(eval_report, f, indent=2)
    logger.info("Saved eval report to %s", report_path)
    logger.info("=== Done ===")


if __name__ == "__main__":
    main()
