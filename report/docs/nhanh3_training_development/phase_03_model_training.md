# Phase 3: Model Training

> **Master plan**: [plan.md](plan.md)
>
> **Context**: [branch3_context.md](branch3_context.md)
>
> **Phụ thuộc**: Phase 2 hoàn thành — session feature dataset có sẵn

**Mục tiêu**: Implement và train GRU model cho session-level classification.

---

## Architecture (kế thừa từ mentor's original)

```
Input (batch, seq_len, 7)
  → PackedSequence (bỏ qua padding)
  → GRU(7 → 32, 1 layer, bidirectional=False)
  → Lấy hidden state cuối (hoặc mean pooling)
  → Dropout(0.2)
  → Linear(32 → 4)
  → Softmax
Output: 4-class [benign, boolean_blind, time_blind, query_splitting]
```

**Tham số tham khảo** (từ `models/branch3_v1/metadata.json`):

| Tham số | Giá trị |
|---------|---------|
| `input_dim` | 7 |
| `hidden_dim` | 32 |
| `num_classes` | 4 |
| `class_names` | [benign, boolean_blind, time_blind, query_splitting] |
| `max_len` | 64 |
| `random_seed` | 42 |

---

## Các bước

### 3.1 Tạo `src/models/branch3_session.py`

```python
class SessionSequenceDetector:
    """GRU-based session classifier."""

    def __init__(self, input_dim=7, hidden_dim=32, num_classes=4, ...):
        pass  # define GRU layers

    def fit(self, train_loader, val_loader, epochs, lr, ...):
        """Train loop with logging."""
        pass

    def predict(self, sequences: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
        """Return (class_ids, probabilities)."""
        pass

    def save(self, path: str):
        """Save model.pt + metadata.json."""
        pass

    @classmethod
    def load(cls, path: str) -> SessionSequenceDetector:
        """Load model.pt + metadata.json."""
        pass
```

**Lưu ý**:
- Dùng `PackedSequence` của PyTorch để handle variable-length sessions
- Không dùng Transformer — GRU 1 layer là đủ (đã kiểm chứng qua architecture
  comparison cũ)
- Log loss, accuracy, F1 per epoch
- Save metadata.json giống format mentor: `input_dim, hidden_dim, num_classes,
  class_names, random_seed, max_len`

### 3.2 Tạo `train/train_branch3.py`

```python
def main():
    cfg = load_config()
    # 1. Load dataset
    train_df = pd.read_csv(cfg.get_path("branch3_session.train_data"))
    val_df = pd.read_csv(cfg.get_path("branch3_session.val_data"))

    # 2. Build DataLoader (collate_fn cho variable-length)
    # 3. Init model
    model = SessionSequenceDetector(...)

    # 4. Train
    model.fit(train_loader, val_loader,
              epochs=cfg.get_path("branch3_session.train.epochs", 30),
              lr=cfg.get_path("branch3_session.train.learning_rate", 0.001))

    # 5. Evaluate on test
    # 6. Save to models/branch3_v2/
    # 7. Log metrics to report/metrics/branch3_train.json
```

### 3.3 Thêm config

Vào `configs/config.yaml`:

```yaml
branch3_session:
  enabled: true
  active_version: "branch3_v2"
  max_session_len: 64
  session_classes:
    benign: 0
    boolean_blind: 1
    time_blind: 2
    query_splitting: 3
  data:
    train: "data/processed/branch3_train.csv"
    val: "data/processed/branch3_val.csv"
    test: "data/processed/branch3_test.csv"
  train:
    hidden_dim: 32
    epochs: 30
    learning_rate: 0.001
    batch_size: 16
    random_seed: 42
```

### 3.4 Train & evaluate

- [ ] Chạy `uv run python train/train_branch3.py`
- [ ] Ghi lại loss curve (tensorboard hoặc log file)
- [ ] Ghi confusion matrix
- [ ] Ghi F1 per class + macro

### 3.5 Pytest

- [ ] `tests/test_branch3_session.py`
- [ ] Test forward pass shape
- [ ] Test variable-length batch
- [ ] Test save/load roundtrip
- [ ] Test predict trên sequence length < max_len

---

## Đầu ra

| File | Mô tả |
|------|-------|
| `src/models/branch3_session.py` | GRU model class |
| `train/train_branch3.py` | Training script |
| `tests/test_branch3_session.py` | Unit tests |
| `configs/config.yaml` (sửa) | Section `branch3_session` |
| `models/branch3_v2/metadata.json` | Model metadata |
| `models/branch3_v2/model.pt` | Trained weights (gitignored) |
| `report/metrics/branch3_train.json` | Training metrics |

## Verification checklist

- [ ] `uv run pytest tests/test_branch3_session.py -q` green
- [ ] Train loss giảm dần
- [ ] F1-macro > baseline (majority class)
- [ ] Confusion matrix shows non-trivial diagonal
- [ ] Model reload được từ disk, predict đúng shape

## Next phase

→ [Phase 4: Hard Evaluation](./phase_04_hard_evaluation.md)
