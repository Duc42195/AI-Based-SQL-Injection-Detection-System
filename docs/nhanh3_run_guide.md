# Nhánh 3 — Hướng dẫn chạy (Updated 20/07/2026)

## Yêu cầu

- Docker + Docker Compose (cho sqlmap capture)
- Python 3.12 + uv
- `mitmdump` (cài qua pip: `pip install mitmproxy==10.4.2`)
- `sqlmap` (cài qua pip hoặc standalone)

---

## 1. Chạy Cách A (Simulated) — không cần Docker

```bash
uv run python scripts/build_nhanh3_session_data.py
```
Tạo `data/processed/nhanh3_session_data.csv` (~162K step-rows, 20K sessions).

---

## 2. Chạy Cách B (Real sqlmap) — cần Docker

Mỗi bước dưới đây phải chạy **từ project root** với `PYTHONPATH` set đúng:

```bash
# Cách 1 (Windows PowerShell): dùng cmd
cmd /c "set PYTHONPATH=%CD% && cd /d %CD% && python script.py"

# Cách 2 (Linux/Mac):
PYTHONPATH=. python script.py
```

### 2a. Khởi động Docker lab

```bash
cd docker
docker compose up -d --build
# Kiểm tra: http://localhost:42801/user?id=1
```

### 2b. Thu thập traffic sqlmap

```bash
uv run python scripts/collect_nhanh3_traffic.py
```

Chạy sqlmap trên 5 endpoints × 6 techniques với 120s delay giữa mỗi kỹ thuật.
Output: `data/raw/nhanh3_sqlmap_sessions/nhanh3_raw_traffic.csv`
Thời gian: ~2 tiếng.

**Cấu hình qua env (tuỳ chọn):**
| Env | Default | Mô tả |
|-----|---------|-------|
| `SQLI_TARGET_URL` | `http://localhost:42801` | URL Docker lab |
| `SQLI_INTER_TECH_DELAY` | `120` | Delay giữa các technique (giây) |

### 2c. Parse traffic → session format

```bash
uv run python scripts/parse_nhanh3_traffic.py
```
Output: `data/processed/nhanh3_session_data_cachb.csv` (36 sessions)

### 2d. (Optional) Thêm CSIC 2010 benign sessions → 86 sessions

File `nhanh3_session_data_cachb.csv` trong repo đã có sẵn 86 sessions (CSIC 2010 integrated). Từ đầu:

```bash
uv run python scripts/fetch_and_wrap_d3_csic2010.py
uv run python scripts/integrate_csic2010_cachb.py
# Output: nhanh3_session_data_cachb.csv (86 sessions)
```

---

## 3. Train models

### 3a. Random Forest baseline

```bash
# Train trên Cách A
uv run python scripts/train_nhanh3.py --cach A

# Train + cross-eval trên Cách B
uv run python scripts/train_nhanh3.py --cach B
```
Output model: `models/nhanh3_v1/session_rf.joblib`
Output report: `reports/nhanh3_eval_cachA.json` / `nhanh3_eval_cachB.json`

### 3b. GRU sequence model

```bash
# Train GRU v1 trên Cách A
uv run python scripts/train_nhanh3_gru.py
```
Output: `models/nhanh3_gru_v1/session_gru.pt`

### 3c. Domain adaptation

```bash
uv run python scripts/domain_adapt_gru.py
```
Output: `models/nhanh3_gru_v2_adapted/session_gru.pt`
Output report: `reports/nhanh3_gru_adapted_eval.json`

### 3d. Threshold tuning

```bash
uv run python scripts/threshold_tune_gru.py
```
Output report: `reports/nhanh3_gru_threshold_tune.json`

---

## 4. Xem kết quả

### Notebook evaluation

```bash
# Cần PYTHONPATH — dùng cmd /c trên Windows:
cmd /c "set PYTHONPATH=%CD% && cd /d %CD% && python -m jupyter nbconvert --to notebook --execute --ExecutePreprocessor.timeout=300 notebooks/nhanh3_eval.ipynb --output nhanh3_eval_executed.ipynb"

# Data report:
cmd /c "set PYTHONPATH=%CD% && cd /d %CD% && python -m jupyter nbconvert --to notebook --execute --ExecutePreprocessor.timeout=300 notebooks/nhanh3_data_report.ipynb --output nhanh3_data_report_executed.ipynb"
```

Hoặc mở bằng Jupyter:

```bash
uv run jupyter notebook notebooks/nhanh3_eval.ipynb
uv run jupyter notebook notebooks/nhanh3_data_report.ipynb
```

### Báo cáo dạng JSON

- `reports/nhanh3_eval_cachA.json` — RF trên Cách A (test set)
- `reports/nhanh3_eval_gru.json` — GRU v1 metrics
- `reports/nhanh3_gru_adapted_eval.json` — Adapted GRU (thresh=0.5)
- `reports/nhanh3_gru_threshold_tune.json` — Threshold tuning (val/test split)

---

## 5. Pipeline đầy đủ (từ A đến Z)

```bash
# 1. Build Cach A
uv run python scripts/build_nhanh3_session_data.py

# 2. Train RF baseline
uv run python scripts/train_nhanh3.py --cach A

# 3. Train GRU
uv run python scripts/train_nhanh3_gru.py

# (skip 4-6 nếu không cần Cach B thật)
# 4. Docker: docker compose up -d --build
# 5. Collect: uv run python scripts/collect_nhanh3_traffic.py
# 6. Parse:   uv run python scripts/parse_nhanh3_traffic.py

# 7. Domain adaptation + threshold tuning
uv run python scripts/domain_adapt_gru.py
uv run python scripts/threshold_tune_gru.py

# 8. Eval notebooks
cmd /c "set PYTHONPATH=%CD% && cd /d %CD% && python -m jupyter nbconvert --to notebook --execute --ExecutePreprocessor.timeout=300 notebooks/nhanh3_eval.ipynb --output nhanh3_eval_executed.ipynb"
cmd /c "set PYTHONPATH=%CD% && cd /d %CD% && python -m jupyter nbconvert --to notebook --execute --ExecutePreprocessor.timeout=300 notebooks/nhanh3_data_report.ipynb --output nhanh3_data_report_executed.ipynb"
```

---

## 6. File map

| File | Vai trò | Input | Output |
|------|---------|-------|--------|
| `build_nhanh3_session_data.py` | Sinh Cach A | HF dataset | `nhanh3_session_data.csv` |
| `collect_nhanh3_traffic.py` | Capture sqlmap | Docker lab | `nhanh3_raw_traffic.csv` |
| `parse_nhanh3_traffic.py` | Parse → sessions | `nhanh3_raw_traffic.csv` | `nhanh3_session_data_cachb.csv` |
| `integrate_csic2010_cachb.py` | Thêm CSIC 2010 | `d3_csic2010_raw.csv` | `nhanh3_session_data_cachb.csv` |
| `train_nhanh3.py` | Train RF | CSV session data | `session_rf.joblib` |
| `train_nhanh3_gru.py` | Train GRU v1 | CSV session data | `nhanh3_gru_v1/*` |
| `domain_adapt_gru.py` | Domain adaptation | GRU v1 + Cach B | `nhanh3_gru_v2_adapted/*` |
| `threshold_tune_gru.py` | Threshold tuning | Adapted GRU | `nhanh3_gru_threshold_tune.json` |
