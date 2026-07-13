"""Continual learning: labelling, rehearsal retraining, validation gate.

When an Admin confirms a query from the Overkill queue, it is labelled and
stored in the new-data store. A periodic retrain script mixes new samples with
a rehearsal buffer of old data (to avoid catastrophic forgetting). A validation
gate promotes the new model to production only if F1/FPR is >= the current
model on a fixed hold-out test set.
"""
