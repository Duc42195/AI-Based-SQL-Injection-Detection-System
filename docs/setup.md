# Setup & File Transfer

Có 2 cách: **Quick start** (copy file có sẵn, chạy ngay) hoặc **Từ đầu** (cần Docker + sqlmap).

---

## Cách 1: Quick start (khuyên dùng)

Chỉ cần Python + uv, **không cần Docker**. Copy data + model từ máy đã train.

### 1.1. Yêu cầu

- Python >= 3.12
- uv

### 1.2. Clone + cài đặt

```bash
git clone <repo-url>
cd AI-Based-SQL-Injection-Detection-System
uv sync --extra dev
```

### 1.3. Copy file data + model

`.gitignore` chặn `data/` và `models/` — cần copy thủ công từ máy đã train:

#### data/processed/

| File | Vai trò |
|------|---------|
| `nhanh3_session_data.csv` | Cách A — 20.000 simulated sessions |
| `nhanh3_session_data_cachb.csv` | Cách B — 86 sessions (36 sqlmap + 50 CSIC) |
| `nhanh2_data.csv` | Nhánh 2 (anomaly detection) |

#### models/

| File / Thư mục | Vai trò |
|----------------|---------|
| `nhanh3_v1/session_rf.joblib` | RF baseline |
| `nhanh3_v1/session_feature_names.joblib` | Feature names |
| `nhanh3_gru_v1/session_gru.pt` | GRU v1 weights |
| `nhanh3_gru_v1/session_scaler.joblib` | Scaler GRU v1 |
| `nhanh3_gru_v2_adapted/session_gru.pt` | GRU v2 adapted weights |
| `nhanh3_gru_v2_adapted/session_scaler.joblib` | Scaler GRU v2 |
| `nhanh2_v1/model.joblib` | Nhánh 2 |
| `nhanh1_v1/model.joblib` | Nhánh 1 |

#### data/raw/ (cho reproducibility)

| File | Vai trò |
|------|---------|
| `nhanh3_sqlmap_sessions/nhanh3_raw_traffic.csv` | Traffic sqlmap raw |
| `nhanh3_sqlmap_sessions/user_*_*` | Sqlmap dump từng technique |
| `d3_csic2010_raw.csv` | CSIC 2010 raw |
| `csic2010/normalTrafficTraining.txt` | CSIC training |

### 1.4. Verify

```bash
uv run python main.py    # Health check
uv run pytest            # 47 tests passed
uv run jupyter notebook notebooks/nhanh3_eval.ipynb
```

---

## Cách 2: Từ đầu (cần Docker)

Chạy toàn bộ pipeline từ A→Z: thu thập traffic thật → parse → train → eval.

### 2.1. Yêu cầu

- Python >= 3.12 + uv
- Docker + Docker Compose
- sqlmap (`pip install sqlmap` hoặc standalone)
- mitmproxy (`pip install mitmproxy==10.4.2`)

### 2.2. Clone + cài đặt

```bash
git clone <repo-url>
cd AI-Based-SQL-Injection-Detection-System
uv sync --extra dev
pip install mitmproxy==10.4.2 sqlmap
```

### 2.3. Khởi động Docker lab

```bash
cd docker
docker compose up -d --build
# Kiểm tra:
curl http://localhost:42801/user?id=1
# Ports: Flask app 42801, PostgreSQL 5433
```

Docker lab gồm:
- **vuln_app**: Flask app có 5 endpoint SQLi (user, product, order, profile, search) — chạy port 42801
- **postgres**: PostgreSQL database — chạy port 5433

### 2.4. Thu thập traffic sqlmap (Cách B)

Script tự động chạy sqlmap qua mitmproxy trên 5 endpoints × 6 techniques (B, E, Q, S, T, U):

```bash
# Mặc định: http://localhost:42801, delay 120s giữa mỗi technique
uv run python scripts/collect_nhanh3_traffic.py

# Tuỳ chỉnh:
# set SQLI_TARGET_URL=http://other-host:42801
# set SQLI_INTER_TECH_DELAY=60
```

Thời gian: ~2 tiếng (30 sqlmap runs × 120s delay).
Output: `data/raw/nhanh3_sqlmap_sessions/nhanh3_raw_traffic.csv`

### 2.5. Parse traffic → session format

```bash
uv run python scripts/parse_nhanh3_traffic.py
# → data/processed/nhanh3_session_data_cachb.csv (36 sessions)
```

### 2.6. (Tuỳ chọn) Thêm CSIC 2010 benign → 86 sessions

```bash
uv run python scripts/fetch_and_wrap_d3_csic2010.py    # Tải CSIC (~40 MB)
uv run python scripts/integrate_csic2010_cachb.py       # Gộp vào
# → data/processed/nhanh3_session_data_cachb.csv (86 sessions)
```

### 2.7. Sinh Cách A (simulated, không cần Docker)

```bash
uv run python scripts/build_nhanh3_session_data.py
# → data/processed/nhanh3_session_data.csv (162K step-rows, 20K sessions)
```

### 2.8. Train models

```bash
# RF baseline
uv run python scripts/train_nhanh3.py --cach A
# → models/nhanh3_v1/session_rf.joblib

# GRU v1
uv run python scripts/train_nhanh3_gru.py
# → models/nhanh3_gru_v1/session_gru.pt

# Domain adaptation (GRU v1 → v2, cần Cách B)
uv run python scripts/domain_adapt_gru.py
# → models/nhanh3_gru_v2_adapted/session_gru.pt

# Threshold tuning
uv run python scripts/threshold_tune_gru.py
# → reports/nhanh3_gru_threshold_tune.json
```

### 2.9. Eval notebooks

```bash
uv run jupyter notebook notebooks/nhanh3_eval.ipynb
uv run jupyter notebook notebooks/nhanh3_data_report.ipynb
uv run jupyter notebook notebooks/exp_nhanh3_arch_comparison.ipynb
```

---

## 3. Cấu trúc thư mục (sau khi hoàn tất)

```
data/
├── processed/
│   ├── nhanh3_session_data.csv           # Cách A (20K sessions)
│   ├── nhanh3_session_data_cachb.csv     # Cách B + CSIC (86 sessions)
│   ├── nhanh2_data.csv                   # Nhánh 2
│   └── sqlmap_payloads.txt
├── raw/
│   ├── nhanh3_sqlmap_sessions/
│   │   ├── nhanh3_raw_traffic.csv
│   │   ├── user_get_B ... user_get_U     # Sqlmap dump
│   │   └── capture.flow
│   ├── d3_csic2010_raw.csv
│   └── csic2010/
│       ├── normalTrafficTraining.txt
│       ├── normalTrafficTest.txt
│       └── anomalousTrafficTest.txt

models/
├── nhanh1_v1/metadata.json
├── nhanh2_v1/model.joblib + metadata.json
├── nhanh3_v1/
│   ├── session_rf.joblib
│   └── session_feature_names.joblib
├── nhanh3_gru_v1/
│   ├── session_gru.pt
│   └── session_scaler.joblib
└── nhanh3_gru_v2_adapted/
    ├── session_gru.pt
    └── session_scaler.joblib
```

## 4. File map

| File | Vai trò | Git? |
|------|---------|:----:|
| `configs/config.yaml` | Tất cả tham số | ✅ |
| `scripts/*.py` | Training + evaluation | ✅ |
| `notebooks/*.ipynb` | Eval + figures | ✅ |
| `src/**/*.py` | Model definitions + utils | ✅ |
| `docker/docker-compose.yml` | Docker lab (Flask + Postgres) | ✅ |
| `docker/vuln_app/app.py` | Web app có lỗi SQLi | ✅ |
| `data/**/*.csv` | Dữ liệu feature | ❌ |
| `data/**/*.txt` | Dữ liệu raw | ❌ |
| `models/**/*.joblib` | Model weights | ❌ |
| `models/**/*.pt` | PyTorch weights | ❌ |
| `reports/*.json` | Kết quả evaluation | ✅ |
| `docs/*.md` | Tài liệu | ✅ |
