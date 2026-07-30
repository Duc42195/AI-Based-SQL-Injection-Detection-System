from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from src.models.branch3_session import (
    SessionDataset,
    SessionSequenceDetector,
    collate_fn,
    fit,
)
from src.utils import get_logger, load_config

logger = get_logger(__name__)


def _load_npy(data_dir: str | Path) -> tuple[np.ndarray, np.ndarray]:
    data_dir = Path(data_dir)
    X = np.load(data_dir / "train_features.npy")
    y = np.load(data_dir / "train_labels.npy")
    return X, y


def _load_test(data_dir: str | Path) -> tuple[np.ndarray, np.ndarray]:
    data_dir = Path(data_dir)
    X = np.load(data_dir / "test_features.npy")
    y = np.load(data_dir / "test_labels.npy")
    return X, y


def main():
    cfg = load_config()
    proc_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    data_dir = proc_dir / "branch3_session_features"
    model_dir = Path(cfg.get_path("paths.models_dir", "models"))
    out_dir = model_dir / "branch3_v2"

    seed = int(cfg.get_path("project.random_seed", 42))
    torch.manual_seed(seed)
    np.random.seed(seed)

    X_train, y_train = _load_npy(data_dir)
    X_test, y_test = _load_test(data_dir)

    input_dim = X_train.shape[2]
    hidden_dim = int(cfg.get_path("branch3_session.train.hidden_dim", 32))
    epochs = int(cfg.get_path("branch3_session.train.epochs", 30))
    lr = float(cfg.get_path("branch3_session.train.learning_rate", 0.001))
    batch_size = int(cfg.get_path("branch3_session.train.batch_size", 16))
    max_len = int(cfg.get_path("branch3_session.max_session_len", 64))

    class_names = ["benign", "boolean_blind", "time_blind", "query_splitting"]

    dataset = SessionDataset(X_train, y_train)
    n_val = int(0.15 * len(dataset))
    n_train = len(dataset) - n_val
    train_ds, val_ds = torch.utils.data.dataset.random_split(
        dataset, [n_train, n_val],
        generator=torch.Generator().manual_seed(seed),
    )
    train_loader = DataLoader(
        train_ds, batch_size=batch_size, shuffle=True, collate_fn=collate_fn
    )
    val_loader = DataLoader(
        val_ds, batch_size=batch_size, shuffle=False, collate_fn=collate_fn
    )

    test_ds = SessionDataset(X_test, y_test)
    test_loader = DataLoader(
        test_ds, batch_size=batch_size, shuffle=False, collate_fn=collate_fn
    )

    model = SessionSequenceDetector(
        input_dim=input_dim,
        hidden_dim=hidden_dim,
        num_classes=len(class_names),
        max_len=max_len,
        class_names=class_names,
        random_seed=seed,
    )

    logger.info(
        "Model: %s params, input_dim=%d, hidden_dim=%d, classes=%d",
        sum(p.numel() for p in model.parameters()),
        input_dim, hidden_dim, len(class_names),
    )
    logger.info(
        "Data: train=%d, val=%d, test=%d",
        len(train_ds), len(val_ds), len(test_ds),
    )

    history = fit(
        model, train_loader, val_loader,
        epochs=epochs, lr=lr, device="cpu",
    )

    from src.models.branch3_session import eval_epoch
    device = torch.device("cpu")
    test_loss, test_acc = eval_epoch(model, test_loader, device)
    logger.info("Test  loss=%.4f  acc=%.4f", test_loss, test_acc)

    model.save(out_dir)

    metrics = {
        "input_dim": input_dim,
        "hidden_dim": hidden_dim,
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": lr,
        "random_seed": seed,
        "train_size": len(train_ds),
        "val_size": len(val_ds),
        "test_size": len(test_ds),
        "n_params": sum(p.numel() for p in model.parameters()),
        "history": {k: [round(v, 6) for v in vals] for k, vals in history.items()},
        "test_loss": round(float(test_loss), 6),
        "test_acc": round(float(test_acc), 6),
    }

    metrics_path = Path(cfg.get_path("paths.reports_dir", "report/metrics"))
    metrics_path.mkdir(parents=True, exist_ok=True)
    with (metrics_path / "branch3_train.json").open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    logger.info("Training metrics saved to %s", metrics_path / "branch3_train.json")
    logger.info("Done. Test accuracy: %.4f", test_acc)


if __name__ == "__main__":
    main()
