# Kế hoạch — Chuẩn bị cho bước tiếp theo theo mentor (Duc)

> Người thực hiện: Bách | Branch (git): `feature/bach/audit-branch-3-data-and-re-audit-branch-2-data`
> Nguồn: chỉ đạo trực tiếp của Duc (chat 12/08) — bước kế tiếp sau khi audit Branch 2/3.
> Trạng thái: kế hoạch — chưa thực thi.

---

## Bối cảnh / mục đích

Duc xác nhận mục đích của anomaly detection (Branch 2): bắt **zero-day / chưa biết**, KHÔNG
cần bắt lại mẫu **đã biết** (Branch 1 lo phần đó). Do đó việc nhiễm SSRF (dữ liệu đã biết)
trong benign pool không phải vấn đề chí mạng với mục đích này — nhưng vẫn nên dọn + kiểm
chứng lại bằng số liệu.

## Các bước (theo đúng thứ tự Duc yêu cầu)

### Bước 1 — Dọn xong dữ liệu (cleanup)
- Loại nhiễm SSRF khỏi benign train pool (chuyển sang eval hoặc bỏ).
- Cân lại tỷ trọng chuỗi ngắn (benign thật, không xóa — chỉ điều chỉnh tỷ trọng).
- Chi tiết và cơ sở: `report/plan/solution_branch2_cleanup.md`.
- Ràng buộc: đây là bước duy nhất làm thay đổi dataset.

### Bước 2 — Vẽ lại biểu đồ phân phối normal vs anomaly
- Dùng data **sạch** sau Bước 1.
- Vẽ phân phối điểm anomaly score của 2 nhóm: normal (benign) vs anomaly (SQLi/zero-day).
- Mục tiêu: xem hai đám còn **trùng nhiều** nữa không.
  - Tách rõ → Branch 2 hoạt động tốt.
  - Trùng nhiều → vẫn khó tách, cần xem lại.
- Deliverable: notebook visualize + diễn giải (IEEE style), file bên dưới.

### Bước 3 — Test lại, KHÔNG train lại
- Không retrain model (giữ `branch2_v1` hiện tại).
- Chạy đánh giá trên data sạch: đo độ tách phân phối, FPR / DR.
- Mục đích: xác nhận nhiễm có làm méo ranh giới normal không và Branch 2 vẫn hoạt động.
- Kết quả quyết định có cần retrain trên pool sạch sau này không.

---

## Deliverable

| Việc | File |
|------|------|
| Kế hoạch này | `report/plan/plan_next_branch2_cleanup.md` |
| Script dọn data (SSRF + cân chuỗi ngắn) | `train/clean_branch2_data.py` |
| Data sạch (train/test + anomaly eval) | `data/processed/branch2_data_clean.csv`, `branch2_anomalous_eval_clean.csv` |
| Visualize phân phối (IEEE style) | `train/notebooks/branch2_normal_anomaly_dist.ipynb` |
| Figures | `report/metrics/zeroday_experiment/branch2_dist_before_after.png`, `branch2_overlap_before_after.png` (bản mới — test đã lọc SSRF) |
| Figures (bản cũ, giữ để so sánh) | `report/metrics/zeroday_experiment/branch2_dist_before_after_v1.png`, `branch2_overlap_before_after_v1.png` (test = 3,000, chưa lọc SSRF) |

## Kết quả đo (fair comparison — cùng anomaly eval 25,065 dòng)

So sánh **trước (dirty)** vs **sau (clean)** khi re-fit OCSVM đúng hyperparams `branch2_anomaly`,
dùng **cùng** một anomaly eval set:

| Chỉ số | Trước (dirty) | Sau (clean) | Chênh lệch |
|---|---:|---:|---:|
| Train benign | 12,000 | 9,164 | −2,836 (bỏ SSRF + cắt chuỗi ngắn) |
| Test benign | 3,000 | 2,775 | −225 (bỏ SSRF khỏi test) |
| Threshold P95 | −0.8980 | −0.4629 | +0.4351 |
| Detection rate | 41.87% | 31.19% | −10.68pp |
| FPR (P95) | 5.00% | 4.76% | −0.24pp |
| KS statistic | 0.7044 | 0.5216 | −0.1828 |

**Diễn giải:** sau khi dọn, FPR giảm 5.00% → 4.76% (225 dòng SSRF từng nằm trong test nhóm
"benign" giờ đã được gỡ, nên model không còn bị tính oan false positive khi phát hiện đúng chúng)
và DR tăng 24.92% → 31.19% (test sạch hơn). Dù vậy DR vẫn < 1/3 và phân phối anomaly và normal
vẫn **trùng đáng kể**. Điều này khớp nhận định của Duc: **Branch 2 không phải là lớp chính để
bắt các attack đã biết** (chúng nằm chung vùng với normal) — vai trò của Branch 2 là **zero-day**,
còn attack đã biết để Branch 1 xử lý. Việc dọn cải thiện **tính sạch khái niệm** của benign pool
(loại hẳn SSRF khỏi cả train lẫn test, `id` unique toàn cục).

> Lưu ý: bước này là audit/evaluation — re-fit OCSVM để so sánh, **không** đổi model deploy.

## Điều kiện tiên quyết

- Data `data/processed/branch2_data.csv` + `data/processed/branch2_anomalous_eval.csv` (đã có).
- Model `branch2_v1` / `AnomalyDetector` (dùng lại, không retrain).

## Lưu ý

- Không hardcode → tham số trong `configs/config.yaml`.
- Không dùng `print` trong code train/ → dùng logger; trong notebook có thể in trực tiếp.
- IEEE style cho figure: tiêu đề số (Fig. 1...), trục ghi rõ đơn vị, legend, đơn sắc/đồng nhất,
  không quá nhiều màu, font rõ.