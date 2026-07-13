# Scripts — vận hành & đánh giá

CLI scripts (sẽ bổ sung dần theo kế hoạch):

- `benchmark_latency.py` — đo latency/throughput suy luận (bước 8).
- `retrain.py` — retrain có rehearsal + validation gate (bước 10).
- `check_drift.py` — log chỉ số concept drift (PSI/KL), FPR/Recall theo thời gian (bước 11).

Mọi tham số (đường dẫn, ngưỡng) đọc từ `configs/config.yaml`; các bước tốn thời gian log tiến trình rõ ràng.
