# Phase 1: Data Generation

> **Master plan**: [plan.md](plan.md)
>
> **Context**: [branch3_context.md](branch3_context.md)

---

## Mục tiêu

Tạo raw session data bằng cách chạy **thuật toán bisection thật** vào
`deploy/demo_db.py`. Mỗi session là một chuỗi request có order thật (không
xáo trộn, không synthetic).

---

## Input / Output

```
Input:
  deploy/demo_db.py              ← database giả (có ASCII/SLEEP)
  configs/config.yaml (new)      ← tham số: số session, pool size, ...

Process:
  train/attack_simulator.py      ← chạy bisection, ghi CSV
  ↓
  boolean session: query thay đổi row_count (0 vs >0)
  time session:    query thay đổi timing (nhanh vs SLEEP 5s)
  benign session:  SELECT hợp lệ, ko có dấu hiệu tấn công

Output:
  data/raw/branch3_sessions/
    boolean_blind_train.csv      ← N boolean sessions (train split)
    boolean_blind_test.csv       ← N boolean sessions (test split)
    time_blind_train.csv         ← N time sessions (train split)
    time_blind_test.csv          ← N time sessions (test split)
    benign_train.csv             ← N benign sessions (train split)
    benign_test.csv              ← N benign sessions (test split)

  Mỗi CSV có schema:
    session_id | step_idx | class | query | row_count | timing_seconds

  Files code mới:
    train/attack_simulator.py
    tests/test_attack_simulator.py
```

---

## Luồng xử lý chi tiết

### Bước 1 — Chuẩn bị

```
deploy/demo_db.py
  └── users table: id, username, email, password, role
  └── SQLite extensions: ASCII(), SLEEP()  ← đã có sẵn
```

Tạo user pool giả để đa dạng hóa ground-truth:

```
generate_synthetic_user_pool(n=5000)
  → 5000 user, mỗi user có password random 6-12 ký tự
  → dùng riêng cho training data (KHÔNG dùng seed 5 user của demo DB)
```

### Bước 2 — Sinh boolean-blind session

```
Với mỗi target_user i trong synthetic_pool[0:N]:
  char_idx = 1
  low = 32, high = 126  (ASCII printable range)

  WHILE char_idx <= len(target_user.password):
    mid = (low + high) // 2
    query = "zzz' OR (ASCII(SUBSTR(password,{char_idx},1)) > {mid}) --"
    row_count = demo_db.execute(query)  ← thực thi thật

    IF row_count > 0:
      low = mid + 1          ─┐
    ELSE:                      ├─ bisection narrowing
      high = mid             ─┘

    IF low >= high:
      print(f"Char {char_idx} = {chr(low)}")
      char_idx += 1
      low, high = 32, 126    ← reset cho ký tự tiếp theo

  → 1 session = ~7 requests/char × ~8 chars = ~56-84 requests
  → Ghi CSV: (session_id, 1, boolean_blind, query, row_count, time)
```

**Cơ chế "oracle"**: boolean-blind dùng **row_count** — nếu đúng, WHERE đúng
với mọi dòng → trả về >0 rows. Nếu sai, WHERE vẫn sai → 0 rows.

### Bước 3 — Sinh time-blind session

Giống boolean-blind, nhưng câu query khác:

```
query = "zzz' OR (SELECT CASE WHEN (ASCII(SUBSTR(password,{i},1))>{mid}) THEN SLEEP(5) ELSE 0 END) --"
```

**Oracle**: thời gian thực thi.
- SLEEP(5) được gọi → ~5 giây → "đúng"
- SLEEP không được gọi → ~1ms → "sai"

→ Ghi CSV với `timing_seconds` là thời gian thực tế.

### Bước 4 — Sinh benign session

```
Với mỗi user trong user_pool:
  query = "SELECT * FROM users WHERE username = '{real_username}'"
  → 1 dòng trả về (hợp lệ)

  gap = random.uniform(10, 120)  ← người gõ chậm, 10-120s giữa các lần
```

Mỗi benign session: 5-15 request, gap ngẫu nhiên.

### Bước 5 — Verify diversity

Từ boolean-blind session, extract (target_user, target_column, char_index,
char_value). Đếm distinct combinations → phải > 90% số session.

Nếu 5000 user pool mà chỉ có 5 distinct traces → memorization trap.

---

## Files cụ thể

### `train/attack_simulator.py` — cấu trúc

```
train/attack_simulator.py
│
├── generate_synthetic_user_pool(n, password_len_range)
│     → list[dict{username, password}]
│
├── BooleanBlindAttacker
│   ├── __init__(db_connection, target_user, column)
│   ├── bisect_char(char_idx) → list[dict{query, row_count}]
│   └── run() → list[dict{step_idx, query, row_count, timing}]
│
├── TimeBlindAttacker
│   ├── __init__(db_connection, target_user, column, sleep_sec)
│   ├── bisect_char(char_idx) → list[dict{query, timing}]
│   └── run() → list[dict{step_idx, query, row_count, timing}]
│
├── BenignSessionGenerator
│   ├── __init__(db_connection, user_pool)
│   └── generate(n_steps) → list[dict{step_idx, query, row_count}]
│
├── generate_all_sessions(
│       output_dir,
│       n_train_per_class,
│       n_test_per_class,
│       user_pool,
│       random_seed=42,
│   ) → dict{report}
│     ├── Sinh boolean N_train + N_test session
│     ├── Sinh time N_train + N_test session
│     ├── Sinh benign N_train + N_test session
│     └── Verify diversity
│
└── load_raw_sessions(path) → pd.DataFrame
```

### `configs/config.yaml` — section mới

```yaml
branch3_session:
  data_generation:
    user_pool_size: 5000
    password_min_len: 6
    password_max_len: 12
    boolean_blind:
      sessions_per_split: 200       # 200 train + 200 test
      max_extract_chars: 8          # tối đa 8 ký tự đầu (password thường 6-12)
    time_blind:
      sessions_per_split: 200
      sleep_seconds: 5
    benign:
      sessions_per_split: 200
      min_steps: 5
      max_steps: 15
      gap_seconds: [10, 120]
    random_seed: 42
```

### `tests/test_attack_simulator.py`

```
test_generate_synthetic_user_pool():
  pool = generate_synthetic_user_pool(100)
  assert len(pool) == 100
  assert all(len(u["password"]) >= 6 for u in pool)

test_boolean_session_not_empty():
  sess = BooleanBlindAttacker(db, user, "password").run()
  assert len(sess) > 0
  assert all("ASCII" in s["query"] for s in sess)

test_time_session_has_timing_variance():
  sess = TimeBlindAttacker(db, user, "password", 0.01).run()
  timings = [s["timing"] for s in sess]
  assert max(timings) > min(timings) * 2  # có nhanh có chậm

test_diversity_ratio():
  stats = verify_diversity(sessions)
  assert stats["distinct_ratio"] > 0.90
```

---

## Đầu ra (checklist)

- [ ] `train/attack_simulator.py` — bisection attack code
- [ ] `tests/test_attack_simulator.py` — unit tests
- [ ] `configs/config.yaml` (sửa) — `branch3_session.data_generation`
- [ ] `data/raw/branch3_sessions/boolean_blind_train.csv`
- [ ] `data/raw/branch3_sessions/boolean_blind_test.csv`
- [ ] `data/raw/branch3_sessions/time_blind_train.csv`
- [ ] `data/raw/branch3_sessions/time_blind_test.csv`
- [ ] `data/raw/branch3_sessions/benign_train.csv`
- [ ] `data/raw/branch3_sessions/benign_test.csv`

## Verification

- [ ] `uv run pytest tests/test_attack_simulator.py -q` green
- [ ] 1 boolean session: có cả step row_count=0 và row_count>0
- [ ] 1 time session: có cả step nhanh (~ms) và step chậm (~sleep_seconds)
- [ ] 1 benign session: tất cả step đều row_count=1
- [ ] Distinct traces > 90% (không memorization)

## Next phase

→ [Phase 2: Feature Engineering](./phase_02_feature_engineering.md)
