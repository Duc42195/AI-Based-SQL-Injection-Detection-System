# Nhánh 3 — Progress & Results

> File này ghi lại tiến trình từng phase: đã làm gì, kết quả ra sao, có vấn đề
> gì cần lưu ý. Mỗi phase hoàn thành sẽ được append vào đây.

---

## Phase 1: Data Generation

**Trạng thái**: ✅ Hoàn thành (30/07/2026)

| Task | Status | Ghi chú |
|------|--------|---------|
| `attack_simulator.py` | ✅ | 371 lines, 3 attacker classes + benign gen + diversity check |
| Tests | ✅ | 17/17 passed |
| Raw data CSV | ✅ | 6 files, ~47k rows, ~4.6MB |
| Diversity verify | ✅ | boolean_blind: 96%, time_blind: N/A (fixed post-gen) |

**Kết quả**:

```
Class           Train sessions  Test sessions  Train rows  Test rows
boolean_blind:  200             200            11200        11200
time_blind:     200             200            10663        10687
benign:         200             200             2061         2035
Total:          600             600            ~23.9k      ~23.9k
boolean_blind diversity: 384 distinct / 400 total = 0.96
time_blind diversity:    396 distinct / 400 total = 0.99 (verified post-hoc với _extract_ground_truth đã fix)
```

**Vấn đề**:
1. **Time payload SLEEP x 5000 rows**: ban đầu `SLEEP(0.05)` được gọi 5000 lần (mỗi row), mất ~250s/query. Đã fix: dùng scalar subquery `(SELECT password FROM users WHERE username = 'target')` → SLEEP gọi 1 lần.
2. **`_extract_ground_truth` không nhận time_blind**: query format khác (dùng subquery). Đã fix với `or "ASCII(SUBSTR((SELECT password" in q`.
3. **Diversity lúc gen = 0%**: do `_extract_ground_truth` chưa update. Verify post-hoc với fix: time_blind train = 98.5%, test = 99.5% ✅
4. **Windows timer resolution ~15ms**: `time.sleep()` không chính xác dưới 15ms. `sleep_seconds=0.05` tạo variance ít (50ms vs 15ms baseline). Không ảnh hưởng data gen vì oracle dùng timing threshold 0.025s. Nếu cần production eval, tăng lên 5.0s.

---

## Phase 2: Feature Engineering

**Trạng thái**: ⏳ Chưa bắt đầu

| Task | Status | Ghi chú |
|------|--------|---------|
| `build_session_dataset.py` | ⏳ | — |
| Tests | ⏳ | — |
| Feature CSV | ⏳ | — |
| Train/val/test split | ⏳ | — |

---

## Phase 3: Model Training

**Trạng thái**: ⏳ Chưa bắt đầu

---

## Phase 4: Hard Evaluation

**Trạng thái**: ⏳ Chưa bắt đầu

---

## Phase 5: Deployment

**Trạng thái**: ⏳ Chưa bắt đầu
