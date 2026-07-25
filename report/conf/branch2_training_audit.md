# Training Audit — Nhánh 2 (Anomaly Detection)

**Ngày:** 16/7/2026
**Tác giả:** AI Agent (theo yêu cầu của Bách)

## Tóm tắt thay đổi

Đã phát hiện và sửa **4 vấn đề kinh điển** trong quá trình training Branch 2:

| # | Vấn đề | Mức độ | Fix |
|---|--------|:------:|-----|
| 1 | Feature scaling gây hại | 🔴 | Bỏ StandardScaler, chỉ log1p-transform length |
| 2 | contamination chung cho cả 2 model | 🟡 | Tách riêng: IF cont=0.01, OCSVM nu=0.005 |
| 3 | Length outlier cực trị (5370 vs mean 47) | 🟡 | log1p-transform length |
| 4 | Chưa tune hyperparameter | 🟡 | Grid search 28 combos, OCSVM gamma=0.01, nu=0.005 |

## Chi tiết từng vấn đề

### 1. Feature scaling — phản trực giác nhưng quan trọng

**Phát hiện:** Scale toàn bộ 4 features bằng StandardScaler làm AUC giảm mạnh:
- IF: 0.734 → 0.678 (↓)
- OCSVM: 0.805 → 0.533 (↓↓)

**Nguyên nhân:** Feature length chiếm ~80% discriminative power (permutation importance drop 0.288). Scaling san bằng trọng số, khiến special_char_ratio (mean 0.039 cả 2 nhóm — gần như vô dụng) được nâng lên ngang hàng → pha loãng tín hiệu từ length.

**Quyết định:** `scale_features: false`. Chỉ log1p-transform length để xử lý outlier.

### 2. Per-algorithm contamination

**Vấn đề:** contamination chung cho IF và OCSVM. IF cần cont=0.01 để đạt DR hợp lý; OCSVM cần nu=0.005 (tuned). Set chung 0.005 → IF DR=0%.

**Fix:** Thêm `ocsvm_nu: 0.005` riêng, `contamination: 0.01` dùng cho IF. Mỗi model tune độc lập — research best practice.

**IF DR=3.59% thay vì 0%** sau fix — có thể so sánh công bằng.

### 3. Length outlier

Benign: max=5370, mean=47, std=57 → tồn tại 1 hoặc vài extreme outlier.
Anomalous (D3): max=453, mean=137 — không có outlier tương tự.

log1p-transform đưa length về range [0.69, 8.59], giúp model không bị skew bởi outlier.

**Lưu ý research:** log-transform nén extreme value → IF (tree split) mất tín hiệu, DR giảm từ 12.32% xuống 3.59%. OCSVM (RBF kernel) ít bị ảnh hưởng hơn.

### 4. Hyperparameter tuning

Grid search trên 80% training, validate AUC trên 20% training + anomalous:

**Isolation Forest (12 combos):**
- n_estimators ∈ {50, 100, 200}
- contamination ∈ {0.001, 0.005, 0.01, "auto"}
- Kết quả: AUC validation phẳng (~0.665–0.666) — contamination không ảnh hưởng ranking
- Final: contamination=0.01 (chọn dựa trên FPR/DR trade-off, không phải AUC)

**One-Class SVM (16 combos):**
- gamma ∈ {"scale", "auto", 0.1, 0.01}
- contamination ∈ {0.001, 0.005, 0.01, 0.05}
- **Best: gamma=0.01, contamination=0.005 → AUC val=0.897, test=0.887**

## Kết quả cuối cùng (Fair Comparison)

| Model | FPR | DR | AUC | Hyperparameters |
|-------|:---:|:--:|:---:|----------------|
| IF | 0.50% | 3.59% | 0.678 | cont=0.01, n_est=100 |
| **OCSVM** | **0.40%** | **19.98%** | **0.887** | **nu=0.005, gamma=0.01** |

Cả 2 dùng chung preprocessing (log1p-transform length, không scale). Mỗi model tune riêng.

**Improvement so với baseline** (OCSVM default, no log-transform, cont=0.01):
- AUC: 0.805 → **0.887** (↑10.2%)
- FPR: 0.73% → **0.40%** (↓45%)
- DR: 23.67% → 19.98% (↓3.7%, trade-off chấp nhận được)

## Files đã thay đổi

| File | Thay đổi |
|------|----------|
| `configs/config.yaml` | Thêm scale_features, log_transform_features, tune section, ocsvm_gamma, ocsvm_nu |
| `src/models/nhanh2_anomaly.py` | Thêm preprocessing pipeline (log1p-transform + StandardScaler), save/load scaler |
| `scripts/train_nhanh2.py` | Thêm hyperparameter grid search, per-algorithm contamination, refactor _build_detector |
| `tests/test_nhanh2_anomaly.py` | Không đổi — 8 tests vẫn pass |
| `notebooks/nhanh2_eval.ipynb` | Kết quả tuned, per-algorithm params, Training Audit section |
| `reports/nhanh2_training_audit.md` | File này |
