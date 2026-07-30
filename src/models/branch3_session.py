from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Sequence

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from torch.utils.data.dataset import random_split

from src.utils import get_logger

logger = get_logger(__name__)


class SessionDataset(Dataset):
    def __init__(self, features: np.ndarray, labels: np.ndarray | None = None):
        self.features = torch.from_numpy(features).float()
        self.labels = torch.from_numpy(labels).long() if labels is not None else None
        self.lengths = self._compute_lengths()

    def _compute_lengths(self) -> torch.Tensor:
        mask = self.features[:, :, :5].sum(dim=2) > 1e-6
        lengths = mask.sum(dim=1).clamp(min=1)
        return lengths

    def __len__(self) -> int:
        return self.features.size(0)

    def __getitem__(self, idx: int):
        x = self.features[idx]
        l = self.lengths[idx]
        if self.labels is not None:
            return x, l, self.labels[idx]
        return x, l


class SessionSequenceDetector(nn.Module):
    def __init__(
        self,
        input_dim: int = 7,
        hidden_dim: int = 32,
        num_classes: int = 4,
        dropout: float = 0.2,
        max_len: int = 64,
        class_names: list[str] | None = None,
        random_seed: int = 42,
    ):
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_classes = num_classes
        self.dropout_p = dropout
        self.max_len = max_len
        self.class_names = class_names or [
            "benign", "boolean_blind", "time_blind", "query_splitting"
        ]
        self.random_seed = random_seed

        self.gru = nn.GRU(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=1,
            batch_first=True,
            bidirectional=False,
        )
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_dim, num_classes)

    def forward(self, x: torch.Tensor, lengths: torch.Tensor) -> torch.Tensor:
        packed = nn.utils.rnn.pack_padded_sequence(
            x, lengths.cpu(), batch_first=True, enforce_sorted=False
        )
        _, hidden = self.gru(packed)
        out = hidden[-1]
        out = self.dropout(out)
        out = self.fc(out)
        return out

    def predict(
        self, sequences: list[np.ndarray], device: str | None = None
    ) -> tuple[np.ndarray, np.ndarray]:
        self.eval()
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        device = torch.device(device)
        self.to(device)

        batch: list[np.ndarray] = []
        lengths: list[int] = []
        for seq in sequences:
            batch.append(seq)
            lengths.append(len(seq))

        max_l = max(lengths)
        padded = np.zeros((len(sequences), max_l, self.input_dim), dtype=np.float32)
        for i, seq in enumerate(sequences):
            padded[i, : len(seq)] = seq

        x = torch.from_numpy(padded).float().to(device)
        lens = torch.tensor(lengths, dtype=torch.long).to(device)

        with torch.no_grad():
            logits = self.forward(x, lens)
            probs = F.softmax(logits, dim=1)
            preds = logits.argmax(dim=1)

        return preds.cpu().numpy(), probs.cpu().numpy()

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        torch.save(self.state_dict(), path / "model.pt")
        meta = {
            "input_dim": self.input_dim,
            "hidden_dim": self.hidden_dim,
            "num_classes": self.num_classes,
            "class_names": self.class_names,
            "random_seed": self.random_seed,
            "max_len": self.max_len,
            "dropout": self.dropout_p,
        }
        with (path / "metadata.json").open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        logger.info("Model saved to %s", path)

    @classmethod
    def load(cls, path: str | Path) -> SessionSequenceDetector:
        path = Path(path)
        with (path / "metadata.json").open("r", encoding="utf-8") as f:
            meta = json.load(f)
        model = cls(
            input_dim=meta["input_dim"],
            hidden_dim=meta["hidden_dim"],
            num_classes=meta["num_classes"],
            dropout=meta.get("dropout", 0.2),
            max_len=meta.get("max_len", 64),
            class_names=meta.get("class_names"),
            random_seed=meta.get("random_seed", 42),
        )
        state = torch.load(path / "model.pt", map_location="cpu", weights_only=True)
        model.load_state_dict(state)
        model.eval()
        logger.info("Model loaded from %s", path)
        return model


def collate_fn(batch):
    xs, ls, ys = zip(*batch)
    max_l = max(ls).item()
    x_pad = torch.zeros(len(batch), max_l, xs[0].size(1))
    for i, (x, l) in enumerate(zip(xs, ls)):
        x_pad[i, :l] = x[:l]
    return x_pad, torch.stack(ls), torch.tensor(ys)


def _accuracy(logits: torch.Tensor, y: torch.Tensor) -> float:
    return (logits.argmax(dim=1) == y).float().mean().item()


def train_epoch(
    model: SessionSequenceDetector,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> tuple[float, float]:
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0
    for x, lens, y in loader:
        x, lens, y = x.to(device), lens.to(device), y.to(device)
        optimizer.zero_grad()
        logits = model(x, lens)
        loss = F.cross_entropy(logits, y)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * x.size(0)
        correct += (logits.argmax(dim=1) == y).sum().item()
        total += x.size(0)
    return total_loss / total, correct / total


@torch.no_grad()
def eval_epoch(
    model: SessionSequenceDetector,
    loader: DataLoader,
    device: torch.device,
) -> tuple[float, float]:
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0
    for x, lens, y in loader:
        x, lens, y = x.to(device), lens.to(device), y.to(device)
        logits = model(x, lens)
        loss = F.cross_entropy(logits, y)
        total_loss += loss.item() * x.size(0)
        correct += (logits.argmax(dim=1) == y).sum().item()
        total += x.size(0)
    return total_loss / total, correct / total


def fit(
    model: SessionSequenceDetector,
    train_loader: DataLoader,
    val_loader: DataLoader,
    epochs: int = 30,
    lr: float = 0.001,
    weight_decay: float = 1e-5,
    device: str | None = None,
    log_interval: int = 5,
) -> dict[str, list[float]]:
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    device = torch.device(device)
    model.to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    history = {"train_loss": [], "train_acc": [], "val_loss": [], "val_acc": []}

    for epoch in range(1, epochs + 1):
        train_loss, train_acc = train_epoch(model, train_loader, optimizer, device)
        val_loss, val_acc = eval_epoch(model, val_loader, device)

        history["train_loss"].append(train_loss)
        history["train_acc"].append(train_acc)
        history["val_loss"].append(val_loss)
        history["val_acc"].append(val_acc)

        if epoch == 1 or epoch % log_interval == 0 or epoch == epochs:
            logger.info(
                "Epoch %3d/%d  train_loss=%.4f  train_acc=%.4f  val_loss=%.4f  val_acc=%.4f",
                epoch, epochs, train_loss, train_acc, val_loss, val_acc,
            )

    return history
