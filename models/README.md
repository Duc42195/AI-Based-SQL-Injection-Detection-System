---
license: unknown
tags:
- security
- sql-injection
- scikit-learn
- pytorch
- anomaly-detection
- text-classification
pipeline_tag: text-classification
---

# VNU SQLi Detection Models

Trained model artifacts for a **3-branch** AI-based SQL Injection detection system, deployed at
the Database Proxy layer:

- **Branch 1** — supervised multi-class classifier (Normal + SQLi variants), per query.
- **Branch 2** — anomaly detector trained on benign traffic only (generalises to unseen syntax).
- **Branch 3** — session-level sequence model over a stream of requests (the main contribution).

Training data: [Jason-42195/VNU-SQLi-Detection](https://huggingface.co/datasets/Jason-42195/VNU-SQLi-Detection).

## Contents

| Folder | Branch | Model | Headline metric |
|---|---|---|---|
| `branch1_v1/` | 1 | TF-IDF (char) + Logistic Regression | F1-macro **0.9822** (5 classes) |
| `branch1_comparison/` | 1 | 4 candidate architectures (5-class) | see table below |
| `branch1_no_*/` | 1 | Leave-one-class-out ablations (zero-day coverage) | F1 ~0.98 on remaining |
| `branch2_v1/` | 2 | One-Class SVM (4 structural features) | avg-precision **0.982** |
| `branch2_zeroday/` | 2 | One-Class SVM (zero-day coverage variant) | — |
| `branch3_v1/` | 3 | GRU session-sequence classifier (4 classes) | see project repo |

Download everything: `hf download Jason-42195/VNU-SQLi-Detection-Models --local-dir models/`

---

## `branch1_v1/` — Branch 1 (supervised multiclass) — **production**

TF-IDF (`char_wb`, 2–4 gram, 50k features) + Logistic Regression. Classifies a query into one of
**5 classes**: `normal`, `union_based`, `error_based`, `boolean_blind`, `time_blind`.

- **F1-macro: 0.9822** on the held-out test set (13,560 rows).
- p50 latency ~0.8 ms, size ~3.5 MB.
- Files: `vectorizer.joblib` (TfidfVectorizer), `model.joblib` (LogisticRegression), `metadata.json`.

```python
import joblib
vectorizer = joblib.load("branch1_v1/vectorizer.joblib")
clf = joblib.load("branch1_v1/model.joblib")

X = vectorizer.transform(["1' OR '1'='1"])
clf.predict(X)  # -> array([3])  (3 = boolean_blind)
```

## `branch1_comparison/` — Branch 1 architecture comparison (5-class)

Four candidates trained on the same 5-class data (`train/compare_branch1_architectures.py`).
The neural heads are sized from the data (true 5-class, no dead `stacked` neuron). TF-IDF+LogReg
was chosen for production on the latency/size trade-off — the F1 gap is negligible.

| Candidate | F1-macro | p50 latency | Size |
|---|---|---|---|
| `candidate_tfidf_logreg` | 0.9822 | 0.8 ms | 3.5 MB |
| `candidate_tfidf_lightgbm` | 0.9912 | 91.7 ms | 5.7 MB |
| `candidate_distilbert` | 0.9892 | 2.9 ms (GPU) | 256 MB |
| `candidate_cnn_sqltok` | 0.9838 | 0.3 ms | 0.11 MB (28.5K params) |

Only the two neural candidates' weights are hosted here (`candidate_distilbert/`:
`model.safetensors` + tokenizer/config; `candidate_cnn_sqltok/`: `model.pt` + `vocab.json`).

```python
# DistilBERT candidate
from transformers import AutoModelForSequenceClassification, AutoTokenizer
tok = AutoTokenizer.from_pretrained("branch1_comparison/candidate_distilbert")
model = AutoModelForSequenceClassification.from_pretrained("branch1_comparison/candidate_distilbert")
# model.config.num_labels == 5
```

The CNN candidate is a small TextCNN over a char-level SQL tokenizer; reconstruct it with the
helper in `train/compare_branch1_architectures.py` (`_build_textcnn_class`, `_encode_texts`) and the
saved `vocab.json` — see `train/notebooks/demo_detect.ipynb` for a runnable example.

## `branch1_no_*/` — leave-one-class-out ablations (zero-day coverage)

Four Branch-1 models, each trained with **one attack class excluded**
(`branch1_no_union_based`, `branch1_no_error_based`, `branch1_no_boolean_blind`,
`branch1_no_time_blind`). Used to measure whether the anomaly branch / combined system still
catches an attack family the supervised model was never trained on. Each scores F1-macro ~0.98 on
its remaining classes. Same file layout as `branch1_v1/`; `metadata.json` records `excluded_label`.

## `branch2_v1/` — Branch 2 (anomaly detection)

One-Class SVM trained on benign traffic only, using 4 structural features
(`length`, `special_char_ratio`, `sql_keyword_count`, `entropy`) — not TF-IDF, so it can
generalise to unseen attack syntax. Average precision ~0.982 (full PR curve / threshold sweep in
the project repo's `report/metrics/`).

```python
# From within the project repo (needs src.models.branch2_anomaly.AnomalyDetector):
from src.models.branch2_anomaly import AnomalyDetector
import numpy as np

detector = AnomalyDetector.load("branch2_v1")
X = np.array([[40, 0.05, 1, 3.6]])  # [length, special_char_ratio, sql_keyword_count, entropy]
detector.score(X)          # continuous anomaly score
detector.anomaly_flags(X)  # boolean flag
```

## `branch2_zeroday/` — Branch 2 (zero-day coverage variant)

One-Class SVM with the same config as `branch2_v1`, used in the zero-day coverage experiment
(pairs with the `branch1_no_*` ablations). Same loader as `branch2_v1`.

## `branch3_v1/` — Branch 3 (session-level sequence model)

A GRU over a session's stream of per-request feature vectors (`input_dim=7`, `hidden_dim=32`,
`max_len=64` requests/session). Classifies a **session** into 4 classes: `benign`,
`boolean_blind`, `time_blind`, `query_splitting`. Files: `model.pt` (state dict), `metadata.json`.
See the project repo for the model definition and the session-feature extractor needed to load it.

---

## Limitations

- Branch 1's `boolean_blind` class has ~13% measured label noise (catch-all bucket for unmatched
  attack rows) — see `data_contract.md` in the project repo.
- The uniformly high Branch-1 F1 (~0.98–0.99 across all 4 architectures) indicates the current
  dataset is easy to separate; it is **not** an adversarial/obfuscation benchmark.
- No adversarial/obfuscation robustness testing yet.
- License: mixed/unclear for the underlying training data (see the dataset repo's card) — treat as
  research / course-project artifacts, not cleared for unrestricted reuse.

## Project repo

Full source, training scripts, and documentation: the `VNU-Database2-Project` repo
(private / course project — ask the author for access).
