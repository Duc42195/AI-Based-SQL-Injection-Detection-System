"""Monitoring: concept-drift metrics, model versioning, rollback (MLOps-lite).

No full CI/CD. Just: periodic logging of drift indicators (PSI or KL-divergence
over feature/embedding distributions, plus FPR/Recall over time), a fixed
retrain schedule with a manual trigger threshold, simple date/version-based
model directories under ``models/``, and fast rollback to a previous version.
"""
