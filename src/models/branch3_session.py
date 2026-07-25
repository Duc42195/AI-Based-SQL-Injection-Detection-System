"""Branch 3 — session-level sequence model.

Classifies a whole session (a sequence of queries) as benign or one of the
temporal attack patterns that look invisible to a per-query classifier:
boolean-blind probing, time-blind probing, or query-splitting.

Per-step input = Branch 1's 5-class probability vector concatenated with
Branch 2's anomaly score. Branch 1 (TF-IDF + Logistic Regression) is a
linear model with no hidden layer, so its probability output *is* the
"content embedding" fed into this sequence model — there's no separate
embedding to train or persist, which keeps this branch's only new artifact
to the GRU weights themselves.

A single-layer GRU consumes the (variable-length, padded) per-step feature
sequence via ``pack_padded_sequence`` and classifies from its final hidden
state. fit/predict/save/load mirrors the style of
``src.models.branch2_anomaly.AnomalyDetector`` for consistency across the
project's model wrappers.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence

from src.utils import get_logger

logger = get_logger(__name__)


class _GRUClassifier(nn.Module):
    """1-layer GRU -> linear classifier over the final hidden state."""

    def __init__(self, input_dim: int, hidden_dim: int, num_classes: int) -> None:
        super().__init__()
        self.gru = nn.GRU(input_dim, hidden_dim, batch_first=True)
        self.fc = nn.Linear(hidden_dim, num_classes)

    def forward(self, x: torch.Tensor, lengths: torch.Tensor) -> torch.Tensor:
        """Args: x (batch, max_len, input_dim) padded; lengths (batch,) true lengths."""
        packed = pack_padded_sequence(x, lengths.cpu(), batch_first=True, enforce_sorted=False)
        _, h_n = self.gru(packed)
        # h_n: (num_layers=1, batch, hidden_dim) -> (batch, hidden_dim). PyTorch's
        # RNN restores original batch order from the packed sequence automatically.
        return self.fc(h_n[-1])


class SessionSequenceDetector:
    """Trainable/persistable wrapper around :class:`_GRUClassifier`."""

    def __init__(
        self,
        input_dim: int = 6,
        hidden_dim: int = 32,
        num_classes: int = 4,
        class_names: list[str] | None = None,
        random_seed: int = 42,
        max_len: int = 64,
    ) -> None:
        """Initialise the session sequence detector.

        Args:
            input_dim: Per-step feature dimension (Branch-1 class probabilities
                concatenated with the Branch-2 anomaly score).
            hidden_dim: GRU hidden state size.
            num_classes: Number of session-level classes (see
                ``configs/config.yaml: branch3_session.session_classes``).
            class_names: Ordered class names matching the label ids 0..num_classes-1.
            random_seed: Seed for weight init and batch shuffling.
            max_len: Sequences longer than this are truncated to the last
                ``max_len`` steps (most-recent-first is not assumed; simple
                truncation from the start).
        """
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_classes = num_classes
        self.class_names = class_names or [str(i) for i in range(num_classes)]
        self.random_seed = random_seed
        self.max_len = max_len
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        torch.manual_seed(random_seed)
        self._model = _GRUClassifier(input_dim, hidden_dim, num_classes).to(self.device)

    def _pad_batch(self, X_sequences: list[np.ndarray]) -> tuple[torch.Tensor, torch.Tensor]:
        """Pad a list of (seq_len, input_dim) arrays to (batch, max_len_in_batch, input_dim)."""
        lengths = [max(1, min(len(x), self.max_len)) for x in X_sequences]
        batch = np.zeros((len(X_sequences), max(lengths), self.input_dim), dtype=np.float32)
        for i, (x, length) in enumerate(zip(X_sequences, lengths)):
            batch[i, :length] = np.asarray(x, dtype=np.float32)[:length]
        return torch.from_numpy(batch).to(self.device), torch.tensor(lengths, dtype=torch.long)

    def fit(
        self,
        X_sequences: list[np.ndarray],
        y: np.ndarray,
        epochs: int = 30,
        lr: float = 1e-3,
        batch_size: int = 16,
    ) -> list[float]:
        """Train on a list of variable-length per-step feature sequences.

        Args:
            X_sequences: List of ``(seq_len_i, input_dim)`` arrays, one per session.
            y: Integer session labels, shape ``(n_sessions,)``.
            epochs: Number of training epochs.
            lr: Adam learning rate.
            batch_size: Mini-batch size.

        Returns:
            Per-epoch mean training loss.
        """
        self._model.train()
        optimizer = torch.optim.Adam(self._model.parameters(), lr=lr)
        criterion = nn.CrossEntropyLoss()
        y_full = torch.tensor(y, dtype=torch.long)

        n = len(X_sequences)
        rng = np.random.RandomState(self.random_seed)
        loss_history: list[float] = []
        logger.info(
            "Training GRU (input_dim=%d hidden_dim=%d num_classes=%d) on %d sessions, %d epochs",
            self.input_dim, self.hidden_dim, self.num_classes, n, epochs,
        )
        for epoch in range(epochs):
            perm = rng.permutation(n)
            epoch_losses = []
            for start in range(0, n, batch_size):
                idx = perm[start : start + batch_size]
                batch_X = [X_sequences[i] for i in idx]
                batch_y = y_full[idx].to(self.device)

                X_padded, lengths = self._pad_batch(batch_X)
                optimizer.zero_grad()
                logits = self._model(X_padded, lengths)
                loss = criterion(logits, batch_y)
                loss.backward()
                optimizer.step()
                epoch_losses.append(loss.item())

            mean_loss = float(np.mean(epoch_losses))
            loss_history.append(mean_loss)
            if (epoch + 1) % 5 == 0 or epoch == 0 or epoch == epochs - 1:
                logger.info("  epoch %d/%d  loss=%.4f", epoch + 1, epochs, mean_loss)

        return loss_history

    def predict_proba(self, X_sequences: list[np.ndarray]) -> np.ndarray:
        """Return softmax class probabilities, shape ``(n, num_classes)``."""
        self._model.eval()
        with torch.no_grad():
            X_padded, lengths = self._pad_batch(X_sequences)
            logits = self._model(X_padded, lengths)
            probs = torch.softmax(logits, dim=1)
        return probs.cpu().numpy()

    def predict(self, X_sequences: list[np.ndarray]) -> np.ndarray:
        """Return predicted class ids, shape ``(n,)``."""
        return np.argmax(self.predict_proba(X_sequences), axis=1)

    def save(self, path: str | Path) -> None:
        """Serialize the model weights and metadata to disk.

        Args:
            path: Directory path. Creates the directory if needed. Writes
                ``model.pt`` (state dict) and ``metadata.json``.
        """
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        torch.save(self._model.state_dict(), path / "model.pt")
        meta = {
            "input_dim": self.input_dim,
            "hidden_dim": self.hidden_dim,
            "num_classes": self.num_classes,
            "class_names": self.class_names,
            "random_seed": self.random_seed,
            "max_len": self.max_len,
        }
        with (path / "metadata.json").open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        logger.info("Model saved to %s", path)

    @classmethod
    def load(cls, path: str | Path) -> "SessionSequenceDetector":
        """Deserialize a saved model.

        Args:
            path: Directory containing ``model.pt`` and ``metadata.json``.

        Returns:
            A loaded :class:`SessionSequenceDetector` instance.
        """
        path = Path(path)
        with (path / "metadata.json").open("r", encoding="utf-8") as f:
            meta = json.load(f)
        detector = cls(
            input_dim=meta["input_dim"],
            hidden_dim=meta["hidden_dim"],
            num_classes=meta["num_classes"],
            class_names=meta.get("class_names"),
            random_seed=meta.get("random_seed", 42),
            max_len=meta.get("max_len", 64),
        )
        state_dict = torch.load(path / "model.pt", map_location=detector.device)
        detector._model.load_state_dict(state_dict)
        detector._model.eval()
        logger.info("Model loaded from %s", path)
        return detector
