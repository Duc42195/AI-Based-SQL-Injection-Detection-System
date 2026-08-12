# Audit Day 1 — Branch 3 (Session Correlator) & Continual Learning

> Người thực hiện: Bách | Sprint 1, task #76 | `train/audit_branch3_data_validity.py`
> Mục đích: xác nhận data pipeline hợp lệ (không leakage/trùng/giả) để con số báo cáo (`report/metrics/branch3_eval.json`) đáng tin trước khi nộp/bàn giao.
> Số liệu chi tiết: `report/metrics/audit_branch3/findings.json` (chạy lại bằng `uv run python train/audit_branch3_data_validity.py`).

---

## Mảng 1 — Branch 3 train/test leakage: ❌ CÓ same-target leakage (nghiêm trọng)

File kiểm: `data/processed/branch3_sessions_cach_a.csv` (1,400 session; train 1,120 / test 280, chia theo session, seed 42).

| class | test session | share target với train | **byte-identical với train** |
|---|---:|---:|---:|
| benign | 70 | 70 | 0 |
| boolean_blind | 70 | **70** | **65** |
| time_blind | 70 | **70** | **67** |
| query_splitting | 70 | 0 | 0 |

**Chẩn đoán:** train & test dùng **chung 100-user synthetic pool** + thuật toán bisection **deterministic theo target** → cùng target sinh ra trace (chuỗi `query_canonical`) **giống hệt từng byte**. Kết quả: phần lớn session test của `boolean_blind`/`time_blind` là **bản copy** của session train.

**Ý nghĩa theo đúng kiến trúc Session Correlator:** đây là rò rỉ giữa **calibration (train) và eval (test)**. Ngưỡng được calibrate rồi eval trên **data overlap** → `DR=1.0 / FPR=0.0` trở nên **lạc quan, KHÔNG phải bằng chứng generalization**.

**Hành động đề xuất:**
1. **Re-caveat** con số trong `report/metrics/branch3_eval.json`: chỉ báo là *sanity trên chính generator*, không phải generalization.
2. **Cách B bắt buộc** (Day 2-3, task #80/#84): chạy sqlmap thật qua Docker lab, dùng để kiểm chứng ngưỡng Cách A có **transfer** sang traffic thật không. Đây là câu hỏi then chốt mà audit này phơi bày.

---

## Mảng 2 — Continual Learning stacked-class leakage: ✅ SẠCH

File: `build_new_class_pool(seed=42)` (363 template) → sample-with-replacement → 727.

| Metric | Giá trị |
|---|---:|
| Tổng template | 363 |
| golden | 73 |
| stream | 290 |
| **golden ∩ stream** | **0** |
| Stream sample tới | 727 (từ **263** distinct template, tái dùng 464 lần) |
| 727 có đụng golden không | **Không** |

**Kết luận:** golden (eval/replay) **không overlap** stream pool → không có template leakage cho lớp `stacked`. Việc 464/727 là template lặp (sample-with-replacement) chỉ làm phóng đại "apparent volume" của lớp mới, đã được ghi trong manifest — không phải leakage.

---

## Mảng 3 — Re-tagger noise rate (zero-day, leave-one-out): ✅ khớp report

Đối chiếu `report/metrics/zeroday_experiment/zeroday_report.md` với `summary.json`:

| label bị loại (zero-day) | B1 miss rate | B2 DR |
|---|---:|---:|
| union_based | 2.47% | 0.53% |
| error_based | 0.00% | 89.68% |
| boolean_blind | 90.20% | 5.40% |
| time_blind | 0.27% | 12.73% |

**Kết luận:** các con số trong report **khớp chính xác** summary.json. Điểm yếu nhất là `boolean_blind` (B1 miss 90.2%, B2 DR 5.4%) — đúng như report đã cảnh báo. Không có mâu thuẫn cần sửa.

---

## Tổng kết & re-caveat trước khi nộp

1. **Con số cần re-caveat:** `branch3_eval.json` (Cách A) — DR=1.0 bị thổi phồng do same-target leakage (Mảng 1). Không báo là generalization.
2. **Con số sạch:** Mảng 2 (stacked CL) và Mảng 3 (zero-day) đều hợp lệ.
3. **Hướng giải quyết:** Cách B (sqlmap thật) là kiểm chứng bắt buộc để biến kết quả Branch 3 thành con số có nghĩa.

**Deliverable Day 1:** báo cáo này + `findings.json`. Chưa cần sửa model; chỉ re-caveat số liệu hiện có.
