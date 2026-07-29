# Plan Nhánh 3 — Session-Level Sequence Model

## 1. Nhánh 3 là gì?

Nhánh 3 là một **mạng GRU** học cách phân loại **cả một chuỗi request** (session) — không nhìn từng câu riêng lẻ. Nó chỉ nhìn vào **dãy điểm số** từ Nhánh 1 (5-class probabilities) và Nhánh 2 (anomaly score) của mỗi bước trong session, rồi học nhận ra mẫu hình tấn công theo thời gian.

## 2. Kiến trúc

```
Input (mỗi bước trong session): [P_normal, P_union, P_error, P_boolean, P_time, anomaly_score, gap_seconds]
→ GRU (1 layer, hidden=32) → Linear(32, 4) → softmax → session label

Output: benign (0) | boolean_blind (1) | time_blind (2) | query_splitting (3)
```

- 7 features/bước: 5 xác suất Nhánh 1 + 1 anomaly score Nhánh 2 + 1 log1p(gap_seconds)
- Session tối đa 64 bước
- GRU 1 lớp, hidden_dim=32

## 3. Từ đầu — cách tấn công hoạt động

### 3.1. Lỗ hổng nối chuỗi

Backend dán thẳng input người dùng vào câu SQL:
```sql
SELECT * FROM users WHERE username = '<input>'
```

Người dùng gõ `admin` → câu SQL bình thường.
Người dùng gõ `zzz' OR (1=1)--` → câu SQL thành:
```sql
SELECT * FROM users WHERE username = 'zzz' OR (1=1)--'
```
→ DBMS thấy `OR (1=1)` luôn đúng → trả về tất cả dòng.

### 3.2. Boolean-blind — dò từng ký tự mật khẩu

Attacker không thấy dữ liệu trực tiếp, chỉ biết "trang có trả dòng không?" (đúng/sai = 1 bit).

Hỏi: `zzz' OR (ASCII(SUBSTR(password,1,1)) > 79)--`
- Đúng (có dòng trả về) → ký tự ASCII > 79
- Sai (0 dòng) → ký tự ASCII ≤ 79

Dùng **chia đôi (bisection)** để dò chính xác trong ~7 lần hỏi / ký tự:
```
Hỏi >79?  → ĐÚNG → (79, 126]
Hỏi >103? → SAI  → (79, 103]
... ~7 lần → ra ký tự 'S'
```

Toàn bộ session dài ~70-80 request, mỗi request phụ thuộc vào kết quả request trước.

### 3.3. Time-blind — dùng thời gian thay vì nội dung

Giống boolean-blind, nhưng thay vì nhìn nội dung:
```sql
zzz' OR (SELECT CASE WHEN (ASCII(SUBSTR(password,1,1))>79) THEN SLEEP(5) ELSE 0 END)--
```
- Chờ 5 giây → đúng
- Trả lời ngay → sai

## 4. Dataset — vì sao phải chạy thật, không lấy ngẫu nhiên?

Vì mỗi câu hỏi **phụ thuộc vào kết quả câu trước** (thuật toán chia đôi), nên không thể tự bịa chuỗi số ngẫu nhiên.

Cách đúng:
1. Dùng `deploy/demo_db.py` làm database giả
2. Viết code (`attack_simulator.py`) đóng vai attacker — chạy thuật toán chia đôi thật, gửi SQL thật vào database giả, nhận kết quả thật
3. Ghi lại toàn bộ ~70-80 câu lệnh theo thứ tự — đó là 1 session
4. Tạo nhiều user giả có mật khẩu khác nhau (synthetic pool 100 user) để session đa dạng, không bị memorization trap
5. Mỗi câu lệnh cho qua Nhánh 1 + Nhánh 2 lấy điểm số thật
6. Đưa chuỗi điểm số đó vào GRU để học mẫu hình

## 5. Các file chính cần build

| File | Vai trò |
|------|---------|
| `train/attack_simulator.py` | Code đóng vai attacker — chạy bisection thật, gửi SQL vào demo_db, ghi log |
| `train/build_session_dataset.py` | Dùng attack_simulator tạo N session cho mỗi lớp, chạy Nhánh 1+2 inference, xuất CSV |
| `src/models/branch3_features.py` | Helpers: tính Branch 1 probabilities, nhóm session, evaluate |
| `src/models/branch3_session.py` | GRU model class (SessionSequenceDetector) |
| `train/train_branch3.py` | Train + eval GRU, save model + metrics |
| `train/eval_branch3_hard.py` | Hard-mode test: boolean_blind session scored bằng model zero-day |
| `tests/test_branch3_session.py` | Unit test cho GRU |
| `deploy/routers/branch3.py` | API stub cho Nhánh 3 |
| `reports/metrics/branch3_eval.json` | Kết quả eval |

## 6. Flow đầy đủ

```
1. attack_simulator.py
   ├── run_benign_session()       — user tra cứu bình thường
   ├── run_boolean_blind_session()— dò password qua boolean oracle
   └── run_time_blind_session()   — dò password qua timing oracle
   
2. build_session_dataset.py
   ├── Gọi attack_simulator sinh N session/lớp
   ├── Chạy Branch 1 (TF-IDF+LogReg) → 5 probabilities/bước
   ├── Chạy Branch 2 (OCSVM) → 1 anomaly score/bước
   └── Ghi CSV: session_id, step_index, branch1_prob_*, branch2_score, gap_seconds, label

3. train_branch3.py
   ├── Đọc CSV → nhóm thành sequences
   ├── Train GRU (input_dim=7, hidden=32, 4 classes, 30 epochs)
   └── Save model + eval JSON

4. eval_branch3_hard.py
   └── Re-score boolean_blind steps với branch1_no_boolean_blind (model zero-day)
```

## 7. Lưu ý từ mentor

- **Không lấy ngẫu nhiên (sample) các câu tấn công có sẵn rồi ghép thành "session"** — đó là lỗi đã mắc phải lúc đầu, session không phản ánh đúng cách tấn công thật.
- **Phải chạy real bisection** — mỗi câu trong chuỗi phụ thuộc vào kết quả câu trước.
- **Synthetic user pool phải đủ lớn** (100 user) — 5 user lặp lại 70 lần = memorization trap.
- **SQLite không có SLEEP()** — phải tự thêm cho time-blind.
- **Time-blind bị Nhánh 1 chặn ~100%** (vì có `SLEEP()` literal) — trong production không bao giờ tới được Nhánh 3.
- **Branch 3 không đọc câu SQL** — chỉ nhìn dãy điểm số từ Nhánh 1 + Nhánh 2, học mẫu hình thời gian.
