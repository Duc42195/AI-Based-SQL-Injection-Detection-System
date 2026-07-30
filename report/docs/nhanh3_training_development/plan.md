# Nhánh 3 — Master Plan

> **Từ**: [branch3_context.md](branch3_context.md) — context, lịch sử, bài toán
>
> Chiến lược: làm từng phase, mỗi phase có đầu ra rõ ràng. Hết phase thì dừng,
> review, rồi mới sang phase tiếp theo.

---

## Tổng quan các phase

| Phase | Tên | Đầu ra chính | Phụ thuộc |
|-------|-----|-------------|-----------|
| 1 | [Data Generation](./phase_01_data_generation.md) | Raw session CSV (boolean, time, benign) | `deploy/demo_db.py` |
| 2 | [Feature Engineering](./phase_02_feature_engineering.md) | Session dataset (B1+B2 scored) | B1 (`branch1_v1`), B2 (`branch2_v1`), Phase 1 |
| 3 | [Model Training](./phase_03_model_training.md) | Trained GRU ✅ + B1 candidate comparison ⏸️ | Phase 2 |
| 4 | [Hard Evaluation](./phase_04_hard_evaluation.md) | Zero-day F1, ablations, trust check ✅ | Phase 3, B1 ablation variants |
| 5 | [Deployment](./phase_05_deployment.md) | `branch3` router, API integration ⏸️ (blocked) | Phase 3, pass Phase 4 |

---

## Progress tracking

Mỗi phase sau khi hoàn thành sẽ cập nhật vào:
- [progress.md](progress.md) — tóm tắt kết quả + vấn đề
- File phase tương ứng — đánh dấu checkbox hoàn thành

## Phase 3 completion

✅ **30/07/2026**: Phase 3 complete. See [progress.md](progress.md) for details.
- GRU trained to 100% accuracy (synthetic data artifact)
- 25/25 branch3 tests passing
- B1 candidate comparison deferred (ablation: B2 alone = 1.0)
- Full ablation study + metrics + notebook generated

## Phase 4 completion

✅ **30/07/2026**: Phase 4 complete. See [progress.md](progress.md) for details.
- Shuffle test: ❌ 0 drop (GRU ignores step order)
- Zero-day boolean_blind: ❌ 0% recall (B3 fails without B1)
- Zero-day time_blind: ✅ 100% recall (B2 alone sufficient)
- Gate decision: ❌ FAIL — synthetic data artifact
- 9/9 eval tests passing

## Phase 6 — Post-mortem experiments (synthetic data artifact investigation)

> Phase 4 gate FAILED — 100% accuracy là synthetic data artifact (homogeneous sessions + B2 scores perfectly separable). Phase này thử từng hướng cải tiến để xem có fix được không.

### 6.1 Delta features — ✅ COMPLETE (30/07)

| Test | Result |
|------|--------|
| Baseline test accuracy | **0.25** (random — 4 classes) |
| Shuffle F1 drop | 0.0 |
| Zero-day boolean_blind recall | 0.0% |
| Zero-day time_blind recall | 0.0% |
| Gate | ❌ FAIL |

**Kết luận**: Delta transform xoá class-mean signal → accuracy rơi từ 1.0 → 0.25. Không có sequence signal thật. Script: `train/exp_6_1_delta_features.py`. Log: `report/metrics/experiment_6_1_delta_features.json`.

### 6.2 Drop B2 + delta features — ✅ COMPLETE (30/07)

| Test | Result |
|------|--------|
| Baseline test accuracy | **0.25** (random) |
| Shuffle F1 drop | 0.0 |
| Zero-day recall | 0.0% (cả 2 variant) |
| Gate | ❌ FAIL |

**Kết luận**: Identical với 6.1. B2 delta đã zero-information sau delta transform. Script: `train/exp_6_2_drop_b2_delta.py`. Log: `report/metrics/experiment_6_2_drop_b2_delta.json`.

### 6.3 Mixed sessions — ✅ COMPLETE (30/07)

| Test | 1:2 (ben:atk) | 1:1 | 2:1 |
|------|:---:|:---:|:---:|
| Baseline test accuracy | **1.0** | **1.0** | **1.0** |
| Shuffle F1 drop | 0.0 | 0.0 | 0.0 |
| Gate | ❌ FAIL | ❌ FAIL | ❌ FAIL |

**Kết luận**: Benign prefix không phá vỡ class-mean signal — B1 bắt time_blind SLEEP() ~100% + boolean_blind ~96%, B3 chỉ cần mean feature là classify được. Script: `train/exp_6_3_mixed_sessions.py`. Log: `report/metrics/experiment_6_3_mixed_sessions.json`.

### Tổng kết Phase 6 — root cause confirmed

Cả 3 experiment đều xác nhận: **synthetic data artifact là cố hữu, không thể fix bằng feature engineering**:

| Root cause | Evidence |
|-----------|----------|
| B1 per-query detection quá mạnh (F1=0.982) | B3 chỉ cần mean B1 probs → 1.0 acc |
| Session labelling by attack type | Model = majority-class classifier, không cần sequence |
| No step order information | Shuffle drop = 0.0 ở mọi experiment |
| delta features → 0.25 (random) | Xác nhận không có sequence signal thật |

> **Cần real mixed-session production traffic** để đánh giá B3 thực sự. Synthetic data không thể sinh được sequence signal vì B1 đã bắt quá tốt từng câu riêng lẻ.

## Nguyên tắc xuyên suốt

1. **Không Cách A / Cách B.** Chỉ theo hướng mentor: bisection thật vào
   `deploy/demo_db.py`.
2. **Verify ground-truth diversity** mỗi khi generate session. Không lặp trace.
3. **Không tin score cao trước khi ablation.** Chạy shuffle test, drop feature,
   re-verify trước khi kết luận.
4. **Mỗi phase phải chạy được độc lập** — nếu phase N fail, phase N+1 không
   phải viết lại.
5. **Config-driven.** Mọi tham số (session count, GRU hyperparams, thresholds)
   đặt trong `configs/config.yaml`.
6. **Test đi kèm.** Mỗi file source mới phải có pytest tương ứng.
