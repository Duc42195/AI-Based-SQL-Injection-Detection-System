"""AI-based SQL Injection Detection System.

Top-level package for the two-branch detection pipeline:

* Branch 1 (supervised): binary SQLi / Normal classifier.
* Branch 2 (anomaly detection): One-Class model trained only on Normal
  traffic to catch zero-day / novel attacks.

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
