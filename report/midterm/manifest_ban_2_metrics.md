
| File / Folder | Role | Who needs it |
|---------------|---------|--------|
| **Metric files** | | |
| `report/metrics/branch1_eval.json` | Branch 1 eval + new per-class ROC | Diep (report), Minh (notebook) |
| `report/metrics/branch2_eval.json` | Branch 2 eval + new PR/CM/per-class DR | Diep, Minh |
| `report/metrics/branch2_threshold_sweep.csv` | 21 thresholds of FPR vs DR vs Precision | Diep (data table), Duc (decision threshold) |
| `report/metrics/branch1_architecture_comparison.json` | 4-architecture comparison (pre-existing) | Diep (Section 5.1) |
| `report/conf/branch2_training_audit.md` | Tuning log (pre-existing) | Duc (review) |
| **Figures** | | |
| `report/metrics/figures/branch1_roc_per_class.png` | Per-class ROC (new file) | Minh (notebook), Diep (report) |
| `report/metrics/figures/branch2_pr_curve.png` | PR curve (new file) | Minh, Diep |
| `report/metrics/figures/branch2_score_dist.png` | Score distribution (new file) | Minh, Diep |
| `report/metrics/figures/branch2_threshold_tradeoff.png` | Threshold trade-off (new file) | Minh, Diep |
| **Script** | | |
| `train/generate_metrics.py` | Automatically regenerates metrics | Duc (code review) |
| **Notebook** | | |
| `train/notebooks/metrics_report.ipynb` | Metrics report notebook (new file) | Minh (used as the base for the test notebook), everyone |
| `train/notebooks/branch2_eval.ipynb` | Detailed evaluation (pre-existing) | — |
| **Model** | | |
| `models/branch1_v1/` | `model.joblib` + `vectorizer.joblib` + `metadata.json` | API backend, Minh |
| `models/branch2_v1/` | `model.joblib` + `metadata.json` | API backend, Minh |
| **Data** | | |
| `data/processed/branch2_data.csv` | 15,000 normal rows (features included) | Minh (if reloading is needed) |
| `data/processed/branch2_anomalous_eval.csv` | 25,065 anomalous rows | Minh |
| HF dataset `Jason-42195/VNU-SQLi-Detection` | Original 68K rows | Everyone |

### Notes
- Latest model on HF: `hf download Jason-42195/VNU-SQLi-Detection-Models --local-dir models/`
- Data unchanged from the previous version (same 15K normal + 25K anomalous)
