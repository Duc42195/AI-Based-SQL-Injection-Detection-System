---
license: unknown
tags:
- security
- sql-injection
- scikit-learn
- anomaly-detection
- text-classification
pipeline_tag: text-classification
---

# VNU SQLi Detection Models

Trained model artifacts for a 2-branch AI-based SQL Injection detection system (Branch 3 —
session-level — is designed but not yet implemented; see the project repo for details).

Data used to train these models: [Jason-42195/VNU-SQLi-Detection](https://huggingface.co/datasets/Jason-42195/VNU-SQLi-Detection).

## `nhanh1_v1/` — Branch 1 (supervised multiclass)

TF-IDF (char_wb, 2-4gram) + Logistic Regression. Classifies a query into one of 5 classes:
`normal`, `union_based`, `error_based`, `boolean_blind`, `time_blind`.

- **F1-macro: 0.9822** on held-out test set (13,560 rows)
- p50 latency: ~0.5ms, size: ~3.9MB
- Files: `vectorizer.joblib` (TfidfVectorizer), `model.joblib` (LogisticRegression), `metadata.json`

```python
import joblib
vectorizer = joblib.load("nhanh1_v1/vectorizer.joblib")
clf = joblib.load("nhanh1_v1/model.joblib")

X = vectorizer.transform(["1' OR '1'='1"])
clf.predict(X)  # -> array([3])  (3 = boolean_blind)
```

## `nhanh2_v1/` — Branch 2 (anomaly detection)

One-Class SVM trained on 100% benign traffic, using 4 structural features (length,
special_char_ratio, sql_keyword_count, entropy) — not TF-IDF, so it can generalize to
unseen attack syntax.

- **AUC: 0.90**, FPR: 0.3% (9/3000 benign), detection rate: 20.7% (5196/25065 anomalous)
- Files: `model.joblib` (wraps `src.models.nhanh2_anomaly.AnomalyDetector`), `metadata.json`

```python
# From within the project repo (needs src.models.nhanh2_anomaly.AnomalyDetector):
from src.models.nhanh2_anomaly import AnomalyDetector
import numpy as np

detector = AnomalyDetector.load("nhanh2_v1")
X = np.array([[40, 0.05, 1, 3.6]])  # [length, special_char_ratio, sql_keyword_count, entropy]
detector.score(X)          # continuous anomaly score
detector.anomaly_flags(X)  # boolean flag
```

## Limitations

- Branch 1's `boolean_blind` class has ~13% measured label noise (catch-all bucket for
  unmatched attack rows) — see `data_contract.md` in the project repo.
- Branch 2's detection rate (20.7%) reflects a diverse anomalous eval set (D3 CSIC2010,
  covering XSS/path-traversal/etc., not just SQLi) — not a pure SQLi zero-day benchmark.
- No adversarial/obfuscation robustness testing yet.
- License: mixed/unclear for underlying training data (see the dataset repo's card) —
  treat as research/course-project artifacts, not yet cleared for unrestricted reuse.

## Project repo

Full source, training scripts, and documentation: see the `VNU-Database2-Project` repo
(private/course project — ask the author for access).
