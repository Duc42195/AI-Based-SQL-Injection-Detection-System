"""Models: training and inference wrappers for the three detection branches.

- Branch 1 (supervised, MULTI-CLASS): Normal + SQLi subtypes (Union/Error/
  Boolean-blind/Time-blind/Stacked). Candidate architectures compared
  empirically on F1-macro vs latency vs size: TF-IDF char n-gram (2-4) + GBM,
  DistilBERT fine-tune, and a CNN with an SQL-keyword tokenizer. Not defaulted
  to a transformer.
- Branch 2 (anomaly): Isolation Forest / One-Class SVM trained on BENIGN only;
  emits a continuous anomaly score (per-query flag + feature for Branch 3).
- Branch 3 (session-level, main contribution): a lightweight sequence model
  (GRU / Transformer) over a session, where each step =
  [Branch-1 content embedding ⊕ Branch-2 anomaly score]. Catches Blind SQLi and
  query-splitting that per-query classifiers miss.
"""
