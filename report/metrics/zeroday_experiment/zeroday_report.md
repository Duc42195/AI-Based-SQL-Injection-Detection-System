# Zero-Day Detection Experiment — Leave-One-Out Protocol

## Objective

Check whether **Branch 2 (anomaly detection)** can detect a form of SQLi it has **never seen before (zero-day)**.

Hypothesis: Branch 1 (supervised) only knows the labels it was trained on — a novel attack type would be mispredicted (usually as normal). Branch 2 (trained on 100% benign) doesn't know any labels, it only measures structural "abnormality" — so it might catch unfamiliar forms.

## Methodology

### Leave-One-Out Protocol

For each of the 4 SQLi labels:

1. **Exclude** that label from Branch 1's training set
2. **Train Branch 1** on the remaining 3 labels + normal
3. **Train Branch 2** normally (benign only)
4. **Test**: feed all queries of the excluded label into **both branches**
5. **Measure**:
   - **B1 miss rate**: % predicted as normal (zero-day bypasses the supervised branch)
   - **B2 DR**: % flagged as anomalous (zero-day caught by the anomaly branch)
   - **Combined coverage**: % caught by AT LEAST 1 branch

### Configuration

| Parameter | Value |
|---------|---------|
| Branch 1 | TF-IDF + Logistic Regression (remaining 4 classes) |
| Branch 2 | One-Class SVM, contamination=0.005, scale_features=false, log_transform=["length"] |
| Features | length, special_char_ratio, sql_keyword_count, entropy |
| Training data | branch1_train.csv (54K train, 13K test), branch2_data.csv (12K benign train) |
| Benign data | branch2_data.csv (3K test split) |
| Anomalous eval | branch2_anomalous_eval.csv (25K rows) |

## Results

### Baseline

| Metric | Value |
|--------|---------|
| FPR (on benign test) | 0.50% |
| DR (on the full anomalous eval set) | 23.21% |

### Leave-One-Out Results

| Excluded label | B1 F1-macro | B1 miss rate | B2 DR | Combined coverage |
|---|---|---|---|---|
| union_based | 0.9803 | 2.47% | 0.53% | 2.97% |
| **error_based** | 0.9784 | 0.00% | **89.68%** | 89.68% |
| boolean_blind | 0.9973 | **90.20%** | 5.40% | 94.00% |
| time_blind | 0.9773 | 0.27% | 12.73% | 12.97% |

### Per-label detail

#### 1. union_based (label 1) — B2 DR = 0.53%

```
B1 predict distribution: {boolean_blind: 2923, normal: 74, error_based: 3}
```

Union queries get predicted as **boolean_blind** by B1 (97.4%) — because UNION SELECT has a WHERE...AND... structure resembling boolean blind. B2 DR is roughly level with FPR → OCSVM doesn't see union_based as different from benign.

#### 2. error_based (label 2) — B2 DR = 89.68% ✅

```
B1 predict distribution: {boolean_blind: 1165, union_based: 395}
```

B1 never predicts it as normal (0% miss rate). B2 catches **~90%** — error_based has a very distinctive structure: many special characters `'`, `(`, `)`, error functions (`CONVERT`, `EXTRACTVALUE`, `UPDATEXML`), long statements. OCSVM clearly separates it from benign.

#### 3. boolean_blind (label 3) — B2 DR = 5.40%

```
B1 predict distribution: {normal: 2706, time_blind: 277, error_based: 10, union_based: 7}
```

**B1 miss rate 90.2%** — boolean_blind queries look structurally very similar to normal traffic. B2 is also weak (5.4%, close to FPR). This is the weakest point for both branches.

#### 4. time_blind (label 4) — B2 DR = 12.73%

```
B1 predict distribution: {boolean_blind: 2992, normal: 8}
```

B1 miss rate is very low (0.27%) — predicted as boolean_blind. B2 DR (12.73%) is below the baseline (23.21%) → time_blind queries have a structure fairly similar to benign.

## Analysis

### When does Branch 2 add value?

| Feature | union | error | boolean | time |
|---------|-------|-------|---------|------|
| average length | ~80 | ~120 | ~70 | ~110 |
| special_char_ratio | 0.05-0.15 | **0.20-0.40** | 0.03-0.10 | 0.05-0.15 |
| sql_keyword_count | 3-5 | **4-10** | 2-4 | 3-6 |
| entropy | 3.0-4.5 | **4.0-5.5** | 2.5-4.0 | 3.0-4.5 |

Error_based stands out on **special_char_ratio** and **sql_keyword_count** — the 2 features OCSVM uses to discriminate.

### Limitations

1. **The current 4 features aren't discriminative enough** for boolean_blind, union_based, time_blind
2. **boolean_blind is the biggest gap**: both branches are weak → needs dedicated feature engineering
3. **OCSVM with 4 low-dimensional features** may miss subtle structure (SQL statement logic)

## Conclusion

1. ✅ **Zero-day detection IS EFFECTIVE** for error_based attacks (DR ~90%)
2. ⚠️ **Not yet sufficient** for union_based (0.53%), boolean_blind (5.40%), time_blind (12.73%)
3. 💡 **Improvements needed**:
   - Feature engineering: token-level features, query structure graph
   - Threshold tuning: a balanced option (FPR=1%) for DR=25.4%
   - Ensemble: combine both branches (combined coverage for boolean_blind reaches 94%)

## Files

| File | Role |
|------|---------|
| `train/run_zeroday_experiment.py` | Runs the full experiment |
| `models/branch2_zeroday/` | OCSVM model (trained fresh) |
| `models/branch1_no_union_based/` | B1 model without union_based |
| `models/branch1_no_error_based/` | B1 model without error_based |
| `models/branch1_no_boolean_blind/` | B1 model without boolean_blind |
| `models/branch1_no_time_blind/` | B1 model without time_blind |
| `report/metrics/zeroday_experiment/summary.json` | Detailed results (JSON) |
| `train/notebooks/zeroday_experiment_report.ipynb` | Notebook for viewing the results |
