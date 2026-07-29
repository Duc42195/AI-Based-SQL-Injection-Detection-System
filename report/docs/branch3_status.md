# Branch 3 — Implementation Status & Remaining Work

> **Author:** Bách (Nhánh 2 + 3)
> **Date:** 29/07/2026
> **Context:** Sau khi hoàn thành pipeline end-to-end (dataset → train → hard-mode eval → ablation), đánh giá các bước còn lại so với kế hoạch.

## 1. Tổng quan

| Mục | Trạng thái | Chi tiết |
|-----|-----------|---------|
| Dataset Cách A (bisection simulation) | ✅ Hoàn thành | 1.400 sessions, 25.166 steps, synthetic pool 100 users |
| Train GRU | ✅ Hoàn thành | hidden=32, 30 epochs, loss 0.97→0.0012 |
| Standard eval | ✅ Hoàn thành | F1=1.0, FPR=0.0, DR=1.0 cả 3 attack types |
| Hard-mode eval (zero-day B1) | ✅ Hoàn thành | B1 miss 90.2%, B3 DR boolean_blind = 100% |
| Ablation experiments (7 configs) | ✅ Hoàn thành | F1=1.0 trên 6/7 config — dataset synthetic quá "dễ" |
| Ablation insight | ✅ Phát hiện quan trọng | Chỉ **gap time một mình** là không đủ (F1=0.667). Mọi feature subset khác đều F1=1.0 → dataset không đủ thử thách |
| Notebook report | ✅ Hoàn thành | `train/notebooks/branch3_eval.ipynb` |

## 2. Các bước còn lại — Phân tích khả thi

### 2.1. Deploy API — load model thật vào router

| Tiêu chí | Đánh giá |
|----------|---------|
| Khả thi | ✅ **Có thể làm ngay** (~30 phút) |
| Phụ thuộc | Không — model đã trained, registry pattern đã có sẵn cho Branch 1+2 |
| Cách làm | Thêm `Branch3Model` class vào `deploy/registry.py`, thêm method `branch3()`, update router để load model thật |
| Rủi ro | Thấp — model test đã pass, inference path đơn giản |

### 2.2. Cách B — sqlmap + Docker lab

| Tiêu chí | Đánh giá |
|----------|---------|
| Khả thi | ❌ **Không thể làm ngay** |
| Lý do | Cần Docker (chưa có), cần sqlmap container, cần vulnerable web app (+ Dockerfile). Đây là infrastructure task, không phải code task. |
| Phụ thuộc | Docker engine, sqlmap image, vulnerable web app image, network config |
| Thời gian ước tính | 2-3 ngày (nếu có Docker sẵn) |
| Giải pháp thay thế | Cách A đã đủ cho proof-of-concept. Cách B là production hardening. |

### 2.3. Threshold calibration

| Tiêu chí | Đánh giá |
|----------|---------|
| Khả thi | ⚠️ **Khả thi nhưng chưa meaningful** |
| Lý do | Với synthetic dataset FPR=0.0, threshold calibration chỉ có ý nghĩa khi có real traffic. Calibrating trên synthetic data sẽ cho threshold quá lỏng (overfit vào pattern đều). |
| Nên làm khi | Có Cách B dataset hoặc real traffic logs |

### 2.4. Real traffic test

| Tiêu chí | Đánh giá |
|----------|---------|
| Khả thi | ❌ **Không thể làm ngay** |
| Lý do | Cần production deployment hoặc staging environment với real user traffic. Đây là deployment step cuối cùng. |
| Phụ thuộc | Deploy API (2.1), CI/CD pipeline, monitoring stack |

## 3. Ablation Results — Chi tiết

Kết quả ablation (retrain GRU trên 7 feature configs):

```
Config                         F1-macro   FPR      DR_bb    DR_tb    DR_qs
full (7 features)              1.0000     0.0000   1.0000   1.0000   1.0000
drop B1 probs (only B2+gap)    1.0000     0.0000   1.0000   1.0000   1.0000
drop B2 score (only B1+gap)    1.0000     0.0000   1.0000   1.0000   1.0000
drop gap (only B1+B2)          1.0000     0.0000   1.0000   1.0000   1.0000
only B1 probs                  1.0000     0.0000   1.0000   1.0000   1.0000
only B2 score                  1.0000     0.0000   1.0000   1.0000   1.0000
only gap time                  0.6674     0.0286   1.0000   0.0143   1.0000
```

**Kết luận ablation:**
- Dataset synthetic Cách A không đủ thử thách — mọi feature subset (trừ gap đơn độc) đều cho F1 hoàn hảo
- GRU không thực sự cần B1 probs, B2 score, hay gap time riêng lẻ — redundant features
- Time-blind pattern không thể phân biệt bằng gap time đơn độc (DR=0.0143) vì CPU scheduling variance
- **Hard-mode eval vẫn là bằng chứng value-add thuyết phục nhất** (zero-day B1 miss 90.2%, B3 DR 100%)

## 4. Shuffle Test — GRU không học Sequence Pattern

Ngày 29/07, chạy shuffle test để kiểm tra GRU có thực sự học sequence dynamics:

| Experiment | F1 | Acc | Ý nghĩa |
|-----------|-----|-----|---------|
| GRU original order | 1.0000 | 1.0000 | Baseline |
| GRU shuffled order | 1.0000 | 1.0000 | Shuffle KHÔNG ảnh hưởng |
| GRU train orig, test shuffled | 1.0000 | 1.0000 | Model không dùng step order |
| RF step-average (7 feats) | 0.9965 | 0.9967 | Step-average ≈ GRU |

**Kết luận:** GRU không học sequence pattern. Model chỉ học per-step feature distributions. RF trên session averages cho kết quả tương đương.

**Hệ quả cho paper:**
- Không claim "sequence learning" — thay bằng "session-level hybrid feature fusion"
- GRU là overkill — RF/XGBoost trên 7 averaged features cho performance tương đương
- Giá trị thật của Branch 3 là kết hợp 3 nguồn tín hiệu: B1 probs + B2 anomaly + gap timing

## 5. Kế hoạch đề xuất

### Prioritization

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| P0 | Shuffle test → paper reframing | Immediate | Cao — ảnh hưởng claims trong paper |
| P1 | Deploy API (load model) | 30 phút | Cao — unblock frontend integration |
| P2 | Cách B dataset | 2-3 ngày | Cao — real traffic validation |
| P3 | Threshold calibration | 1 ngày | Trung bình — cần Cách B trước |
| P4 | Real traffic test | 2-3 ngày | Thấp — phụ thuộc production |

### Deploy API status (29/07 PM)
✅ **Done.** `Branch3Model` + `Branch3Prediction` added to `deploy/registry.py`, router updated in `deploy/routers/branch3.py`. Model loads from `models/branch3_v1/`, runs inference by chaining B1 + B2 per step, returns `status:"ready"` with `session_label` / `is_attack`. 112/112 tests green.

Next step: frontend (Minh) now calls `/api/v1/branch3/session` instead of getting `not_ready`.

## 5. File tham khảo

| File | Vai trò |
|------|---------|
| `report/metrics/branch3_eval.json` | Standard eval results |
| `report/metrics/branch3_eval_hard.json` | Hard-mode eval results |
| `report/metrics/branch3_ablation.json` | Ablation experiment results |
| `train/notebooks/branch3_eval.ipynb` | Visualization notebook (IEEE style) |
| `train/notebooks/branch3_shuffle_test.ipynb` | Shuffle test notebook |
| `train/run_ablation_branch3.py` | Ablation experiment script |
| `report/plan/nhanh3_plan.md` | Original plan |
| `report/metrics/branch3_final_report.json` | Final report v6 (includes shuffle test) |
