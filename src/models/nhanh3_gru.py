"""GRU-based sequence model for Branch 3 session-level SQLi detection.

Processes per-query feature sequences through GRU layers, capturing
query-order patterns that aggregate models (e.g. Random Forest on
summary statistics) inherently discard.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from torch import nn, Tensor
from torch.utils.data import Dataset, DataLoader
from sklearn.preprocessing import StandardScaler

from src.utils import get_logger, load_config

logger = get_logger(__name__)

FEATURE_NAMES = ["length", "special_char_ratio", "sql_keyword_count", "entropy", "is_attack_query"]
SEQ_FEATURES = [f for f in FEATURE_NAMES if f != "is_attack_query"]


def _pad_collate(batch: list[tuple[Tensor, int]]) -> tuple[Tensor, Tensor, Tensor]:
    xs, ys = zip(*batch)
    lengths = torch.tensor([len(x) for x in xs], dtype=torch.long)
    padded = torch.nn.utils.rnn.pad_sequence(xs, batch_first=True)
    return padded, lengths, torch.tensor(ys, dtype=torch.long)


class SessionSequenceDataset(Dataset):
    """Map session-level step data to fixed-dimension sequences."""

    def __init__(self, df: pd.DataFrame, max_len: int = 64, label_binary: bool = True):
        self.max_len = max_len
        seqs = []
        labs = []
        for _, group in df.groupby("session_id"):
            group = group.sort_values("step")
            feats = group[FEATURE_NAMES].values.astype(np.float32)
            seqs.append(torch.from_numpy(feats))
            label = group["session_label"].iloc[0]
            if label_binary:
                label = 1 if label > 0 else 0
            labs.append(label)
        self.seqs = seqs
        self.labs = labs

    def __len__(self) -> int:
        return len(self.seqs)

    def __getitem__(self, idx: int) -> tuple[Tensor, int]:
        seq = self.seqs[idx]
        if len(seq) > self.max_len:
            seq = seq[-self.max_len:]
        return seq, self.labs[idx]


class GRUSessionClassifier(nn.Module):
    """GRU-based sequence classifier for session-level SQLi detection.

    Args:
        input_dim: Number of per-step features.
        hidden_dim: GRU hidden state size.
        num_layers: Number of stacked GRU layers.
        num_classes: Output classes (2 for binary).
        dropout: Dropout applied between GRU layers and after GRU.
        bidirectional: Whether to use bidirectional GRU.
    """

    def __init__(
        self,
        input_dim: int = len(FEATURE_NAMES),
        hidden_dim: int = 64,
        num_layers: int = 2,
        num_classes: int = 2,
        dropout: float = 0.3,
        bidirectional: bool = False,
    ):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.bidirectional = bidirectional
        self.num_directions = 2 if bidirectional else 1

        self.gru = nn.GRU(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
            bidirectional=bidirectional,
        )

        fc_in = hidden_dim * self.num_directions
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(fc_in, num_classes)

    def forward(self, x: Tensor, lengths: Tensor | None = None) -> Tensor:
        if lengths is not None:
            lengths_cpu = lengths.cpu().clamp(min=1)
            x = nn.utils.rnn.pack_padded_sequence(x, lengths_cpu, batch_first=True, enforce_sorted=False)

        gru_out, h_n = self.gru(x)

        if lengths is not None:
            gru_out, _ = nn.utils.rnn.pad_packed_sequence(gru_out, batch_first=True)

        if self.bidirectional:
            last = torch.cat((h_n[-2], h_n[-1]), dim=1)
        else:
            last = h_n[-1]

        out = self.dropout(last)
        return self.fc(out)


class GRUSessionInference:
    """Inference wrapper for the GRU session model.

    Mirrors the :class:`SessionClassifier` interface so the rest of the
    system can use it without changes.
    """

    def __init__(self, version: str | None = None):
        cfg = load_config()
        v = version or cfg.get_path("branch3_session.active_version", "nhanh3_v1")
        models_dir = Path(cfg.get_path("paths.models_dir", "models"))
        model_path = models_dir / v / "session_gru.pt"
        scaler_path = models_dir / v / "session_scaler.joblib"

        if not model_path.exists():
            logger.warning("GRU model not found at %s", model_path)
            self._model = None
            return

        self._model = GRUSessionClassifier(
            input_dim=cfg.get_path("branch3_session.gru.input_dim", len(FEATURE_NAMES)),
            hidden_dim=cfg.get_path("branch3_session.gru.hidden_dim", 64),
            num_layers=cfg.get_path("branch3_session.gru.num_layers", 2),
            dropout=cfg.get_path("branch3_session.gru.dropout", 0.3),
            bidirectional=cfg.get_path("branch3_session.gru.bidirectional", False),
        )
        self._model.load_state_dict(
            torch.load(model_path, map_location="cpu", weights_only=True)
        )
        self._model.eval()
        self._scaler: StandardScaler = joblib.load(scaler_path)
        self._max_len = cfg.get_path("branch3_session.max_session_len", 64)
        self._steps: list[list[float]] = []
        logger.info("Loaded GRU session model: %s", model_path)

    def predict(self, query: str, is_attack: float = 0.0, reset: bool = False) -> dict:
        from src.preprocessing.statistical_features import extract_statistical_features

        if self._model is None:
            return {"session_label": -1, "confidence": 0.0, "is_ready": False}

        if reset:
            self._steps = []

        f = extract_statistical_features(query)
        self._steps.append([f.length, f.special_char_ratio, f.sql_keyword_count, f.entropy, is_attack])
        if len(self._steps) > self._max_len:
            self._steps = self._steps[-self._max_len:]

        arr = self._scaler.transform(np.array(self._steps, dtype=np.float32).reshape(1, -1, 5))
        with torch.no_grad():
            x = torch.from_numpy(arr)
            logits = self._model(x)
            probs = torch.softmax(logits, dim=1)
            label = int(torch.argmax(probs, dim=1)[0])
            confidence = float(torch.max(probs, dim=1)[0])

        return {"session_label": label, "confidence": round(confidence, 4), "is_ready": True}
