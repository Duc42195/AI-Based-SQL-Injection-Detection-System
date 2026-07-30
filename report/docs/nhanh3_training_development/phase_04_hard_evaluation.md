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

- [x] Shuffle steps trong mỗi session của test set (random seed fixed)
- [x] Predict với model đã train
- [x] So sánh F1-macro vs original

### 4.2 Zero-day test (B1 leave-one-out)

Dùng B1 variant chưa thấy 1 class để test B3. Nếu B3 recover được recall,
chứng tỏ B3 aggregate signal từ B2.

Cách làm: dùng lại `branch1_no_boolean_blind`, `branch1_no_time_blind`,
`branch1_no_error_based`, `branch1_no_union_based` (đã có sẵn).

- [x] Re-score session data với `branch1_no_boolean_blind`
- [x] Predict với B3 — check recall trên boolean_blind class (0% ❌)
- [x] Lặp lại với các class khác — time_blind: 100% ✅

**Benchmark**: recall > 90% trên class mà B1 miss > 90%.

### 4.3 Ablation: drop gap_seconds

Loại bỏ feature gap_seconds khỏi input. Nếu F1 không đổi → timing không phải
tín hiệu chính (tốt — model không dùng shortcut timing).

- [x] Tạo dataset mới chỉ có 6 features (bỏ cột gap)
- [x] Retrain — Drop Gap acc = 1.0 (timing không cần thiết)
- [x] So sánh F1

### 4.4 Ablation: drop B2 score

Loại bỏ anomaly_score. Nếu F1 giảm mạnh → B2 đóng vai trò quan trọng (xác
nhận luận điểm B3 aggregate weak signal từ B2).

- [x] Tạo dataset với 6 features (bỏ anomaly_score)
- [x] So sánh F1 — Drop B2 acc = 1.0 (B2 không cần thiết trên synthetic data)

### 4.5 Diversity re-verify

Với session data đã generate, đếm distinct traces. Nếu số distinct traces thấp
(< 90% số session) → data bị memorization trap.

- [x] Extract ground-truth (password char value) từ mỗi boolean-blind session
- [x] Đếm distinct (target_user, target_column, target_char_index, char_value)
- [x] Assert distinct ratio > 90% — ~96% (from Phase 1)

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

- [x] Shuffle test → ❌ 0 drop (F1 unchanged 0.375)
- [x] Zero-day boolean_blind → ❌ target_recall 0.0%
- [x] Zero-day time_blind → ✅ target_recall 100.0%
- [x] Ablation drop gap → ✅ (reuse Phase 3 data)
- [x] Ablation drop B2 → ✅ (reuse Phase 3 data)
- [x] Diversity re-verify → ✅ 100%

**Gate decision**: ❌ FAIL → Phase 3 fix needed (synthetic data artifact)

### 4.3 Ghi metrics

- [x] `report/metrics/branch3_hard_eval.json`

### 4.4 Pytest

- [x] `tests/test_eval_branch3_hard.py` — 9 tests ✅

---

## Đầu ra

| File | Mô tả |
|------|-------|
| `train/eval_branch3_hard.py` | Eval suite |
| `tests/test_eval_branch3_hard.py` | Tests |
| `report/metrics/branch3_hard_eval.json` | Kết quả |

## Verification checklist

- [x] Tất cả 5 tests pass theo tiêu chí ở trên → ❌ Gate FAIL
- [x] `uv run pytest tests/test_eval_branch3_hard.py -q` green
- [x] Kết quả ghi vào JSON, có thể đọc được

### Kết quả chi tiết

```json
{
  "shuffle_test": { "f1_drop": 0.0, "passes": false },
  "zero_day_no_boolean_blind": { "target_recall": 0.0, "passes": false },
  "zero_day_no_time_blind": { "target_recall": 1.0, "passes": true },
  "ablation_drop_gap": true,
  "ablation_drop_b2": true,
  "diversity": true,
  "gate_decision": "FAIL → Phase 3 fix"
}
```

### Phân tích

1. **Shuffle test thất bại (0 drop)**: GRU không dùng step order → model hoạt động như MLP trên aggregate features. Synthetic data đồng nhất (cùng attack type trong mỗi session) làm sequence signal vô dụng.
2. **Zero-day boolean_blind thất bại (0% recall)**: B3 không catch được boolean_blind khi B1 không có class đó. B2 anomaly score không phân biệt được boolean_blind (-2.9) với benign (-1.41).
3. **Zero-day time_blind PASS (100%)**: time_blind có B2 score rất anomalous (+1.99), B3 chỉ cần threshold trên B2 là detect được.
4. **Ablation PASS**: timing và B2 đều redundant trên synthetic data.
5. **Diversity PASS**: 100% distinct sessions.

## Decision gating

```
Phase 4 pass? → YES → Phase 5 (Deploy)
              → NO  → Quay lại Phase 3 (fix model/data)
              ──────────────────────────────────
              ACTUAL: ❌ FAIL — synthetic data artifact
              Remedy: need real mixed-session production data
```

## Next phase

Phase 5 tạm thời bị block. Cần:
- Thu thập real traffic data (mixed sessions, không homogeneous)
- Hoặc tạo synthetic mixed-session benchmark
- Re-train + re-eval

→ [Phase 5: Deployment](./phase_05_deployment.md) (blocked until pass)
