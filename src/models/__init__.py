"""Models: training and inference wrappers for both detection branches.

- Branch 1 (supervised): candidate architectures are DistilBERT fine-tune vs.
  a lightweight TF-IDF char n-gram (2-4) + Logistic Regression / GBM. The final
  choice is decided empirically on F1-vs-latency, not defaulted to DistilBERT.
- Branch 2 (anomaly): One-Class SVM or Isolation Forest trained on Normal only.
"""
