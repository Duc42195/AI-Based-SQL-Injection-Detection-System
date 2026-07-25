# Notebooks — Architecture Comparison Experiments

Home for experimental notebooks (step 1 of the 14-day plan).

- `01_arch_comparison.ipynb` — **(Day 1, to be created)** Quick comparison of 2 directions for Branch 1:
  - (a) **DistilBERT** fine-tuning.
  - (b) **TF-IDF char n-gram (2–4) + Logistic Regression / GBM** (XGBoost/LightGBM).

  Lock in the architecture based on **F1-score weighed against measured latency** — do NOT default to DistilBERT.
  Record: F1, Precision, Recall, latency/query (p50/p95), model size.

> Dataset: see `data/raw/`. If real data isn't available yet → use a public dataset (cite the source clearly) + mark it `TODO`.
