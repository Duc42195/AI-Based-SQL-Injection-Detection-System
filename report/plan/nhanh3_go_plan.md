# Kế hoạch Branch 3 — GO (F1=1.0, ablation passes)

**Ngày**: 29/07/2026 (Day 17)
**Người**: Lương Chí Bách (Bach)
**Context**: Branch 3 đã train hybrid A+B, F1=1.0, ablation phân hóa (drop_B1=0.9773). Cần hoàn thiện cho RIVF paper + demo.

## Kết quả hiện tại

| Model | F1 | Ghi chú |
|---|---|---|
| Cách A baseline | 1.0000 | 1400 sessions, 4-class |
| Cách B 4-class | 0.7500 | 92 sessions, no query_splitting |
| Hybrid A+B v3 | **1.0000** | active_version hiện tại, deploy sẵn |
| Cross A→B | 0.2500 | Synthetic→HTTP: domain gap (B2 polarity đảo) |
| Few-shot (7 B sess) | 0.7500 | 7 sessions đủ bridge gap |

### Feature distributions

| | B1_normal | B1_boolean | **B2** | gap_seconds |
|---|---|---|---|---|
| A.benign | 0.839 | 0.096 | **-4.51** | 61.0s |
| B.benign | 0.887 | 0.074 | **-3.60** | 6.9s |
| A.boolean | 0.384 | 0.354 | **+2.30** | 0.009s |
| B.boolean | 0.079 | 0.870 | **-2.51** | 0.007s |
| A.time | 0.028 | 0.117 | **+10.97** | 0.034s |
| B.time | 0.013 | 0.395 | **-2.44** | 0.005s |

## Todo (step-by-step)

### 1. Latency benchmark
- Đo inference time của cả pipeline: request → B1 → B2 → B3 → decision
- Ghi vào `report/metrics/latency_benchmark.json`

### 2. Push model lên HuggingFace
```bash
hf upload Jason-42195/VNU-SQLi-Detection-Models models/branch3_v1_hybrid_AB_v3 branch3_v1 --repo-type model
```

### 3. Ghi kết quả → gửi Diep cho paper
- Branch 3 detection rates (boolean_blind, time_blind, query_splitting)
- Ablation results
- Cross-domain analysis
- File đích: gửi cho Diep hoặc ghi vào `report/metrics/branch3_final_report.json`

## Files quan trọng

| File | Vai trò |
|---|---|
| `configs/config.yaml` | active_version = branch3_v1_hybrid_AB_v3 |
| `models/branch3_v1_hybrid_AB_v3/` | GRU model (model.pt + metadata.json) |
| `data/processed/branch3_sessions_cach_a.csv` | Cách A (1400 sessions, 25077 rows) |
| `data/processed/branch3_sessions_cach_b_v2.csv` | Cách B (92 sessions, 720 rows, fixed gaps) |
| `data/processed/branch3_sessions_cach_b_wrapped.csv` | Cách B với SQL-wrapped queries (thử nghiệm) |
| `train/capture_sqlmap_sessions.py` | Cách B capture script (DVWA Docker) |
| `report/metrics/branch3_cach_b_results_v2.json` | Cách B eval results (version 2) |
| `report/metrics/branch3_deep_analysis.json` | Deep analysis (few-shot, B1 wrapping, feature importance) |
| `report/metrics/branch3_final_report.json` | Final report (version 5, current) |
| `train/eval_cach_b_comprehensive.py` | *(deleted)* — đã chạy xong |
| `train/deep_analysis.py` / `train/deep_analysis_v2.py` | *(deleted)* — đã chạy xong |
| `train/trace_and_wrap.py` | *(deleted)* — đã chạy xong |
| `train/retrain_with_fixed_gaps.py` | *(deleted)* — đã chạy xong |
