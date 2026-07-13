"""AI-based SQL Injection Detection System.

Top-level package for the three-branch detection pipeline:

* Branch 1 (supervised): multi-class classifier (Normal + SQLi subtypes).
* Branch 2 (anomaly detection): One-Class model trained only on Normal
  traffic to catch zero-day / novel attacks; emits a continuous score.
* Branch 3 (session-level): sequence model over a session that fuses Branch-1
  embeddings with Branch-2 scores to catch Blind SQLi / query-splitting.

Sub-packages
------------
- preprocessing:      canonicalization + tokenization / feature extraction.
- models:             training + inference wrappers for both branches.
- decision:           central decision logic and the "Overkill" review queue.
- continual_learning: labelling, rehearsal retraining, validation gate.
- monitoring:         concept-drift metrics, model versioning, rollback.
- utils:              shared config loading and logging helpers.
"""

__version__ = "0.1.0"
