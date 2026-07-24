# Plan: Test Nhánh 2 — Zero-day Detection via Leave-One-Out

## Mục tiêu
Kiểm tra Nhánh 2 có phát hiện được **zero-day SQLi** (dạng chưa từng thấy) không.

Cách làm: loại bỏ 1 label khỏi Nhánh 1, xem Nhánh 2 có bắt được label đó không.

## Kết quả (23/07/2026)

| Excluded label | B1 F1-macro | B1 miss rate | B2 DR | Combined coverage |
|---|---|---|---|---|
| union_based | 0.9803 | 2.47% | 0.53% | 2.97% |
| **error_based** | 0.9784 | 0.00% | **89.68%** | 89.68% |
| boolean_blind | 0.9973 | **90.20%** | 5.40% | 94.00% |
| time_blind | 0.9773 | 0.27% | 12.73% | 12.97% |

**Baseline:** FPR=0.50%, DR (all anomalous)=23.21%

> ⚠️ **Upload HF:** SKIPPED — token không có quyền ghi vào repo `Jason-42195/VNU-SQLi-Detection` (403 Forbidden). Cần token Write trên repo đó hoặc tạo repo riêng. Data đã có local.

### Phát hiện chính

1. **error_based → B2 bắt rất tốt (DR 89.68%)** — vượt xa baseline 23%. Error-based attacks có cấu trúc đặc trưng (nhiều ký tự đặc biệt như `'`, `(`, error functions) → OCSVM phân biệt được rõ với benign.
2. **boolean_blind → B1 fails (90.2% predict normal), B2 yếu (5.4%)** — boolean-blind queries rất giống normal traffic về mặt thống kê.
3. **union_based → B1 + B2 đều miss (combined 2.97%)** — UNION queries không có đặc điểm cấu trúc nổi bật.
4. **time_blind → B2 catch một phần (12.73%)** — nhưng vẫn thấp hơn baseline.

### Kết luận
- **Zero-day detection CÓ HIỆU QUẢ** cho error_based attacks (DR ~90%).
- **Chưa đủ** cho union_based, boolean_blind, time_blind — cần thêm features hoặc threshold tuning.
- Điểm yếu nhất: **boolean_blind** — cả 2 nhánh đều yếu, cần feature engineering riêng.

## Files đã tạo

| File | Nội dung |
|------|----------|
| `scripts/run_zeroday_experiment.py` | Script chạy toàn bộ experiment |
| `models/nhanh2_zeroday/` | OCSVM model (trained fresh cho experiment) |
| `models/nhanh1_no_{label}/` | 4 B1 models, mỗi model bỏ 1 SQLi label |
| `reports/zeroday_experiment/summary.json` | Kết quả chi tiết (JSON) |
