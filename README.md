# AI-Based SQL Injection Detection System

Hệ thống phát hiện SQL Injection dựa trên AI, đặt tại **Database Proxy — Vị trí B** (sau khi backend build xong câu SQL, *trước* DB). Kiến trúc **ba nhánh** (bản kế hoạch V4):

- **Nhánh 1 (Supervised, đa lớp):** phân loại `Normal` + các loại SQLi (`Union / Error / Boolean-blind / Time-blind / Stacked`). So sánh 3 nhóm model: **TF-IDF+GBM**, **DistilBERT**, **CNN + SQL-tokenizer** → chọn theo **F1-macro vs latency vs size**.
- **Nhánh 2 (Anomaly Detection):** học "vùng an toàn" từ **100% traffic benign**, xuất **điểm bất thường liên tục** (cờ zero-day + feature cho Nhánh 3) bằng **Isolation Forest / One-Class SVM**.
- **Nhánh 3 (Session-level — đóng góp chính):** mô hình chuỗi (GRU / Transformer nhẹ) trên toàn **session**; mỗi bước = `[embedding nội dung (Nhánh 1) ⊕ điểm bất thường (Nhánh 2)]`. Bắt **Blind SQLi** và **query-splitting** mà bộ phân loại đơn-query bỏ lọt.

> ⏱️ **Deadline:** hoàn thành kỹ thuật **26/7/2026**, nộp báo cáo **28/7/2026** (14 ngày).
> Ưu tiên **MVP chạy end-to-end sớm** hơn là tối ưu hoàn hảo từng phần.

---

## Cơ chế kết hợp quyết định (Decision Logic)

Ma trận cơ sở per-query (Nhánh 3 có thể **leo thang** một query benign lên BLOCK/OVERKILL nếu session bị phân loại là tấn công Blind/query-splitting):

| Nhánh 1 | Nhánh 2 (Anomaly) | Hành động |
|:---:|:---:|:---|
| lớp tấn công | bất kỳ | **BLOCK** ngay + ghi log |
| `Normal` | `1` | **OVERKILL** — không thực thi, đưa vào hàng đợi chờ Admin xác nhận. Quá `timeout` → **deny by default** |
| `Normal` | `0` | **ALLOW** — cho phép thực thi |

---

## Cấu trúc thư mục

```
.
├── configs/
│   └── config.yaml            # Thresholds, paths, timeouts — KHÔNG hardcode
├── src/
│   ├── preprocessing/         # Canonicalization + tokenization / feature extraction
│   ├── models/                # Nhánh 1 (đa lớp), Nhánh 2 (anomaly), Nhánh 3 (session), wrapper
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

## Kế hoạch triển khai (14 ngày — V4)

> Ưu tiên cắt từ dưới lên khi thiếu thời gian: **(1)** lõi Nhánh 1 đa lớp + Nhánh 2 + Overkill + end-to-end → **(2)** Nhánh 3 trên session data Cách A → **(3)** Nhánh 3 Cách B (sqlmap thật) + so sánh A↔B → **(4)** Continual Learning đầy đủ (hạ xuống demo 1 vòng nếu cần).

| Ngày | Việc chính |
|---|---|
| 1–2 | Setup repo; tải D1/D3/D4; làm sạch + **gán nhãn đa lớp** D1; làm giàu benign từ CSIC 2010; **test song song 3 model Nhánh 1** trên tập nhỏ để chốt hướng |
| 3–4 | Train đầy đủ **Nhánh 1** (model thắng); F1-macro/latency/size + confusion matrix |
| 5–6 | Trích đặc trưng thống kê; train **Nhánh 2** (chỉ benign); xuất điểm bất thường |
| 7 | Canonicalization + sinh tập **adversarial** (WAF-A-MoLE); đưa 1 phần vào training Nhánh 1 (robust) |
| 8–9 | **Session data Cách A** (script mô phỏng); dựng **Nhánh 3** (Tầng 1 tái dùng + GRU/Transformer nhỏ) |
| 10 | Cơ chế kết hợp 3 nhánh + **Overkill**; kiểm thử end-to-end |
| 11–12 | **Session data Cách B** (Docker + sqlmap + proxy capture); train/test Nhánh 3 trên B; **so sánh A↔B** |
| 13 | **Continual Learning**: pipeline Overkill→nhãn→retrain→validation gate chạy ≥1 vòng có drift |
| 14 | Tổng hợp bảng kết quả; viết Thảo luận/Hạn chế/Threat model; ráp báo cáo |

---

## Quy ước kỹ thuật

- Python **type hints** + **docstring** cho mọi hàm/class public.
- Dùng module `logging` (qua `src.utils.get_logger`) — **không `print`** trong code production.
- **pytest** cho: canonicalization, decision logic, validation gate.
- Config tách riêng (`.yaml` / `.env`) — **không hardcode**.
- Bước tốn thời gian (train/retrain/benchmark): log tiến trình rõ ràng.

## Nguồn dữ liệu (public — ghi rõ nguồn)

| ID | Dataset | Dùng cho | Ghi chú |
|---|---|---|---|
| D1 | SQLiV3 (~30.9K) | Nhánh 1 | ⚠️ khử trùng lặp/null; **gán nhãn lại đa lớp**; cân bằng lại (traffic thật <1% tấn công) |
| D2 | sqliv5 | Adversarial test | có sẵn biến thể adversarial |
| D3 | CSIC 2010 (traffic normal) | Nhánh 2, làm giàu benign | benign phức tạp (JOIN/subquery) |
| D4 | payload-box | Gán nhãn đa lớp Nhánh 1 | phân theo DBMS/kỹ thuật |
| D5 | WAF-A-MoLE | Sinh adversarial | adversarial training |
| D6 | DVWA/WebGoat (Docker) | Session data Cách B | sqlmap tấn công thật + proxy capture |

**Session data (Nhánh 3)** tạo bằng **2 cách để so sánh**: **Cách A** (script mô phỏng nhanh từ D1) và **Cách B** (sqlmap thật lên DVWA/WebGoat, capture qua mitmproxy/Burp). So sánh A↔B là một kết quả học thuật.

> ⚠️ **TODO:** một số nhận định trong báo cáo cần verify bằng Web Search trước khi nộp. Session data phần lớn tổng hợp — nêu rõ ở phần Hạn chế.
