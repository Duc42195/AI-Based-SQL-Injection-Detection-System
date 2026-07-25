# Scripts — operations & evaluation

CLI scripts (added incrementally per the plan):

- `benchmark_latency.py` — measures inference latency/throughput (step 8).
- `retrain.py` — retrain with rehearsal + validation gate (step 10).
- `check_drift.py` — logs concept-drift metrics (PSI/KL), FPR/Recall over time (step 11).

All parameters (paths, thresholds) are read from `configs/config.yaml`; time-consuming steps log progress clearly.
