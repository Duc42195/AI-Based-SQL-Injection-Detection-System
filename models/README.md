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

- **Branch 1** — supervised multi-class classifier (Normal + 5 SQLi variants), per query.
- **Branch 2** — anomaly detector trained on benign traffic only (generalises to unseen syntax).
- **Branch 3** — Session Correlator: not a separately-trained model, re-uses Branch 1 + Branch 2 and correlates their signals over a session (the main contribution).

Training data: [Jason-42195/VNU-SQLi-Detection](https://huggingface.co/datasets/Jason-42195/VNU-SQLi-Detection).

## Contents

| Folder | Branch | Model | Headline metric |
|---|---|---|---|
| `branch1_v1/` | 1 | **DistilBERT** (fine-tuned, 6-class) | F1-macro **0.9699** |
| `branch1_v1_logreg_backup/` | 1 | TF-IDF (char) + Logistic Regression — former production champion, superseded | F1-macro 0.8977 |
| `branch1_comparison/` | 1 | 4 candidate architectures (6-class) | see table below |
| `branch1_no_*/` | 1 | Leave-one-class-out ablations (zero-day coverage) | F1 ~0.98–0.99 on remaining |
| `branch2_v1/` | 2 | **Local Outlier Factor** (12 structural/lexical features) | AUC **0.915**, detection 78.4% @ FPR 5.3% |
| `branch2_zeroday/` | 2 | Local Outlier Factor (zero-day coverage variant) | — |
| `branch3_v2/` | 3 | Session Correlator (no weights — reuses `branch1_v1`/`branch2_v1`, 4 calibrated thresholds) | FPR=0.0, detection rate 95.7–100% on 3 session-attack classes, 280-session held-out test set |

Download everything: `hf download Jason-42195/VNU-SQLi-Detection-Models --local-dir models/`

---

## `branch1_v1/` — Branch 1 (supervised multiclass) — **production**

Fine-tuned `distilbert-base-uncased` (max_length 128, 3 epochs). Classifies a query into one of
**6 classes**: `normal`, `union_based`, `error_based`, `boolean_blind`, `time_blind`, `stacked`.

- **F1-macro: 0.9699** on the held-out test set (18,295 rows; 71,705 train rows).
- p50 latency ~2.8 ms (GPU), size ~256 MB.
- Chosen over the lighter TF-IDF+LogReg baseline (`branch1_v1_logreg_backup/`, F1-macro 0.8977)
  because the gap concentrates in the two hardest classes: `stacked` (0.700 → 0.932) and
  `time_blind` (0.812 → 0.973) — see `branch1_comparison/` below. Latency is still real-time.
- Files: `model.safetensors`, `tokenizer.json`, `tokenizer_config.json`, `config.json`, `metadata.json`.

```python
from src.models.branch1_loader import load_branch1_artifacts

vectorizer, clf = load_branch1_artifacts("branch1_v1")  # auto-detects DistilBERT vs sklearn layout
X = vectorizer.transform(["1' OR '1'='1"])
clf.predict(X)  # -> array([3])  (3 = boolean_blind)
```

## `branch1_v1_logreg_backup/` — former production model (superseded)

TF-IDF (`char_wb`, 2–4 gram, 50k features) + Logistic Regression. Kept as a lightweight fallback
and as the baseline in the architecture comparison. F1-macro **0.8977** on the same 6-class split
— same loader (`load_branch1_artifacts`) works on this folder too (`vectorizer.joblib` +
`model.joblib` layout).

## `branch1_comparison/` — Branch 1 architecture comparison (6-class)

Four candidates trained on the same 6-class data, including `stacked`
(`train/compare_branch1_architectures.py`). DistilBERT was chosen for production: the F1 gap over
TF-IDF+LogReg concentrates in `stacked`/`time_blind`, and latency/size are still acceptable.

| Candidate | F1-macro | p50 latency | Size |
|---|---|---|---|
| `candidate_tfidf_logreg` | 0.8977 | 0.5 ms | 0.4 MB |
| `candidate_tfidf_lightgbm` | 0.9624 | 3.0 ms | 4.7 MB |
| `candidate_distilbert` | 0.9648 | 2.8 ms (GPU) | 256 MB |
| `candidate_cnn_sqltok` | 0.7490 | 0.3 ms | 0.15 MB |

(Deployed `branch1_v1/` scores slightly higher, 0.9699, because it was retrained afterwards on a
larger train split — see `metadata.json` in each folder for exact row counts.)

Only the two neural candidates' weights are hosted here (`candidate_distilbert/`:
`model.safetensors` + tokenizer/config; `candidate_cnn_sqltok/`: `model.pt` + `vocab.json`).

The CNN candidate is a small TextCNN over a char-level SQL tokenizer; reconstruct it with the
helper in `train/compare_branch1_architectures.py` (`_build_textcnn_class`, `_encode_texts`) and
the saved `vocab.json`.

## `branch1_no_*/` — leave-one-class-out ablations (zero-day coverage)

Four Branch-1 models, each trained with **one attack class excluded**
(`branch1_no_union_based`, `branch1_no_error_based`, `branch1_no_boolean_blind`,
`branch1_no_time_blind`). Used to measure whether the anomaly branch / combined system still
catches an attack family the supervised model was never trained on. Each scores F1-macro
~0.98–0.99 on its remaining classes. `metadata.json` records `excluded_label`.

## `branch2_v1/` — Branch 2 (anomaly detection) — **production**

**Local Outlier Factor** (`n_neighbors=5`, `contamination=0.05`) trained on benign traffic only,
using 12 structural/lexical features (length, special-char ratio, SQL keyword count, entropy,
bigram entropy, quote/paren imbalance, token-length/run stats) — not TF-IDF, so it generalises to
unseen attack syntax.

- **AUC 0.915**, detection rate **78.4%** at FPR 5.3% (full PR curve / threshold sweep in the
  project repo's `report/metrics/`).
- Chosen over Isolation Forest (AUC 0.903) and One-Class SVM (AUC 0.579, which misclassified
  benign traffic from sources unlike its training distribution as anomalous).

```python
# From within the project repo (needs src.models.branch2_anomaly.AnomalyDetector):
from src.models.branch2_anomaly import AnomalyDetector
import numpy as np

detector = AnomalyDetector.load("branch2_v1")
X = np.array([[40, 0.05, 1, 3.6, 0, 0, 0, 5, 8, 0, 0, 0]])  # 12 features, see feature_names in metadata.json
detector.score(X)          # continuous anomaly score
detector.predict(X)        # boolean/label flag
```

## `branch2_zeroday/` — Branch 2 (zero-day coverage variant)

Local Outlier Factor with the same config as `branch2_v1`, used in the zero-day coverage
experiment (pairs with the `branch1_no_*` ablations). Same loader as `branch2_v1`.

## `branch3_v2/` — Branch 3 (Session Correlator)

Not a trained model — no weights, just `metadata.json` holding 4 calibrated scalar thresholds
(`content_threshold`, `per_query_threshold`, `median_threshold`, `fraction_threshold`). At
inference time it re-uses `branch1_v1`'s classifier (re-scores the session's concatenated query
text) and `branch2_v1`'s anomaly detector (aggregates its per-query scores), OR'ing the two checks
together. Classifies a **session** into 4 classes: `benign`, `boolean_blind`, `time_blind`,
`query_splitting`. See the project repo's `src/models/branch3_session.py`
(`SessionCorrelator`) for the scoring logic, and `report/plan/data_contract.md` §4.2 for why
this replaced an earlier trained GRU design (`branch3_v1`, removed) — a diagnostic found the GRU's
dense projection collapsed a clear bisection signal (cosine similarity 0.961 between consecutive
steps) into near-identical post-classifier probabilities.

Content-check alone and the combined check both reach FPR=0.0 with detection 95.7–100% across the
3 session-attack classes on 280 held-out sessions; the behavior-check alone misses `time_blind`
entirely (0% — the content check is what carries that class), which is why the two are OR'd rather
than used separately.

---

## Limitations

- Branch 1's `boolean_blind` class has ~13% measured label noise (catch-all bucket for unmatched
  attack rows) — see `data_contract.md` in the project repo.
- The architecture-comparison numbers are on a harder 6-class split (adds `stacked`, previously a
  dead neuron in older 5-class experiments) — don't compare them to earlier 5-class READMEs.
- Cross-split leakage (949 identical texts straddling train & test) was found and **fixed** by
  deduplicating `query_canonical` before the split; the numbers here are leakage-free.
- No adversarial/obfuscation robustness testing yet.
- Branch 3's session data is self-generated (bisection algorithm against a self-hosted demo DB),
  not independently-captured attacker traffic — near-perfect detection reflects both branches
  scoring data from the same generation process they were built around, not generalization to
  novel evasive traffic.
- License: mixed/unclear for the underlying training data (see the dataset repo's card) — treat as
  research / course-project artifacts, not cleared for unrestricted reuse.

## Project repo

Full source, training scripts, and documentation: the `VNU-Database2-Project` repo
(private / course project — ask the author for access).
