# Phase 2: Feature Engineering

> **Master plan**: [plan.md](plan.md)
>
> **Context**: [branch3_context.md](branch3_context.md)
>
> **Phụ thuộc**: Phase 1 hoàn thành — raw session CSV có sẵn

**Mục tiêu**: Biến raw session data thành feature vectors bằng cách đưa mỗi
query qua Branch 1 (probabilities) và Branch 2 (anomaly score). Kết quả là một
CSV sẵn sàng cho training.

---

## Input / Output

```
Input:  data/raw/branch3_sessions/*.csv
        (session_id, step_idx, class, query, row_count, timing, ...)

Output: data/processed/branch3_dataset.csv
        (session_id, step_idx, class,
         b1_prob_normal, b1_prob_bool, ..., b1_prob_stacked,
         b2_anomaly_score,
         gap_seconds, gap_log1p)
```

**Per-step feature vector** (dim=7):

| Index | Feature | Source |
|-------|---------|--------|
| 0 | P(normal) | B1 prediction |
| 1 | P(boolean_blind) | B1 prediction |
| 2 | P(time_blind) | B1 prediction |
| 3 | P(error_based) | B1 prediction |
| 4 | P(union_based) / P(stacked) | B1 prediction |
| 5 | anomaly_score | B2 prediction |
| 6 | log1p(gap_seconds) | computed |

---

## Các bước

### 2.1 Tạo `train/build_session_dataset.py`

File này đọc raw CSV, score qua B1 + B2, và ghi feature CSV.

```python
# build_session_dataset.py
def score_query(query: str) -> tuple[np.ndarray, float]:
    """Return (b1_probs_5d, b2_anomaly_score) for one query."""
    pass  # gọi model branch1_v1, branch2_v1

def build_session_dataset(
    raw_path: str,
    output_path: str,
    b1_model_path: str,
    b2_model_path: str,
) -> pd.DataFrame:
    """Đọc raw CSV → thêm cột features → ghi output."""
    pass

def compute_gap_log1p(timestamps: list[float]) -> list[float]:
    """Tính log1p(Δt) giữa các step."""
    pass
```

**Lưu ý**:
- Dùng model thật từ `models/` (load qua registry hoặc joblib)
- Nếu raw CSV chưa có B1/B2 score, phải chạy inference
- gap_seconds = 0 cho step đầu tiên (không có previous step)
- log1p transform: `log1p(x) = log(1 + x)` để normalize right-skew

### 2.2 Verify features bằng tay

- [ ] Lấy 1 benign session: B1 probs phải nghiêng về "normal"
- [ ] Lấy 1 boolean session: B1 probs có thể nghiêng về boolean_blind
- [ ] Lấy 1 time session: tương tự
- [ ] anomaly_score phải khác nhau giữa benign và attack
- [ ] gap_log1p của benign phải lớn hơn attack (người gõ chậm hơn script)

### 2.3 Chia train/val/test

- [ ] Tách session-level (không step-level) — stratify theo class
- [ ] Config: `branch3_session.train_val_test_ratio: [0.7, 0.15, 0.15]`
- [ ] Lưu 3 file riêng: `_train.csv`, `_val.csv`, `_test.csv`

### 2.4 Pytest

- [ ] `tests/test_build_session_dataset.py`
- [ ] Test `compute_gap_log1p` với timestamps known
- [ ] Test output shape đúng (n_steps x 7)

---

## Đầu ra

| File | Mô tả |
|------|-------|
| `train/build_session_dataset.py` | Feature pipeline |
| `tests/test_build_session_dataset.py` | Tests |
| `data/processed/branch3_{train,val,test}.csv` | Session feature datasets |

## Verification checklist

- [ ] `uv run pytest tests/test_build_session_dataset.py -q` green
- [ ] Output CSV có đúng 7 cột features
- [ ] Số dòng = tổng steps của tất cả sessions
- [ ] Số session train/val/test đúng ratio
- [ ] Step features giữa benign và attack có distribution khác nhau

## Next phase

→ [Phase 3: Model Training](./phase_03_model_training.md)
