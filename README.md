# AI-Based SQL Injection Detection System

Hệ thống phát hiện SQL Injection dựa trên AI, đặt tại **Database Proxy** — chặn câu lệnh SQL *trước khi* thực thi. Kiến trúc **hai nhánh song song**:

- **Nhánh 1 (Supervised):** phân loại nhị phân `SQLi` / `Normal`.
- **Nhánh 2 (Anomaly Detection):** học "vùng an toàn" từ 100% truy vấn Normal, phát hiện bất thường / zero-day bằng **Isolation Forest** hoặc **One-Class SVM**.

> ⏱️ **Deadline:** hoàn thành kỹ thuật **26/7/2026**, nộp báo cáo **28/7/2026** (14 ngày).
> Ưu tiên **MVP chạy end-to-end sớm** hơn là tối ưu hoàn hảo từng phần.

---

## Cơ chế kết hợp quyết định (Decision Logic)

| Nhánh 1 (SQLi) | Nhánh 2 (Anomaly) | Hành động |
|:---:|:---:|:---|
| `1` | bất kỳ | **BLOCK** ngay + ghi log |
| `0` | `1` | **OVERKILL** — không thực thi, đưa vào hàng đợi chờ Admin xác nhận. Quá `timeout` → **deny by default** |
| `0` | `0` | **ALLOW** — cho phép thực thi |

---

## Cấu trúc thư mục

```
.
├── configs/
│   └── config.yaml            # Thresholds, paths, timeouts — KHÔNG hardcode
├── src/
│   ├── preprocessing/         # Canonicalization + tokenization / feature extraction
│   ├── models/                # Nhánh 1, Nhánh 2, wrapper load model
│   ├── decision/              # Decision logic + hàng đợi Overkill
│   ├── continual_learning/    # Gán nhãn, retrain (rehearsal), validation gate
│   ├── monitoring/            # Drift monitoring, versioning, rollback
│   └── utils/                 # config loader + logging setup (đã có)
├── api/                       # FastAPI service + endpoint xác nhận Admin
├── tests/                     # pytest: canonicalization, decision, validation gate
├── data/
│   ├── raw/                   # Dataset gốc (SQLi + Normal)
│   ├── processed/             # Dữ liệu đã canonicalize / feature
│   └── adversarial/           # Tập test adversarial (obfuscation)
├── models/                    # Model theo version: v0/, v1/, ... (rollback nhanh)
├── notebooks/                 # Thực nghiệm so sánh kiến trúc (Day 1)
├── scripts/                   # retrain, benchmark latency
├── main.py                    # Health check: load config + log banner
└── pyproject.toml             # Dependencies (uv)
```

---

## Cài đặt

Dự án dùng [`uv`](https://docs.astral.sh/uv/). Stack **core (nhẹ)** đủ cho Day-1 + nhánh TF-IDF, anomaly, decision, API:

```bash
uv sync                          # core deps
uv sync --extra gbm --extra dev  # + XGBoost/LightGBM + pytest/jupyter
```

Stack **transformer (nặng — cài khi Day-1 chốt DistilBERT):**

```bash
uv sync --extra transformer --extra inference   # torch, transformers, ctranslate2
```

### Chạy thử scaffold
```bash
uv run python main.py    # log banner từ config
uv run pytest            # smoke test config loader
```

---

## Cấu hình

Mọi ngưỡng / đường dẫn / timeout nằm ở [`configs/config.yaml`](configs/config.yaml).
Override khi runtime bằng biến môi trường `SQLIDS_<SECTION>_<KEY>` (xem [`.env.example`](.env.example)):

```bash
SQLIDS_DECISION_OVERKILL_TIMEOUT_SECONDS=120
SQLIDS_LOGGING_LEVEL=DEBUG
```

---

## Canonicalization (chống evasion)

Trước khi tokenize, chuẩn hóa input dễ bị né tránh:
- Decode encoding phổ biến: URL-encode, hex, `CHAR()` / `ASCII()`.
- Chuẩn hóa hoa/thường từ khóa SQL.
- **Đánh dấu (không xóa)** comment `/* */` và `--` như một feature riêng.

Mục tiêu: giảm rủi ro né tránh bằng biến đổi cú pháp tương đương.

---

## Continual Learning & Monitoring (MLOps-lite)

- **Continual Learning:** Admin xác nhận truy vấn trong hàng đợi Overkill → gán nhãn, lưu kho dữ liệu mới → script retrain dùng **rehearsal** (trộn mới + cũ, tránh catastrophic forgetting) → **validation gate** (chỉ promote nếu F1/FPR ≥ model hiện tại trên tập test cố định).
- **Concept Drift:** log định kỳ **PSI/KL-divergence** trên phân phối feature + FPR/Recall theo thời gian; lịch retrain cố định (weekly) + trigger thủ công; versioning theo thư mục `models/vN/`; **rollback** nhanh về bản trước.

---

## Kế hoạch triển khai (14 ngày)

1. Thực nghiệm so sánh **DistilBERT vs TF-IDF+GBM** (notebook) → chốt kiến trúc theo **F1 vs latency**.
2. Pipeline canonicalization + tiền xử lý.
3. Train & eval **Nhánh 1** (Precision/Recall/F1, Confusion Matrix).
4. Xây tập **adversarial** (obfuscation trên SQLi có sẵn).
5. Train & eval **Nhánh 2** (FPR trên normal, tỷ lệ phát hiện bất thường).
6. Bộ xử lý trung tâm + chính sách **Overkill** (hàng đợi, timeout, endpoint Admin).
7. Đóng gói **FastAPI**, tối ưu suy luận (CTranslate2 nếu dùng transformer).
8. **Benchmark** latency/throughput; mô phỏng Database Proxy real-time.
9. Test payload SQLi thật + tập adversarial.
10. Pipeline **Continual Learning** (gán nhãn → retrain rehearsal → validation gate).
11. Giám sát **Concept Drift** (log drift, lịch retrain, versioning, rollback).

---

## Quy ước kỹ thuật

- Python **type hints** + **docstring** cho mọi hàm/class public.
- Dùng module `logging` (qua `src.utils.get_logger`) — **không `print`** trong code production.
- **pytest** cho: canonicalization, decision logic, validation gate.
- Config tách riêng (`.yaml` / `.env`) — **không hardcode**.
- Bước tốn thời gian (train/retrain/benchmark): log tiến trình rõ ràng.

## Nguồn dữ liệu

> ⚠️ **TODO:** Chưa có dataset thật. Cần bổ sung dataset SQLi + log Normal. Tạm thời có thể dùng dataset public (ghi rõ nguồn) và đánh dấu `TODO` để thay bằng dữ liệu thật.
