from __future__ import annotations

import numpy as np
import pytest
import torch

from src.models.branch3_session import (
    SessionDataset,
    SessionSequenceDetector,
    collate_fn,
    eval_epoch,
    fit,
)


class TestSessionDataset:
    def test_basic_shape(self):
        X = np.random.randn(10, 5, 7).astype(np.float32)
        y = np.random.randint(0, 4, size=10)
        ds = SessionDataset(X, y)
        assert len(ds) == 10
        x_out, l_out, y_out = ds[0]
        assert x_out.shape == (5, 7)
        assert l_out.item() > 0

    def test_no_labels(self):
        X = np.random.randn(5, 8, 7).astype(np.float32)
        ds = SessionDataset(X)
        assert len(ds) == 5
        x_out, l_out = ds[0]
        assert x_out.shape == (8, 7)

    def test_lengths_clamped_min_1(self):
        X = np.zeros((3, 5, 7), dtype=np.float32)
        ds = SessionDataset(X)
        assert ds.lengths.tolist() == [1, 1, 1]


class TestCollateFn:
    def test_basic(self):
        X = np.random.randn(3, 5, 7).astype(np.float32)
        y = np.array([0, 1, 2])
        ds = SessionDataset(X, y)
        batch = [ds[0], ds[1], ds[2]]
        x_pad, lengths, labels = collate_fn(batch)
        assert x_pad.shape == (3, lengths.max().item(), 7)
        assert labels.shape == (3,)
        assert lengths.shape == (3,)


class TestSessionSequenceDetector:
    def test_default_init(self):
        model = SessionSequenceDetector()
        assert model.input_dim == 7
        assert model.hidden_dim == 32
        assert model.num_classes == 4
        assert model.max_len == 64

    def test_forward_shape(self):
        model = SessionSequenceDetector()
        X = torch.randn(2, 5, 7)
        lengths = torch.tensor([5, 5])
        logits = model(X, lengths)
        assert logits.shape == (2, 4)

    def test_forward_variable_length(self):
        model = SessionSequenceDetector()
        X = torch.randn(2, 10, 7)
        X[1, 5:] = 0
        lengths = torch.tensor([10, 5])
        logits = model(X, lengths)
        assert logits.shape == (2, 4)
        logits.sum().backward()
        assert model.gru.weight_ih_l0.grad is not None

    def test_predict_returns_tuple(self):
        model = SessionSequenceDetector()
        seqs = [np.random.randn(5, 7).astype(np.float32) for _ in range(3)]
        preds, probs = model.predict(seqs)
        assert preds.shape == (3,)
        assert probs.shape == (3, 4)

    def test_predict_with_device(self):
        model = SessionSequenceDetector()
        seqs = [np.random.randn(4, 7).astype(np.float32) for _ in range(2)]
        preds, probs = model.predict(seqs, device='cpu')
        assert preds.shape == (2,)
        assert probs.shape == (2, 4)

    def test_save_load_equivalence(self, tmp_path):
        model = SessionSequenceDetector()
        model.eval()
        X = torch.randn(2, 5, 7)
        lengths = torch.tensor([5, 5])
        out_before = model(X, lengths)
        model.save(tmp_path)
        loaded = SessionSequenceDetector.load(tmp_path)
        loaded.eval()
        out_after = loaded(X, lengths)
        assert torch.allclose(out_before, out_after)

    def test_save_load_custom_params(self, tmp_path):
        model = SessionSequenceDetector(input_dim=7, hidden_dim=64, num_classes=3, max_len=32)
        model.eval()
        model.save(tmp_path)
        loaded = SessionSequenceDetector.load(tmp_path)
        assert loaded.hidden_dim == 64
        assert loaded.num_classes == 3
        assert loaded.max_len == 32

    def test_save_load_invalid_path(self):
        with pytest.raises((FileNotFoundError, RuntimeError)):
            SessionSequenceDetector.load('nonexistent/path')


class TestTraining:
    def test_fit_updates_weights(self):
        model = SessionSequenceDetector()
        X = np.random.randn(20, 8, 7).astype(np.float32)
        y = np.random.randint(0, 4, size=20)
        ds = SessionDataset(X, y)
        n_val, n_train = 5, 15
        train_ds, val_ds = torch.utils.data.dataset.random_split(ds, [n_train, n_val], generator=torch.Generator().manual_seed(42))
        train_loader = torch.utils.data.DataLoader(train_ds, batch_size=4, shuffle=True, collate_fn=collate_fn)
        val_loader = torch.utils.data.DataLoader(val_ds, batch_size=4, shuffle=False, collate_fn=collate_fn)
        w_before = model.gru.weight_ih_l0.data.clone()
        history = fit(model, train_loader, val_loader, epochs=2, lr=0.01, device='cpu')
        w_after = model.gru.weight_ih_l0.data
        assert not torch.allclose(w_before, w_after)
        assert 'train_loss' in history and 'train_acc' in history
        assert 'val_loss' in history and 'val_acc' in history
        assert len(history['train_loss']) == 2

    def test_eval_epoch(self):
        model = SessionSequenceDetector()
        X = np.random.randn(10, 8, 7).astype(np.float32)
        y = np.random.randint(0, 4, size=10)
        ds = SessionDataset(X, y)
        loader = torch.utils.data.DataLoader(ds, batch_size=4, shuffle=False, collate_fn=collate_fn)
        loss, acc = eval_epoch(model, loader, torch.device('cpu'))
        assert isinstance(loss, float) and isinstance(acc, float)
        assert 0.0 <= acc <= 1.0
