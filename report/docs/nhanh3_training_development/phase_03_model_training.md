# Phase 3: Model Training

> **Master plan**: [plan.md](plan.md)
>
> **Context**: [branch3_context.md](branch3_context.md)
>
> **Phụ thuộc**: Phase 2 hoàn thành — session feature dataset có sẵn

**Mục tiêu**: Implement và train GRU model cho session-level classification.

---

## B1 candidate comparison

Trước khi train GRU chính thức, cần xác nhận rằng B1 backbone khác nhau
(cnn_sqltok, distilbert) có ảnh hưởng đến B3 accuracy hay không.

**Kỳ vọng**: F1-macro ~0.985 cho cả 3 candidates → B1 probs tương tự
→ B3 không bị ảnh hưởng. Nhưng cần ablation để có số.

Các bước:
- Tích hợp `candidate_cnn_sqltok` và `candidate_distilbert` vào
  `build_session_dataset.py` (thêm `--b1-backbone` flag hoặc config-driven)
- Chạy feature extraction 3 lần (tfidf_logreg, cnn_sqltok, distilbert)
- Train GRU trên mỗi feature set
- So sánh B3 F1-macro

**Nếu F1-macro khác biệt > 0.01**: cần chọn backbone cho B3 production.
**Nếu F1-macro tương đương (< 0.01)**: dùng tfidf_logreg (đã chọn cho B1).

Output: `report/metrics/branch3_candidate_comparison.json`

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

### 3.1 B1 candidate comparison

**Trạng thái**: ⏸️ **Deferred** — ablation cho thấy B2 alone (1 dim) đã đạt 1.0 accuracy. Candidate backbone comparison không còn meaningful trên synthetic data. Sẽ làm lại khi có real data ở Phase 4.

Cần implement trước vì feature extraction phụ thuộc vào B1 backbone.

- [x] ~~Thêm `--b1-backbone` flag~~ → Deferred
- [x] ~~Chạy feature extraction 3 lần~~ → Deferred
- [x] ~~Train GRU 3 lần~~ → Deferred
- [x] ~~So sánh~~ → Deferred

**Kết luận**: tfidf_logreg vẫn là default backbone cho B1. Khi có real data sẽ re-evaluate.

### 3.2 Tạo `src/models/branch3_session.py`

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

### 3.3 Tạo `train/train_branch3.py`

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

### 3.4 Thêm config

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

### 3.5 Train & evaluate

- [x] Chạy `uv run python train/train_branch3.py`
- [x] ~~Chạy candidate comparison script~~ → Deferred
- [x] Ghi loss curve vào `report/metrics/branch3_train.json`
- [x] Ghi confusion matrix vào `report/metrics/branch3_confusion.json`
- [x] Ghi F1 per class + macro
- [x] Ghi ablation results `report/metrics/branch3_ablation.json`
- [x] Ghi notebook `train/notebooks/branch3_training_results.ipynb`

### 3.6 Pytest

- [x] `tests/test_branch3_session.py` — 14 tests
- [x] `tests/test_branch3_candidates.py` — 11 tests
- [x] Test forward pass shape
- [x] Test variable-length batch
- [x] Test save/load roundtrip
- [x] Test predict trên sequence length < max_len

---

## Đầu ra

| File | Mô tả | Trạng thái |
|------|-------|------------|
| `src/models/branch3_session.py` | GRU model class | ✅ |
| `train/train_branch3.py` | Training script | ✅ |
| `tests/test_branch3_session.py` | Unit tests (14) | ✅ |
| `tests/test_branch3_candidates.py` | Candidate integration tests (11) | ✅ |
| `configs/config.yaml` (sửa) | Section `branch3_session` | ✅ |
| `models/branch3_v2/metadata.json` | Model metadata | ✅ |
| `models/branch3_v2/model.pt` | Trained weights (gitignored) | ✅ |
| `report/metrics/branch3_train.json` | Training metrics | ✅ |
| `report/metrics/branch3_confusion.json` | Confusion matrix + F1 | ✅ |
| `report/metrics/branch3_ablation.json` | Ablation study | ✅ |
| `report/metrics/figures/branch3_metrics_summary.png` | Metrics figure | ✅ |
| `train/notebooks/branch3_training_results.ipynb` | Executed notebook | ✅ |
| ~~`report/metrics/branch3_candidate_comparison.json`~~ | B1 backbone comparison | ⏸️ Deferred |

## Verification checklist

- [x] `uv run pytest tests/test_branch3_session.py -q` green (25/25 passed)
- [x] Train loss giảm dần (0.928 → 0.001)
- [x] F1-macro = 1.0 > baseline (majority class = 0.25)
- [x] Confusion matrix shows perfect diagonal (all 1.0)
- [x] Model reload được từ disk, predict đúng shape

## Next phase

→ [Phase 4: Hard Evaluation](./phase_04_hard_evaluation.md)

