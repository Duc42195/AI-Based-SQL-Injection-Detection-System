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
| 3 | [Model Training](./phase_03_model_training.md) | Trained GRU `branch3_v2/` | Phase 2 |
| 4 | [Hard Evaluation](./phase_04_hard_evaluation.md) | Zero-day F1, ablations, trust check | Phase 3, B1 ablation variants |
| 5 | [Deployment](./phase_05_deployment.md) | `branch3` router, API integration | Phase 3, pass Phase 4 |

---

## Progress tracking

Mỗi phase sau khi hoàn thành sẽ cập nhật vào:
- [progress.md](progress.md) — tóm tắt kết quả + vấn đề
- File phase tương ứng — đánh dấu checkbox hoàn thành

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
