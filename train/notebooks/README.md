# Notebooks — Thực nghiệm so sánh kiến trúc

Nơi chứa notebook thực nghiệm (bước 1 trong kế hoạch 14 ngày).

- `01_arch_comparison.ipynb` — **(Day 1, sẽ tạo)** So sánh nhanh 2 hướng cho Nhánh 1:
  - (a) **DistilBERT** fine-tune.
  - (b) **TF-IDF char n-gram (2–4) + Logistic Regression / GBM** (XGBoost/LightGBM).

  Chốt kiến trúc dựa trên **F1-score đối chiếu latency đo được** — KHÔNG mặc định chọn DistilBERT.
  Ghi lại: F1, Precision, Recall, latency/query (p50/p95), kích thước model.

> Dataset: xem `data/raw/`. Nếu chưa có dữ liệu thật → dùng dataset public (ghi rõ nguồn) + đánh dấu `TODO`.
