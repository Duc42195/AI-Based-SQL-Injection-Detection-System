# Kế hoạch — Prototype: LogisticRegression vs GRU

**Ngày:** 29/07/2026
**Context:** Shuffle test cho thấy GRU không học sequence — model chỉ học per-step feature distributions. Mentor đề xuất dùng LogisticRegression (giống Branch 1) thay GRU.

## Mục tiêu

So sánh LogisticRegression (phong cách Branch 1) với GRU hiện tại trên task session-level classification (4 classes).

## Feature engineering

| Feature | Mô tả | Dạng |
|---------|-------|------|
| `B1_[normal/union/error/boolean/time]_mean` | Mean B1 probs per session | 5 |
| `B1_*_std` | Std của mỗi B1 prob | 5 |
| `B2_score_mean` | Mean anomaly score | 1 |
| `B2_score_std` | Std anomaly score | 1 |
| `gap_log1p_mean` | Mean gap time | 1 |
| `gap_log1p_std` | Std gap time | 1 |
| `gap_log1p_max` | Max gap time (time-blind signal) | 1 |
| `gap_log1p_slope` | Linear trend của gap (tăng dần?) | 1 |

Total: **16 features** (so với GRU 7 features per step)

## Pipeline

```
Session steps → per-step features (7-dim)
→ session-level aggregation (mean/std/max/slope)
→ StandardScaler
→ LogisticRegression (multinomial, L2)
→ class prediction
```

## So sánh

| Tiêu chí | GRU | LogisticRegression |
|----------|-----|--------------------|
| Architecture | GRU hidden=32 | Linear softmax |
| Input | 7-dim per step, padded | 16-dim averaged |
| Train params | ~3k weights | ~80 weights |
| Inference | ~1.6ms (padded) | ~0.05ms |
| F1 (target) | 1.0000 | ? |
| Interpretability | Black box | Coefficients readable |

## Steps

1. [ ] Feature extraction script: `train/branch3_lr_features.py`
2. [ ] Train + eval script: `train/compare_gru_vs_lr.py`
3. [ ] Ghi metrics vào `report/metrics/branch3_gru_vs_lr.json`
4. [ ] Chạy logistic regression coefficients → feature importance plot
5. [ ] Kết luận: swap GRU → LR hay keep GRU
