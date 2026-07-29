# Plan A — Mở rộng Cách A (pool + noise)

> Mục tiêu: attack memorization trap bằng cách tăng độ đa dạng của synthetic dataset, không cần Docker.

## 1. Vấn đề hiện tại

- Pool 100 users → chỉ 100 distinct patterns/class → GRU hidden=32 học thuộc
- Ablation F1=1.0 trên 6/7 config là red flag: model không thực sự học sequential dependency
- Hard-mode eval (DR=100%) là evidence duy nhất còn đáng tin, nhưng chưa đủ thuyết phục peer review

## 2. Thay đổi

### 2.1. Pool users: 100 → 5000

Chỉ sửa 1 dòng trong `build_session_dataset.py`:
```python
pool = generate_synthetic_user_pool(n_users=5000, rng=np.random.default_rng(42))
```

5000 users × ~70 steps/user = 350K steps, ~5000 sessions/class.

### 2.2. Thêm noise injection

Hiện tại bisection chạy deterministic với ground-truth cố định. Thêm 3 loại noise:

**a) Noise step order** — xác suất p=0.05 shuffle 2 bước liền kề
**b) Noise feature** — Gaussian noise σ=0.01 vào Branch 1 probabilities + Branch 2 score
**c) Noise gap time** — thay vì gap đều, dùng exponential distribution λ=2.0s

### 2.3. Retrain + re-eval

- Retrain GRU (30 epochs)
- Re-run ablation (7 configs)
- So sánh: nếu ablation giờ cho F1 < 1.0 trên các config drop-feature → dataset đã đủ khó

## 3. Effort

| Task | Thời gian | Code changes |
|------|-----------|-------------|
| Sửa pool size | 5 phút | 1 tham số |
| Noise injection | 30 phút | Thêm vào `attack_simulator.py` hoặc `build_session_dataset.py` |
| Retrain | 5 phút | `uv run python train/train_branch3.py` |
| Re-run ablation | 5 phút | `uv run python train/run_ablation_branch3.py` |
| **Tổng** | **~45 phút** | **~50 dòng code** |

## 4. Rủi ro

| Rủi ro | Khả năng | Giảm thiểu |
|--------|----------|------------|
| Noise quá nhỏ → ablation vẫn F1=1.0 | Cao | Tăng noise σ dần đến khi ablation phân hóa |
| Noise quá lớn → GRU không học được | Thấp | σ bắt đầu 0.01, test trên validation |
| pool 5000 users chậm | Thấp | ~350K steps, vẫn chạy trong 2-3 phút |

## 5. Output sau khi chạy

- `report/metrics/branch3_eval_v2.json` — eval mới
- `report/metrics/branch3_ablation_v2.json` — ablation mới
- So sánh ablation cũ (F1=1.0 everywhere) vs mới (kỳ vọng có config fail)
- Nếu ablation vẫn F1=1.0 → chứng minh dataset vấn đề cơ bản, cần Cách B

## 6. Khi nào làm

Sau khi đọc 2 plan, nếu muốn kết quả nhanh để đánh giá → chọn Plan A.
