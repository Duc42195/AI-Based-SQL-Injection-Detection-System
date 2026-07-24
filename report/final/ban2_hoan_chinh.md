# Báo cáo — Hệ thống phát hiện SQL Injection dựa trên AI

## (Bản 2 — Tầm nhìn hoàn chỉnh: 3 nhánh + hệ thống đầy đủ)

> Bản đầy đủ theo thiết kế gốc của đề tài. **Nhánh 1 + Nhánh 2 đã có kết quả thực nghiệm thật**
> (giống Bản 1); **Nhánh 3 + hệ thống tích hợp (API/Bộ xử lý trung tâm/Continual Learning/
> Concept Drift) là thiết kế/Future Work**, chưa có thực nghiệm tại thời điểm nộp 25/7 — xem
> `De_xuat_SQLi_Detection_AI.md` Mục 13 để biết danh sách đầy đủ.

---

## 1. Đặt vấn đề và Mục tiêu

*(TODO — giữ nguyên Mục 1 `De_xuat_SQLi_Detection_AI.md`, đầy đủ 3 nhánh)*

## 2. Công trình liên quan

*(TODO — dùng lại khảo sát đã có)*

## 3. Kiến trúc tổng thể

*(TODO — sơ đồ 3 nhánh + Bộ xử lý trung tâm + Overkill + Continual Learning, xem Mục 3
`De_xuat_SQLi_Detection_AI.md`; ghi rõ phần nào đã chạy thật (Nhánh 1+2) vs thiết kế (Nhánh 3,
tích hợp))*

## 4. Dữ liệu

### 4.1 Nhánh 1 + Nhánh 2 (đã có)
*(TODO — D1/D3/D4/D7, xem `data_contract.md`)*

### 4.2 Nhánh 3 (kế hoạch, chưa thực hiện)
*(TODO — Docker lab + sqlmap Cách B, script mô phỏng Cách A, schema nhãn 2 tầng — xem Mục 4.3-4.4
`De_xuat_SQLi_Detection_AI.md`)*

## 5. Phương pháp

### 5.1 Nhánh 1 — Supervised đa lớp (đã triển khai)
### 5.2 Nhánh 2 — Anomaly Detection (đã triển khai)
### 5.3 Nhánh 3 — Session-level Sequence Model (thiết kế, Future Work)
### 5.4 Bộ xử lý trung tâm + chính sách Overkill (thiết kế, Future Work)
### 5.5 Continual Learning + Concept Drift (thiết kế, Future Work)

*(TODO — điền chi tiết từng phần, đánh dấu rõ trạng thái)*

## 6. Thực nghiệm và Kết quả

### 6.1 Nhánh 1 (thật)
### 6.2 Nhánh 2 (thật)
### 6.3 Demo minh hoạ 2 nhánh (thật — `notebooks/demo_detect.ipynb`)
### 6.4 Nhánh 3 (dự kiến/thiết kế — chưa có số liệu)

## 7. Threat Model và Rủi ro

*(TODO — bảng phân loại case trong/ngoài phạm vi phát hiện, xem thảo luận trước đó về Vị trí B)*

## 8. Thảo luận và Hạn chế

*(TODO — nêu rõ: 2/3 nhánh thực nghiệm, Nhánh 3 + hệ thống tích hợp là Future Work do giới hạn
thời gian (đổi hạn 25/7, chỉ còn 5 ngày — xem `De_xuat_SQLi_Detection_AI.md` Mục 0))*

## 9. Kết luận và Hướng phát triển

*(TODO — tóm tắt đóng góp thật + roadmap Future Work đầy đủ, xem Mục 13 `De_xuat_SQLi_Detection_AI.md`:
Nhánh 3, Continual Learning, Concept Drift, Session Store, benchmark, adversarial hardening,
sanity-check quy mô lớn, publish dataset, so sánh SOTA)*

## Tài liệu tham khảo

*(TODO — dùng lại từ khảo sát đã có)*
