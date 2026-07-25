# Plan: Testing Branch 2 — Zero-day Detection via Leave-One-Out

## Objective
Check whether Branch 2 can detect **zero-day SQLi** (a form never seen before).

Method: exclude 1 label from Branch 1, see whether Branch 2 catches that label.

## Results (23 Jul 2026)

| Excluded label | B1 F1-macro | B1 miss rate | B2 DR | Combined coverage |
|---|---|---|---|---|
| union_based | 0.9803 | 2.47% | 0.53% | 2.97% |
| **error_based** | 0.9784 | 0.00% | **89.68%** | 89.68% |
| boolean_blind | 0.9973 | **90.20%** | 5.40% | 94.00% |
| time_blind | 0.9773 | 0.27% | 12.73% | 12.97% |

**Baseline:** FPR=0.50%, DR (all anomalous)=23.21%

> ⚠️ **HF upload:** SKIPPED — the token doesn't have write access to the `Jason-42195/VNU-SQLi-Detection` repo (403 Forbidden). Needs a Write token on that repo or a separate repo. Data exists locally.

### Key findings

1. **error_based → B2 catches it very well (DR 89.68%)** — far above the 23% baseline. Error-based attacks have a distinctive structure (many special characters like `'`, `(`, error functions) → OCSVM clearly separates it from benign.
2. **boolean_blind → B1 fails (90.2% predicted normal), B2 is weak (5.4%)** — boolean-blind queries look statistically very similar to normal traffic.
3. **union_based → both B1 and B2 miss it (combined 2.97%)** — UNION queries don't have a standout structural signature.
4. **time_blind → B2 catches a partial amount (12.73%)** — still below the baseline.

### Conclusion
- **Zero-day detection IS EFFECTIVE** for error_based attacks (DR ~90%).
- **Not yet sufficient** for union_based, boolean_blind, time_blind — needs more features or threshold tuning.
- Weakest point: **boolean_blind** — both branches are weak, needs dedicated feature engineering.

## Files created

| File | Content |
|------|----------|
| `train/run_zeroday_experiment.py` | Script running the full experiment |
| `models/branch2_zeroday/` | OCSVM model (trained fresh for the experiment) |
| `models/branch1_no_{label}/` | 4 B1 models, each excluding 1 SQLi label |
| `report/metrics/zeroday_experiment/summary.json` | Detailed results (JSON) |
