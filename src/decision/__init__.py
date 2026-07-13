"""Decision layer: combine both branches and manage the Overkill queue.

Decision matrix
---------------
- SQLi == 1 (regardless of Branch 2)  -> BLOCK immediately + log.
- SQLi == 0 and Anomaly == 1          -> OVERKILL: do NOT execute; enqueue for
  Admin confirmation. On timeout, deny by default.
- SQLi == 0 and Anomaly == 0          -> ALLOW execution.
"""
