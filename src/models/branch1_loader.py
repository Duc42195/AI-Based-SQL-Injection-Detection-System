"""Architecture-agnostic loading for Branch 1's (vectorizer, classifier) pair.

Every consumer in this codebase (``deploy.registry.Branch1Model``,
``SessionCorrelator``, ``branch1_probabilities``, the various eval/build
scripts) only ever calls ``vectorizer.transform(texts)`` then
``clf.predict_proba(X)`` / reads ``clf.classes_`` - never sklearn internals
directly. That is the seam this module exploits: :class:`DistilBertClassifier`
implements the same two members over a fine-tuned Hugging Face model, and
:class:`IdentityVectorizer` is a no-op stand-in for ``TfidfVectorizer`` (a
transformer model tokenizes raw text itself), so a DistilBERT-backed Branch 1
model drops into every existing call site with no changes there - only the
*loading* code (this module) needs to know two artifact layouts exist.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)


class IdentityVectorizer:
    """No-op stand-in for ``TfidfVectorizer`` when Branch 1 is a transformer.

    ``DistilBertClassifier`` tokenizes raw text itself, so the "vectorizer"
    step in the shared ``vectorizer.transform() -> clf.predict_proba()`` call
    path just needs to pass texts through unchanged.
    """

    def transform(self, texts: list[str]) -> list[str]:
        return list(texts)


class DistilBertClassifier:
    """Fine-tuned DistilBERT model + tokenizer, presented as an sklearn-like classifier.

    Exposes ``predict_proba`` and ``classes_`` - the only two members every
    caller in this codebase actually uses - so it is interchangeable with the
    ``LogisticRegression`` classifier it replaces.
    """

    def __init__(self, model_dir: str | Path, max_length: int = 128, batch_size: int = 32) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
        self._model = AutoModelForSequenceClassification.from_pretrained(str(model_dir)).to(self._device)
        self._model.eval()
        self._max_length = max_length
        self._batch_size = batch_size
        # Labels are 0-indexed and contiguous at training time (see
        # train/compare_branch1_architectures.py's _num_classes), so the
        # model's output logit index IS the label id directly - matching
        # sklearn's `clf.classes_` convention with no remapping needed.
        self.classes_ = list(range(self._model.config.num_labels))

    def predict_proba(self, texts: list[str]) -> np.ndarray:
        torch = self._torch
        texts = list(texts)
        out = np.zeros((len(texts), len(self.classes_)), dtype=np.float64)
        with torch.no_grad():
            for i in range(0, len(texts), self._batch_size):
                batch = texts[i : i + self._batch_size]
                enc = self._tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=self._max_length,
                    return_tensors="pt",
                ).to(self._device)
                logits = self._model(**enc).logits
                probs = torch.softmax(logits, dim=-1).cpu().numpy()
                out[i : i + len(batch)] = probs
        return out

    def predict(self, texts: list[str]) -> np.ndarray:
        """Hard label predictions (argmax over :meth:`predict_proba`)."""
        probs = self.predict_proba(texts)
        idx = np.argmax(probs, axis=1)
        classes = np.array(self.classes_)
        return classes[idx]


def is_distilbert_dir(model_dir: str | Path) -> bool:
    """True if ``model_dir`` holds a Hugging Face model rather than joblib artifacts."""
    model_dir = Path(model_dir)
    return (model_dir / "config.json").exists() and (
        (model_dir / "model.safetensors").exists() or (model_dir / "pytorch_model.bin").exists()
    )


def branch1_artifacts_exist(model_dir: str | Path) -> bool:
    """True if a loadable Branch-1 model (either artifact layout) is present."""
    model_dir = Path(model_dir)
    return is_distilbert_dir(model_dir) or (model_dir / "vectorizer.joblib").exists()


def load_branch1_artifacts(
    model_dir: str | Path, distilbert_cfg: dict[str, Any] | None = None
) -> tuple[Any, Any]:
    """Load Branch-1's (vectorizer, classifier) pair, whichever architecture is on disk.

    Args:
        model_dir: Directory containing either ``vectorizer.joblib`` +
            ``model.joblib`` (sklearn) or a Hugging Face model (DistilBERT).
        distilbert_cfg: ``branch1_supervised.distilbert`` config block
            (``max_length``, ``batch_size``); only consulted for the
            DistilBERT layout.

    Returns:
        A ``(vectorizer, clf)`` pair with the ``transform``/``predict_proba``/
        ``classes_`` surface every caller in this codebase relies on.
    """
    model_dir = Path(model_dir)
    if is_distilbert_dir(model_dir):
        distilbert_cfg = distilbert_cfg or {}
        logger.info("Loading Branch-1 DistilBERT model from %s", model_dir)
        vectorizer = IdentityVectorizer()
        clf = DistilBertClassifier(
            model_dir,
            max_length=int(distilbert_cfg.get("max_length", 128)),
            batch_size=int(distilbert_cfg.get("batch_size", 32)),
        )
        return vectorizer, clf
    vectorizer = joblib.load(model_dir / "vectorizer.joblib")
    clf = joblib.load(model_dir / "model.joblib")
    return vectorizer, clf


def train_distilbert(
    train_texts: list[str],
    train_labels: list[int],
    out_dir: str | Path,
    *,
    num_classes: int,
    distilbert_cfg: dict[str, Any],
    seed: int | None = None,
) -> dict[str, Any]:
    """Fine-tune DistilBERT on ``(train_texts, train_labels)`` and save it to ``out_dir``.

    Mirrors ``train/compare_branch1_architectures.py``'s ``run_distilbert``
    training loop, generalized to take texts+labels directly (not a
    train/test dataframe pair) so both the production trainer
    (``train/train_branch1.py``) and the continual-learning trainer
    (``src/continual_learning/trainer.py``, which trains M0/M1/M2 for the
    real-class-holdout scenario) share one training path rather than two
    copies that could drift apart.

    Args:
        train_texts: Canonicalized query strings.
        train_labels: Integer label ids, 0-indexed and contiguous
            (``LABEL_NAMES`` ids) - matching what the model's output logit
            index means everywhere else in this codebase.
        out_dir: Where to ``save_pretrained`` the model + tokenizer.
        num_classes: Size of the classification head. Passed explicitly
            (rather than inferred as ``max(labels)+1``) so a fold that
            happens not to contain the highest-id class still gets a head
            sized for the full label space (needed for the CL scenario's
            M0, which holds out a whole class).
        distilbert_cfg: ``branch1_supervised.distilbert`` config block.

    Returns:
        Metrics dict with ``train_time_s`` (no test-set metrics - the caller
        evaluates the saved model itself, since evaluation sets vary by caller).
    """
    import time

    import torch
    from torch.utils.data import DataLoader, Dataset
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    if seed is not None:
        torch.manual_seed(seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Fine-tuning DistilBERT on device=%s, n=%d, classes=%d", device, len(train_texts), num_classes)

    tokenizer = AutoTokenizer.from_pretrained(distilbert_cfg["pretrained"])
    model = AutoModelForSequenceClassification.from_pretrained(
        distilbert_cfg["pretrained"], num_labels=num_classes
    ).to(device)

    class QueryDataset(Dataset):
        def __init__(self, texts: list[str], labels: list[int]):
            self.texts = texts
            self.labels = labels

        def __len__(self) -> int:
            return len(self.texts)

        def __getitem__(self, idx: int) -> dict[str, Any]:
            return {"text": self.texts[idx], "label": self.labels[idx]}

    def collate(batch: list[dict[str, Any]]) -> dict[str, "torch.Tensor"]:
        texts = [b["text"] for b in batch]
        labels = torch.tensor([b["label"] for b in batch], dtype=torch.long)
        enc = tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=distilbert_cfg["max_length"],
            return_tensors="pt",
        )
        enc["labels"] = labels
        return enc

    train_ds = QueryDataset(list(train_texts), [int(label) for label in train_labels])
    train_loader = DataLoader(
        train_ds, batch_size=distilbert_cfg["batch_size"], shuffle=True, collate_fn=collate
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=distilbert_cfg["learning_rate"])

    t0 = time.perf_counter()
    model.train()
    for epoch in range(distilbert_cfg["epochs"]):
        epoch_loss = 0.0
        for batch in train_loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            optimizer.zero_grad()
            outputs = model(**batch)
            outputs.loss.backward()
            optimizer.step()
            epoch_loss += outputs.loss.item()
        logger.info("  epoch %d/%d loss=%.4f", epoch + 1, distilbert_cfg["epochs"], epoch_loss / len(train_loader))
    train_time_s = time.perf_counter() - t0

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)
    model_size_bytes = sum(f.stat().st_size for f in out_dir.rglob("*") if f.is_file())
    logger.info("Saved DistilBERT model to %s (train_time=%.1fs)", out_dir, train_time_s)
    return {"train_time_s": train_time_s, "model_size_bytes": model_size_bytes}
