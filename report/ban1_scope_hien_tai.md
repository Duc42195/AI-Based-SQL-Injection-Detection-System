# Báo cáo — Hệ thống phát hiện SQL Injection dựa trên AI

## (Bản 1 — theo scope thực nghiệm hiện tại: Nhánh 1 + Nhánh 2)

> Nộp: Thứ 7, 25/7/2026. Phạm vi: 2 nhánh đã có kết quả thực nghiệm thật (Nhánh 1 supervised
> đa lớp, Nhánh 2 anomaly detection) + notebook demo. Không đề cập chi tiết Nhánh 3/hệ thống
> đầy đủ — xem [ban2_hoan_chinh.md](ban2_hoan_chinh.md) cho tầm nhìn đầy đủ.

---

## 1. Đặt vấn đề và Mục tiêu

*(TODO — Diệp: dùng lại Mục 1 của `De_xuat_SQLi_Detection_AI.md`, bỏ phần nhắc Nhánh 3 là trọng tâm)*

## 2. Công trình liên quan

*(TODO — dùng lại khảo sát đã có, giữ nguyên)*

## 3. Kiến trúc đề xuất (2 nhánh)

*(TODO — sơ đồ Nhánh 1 + Nhánh 2 + verdict đơn giản, xem `notebooks/demo_detect.ipynb` mục 2)*

## 4. Dữ liệu và Tiền xử lý

*(TODO — D1/D4/D7 cho Nhánh 1, D1/D3/D7 cho Nhánh 2; canonicalization; xem `data_contract.md`)*

## 5. Phương pháp

### 5.1 Nhánh 1 — Supervised đa lớp
*(TODO — so sánh 4 kiến trúc, chọn TF-IDF+LogReg, lý do)*

### 5.2 Nhánh 2 — Anomaly Detection
*(TODO — Isolation Forest vs One-Class SVM, chọn OCSVM, lý do)*

## 6. Thực nghiệm và Kết quả

### 6.1 Nhánh 1
*(TODO — F1-macro=0.982, per-class, confusion matrix — xem `reports/nhanh1_eval.json`)*

### 6.2 Nhánh 2
*(TODO — FPR=0,3%, detection rate=20,7%, AUC=0,90 (OCSVM); ROC curve — xem `reports/nhanh2_eval.json`)*

### 6.3 Demo minh hoạ
*(TODO — kết quả từ `notebooks/demo_detect.ipynb`: ví dụ input/output, sanity-check 19/20 đúng trên mẫu 20 dòng)*

## 7. Thảo luận và Hạn chế

*(TODO — nhiễu nhãn `boolean_blind` ~13%, dữ liệu D1 license chưa rõ, chưa test adversarial đầy đủ — xem `data_contract.md`)*

## 8. Kết luận và Hướng phát triển

*(TODO — tóm tắt 2 nhánh đã làm; Nhánh 3 + hệ thống đầy đủ + Continual Learning là bước tiếp theo, xem Bản 2)*

## Tài liệu tham khảo

*(TODO — dùng lại từ khảo sát đã có)*
