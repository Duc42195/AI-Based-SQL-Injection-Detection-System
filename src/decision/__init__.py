"""Decision layer: combine both branches and manage the Overkill queue.

Fuses signals from all three branches. Base per-query matrix:

- SQLi (Branch 1) attack class  -> BLOCK immediately + log.
- SQLi == Normal and Anomaly (Branch 2) == 1 -> OVERKILL: do NOT execute;
  enqueue for Admin confirmation. On timeout, deny by default.
- SQLi == Normal and Anomaly == 0 -> ALLOW execution.

Branch 3 (session) can escalate an otherwise-benign query to BLOCK/OVERKILL
when the surrounding session is classified as a Blind/query-splitting attack.
The Overkill queue also feeds labelled samples to continual learning.
"""
