

| File / Folder | Vai trò | Ai cần |
|---------------|---------|--------|
| **Metric files** | | |
| `report/metrics/nhanh1_eval.json` | Eval Nhánh 1 + ROC per class mới | Diệp (báo cáo), Minh (notebook) |
| `report/metrics/nhanh2_eval.json` | Eval Nhánh 2 + PR/CM/per-class DR mới | Diệp, Minh |
| `report/metrics/nhanh2_threshold_sweep.csv` | 21 ngưỡng FPR vs DR vs Precision | Diệp (bảng số), Đức (decision threshold) |
| `report/metrics/nhanh1_architecture_comparison.json` | So sánh 4 kiến trúc (đã có trước) | Diệp (Mục 5.1) |
| `report/journal/nhanh2_training_audit.md` | Nhật ký tuning (đã có trước) | Đức (review) |
| **Figures** | | |
| `report/metrics/figures/nhanh1_roc_per_class.png` | ROC per class (file mới) | Minh (notebook), Diệp (báo cáo) |
| `report/metrics/figures/nhanh2_pr_curve.png` | PR curve (file mới) | Minh, Diệp |
| `report/metrics/figures/nhanh2_score_dist.png` | Score distribution (file mới) | Minh, Diệp |
| `report/metrics/figures/nhanh2_threshold_tradeoff.png` | Threshold trade-off (file mới) | Minh, Diệp |
| **Script** | | |
| `scripts/generate_metrics.py` | Tái tạo metric tự động | Đức (review code) |
| **Notebook** | | |
| `notebooks/metrics_report.ipynb` | Notebook báo cáo metric (file mới) | Minh (dùng làm base cho test notebook), mọi người |
| `notebooks/nhanh2_eval.ipynb` | Eval chi tiết (đã có từ trước) | — |
| **Model** | | |
| `models/nhanh1_v1/` | `model.joblib` + `vectorizer.joblib` + `metadata.json` | API backend, Minh |
| `models/nhanh2_v1/` | `model.joblib` + `metadata.json` | API backend, Minh |
| **Data** | | |
| `data/processed/nhanh2_data.csv` | 15.000 normal rows (features sẵn) | Minh (nếu cần load lại) |
| `data/processed/nhanh2_anomalous_eval.csv` | 25.065 anomalous rows | Minh |
| HF dataset `Jason-42195/VNU-SQLi-Detection` | Gốc 68K rows | Tất cả |

### Lưu ý
- Model mới nhất trên HF: `hf download Jason-42195/VNU-SQLi-Detection-Models --local-dir models/`
- Data không đổi so với bản cũ (cùng 15K normal + 25K anomalous)
