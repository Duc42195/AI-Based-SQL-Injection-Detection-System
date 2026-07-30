# Phase 4: Hard Evaluation

> **Master plan**: [plan.md](plan.md)
>
> **Context**: [branch3_context.md](branch3_context.md) (Section 4 — Hard Eval)
>
> **Phụ thuộc**: Phase 3 hoàn thành — GRU model đã train

**Mục tiêu**: Kiểm tra xem B3 có thực sự học sequence signal hay chỉ học
"đếm nhãn B1". Dùng ablation, zero-day test, shuffle test để xác nhận.

---

## Background

Mentor's original hard eval (`train/eval_branch3_hard.py`) dùng
`branch1_no_boolean_blind` — B1 chưa thấy boolean_blind bao giờ, miss 90.2% —
B3 vẫn đạt **98.6% recall**. Đây là proof duy nhất B3 thực sự aggregate weak
signal.

**Nếu Phase 4 pass, Phase 5 (deploy) mới có ý nghĩa.**

---

## Các thử nghiệm

### 4.1 Shuffle test

Hoán vị ngẫu nhiên step order trong mỗi session. Nếu B3 chỉ đếm label (không
học sequence), F1 sẽ **không đổi**. Nếu B3 học sequence thật, F1 sẽ **giảm**.

Criterion: F1(shuffled) < F1(original) — mức giảm càng lớn càng tốt.

- [ ] Shuffle steps trong mỗi session của test set (random seed fixed)
- [ ] Predict với model đã train
- [ ] So sánh F1-macro vs original

### 4.2 Zero-day test (B1 leave-one-out)

Dùng B1 variant chưa thấy 1 class để test B3. Nếu B3 recover được recall,
chứng tỏ B3 aggregate signal từ B2.

Cách làm: dùng lại `branch1_no_boolean_blind`, `branch1_no_time_blind`,
`branch1_no_error_based`, `branch1_no_union_based` (đã có sẵn).

- [ ] Re-score session data với `branch1_no_boolean_blind`
- [ ] Predict với B3 — check recall trên boolean_blind class
- [ ] Lặp lại với các class khác

**Benchmark**: recall > 90% trên class mà B1 miss > 90%.

### 4.3 Ablation: drop gap_seconds

Loại bỏ feature gap_seconds khỏi input. Nếu F1 không đổi → timing không phải
tín hiệu chính (tốt — model không dùng shortcut timing).

- [ ] Tạo dataset mới chỉ có 6 features (bỏ cột gap)
- [ ] Retrain hoặc zero-shot predict
- [ ] So sánh F1

### 4.4 Ablation: drop B2 score

Loại bỏ anomaly_score. Nếu F1 giảm mạnh → B2 đóng vai trò quan trọng (xác
nhận luận điểm B3 aggregate weak signal từ B2).

- [ ] Tạo dataset với 6 features (bỏ anomaly_score)
- [ ] So sánh F1

### 4.5 Diversity re-verify

Với session data đã generate, đếm distinct traces. Nếu số distinct traces thấp
(< 90% số session) → data bị memorization trap.

- [ ] Extract ground-truth (password char value) từ mỗi boolean-blind session
- [ ] Đếm distinct (target_user, target_column, target_char_index, char_value)
- [ ] Assert distinct ratio > 90%

---

## Tiêu chí pass (gating deploy)

Tất cả điều kiện sau phải đúng mới được vào Phase 5:

| Test | Pass | Fail |
|------|------|------|
| Shuffle test | F1 giảm ≥ 0.05 | F1 không đổi |
| Zero-day B1 ablation | Recall > 90% | Recall < 90% |
| Ablation drop gap | F1 giảm < 0.03 | F1 giảm ≥ 0.03 |
| Ablation drop B2 | F1 giảm ≥ 0.05 | F1 không đổi |
| Diversity | Distinct traces > 90% | Distinct traces < 90% |

---

## Các bước

### 4.1 Tạo `train/eval_branch3_hard.py`

```python
def shuffle_test(model, test_loader) -> dict:
    """Shuffle steps per session, return metrics."""
    pass

def zero_day_test(model, dataset, b1_variant_path, target_class) -> dict:
    """Re-score với B1 variant, test B3 recall."""
    pass

def ablation_test(model, dataset, drop_cols) -> dict:
    """Drop features, retrain/predict zero-shot."""
    pass

def diversity_check(dataset) -> dict:
    """Count distinct traces, return ratio."""
    pass
```

### 4.2 Chạy từng test

- [ ] Shuffle test
- [ ] Zero-day boolean_blind
- [ ] Zero-day time_blind
- [ ] Ablation drop gap
- [ ] Ablation drop B2
- [ ] Diversity re-verify

### 4.3 Ghi metrics

- [ ] `report/metrics/branch3_hard_eval.json`

### 4.4 Pytest

- [ ] `tests/test_eval_branch3_hard.py`

---

## Đầu ra

| File | Mô tả |
|------|-------|
| `train/eval_branch3_hard.py` | Eval suite |
| `tests/test_eval_branch3_hard.py` | Tests |
| `report/metrics/branch3_hard_eval.json` | Kết quả |

## Verification checklist

- [ ] Tất cả 5 tests pass theo tiêu chí ở trên
- [ ] `uv run pytest tests/test_eval_branch3_hard.py -q` green
- [ ] Kết quả ghi vào JSON, có thể đọc được

## Decision gating

```
Phase 4 pass? → YES → Phase 5 (Deploy)
              → NO  → Quay lại Phase 3 (fix model/data)
```

## Next phase

→ [Phase 5: Deployment](./phase_05_deployment.md)
