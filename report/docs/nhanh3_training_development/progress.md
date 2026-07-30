# Nhánh 3 — Progress & Results

> File này ghi lại tiến trình từng phase: đã làm gì, kết quả ra sao, có vấn đề
> gì cần lưu ý. Mỗi phase hoàn thành sẽ được append vào đây.

---

## Phase 1: Data Generation

**Trạng thái**: ✅ Hoàn thành (30/07/2026)

| Task | Status | Ghi chú |
|------|--------|---------|
| `attack_simulator.py` | ✅ | 382 lines, 4 attacker classes + benign gen + diversity + LABEL_MAP |
| Tests | ✅ | 25 tests (thêm 8 cho _split_payload + QuerySplittingAttacker) |
| Raw data CSV | ✅ | 8 files (4 class × 2 splits), ~50k rows, ~5.7MB |
| Diversity verify | ✅ | boolean_blind 96%, time_blind 96%, query_splitting 99% |
| `session_label` column | ✅ | Mapping: benign=0, boolean_blind=1, time_blind=2, query_splitting=3 |
| Query splitting | ✅ | 12 injection payloads, split 3-8 fragments/session |

**Kết quả**:

```
Class           Label  Train sessions  Test sessions  Train rows  Test rows
benign          0      200             200             2033         2013
boolean_blind   1      200             200            11200        11200
time_blind      2      200             200            10663        10687
query_splitting 3      200             200             1137         1129
Total           —      800             800           ~25k         ~25k

Diversity:
  boolean_blind:   384 distinct / 400 = 0.96
  time_blind:      384 distinct / 400 = 0.96
  query_splitting: 359 distinct / 363 = 0.99
```

**CSV structure**: 8 files, 1 per class per split:
```
data/raw/branch3_sessions/
├── boolean_blind_train.csv   (200 sessions, ~11k rows)
├── boolean_blind_test.csv    (200 sessions, ~11k rows)
├── time_blind_train.csv      (200 sessions, ~10.7k rows)
├── time_blind_test.csv       (200 sessions, ~10.7k rows)
├── query_splitting_train.csv (200 sessions, ~1.1k rows)
├── query_splitting_test.csv  (200 sessions, ~1.1k rows)
├── benign_train.csv          (200 sessions, ~2k rows)
└── benign_test.csv           (200 sessions, ~2k rows)
```
Schema: `session_id, step_idx, session_label, class, query, row_count, timing_seconds`

**Vấn đề**:
1. **Time payload SLEEP × 5000 rows**: ban đầu `SLEEP(0.05)` được gọi 5000 lần (mỗi row), mất ~250s/query. Đã fix: dùng scalar subquery → SLEEP gọi 1 lần.
2. **`_extract_ground_truth` không nhận time_blind**: query format khác (dùng subquery). Đã fix.
3. **Windows timer resolution ~15ms**: `time.sleep()` không chính xác dưới 15ms. `sleep_seconds=0.05` tạo variance ít. Nếu cần production eval, tăng lên 5.0s.
4. **Query_splitting rows ít hơn**: vì mỗi session chỉ có 3-8 fragments (không phải 56 steps như blind). Điều này đúng với bản chất của query_splitting.

---

## Phase 2: Feature Engineering

**Trạng thái**: ✅ Hoàn thành (30/07/2026)

### Chi tiết
Mỗi session step → 7-dim feature vector:
- **dim 0-4**: B1 probabilities (normal, union_based, error_based, boolean_blind, time_blind) — `predict_proba` từ `branch1_v1`
- **dim 5**: B2 anomaly score — `score()` từ `branch2_v1` (OCSVM)
- **dim 6**: `log1p(timing_seconds)` — thời gian thực thi query

| Task | Status | Ghi chú |
|------|--------|---------|
| `build_session_dataset.py` | ✅ | 150 lines, xử lý 4000 sessions |
| Feature `.npy` files | ✅ | train+test, (2000, 64, 7) mỗi split |
| Metadata | ✅ | `data/processed/branch3_session_features/metadata.json` |
| NaN/Inf check | ✅ | 0 NaN, 0 Inf |

### Output shape
| Split | Features | Labels | Sessions/class |
|-------|----------|--------|----------------|
| Train | (2000, 64, 7) | (2000,) | 500 × 4 classes |
| Test | (2000, 64, 7) | (2000,) | 500 × 4 classes |

### Feature statistics (non-padded, train split)
| dim | Component | Mean | Std | [Min, Max] |
|-----|-----------|------|-----|-----------|
| 0 | normal prob | 0.175 | 0.308 | [0.001, 0.969] |
| 1 | union_based prob | 0.030 | 0.022 | [0.003, 0.546] |
| 2 | error_based prob | 0.008 | 0.002 | [0.002, 0.019] |
| 3 | boolean_blind prob | 0.412 | 0.371 | [0.006, 0.893] |
| 4 | time_blind prob | 0.375 | 0.412 | [0.008, 0.963] |
| 5 | B2 anomaly score | -1.285 | 2.990 | [-4.798, 2.428] |
| 6 | gap_log1p | 0.029 | 0.019 | [0.015, 0.090] |

### Lưu ý
- B1 classes: 5 (stacked=5 đã bị loại khỏi model từ trước)
- B2 anomaly score âm = normal, dương = anomalous (OCSVM convention)
- Session < 64 steps → pre-padded với 0; session ≥ 64 → truncate lấy 64 steps cuối
- Dữ liệu đã shuffle ngẫu nhiên (seed=42) để tránh class ordering bias
- Model mentor (`branch3_v1/model.pt`) có architecture giống hệt: input_dim=7, hidden_dim=32, num_classes=4

---

## Phase 3: Model Training

**Trạng thái**: ✅ Hoàn thành (30/07/2026)

### Deliverables

| File | Mô tả |
|------|-------|
| `src/models/branch3_session.py` | GRU model class (241 lines, 4068 params) |
| `train/train_branch3.py` | Training script (133 lines) |
| `tests/test_branch3_session.py` | 14 unit tests ✅ |
| `tests/test_branch3_candidates.py` | 11 integration tests ✅ |
| `models/branch3_v2/model.pt` | Trained weights (4068 params) |
| `models/branch3_v2/metadata.json` | Model metadata |
| `report/metrics/branch3_train.json` | Training history (30 epochs) |
| `report/metrics/branch3_confusion.json` | Confusion matrix + F1 scores |
| `report/metrics/branch3_ablation.json` | Ablation study results |
| `report/metrics/figures/branch3_metrics_summary.png` | 4-panel metrics figure |
| `train/notebooks/branch3_training_results.ipynb` | Executed results notebook |

### Results

| Metric | Value |
|--------|-------|
| Test Accuracy | **1.0000** |
| F1-macro | **1.0000** |
| Test Loss | 0.000358 |
| Parameters | 4,068 |
| Train Samples | 1,700 |
| Val Samples | 300 |
| Test Samples | 2,000 |
| Convergence | < 10 epochs |

### Ablation Study

| Variant | Test Acc | Parameters | Note |
|---------|----------|------------|------|
| Full (7-dim) | **1.0000** | 4068 | Baseline |
| Drop B2 (no anomaly) | 1.0000 | 2980 | B2 not needed |
| Drop Gap (no timing) | 1.0000 | 4068 | Timing not needed |
| Only B1 (5-dim) | **1.0000** | 3044 | B1 alone sufficient |
| Only B2 (1-dim) | **1.0000** | 3652 | B2 alone sufficient |
| Only Gap (1-dim) | 0.8590 | 4068 | Timing insufficient alone |
| B2 + Gap (2-dim) | 1.0000 | 3652 | Combines two 1-dim sources |
| Shuffled (control) | 0.2630 | 4068 | Random baseline=0.25 |

### Key Findings

1. **100% accuracy is a synthetic data artifact** — every session is homogeneous (same attack type throughout), making classification trivial
2. **B2 (anomaly, 1 dim) alone = 1.0** — anomaly score distributions per class are perfectly separable (benign=-1.41, boolean=-2.90, time=+1.99, query_splitting=-0.39)
3. **GRU does NOT use sequence order** — shuffle test: accuracy unchanged (1.0 → 1.0); MLP flat model on B2 alone achieves same result
4. **B1 candidate comparison deferred (step 3.1)** — ablation proves B2 alone = 1.0, so B1 backbone choice is irrelevant on synthetic data
5. **Phase 4 needed for real evaluation** — synthetic data overestimates performance; need real production data with mixed sessions

### Issues

- B1 candidate comparison (3.1) deferred — không còn meaningful trên synthetic data
- 25/25 branch3 tests passed (168/172 full suite; 4 FastAPI/Streamlit errors pre-existing)
- `report/metrics/metrics/` stale dir cleaned (old double-path bug)
- matplotlib added to dev dependencies

---

## Phase 4: Hard Evaluation

**Trạng thái**: ✅ Hoàn thành (30/07/2026)

### Deliverables

| File | Mô tả |
|------|-------|
| `train/eval_branch3_hard.py` | Eval suite (shuffle, zero-day, ablation, diversity) |
| `tests/test_eval_branch3_hard.py` | 9 unit tests ✅ |
| `report/metrics/branch3_hard_eval.json` | Results |

### Tests & Results

| # | Test | Pass | Details |
|---|------|------|---------|
| 4.1 | Shuffle test | ❌ FAIL | orig_acc=shuf_acc=0.5 (0 drop) — GRU ignores step order |
| 4.2 | Zero-day: no_boolean_blind | ❌ FAIL | target_recall=0.0 — B3 fails without B1's boolean_blind signal |
| 4.2 | Zero-day: no_time_blind | ✅ PASS | target_recall=1.0 — B2 anomaly score catches time_blind alone |
| 4.3 | Ablation drop gap | ✅ PASS | Only Gap = 0.859 < 0.99 (timing insufficient alone) |
| 4.3 | Ablation drop B2 | ✅ PASS | Drop B2 = 1.0 ≥ 0.99 (B2 not needed on synthetic data) |
| 4.4 | Diversity | ✅ PASS | 100% distinct sessions |

**Gate**: ❌ FAIL → quay lại Phase 3 fix

### Key Findings

1. **GRU hoàn toàn không dùng step order** — shuffle test: 0 drop (acc giữ nguyên 0.5). Model là MLP trên average features.
2. **Zero-day boolean_blind thất bại hoàn toàn (0% recall)**: Khi B1 không có boolean_blind class, B3 mất khả năng detect boolean_blind. B2 anomaly score không đủ vì boolean_blind trông giống benign (B2: -2.9 vs -1.41).
3. **Zero-day time_blind vẫn 100%**: time_blind có B2 score rất bất thường (+1.99), trong khi boolean_blind (-2.9) gần với benign (-1.41). B2 feature là đủ cho time_blind.
4. **Không reproduce được kết quả mentor (98.6%)** — có thể do model retrain (branch3_v2 khác branch3_v1) hoặc do pipeline khác.
5. **B3 chỉ mạnh khi kết hợp B1 + B2** — khi một trong hai thiếu, recall giảm mạnh.

### Issues

- Shuffle test 0 drop → xác nhận sequence signal không tồn tại trong synthetic data
- Gate không pass → cần real mixed-session data để test B3 thực sự
- 9/9 tests passed

---

## Phase 5: Deployment

**Trạng thái**: ⏳ Chưa bắt đầu
