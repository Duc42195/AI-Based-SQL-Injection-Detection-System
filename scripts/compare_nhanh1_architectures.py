"""Day 1 experiment: compare candidate architectures for Branch 1 (Nhanh 1).

Candidates (see AGENTS.md / De_xuat doc - do NOT default to a transformer):
  (a) TF-IDF (char n-gram) + Logistic Regression
  (b) TF-IDF (char n-gram) + LightGBM
  (c) DistilBERT fine-tune
  (d) Small CNN + SQL-keyword-aware tokenizer (~69K params reference)

For each candidate: F1-macro, per-class F1, confusion matrix, single-query
inference latency (p50/p95), and model size on disk. Final architecture
choice is made on F1-macro vs latency vs size - not accuracy alone, since the
original per-source class sizes were heavily imbalanced (see data_contract.md).
"""

from __future__ import annotations

import json
import time
import warnings
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="X does not have valid feature names")
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix

from src.preprocessing.multiclass_tagger import LABEL_NAMES
from src.utils import get_logger, load_config

logger = get_logger(__name__)

LABEL_ORDER = sorted(LABEL_NAMES.keys())
LABEL_NAMES_ORDERED = [LABEL_NAMES[i] for i in LABEL_ORDER]


def load_data(processed_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the Nhanh 1 train/test split.

    Args:
        processed_dir: Directory containing nhanh1_train.csv.

    Returns:
        (train_df, test_df) tuple.
    """
    df = pd.read_csv(processed_dir / "nhanh1_train.csv")
    train_df = df[df["split"] == "train"].reset_index(drop=True)
    test_df = df[df["split"] == "test"].reset_index(drop=True)
    logger.info("Loaded train=%d test=%d rows", len(train_df), len(test_df))
    return train_df, test_df


def measure_latency(predict_one: Callable[[str], int], texts: list[str], n: int = 200) -> dict[str, float]:
    """Measure single-query inference latency (warm, after 1 warmup call).

    Args:
        predict_one: Function taking one raw text and returning a label.
        texts: Pool of texts to sample from.
        n: Number of single-query calls to time.

    Returns:
        Dict with p50_ms and p95_ms.
    """
    sample = texts[:n] if len(texts) >= n else (texts * (n // max(1, len(texts)) + 1))[:n]
    predict_one(sample[0])  # warmup
    latencies = []
    for text in sample:
        start = time.perf_counter()
        predict_one(text)
        latencies.append((time.perf_counter() - start) * 1000)
    return {
        "p50_ms": float(np.percentile(latencies, 50)),
        "p95_ms": float(np.percentile(latencies, 95)),
    }


def evaluate_predictions(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    """Compute F1-macro, per-class report, and confusion matrix.

    Args:
        y_true: Ground-truth labels.
        y_pred: Predicted labels.

    Returns:
        Dict with f1_macro, per_class report (dict), and confusion_matrix (list of lists).
    """
    report = classification_report(
        y_true, y_pred, labels=LABEL_ORDER, target_names=LABEL_NAMES_ORDERED, output_dict=True, zero_division=0
    )
    cm = confusion_matrix(y_true, y_pred, labels=LABEL_ORDER)
    return {
        "f1_macro": report["macro avg"]["f1-score"],
        "per_class": {name: report[name] for name in LABEL_NAMES_ORDERED},
        "confusion_matrix": cm.tolist(),
    }


def run_tfidf_logreg(
    train_df: pd.DataFrame, test_df: pd.DataFrame, cfg, models_dir: Path
) -> dict[str, Any]:
    """Train + evaluate candidate (a): TF-IDF + Logistic Regression."""
    logger.info("=== Candidate (a): TF-IDF + Logistic Regression ===")
    tfidf_cfg = cfg.get_path("branch1_supervised.tfidf")
    vectorizer = TfidfVectorizer(
        analyzer=tfidf_cfg["analyzer"],
        ngram_range=(tfidf_cfg["ngram_min"], tfidf_cfg["ngram_max"]),
        max_features=tfidf_cfg["max_features"],
    )
    X_train = vectorizer.fit_transform(train_df["query_canonical"].astype(str))
    X_test = vectorizer.transform(test_df["query_canonical"].astype(str))

    clf = LogisticRegression(max_iter=1000, n_jobs=-1)
    t0 = time.perf_counter()
    clf.fit(X_train, train_df["label"])
    train_time_s = time.perf_counter() - t0

    y_pred = clf.predict(X_test)
    metrics = evaluate_predictions(test_df["label"].to_numpy(), y_pred)

    def predict_one(text: str) -> int:
        return int(clf.predict(vectorizer.transform([text]))[0])

    metrics["latency"] = measure_latency(predict_one, test_df["query_canonical"].astype(str).tolist())
    metrics["train_time_s"] = train_time_s

    out_dir = models_dir / "candidate_tfidf_logreg"
    out_dir.mkdir(parents=True, exist_ok=True)
    import joblib

    joblib.dump(vectorizer, out_dir / "vectorizer.joblib")
    joblib.dump(clf, out_dir / "model.joblib")
    metrics["model_size_bytes"] = sum(f.stat().st_size for f in out_dir.glob("*.joblib"))

    logger.info("(a) F1-macro=%.4f train_time=%.1fs p50=%.3fms", metrics["f1_macro"], train_time_s, metrics["latency"]["p50_ms"])
    return metrics


def run_tfidf_lightgbm(
    train_df: pd.DataFrame, test_df: pd.DataFrame, cfg, models_dir: Path
) -> dict[str, Any]:
    """Train + evaluate candidate (b): TF-IDF + LightGBM."""
    logger.info("=== Candidate (b): TF-IDF + LightGBM ===")
    import lightgbm as lgb

    tfidf_cfg = cfg.get_path("branch1_supervised.tfidf")
    vectorizer = TfidfVectorizer(
        analyzer=tfidf_cfg["analyzer"],
        ngram_range=(tfidf_cfg["ngram_min"], tfidf_cfg["ngram_max"]),
        max_features=tfidf_cfg["max_features"],
    )
    X_train = vectorizer.fit_transform(train_df["query_canonical"].astype(str))
    X_test = vectorizer.transform(test_df["query_canonical"].astype(str))

    clf = lgb.LGBMClassifier(
        objective="multiclass",
        num_class=len(LABEL_ORDER),
        n_estimators=200,
        random_state=cfg.get_path("project.random_seed", 42),
        verbose=-1,
    )
    t0 = time.perf_counter()
    clf.fit(X_train, train_df["label"].to_numpy())
    train_time_s = time.perf_counter() - t0

    y_pred = clf.predict(X_test)
    metrics = evaluate_predictions(test_df["label"].to_numpy(), y_pred)

    def predict_one(text: str) -> int:
        return int(clf.predict(vectorizer.transform([text]))[0])

    metrics["latency"] = measure_latency(predict_one, test_df["query_canonical"].astype(str).tolist())
    metrics["train_time_s"] = train_time_s

    out_dir = models_dir / "candidate_tfidf_lightgbm"
    out_dir.mkdir(parents=True, exist_ok=True)
    import joblib

    joblib.dump(vectorizer, out_dir / "vectorizer.joblib")
    joblib.dump(clf, out_dir / "model.joblib")
    metrics["model_size_bytes"] = sum(f.stat().st_size for f in out_dir.glob("*.joblib"))

    logger.info("(b) F1-macro=%.4f train_time=%.1fs p50=%.3fms", metrics["f1_macro"], train_time_s, metrics["latency"]["p50_ms"])
    return metrics


def run_distilbert(
    train_df: pd.DataFrame, test_df: pd.DataFrame, cfg, models_dir: Path
) -> dict[str, Any]:
    """Train + evaluate candidate (c): DistilBERT fine-tune."""
    logger.info("=== Candidate (c): DistilBERT fine-tune ===")
    import torch
    from torch.utils.data import DataLoader, Dataset
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    bert_cfg = cfg.get_path("branch1_supervised.distilbert")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Using device: %s", device)

    tokenizer = AutoTokenizer.from_pretrained(bert_cfg["pretrained"])
    model = AutoModelForSequenceClassification.from_pretrained(
        bert_cfg["pretrained"], num_labels=len(LABEL_ORDER)
    ).to(device)

    class QueryDataset(Dataset):
        def __init__(self, texts: list[str], labels: list[int]):
            self.texts = texts
            self.labels = labels

        def __len__(self) -> int:
            return len(self.texts)

        def __getitem__(self, idx: int) -> dict[str, Any]:
            return {"text": self.texts[idx], "label": self.labels[idx]}

    def collate(batch: list[dict[str, Any]]) -> dict[str, torch.Tensor]:
        texts = [b["text"] for b in batch]
        labels = torch.tensor([b["label"] for b in batch], dtype=torch.long)
        enc = tokenizer(
            texts, padding=True, truncation=True, max_length=bert_cfg["max_length"], return_tensors="pt"
        )
        enc["labels"] = labels
        return enc

    train_ds = QueryDataset(train_df["query_canonical"].astype(str).tolist(), train_df["label"].tolist())
    train_loader = DataLoader(train_ds, batch_size=bert_cfg["batch_size"], shuffle=True, collate_fn=collate)

    optimizer = torch.optim.AdamW(model.parameters(), lr=bert_cfg["learning_rate"])

    t0 = time.perf_counter()
    model.train()
    for epoch in range(bert_cfg["epochs"]):
        epoch_loss = 0.0
        for batch in train_loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            optimizer.zero_grad()
            outputs = model(**batch)
            outputs.loss.backward()
            optimizer.step()
            epoch_loss += outputs.loss.item()
        logger.info("  epoch %d/%d loss=%.4f", epoch + 1, bert_cfg["epochs"], epoch_loss / len(train_loader))
    train_time_s = time.perf_counter() - t0

    model.eval()
    all_preds = []
    test_texts = test_df["query_canonical"].astype(str).tolist()
    with torch.no_grad():
        for i in range(0, len(test_texts), bert_cfg["batch_size"]):
            batch_texts = test_texts[i : i + bert_cfg["batch_size"]]
            enc = tokenizer(
                batch_texts, padding=True, truncation=True, max_length=bert_cfg["max_length"], return_tensors="pt"
            ).to(device)
            logits = model(**enc).logits
            all_preds.extend(logits.argmax(dim=-1).cpu().tolist())

    metrics = evaluate_predictions(test_df["label"].to_numpy(), np.array(all_preds))

    def predict_one(text: str) -> int:
        enc = tokenizer(
            [text], padding=True, truncation=True, max_length=bert_cfg["max_length"], return_tensors="pt"
        ).to(device)
        with torch.no_grad():
            logits = model(**enc).logits
        return int(logits.argmax(dim=-1).cpu().item())

    metrics["latency"] = measure_latency(predict_one, test_texts)
    metrics["train_time_s"] = train_time_s

    out_dir = models_dir / "candidate_distilbert"
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)
    metrics["model_size_bytes"] = sum(f.stat().st_size for f in out_dir.rglob("*") if f.is_file())

    logger.info(
        "(c) F1-macro=%.4f train_time=%.1fs p50=%.3fms", metrics["f1_macro"], train_time_s, metrics["latency"]["p50_ms"]
    )
    return metrics


def _build_char_vocab(texts: list[str], vocab_size: int) -> dict[str, int]:
    """Build a char-level vocabulary from the most frequent characters.

    Args:
        texts: Training texts to build the vocabulary from.
        vocab_size: Max vocabulary size (including <PAD>/<UNK>).

    Returns:
        Dict mapping character -> integer id. id 0 = <PAD>, id 1 = <UNK>.
    """
    from collections import Counter

    counts = Counter()
    for t in texts:
        counts.update(t)
    most_common = [c for c, _ in counts.most_common(vocab_size - 2)]
    vocab = {"<PAD>": 0, "<UNK>": 1}
    for i, c in enumerate(most_common, start=2):
        vocab[c] = i
    return vocab


def _encode_texts(texts: list[str], vocab: dict[str, int], max_length: int) -> "torch.Tensor":
    """Encode texts to fixed-length integer id sequences (char-level, padded/truncated)."""
    import torch

    unk = vocab["<UNK>"]
    ids = torch.zeros((len(texts), max_length), dtype=torch.long)
    for i, t in enumerate(texts):
        encoded = [vocab.get(c, unk) for c in t[:max_length]]
        ids[i, : len(encoded)] = torch.tensor(encoded, dtype=torch.long)
    return ids


def _build_textcnn_class():
    """Build the TextCNN nn.Module class (deferred so torch is imported lazily)."""
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    class _TextCNN(nn.Module):
        """Small CNN over char-level SQL text (Kim 2014 TextCNN, ~tens of K params)."""

        def __init__(
            self, vocab_size: int, embedding_dim: int, num_filters: int, kernel_sizes: list[int], num_classes: int
        ):
            super().__init__()
            self.embedding = nn.Embedding(vocab_size, embedding_dim, padding_idx=0)
            self.convs = nn.ModuleList(
                [nn.Conv1d(embedding_dim, num_filters, kernel_size=k) for k in kernel_sizes]
            )
            self.dropout = nn.Dropout(0.3)
            self.fc = nn.Linear(num_filters * len(kernel_sizes), num_classes)

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            emb = self.embedding(x).transpose(1, 2)  # (batch, embedding_dim, seq_len)
            pooled = [F.max_pool1d(F.relu(conv(emb)), kernel_size=conv(emb).shape[-1]).squeeze(-1) for conv in self.convs]
            concat = torch.cat(pooled, dim=1)
            concat = self.dropout(concat)
            return self.fc(concat)

    return _TextCNN


def run_cnn_sqltok(
    train_df: pd.DataFrame, test_df: pd.DataFrame, cfg, models_dir: Path
) -> dict[str, Any]:
    """Train + evaluate candidate (d): small CNN over a char-level SQL tokenizer."""
    logger.info("=== Candidate (d): CNN + char-level SQL tokenizer ===")
    import torch
    import torch.nn.functional as F

    cnn_cfg = cfg.get_path("branch1_supervised.cnn_sqltok")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Using device: %s", device)

    train_texts = train_df["query_canonical"].astype(str).tolist()
    test_texts = test_df["query_canonical"].astype(str).tolist()
    vocab = _build_char_vocab(train_texts, cnn_cfg["vocab_size"])
    logger.info("Char vocab size: %d", len(vocab))

    X_train = _encode_texts(train_texts, vocab, cnn_cfg["max_length"]).to(device)
    y_train = torch.tensor(train_df["label"].tolist(), dtype=torch.long).to(device)
    X_test = _encode_texts(test_texts, vocab, cnn_cfg["max_length"]).to(device)

    TextCNN = _build_textcnn_class()
    model = TextCNN(
        vocab_size=len(vocab),
        embedding_dim=cnn_cfg["embedding_dim"],
        num_filters=cnn_cfg["num_filters"],
        kernel_sizes=cnn_cfg["kernel_sizes"],
        num_classes=len(LABEL_ORDER),
    ).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    logger.info("Model parameter count: %d", n_params)

    optimizer = torch.optim.Adam(model.parameters(), lr=cnn_cfg["learning_rate"])
    batch_size = cnn_cfg["batch_size"]

    t0 = time.perf_counter()
    model.train()
    n = X_train.shape[0]
    for epoch in range(cnn_cfg["epochs"]):
        perm = torch.randperm(n)
        epoch_loss = 0.0
        n_batches = 0
        for i in range(0, n, batch_size):
            idx = perm[i : i + batch_size]
            optimizer.zero_grad()
            logits = model(X_train[idx])
            loss = F.cross_entropy(logits, y_train[idx])
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
            n_batches += 1
        logger.info("  epoch %d/%d loss=%.4f", epoch + 1, cnn_cfg["epochs"], epoch_loss / n_batches)
    train_time_s = time.perf_counter() - t0

    model.eval()
    with torch.no_grad():
        preds = model(X_test).argmax(dim=-1).cpu().numpy()
    metrics = evaluate_predictions(test_df["label"].to_numpy(), preds)

    def predict_one(text: str) -> int:
        x = _encode_texts([text], vocab, cnn_cfg["max_length"]).to(device)
        with torch.no_grad():
            return int(model(x).argmax(dim=-1).cpu().item())

    metrics["latency"] = measure_latency(predict_one, test_texts)
    metrics["train_time_s"] = train_time_s
    metrics["n_params"] = n_params

    out_dir = models_dir / "candidate_cnn_sqltok"
    out_dir.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), out_dir / "model.pt")
    with (out_dir / "vocab.json").open("w", encoding="utf-8") as f:
        json.dump(vocab, f)
    metrics["model_size_bytes"] = sum(f.stat().st_size for f in out_dir.glob("*") if f.is_file())

    logger.info(
        "(d) F1-macro=%.4f train_time=%.1fs p50=%.3fms n_params=%d",
        metrics["f1_macro"],
        train_time_s,
        metrics["latency"]["p50_ms"],
        n_params,
    )
    return metrics


CANDIDATES: dict[str, Callable] = {
    "tfidf_logreg": run_tfidf_logreg,
    "tfidf_lightgbm": run_tfidf_lightgbm,
    "distilbert": run_distilbert,
    "cnn_sqltok": run_cnn_sqltok,
}


def main() -> None:
    """Run the architecture comparison, resuming already-computed candidates."""
    import sys

    cfg = load_config()
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    models_dir = Path(cfg.get_path("paths.models_dir", "models")) / "nhanh1_comparison"
    models_dir.mkdir(parents=True, exist_ok=True)

    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / "nhanh1_architecture_comparison.json"

    results: dict[str, Any] = {}
    if out_path.exists():
        with out_path.open(encoding="utf-8") as f:
            results = json.load(f)
        logger.info("Resuming: found existing results for %s", list(results.keys()))

    requested = sys.argv[1:] or list(CANDIDATES.keys())
    train_df, test_df = load_data(processed_dir)

    for name in requested:
        if name in results:
            logger.info("Skipping %s (already computed; delete %s to force rerun)", name, out_path)
            continue
        results[name] = CANDIDATES[name](train_df, test_df, cfg, models_dir)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=float)
        logger.info("Saved incremental results to %s", out_path)

    print("\n=== SUMMARY ===")
    for name, m in results.items():
        print(f"{name:20s} F1-macro={m['f1_macro']:.4f}  p50={m['latency']['p50_ms']:.3f}ms  p95={m['latency']['p95_ms']:.3f}ms  size={m['model_size_bytes']/1024:.1f}KB")


if __name__ == "__main__":
    main()
