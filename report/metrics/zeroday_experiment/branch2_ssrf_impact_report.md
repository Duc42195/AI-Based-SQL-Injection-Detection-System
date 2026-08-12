# Branch 2 — SSRF/OS-cmd rows trong benign pool: Ảnh hưởng audit

> Người thực hiện: Bách | `train/audit_branch2_ssrf_impact.py`
> Số liệu chi tiết: `report/metrics/zeroday_experiment/branch2_ssrf_impact.json` (chạy lại bằng `uv run python train/audit_branch2_ssrf_impact.py`).
> Bối cảnh: phát hiện trong quá trình audit — benign pool Branch 2 có lẫn các dòng call-back/SSRF/OS-cmd. Đây là mảng đánh giá **chất lượng dữ liệu** của Branch 2 (nhánh anomaly/zero-day), tách riêng khỏi report audit Branch 3.

---

## Vấn đề được phơi bày

Benign pool Branch 2 (12,000 dòng train) chứa **928 dòng (7.73%)** có query chứa call-back/SSRF/OS-cmd (`owasp.org`, `/etc/passwd`, `shellshock`). Các dòng này không thuộc phạm vi anchor filter của dataset — filter nhắm **SQLi + OS-cmd/SSI**, **không** SSRF → "100% benign" của Branch 2 trên thực tế không sạch tuyệt đối.

## Model hiện tại (OCSVM v1) xử lý 928 dòng đó thế nào

- Chỉ **0.54%** bị cờ anomalous → hầu hết nằm **bên trong** phân phối normal (score trung bình −1.15, gần vùng benign).
- Giải thích: Branch 2 chỉ nhìn 4 đặc trưng cấu trúc (`length, special_char_ratio, sql_keyword_count, entropy`), **không nhìn nội dung URL** → các call-back SSRF không phải outlier trong không gian feature này.

## Thử nghiệm "nếu bỏ 928 dòng ra khỏi pool"

| Chỉ số | Có SSRF | Bỏ SSRF | Δ |
|---|---:|---:|---:|
| FPR benign | 0.0030 | 0.0037 | +0.0007 (không đáng kể) |
| Detection rate | 0.2073 | 0.2308 | **+2.35pp** |
| p90 score benign | −1.304 | −0.999 | +0.305 |

## Kết luận / đề xuất cho Duc

- **FPR gần như không đổi** → sự ô nhiễm này **không phá** Branch 2, **không cần retrain** `branch2_v1` chỉ vì lý do SSRF.
- Điểm tích cực duy nhất khi dọn: **detection rate cải thiện +2.35pp** (0.207 → 0.231). Nếu muốn con số DR đẹp cho paper, lọc SSRF khỏi benign pool (thêm `owasp\.org` vào `matches_any_attack_signature()`) rồi retrain là hợp lý — vừa đúng nguyên tắc (benign pool phải sạch) vừa nâng DR.
- Đây là ghi chú chất lượng dữ liệu, **không phải lỗi cần sửa gấp**.
