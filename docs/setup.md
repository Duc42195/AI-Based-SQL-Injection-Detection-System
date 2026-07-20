# Setup & File Transfer

## 1. Requirements

- **Python** >= 3.12
- **uv** (Python package manager)
- **Docker** + Docker Compose (chỉ cần nếu muốn tự collect sqlmap traffic)
- **sqlmap** + **mitmproxy** (chỉ cần nếu muốn tự collect)

## 2. Clone + Install

```bash
git clone <repo-url>
cd AI-Based-SQL-Injection-Detection-System
uv sync --extra dev
```

## 3. Files bị gitignore — cần copy thủ công

`.gitignore` chặn commit `data/` và `models/`. Để chạy được ngay, cần copy các file sau từ máy đã train sang:

### 3a. Data files

Copy vào `data/processed/`:

| File | Dung lượng | Vai trò |
|------|-----------|---------|
| `nhanh3_session_data.csv` | ~15 MB | Cách A — 20.000 simulated sessions |
| `nhanh3_session_data_cachb.csv` | ~500 KB | Cách B — 86 sessions (36 sqlmap + 50 CSIC) |
| `nhanh2_data.csv` | ~5 MB | Nhánh 2 data (nếu cần anomaly detection) |

Nếu muốn tự sinh:
```bash
uv run python scripts/build_nhanh3_session_data.py    # → nhanh3_session_data.csv (20K sessions)
uv run python scripts/parse_nhanh3_traffic.py          # → nhanh3_session_data_cachb.csv (36 sessions)
uv run python scripts/integrate_csic2010_cachb.py      # → +50 CSIC sessions = 86
```

### 3b. Model files

Copy vào `models/`:

| File / Thư mục | Vai trò |
|----------------|---------|
| `models/nhanh3_v1/session_rf.joblib` | RF baseline |
| `models/nhanh3_v1/session_feature_names.joblib` | Feature names cho RF |
| `models/nhanh3_gru_v1/session_gru.pt` | GRU v1 weights |
| `models/nhanh3_gru_v1/session_scaler.joblib` | Scaler cho GRU v1 |
| `models/nhanh3_gru_v2_adapted/session_gru.pt` | GRU v2 adapted weights |
| `models/nhanh3_gru_v2_adapted/session_scaler.joblib` | Scaler cho GRU v2 |
| `models/nhanh2_v1/model.joblib` | Nhánh 2 (anomaly) |
| `models/nhanh2_v1/metadata.json` | Metadata Nhánh 2 |
| `models/nhanh1_v1/model.joblib` | Nhánh 1 (TF-IDF + LogReg) |
| `models/nhanh1_v1/metadata.json` | Metadata Nhánh 1 |

Nếu muốn tự train:
```bash
uv run python scripts/train_nhanh3.py --cach A        # → RF baseline
uv run python scripts/train_nhanh3_gru.py              # → GRU v1
uv run python scripts/domain_adapt_gru.py              # → GRU v2 adapted
uv run python scripts/threshold_tune_gru.py            # → threshold tuning report
```

### 3c. Raw data (cho reproducibility)

Copy vào `data/raw/` nếu cần chạy lại từ đầu:

| File / Thư mục | Vai trò |
|----------------|---------|
| `data/raw/nhanh3_sqlmap_sessions/nhanh3_raw_traffic.csv` | Traffic sqlmap raw (~700 KB) |
| `data/raw/d3_csic2010_raw.csv` | CSIC 2010 raw (~40 MB) |
| `data/raw/nhanh3_sqlmap_sessions/` (các file `.flow`, `_B/_E/...`) | Session dump cho reproducibility |

### 3d. Cấu trúc thư mục sau khi copy

```
data/processed/
├── nhanh3_session_data.csv           # Cách A
├── nhanh3_session_data_cachb.csv     # Cách B + CSIC
├── nhanh2_data.csv                   # Nhánh 2
└── sqlmap_payloads.txt               # Payload reference

data/raw/
├── nhanh3_sqlmap_sessions/
│   ├── nhanh3_raw_traffic.csv
│   ├── user_get_B ... user_get_U     # Sqlmap dump từng technique
│   └── capture.flow                  # mitmproxy flow
├── d3_csic2010_raw.csv
└── csic2010/
    ├── normalTrafficTraining.txt
    ├── normalTrafficTest.txt
    └── anomalousTrafficTest.txt

models/
├── nhanh1_v1/metadata.json
├── nhanh2_v1/metadata.json          # (git kept)
├── nhanh2_v1/model.joblib           # (gitignored)
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

## 4. Verify

```bash
uv run python main.py                  # Health check
uv run pytest                          # 47 tests
uv run jupyter notebook notebooks/     # Mở notebooks
```

## 5. Pipeline đầy đủ (A→Z)

Xem `docs/nhanh3_run_guide.md`.

## 6. File map nhanh

| File | Vai trò | Git? |
|------|---------|:----:|
| `configs/config.yaml` | Tất cả tham số | ✅ |
| `scripts/*.py` | Training + evaluation | ✅ |
| `notebooks/*.ipynb` | Eval + figures | ✅ |
| `src/models/*.py` | Model definitions | ✅ |
| `data/processed/*.csv` | Dữ liệu feature | ❌ |
| `data/raw/*.csv` | Dữ liệu gốc | ❌ |
| `models/**/*.joblib` | Model weights | ❌ |
| `models/**/*.pt` | PyTorch weights | ❌ |
| `reports/*.json` | Kết quả evaluation | ✅ |
| `docs/*.md` | Tài liệu | ✅ |
