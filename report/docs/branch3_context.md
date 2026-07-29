# Nhánh 3 — Context & History

> File này tổng hợp toàn bộ context về Nhánh 3 (Session-level Sequence Model) để
> người đọc hiểu được: bài toán là gì, ai đã làm gì, file nào còn/đã xóa, và
> hướng dẫn của anh mentor.

---

## 1. Bài toán

Nhánh 3 phát hiện tấn công SQLi ở cấp độ **session** — một chuỗi nhiều request
liên tiếp từ cùng một tác nhân. Lý do cần thiết: các kiểu tấn công **blind SQLi**
(boolean-blind, time-blind) chỉ biểu hiện rõ khi nhìn cả chuỗi request, vì mỗi
bước riêng lẻ trông giống truy vấn hợp lệ.

Cơ chế tấn công blind SQLi theo kiểu **chia đôi (bisection)**, session ~70–80
request dò từng ký tự mật khẩu: giải thích chi tiết ở **Section 4** của
[data_contract.md](../plan/data_contract.md).

---

## 2. Files do mentor (Duc42195) tạo — còn giữ

Mentor code toàn bộ infrastructure cho Nhánh 3. Các file sau **vẫn còn trong
repo** và là tài liệu tham khảo chính:

| File | Vai trò |
|------|---------|
| `deploy/demo_db.py` | Database giả có hàm `ASCII()`, `SLEEP()` dùng làm mục tiêu cho tấn công bisection thật. Đây là nền tảng của Cách B đúng. |
| `report/plan/data_contract.md` (Section 4) | Mô tả cơ chế tấn công bisection, giải thích vì sao session là cần thiết, và cách build dataset đúng. |
| `models/branch3_v1*/metadata.json` (14 variants) | Metadata của 14 model GRU đã train, bao gồm cross-validation, cross-domain (A→B, B→A), hybrid, cached. **Chỉ có metadata, model weights (`.pt`) không được track trong git.** |
| `tests/test_attack_simulator.py` | Test cho attack_simulator (file source đã xóa). **Hiện tại bị orphan — cần xóa hoặc phục hồi code.** |

### Các model variant — trạng thái hiện tại

| Model | Tác giả | Trạng thái |
|-------|---------|-----------|
| `models/branch3_v1/` | **Mentor** (Duc42195, `b658085`) | ✅ Giữ — mentor train |
| `models/branch3_v1_cachA_baseline/` | **Bách** (`1e8c150`) | ❌ Đã xóa |
| `models/branch3_v1_cachB_only/` | **Bách** (`1e8c150`) | ❌ Đã xóa |
| `models/branch3_v1_cachB_4class/` | **Bách** (`1e8c150`) | ❌ Đã xóa |
| `models/branch3_v1_cachB_4class_v3/` | **Bách** (`1e8c150`) | ❌ Đã xóa |
| 7 hybrid/cross variants còn lại | **Bách** (`1e8c150`) | ❌ Đã xóa |

Chỉ giữ `models/branch3_v1/` (mentor). 13 variant do Bách train trên Cách A / Cách B
đã bị xóa.

---

## 3. Files do chúng ta (AI + Bách) tạo — đã xóa

Toàn bộ file Nhánh 3 do chúng ta viết đã bị xóa trong commit `0cb33ac`
(`remove/redundant-files`) và `dba3c38` (`update-and-remove-file`).

### Source code (xóa hết)

| File | Tác giả gốc | Ghi chú |
|------|-------------|---------|
| `train/attack_simulator.py` | Mentor | Mô phỏng tấn công bisection thật vào demo_db |
| `train/train_branch3.py` | Mentor | Train GRU trên session dataset |
| `train/build_session_dataset.py` | Mentor | Build session dataset từ labeled queries |
| `train/eval_branch3_hard.py` | Mentor | Evaluation trên hard test set |
| `src/models/branch3_session.py` | Mentor | GRU model definition |
| `src/models/branch3_features.py` | Mentor | Feature extraction cho session |
| `deploy/routers/branch3.py` | Mentor | FastAPI router cho B3 |
| `tests/test_branch3_session.py` | Mentor | Unit test |
| `train/capture_sqlmap_sessions.py` | Mentor | Capture session từ sqlmap + Docker |
| `train/branch3_lr_features.py` | Bách | LogisticRegression feature engineering |
| `train/compare_gru_vs_lr.py` | Bách | So sánh GRU vs LR |
| `train/compare_branch3_architectures.py` | Bách | So sánh multiple architectures |
| `train/run_ablation_branch3.py` | Bách | Ablation study |
| `train/analyze_cach_b_signal.py` | Bách | Analyze sequence signal trong Cách B |

### Data files (xóa hết)

```
data/processed/branch3_sessions_cach_a.csv
data/processed/branch3_sessions_cach_b.csv
data/processed/branch3_sessions_cach_b_v2.csv
data/processed/branch3_sessions_cach_b_wrapped.csv
data/processed/nhanh3_session_data.csv
data/processed/nhanh3_session_data_cachb.csv
data/raw/nhanh3_sqlmap_sessions/
```

### Report & Docs (xóa hết)

```
report/docs/branch3_context.md         — Context cũ (chính file này đang được viết lại)
report/docs/branch3_status.md          — Status report
report/plan/nhanh3_prototype_compare.md
report/plan/nhanh3_cach_a_expand.md
report/plan/nhanh3_cach_b_sqlmap.md    — Hướng dẫn Cách B từ mentor
report/plan/nhanh3_go_plan.md
report/plan/nhanh3_plan.md
report/metrics/branch3_*.json           — 17+ file metrics

train/notebooks/branch3_eval.ipynb      — Mentor
train/notebooks/branch3_shuffle_test.ipynb  — Bách
```

### Deploy references (đã sửa)

- `configs/config.yaml`: xóa `branch3_session:` section
- `deploy/main.py`: gỡ import + router registration
- `deploy/schemas.py`: gỡ `Branch3Response` khỏi `DetectResponse`, `DemoExecuteResponse`
- `deploy/routers/detect.py`: gỡ `run_branch3` + `Branch3Response`, đơn giản `fuse_decision(b1, b2)`
- `deploy/routers/demo.py`: gỡ `run_branch3`
- `deploy/routers/data.py`: gỡ `branch3` khỏi annotation pools
- `deploy/tasks.py`: gỡ `branch3` khỏi `VALID_TASKS`, `label_options`
- `app/ui.py`: gỡ `render_branch3`, `branch3` khỏi `TASKS`
- `app/streamlit_app.py`: gỡ call `render_branch3`
- `app/api_client.py`: gỡ `branch3_session`
- `app/state.py`: gỡ `branch3` khỏi type hint
- `tests/test_api.py`: gỡ `test_branch3_session_ready`, `branch3` khỏi health check
- `tests/test_app_pages.py`: gỡ `branch3` khỏi test data

---

## 4. Hướng dẫn từ anh mentor (nguyên văn)

> xong e cày nhánh 3 hộ a
>
> **Nhánh 3 là gì — giải thích từ đầu**
>
> ### 4.1 Từ ngữ cần hiểu trước
>
> | Từ | Nghĩa đơn giản |
> |-----|---------------|
> | Trường nhập | Ô trên giao diện web mà người dùng gõ chữ vào (ví dụ ô "Tên đăng nhập") |
> | Backend | Code chạy trên server, nhận chữ người dùng gõ, rồi xây câu lệnh SQL để hỏi database |
> | DBMS | Phần mềm quản lý database (SQLite, MySQL...) — nó chỉ biết chạy đúng câu lệnh nó nhận được, không biết phần nào là do người dùng gõ, phần nào là code gốc |
> | Nối chuỗi (concatenation) | Cách backend dán thẳng chữ người dùng gõ vào giữa câu lệnh SQL dạng văn bản, không kiểm tra an toàn — đây chính là lỗ hổng |
> | SQL Injection | Khi kẻ tấn công gõ vào ô nhập một chuỗi đặc biệt khiến câu lệnh SQL bị đổi nghĩa sau khi nối chuỗi |
> | Session (phiên) | Một chuỗi nhiều lần gửi request liên tiếp từ cùng một kẻ tấn công |
> | Boolean-blind | Kiểu tấn công dò dữ liệu bí mật (như mật khẩu) mà không nhìn thấy dữ liệu trực tiếp — chỉ đoán qua việc "trang có trả kết quả hay không" |
> | Time-blind | Giống trên, nhưng đoán qua trang trả lời nhanh hay chậm thay vì nội dung trang |
> | Chia đôi (bisection) | Cách dò một con số bằng cách liên tục hỏi "lớn hơn X không?" rồi thu hẹp phạm vi dần — giống trò chơi đoán số |
>
> ### 4.2 Trên giao diện → attacker nhập gì → DBMS chạy ra sao
>
> Dùng đúng ví dụ trong code hiện có (`deploy/demo_db.py`): bảng users có
> cột `id`, `username`, `email`, `password`, `role`.
>
> Trên giao diện: chỉ có 1 ô nhập — "Tên đăng nhập".
>
> Backend (có lỗ hổng) xây câu SQL bằng cách nối chuỗi:
>
> ```sql
> SELECT * FROM users WHERE username = '<chữ người dùng gõ>'
> ```
>
> **Trường hợp bình thường** — người dùng gõ `admin`:
>
> ```sql
> SELECT * FROM users WHERE username = 'admin'
> ```
> → DBMS chạy, trả về đúng 1 dòng (thông tin của admin).
>
> **Trường hợp bị tấn công** — attacker gõ vào ô đó: `zzz' OR (1=1)--`
>
> Backend nối chuỗi y nguyên, không kiểm tra gì cả, ra câu lệnh:
>
> ```sql
> SELECT * FROM users WHERE username = 'zzz' OR (1=1)--'
> ```
>
> DBMS không biết đoạn `zzz' OR (1=1)--` là do attacker gõ vào — với nó, đây
> chỉ là một câu lệnh SQL bình thường. Vì `1=1` luôn đúng, nên WHERE đúng với
> MỌI dòng → DBMS trả về TẤT CẢ các dòng, kể cả password của admin.
>
> ### 4.3 Từ ví dụ đơn giản → cách dò từng ký tự mật khẩu (boolean-blind)
>
> Attacker muốn biết mật khẩu của `bob`, nhưng trang không hiển thị cột
> password. Attacker chỉ biết được "trang có trả dòng nào không" (1 bit/lần).
>
> Thay vì hỏi `1=1` (luôn đúng), attacker hỏi một câu liên quan tới mật khẩu:
>
> ```sql
> zzz' OR (ASCII(SUBSTR(password,1,1)) > 79) --
> ```
>
> Dịch: "Mã ASCII của ký tự đầu tiên trong password của bob có lớn hơn 79 không?"
>
> Nếu đúng → WHERE đúng với mọi dòng → trả về nhiều dòng (leak).
> Nếu sai → WHERE vẫn sai → trả về 0 dòng.
>
> Attacker lặp lại theo kiểu chia đôi:
>
> ```
> Hỏi 1: > 79?   → ĐÚNG  → ký tự trong (79, 126]
> Hỏi 2: > 103?  → SAI   → ký tự trong (79, 103]
> Hỏi 3: > 91?   → SAI   → ký tự trong (79, 91]
> Hỏi 4: > 85?   → SAI   → ký tự trong (79, 85]
> Hỏi 5: > 82?   → ĐÚNG  → ký tự trong (82, 85]
> Hỏi 6: > 84?   → SAI   → ký tự trong (82, 84]
> Hỏi 7: > 83?   → SAI   → ký tự = 83 = chữ 'S'
> ```
>
> ~7 lần hỏi / ký tự (ASCII có ~94 giá trị, chia đôi 7 lần). Toàn bộ chuỗi
> ~70–80 lần hỏi là một **session** tấn công.
>
> **Time-blind** giống hệt, chỉ khác câu hỏi:
>
> ```sql
> zzz' OR (SELECT CASE WHEN (ASCII(SUBSTR(password,1,1))>79) THEN SLEEP(5) ELSE 0 END) --
> ```
>
> Attacker đo thời gian trả lời: chờ 5s = đúng, trả lời ngay = sai.
>
> ### 4.4 Vì sao phải làm dataset kiểu này mới "có cơ sở khoa học"
>
> Vì mỗi câu hỏi trong chuỗi **phụ thuộc vào kết quả câu trước** (chia đôi
> dần), nên không thể tự bịa ra chuỗi số ngẫu nhiên rồi gọi là "session tấn
> công" — nó sẽ không phản ánh đúng cách tấn công thật (đây chính là lỗi tôi
> mắc phải lúc đầu: lấy ngẫu nhiên các câu tấn công có sẵn, không liên quan).
>
> Cách làm đúng:
>
> 1. Dựng database giả — dùng luôn `deploy/demo_db.py` có sẵn trong dự án.
> 2. Viết code đóng vai kẻ tấn công thật sự — chạy thuật toán chia đôi, gửi
>    từng câu lệnh thật vào database, nhận kết quả thật (số dòng trả về hoặc
>    thời gian). Cần thêm `SLEEP()` vào SQLite vì nó không có sẵn.
> 3. Ghi lại toàn bộ chuỗi ~70–80 câu lệnh theo đúng thứ tự → 1 session.
> 4. Lặp lại với nhiều "nạn nhân" giả (100 user, mật khẩu ngẫu nhiên) để có
>    session đa dạng, không lặp lại.
> 5. Mỗi câu lệnh được đưa qua Nhánh 1 (chấm điểm) và Nhánh 2 (chấm điểm) —
>    lấy điểm số thật, không phải nhãn.
> 6. Đưa chuỗi điểm số vào Nhánh 3 (GRU) để học: "chuỗi điểm số biến đổi theo
>    kiểu này, qua ~70 bước, khớp với mẫu hình tấn công loại nào?"
>
> Điểm mấu chốt: **Nhánh 3 không đọc câu SQL** — nó chỉ nhìn dãy điểm số từ
> Nhánh 1/Nhánh 2, rồi học cách nhận ra mẫu hình theo thời gian.

---

---

## ⚠️ Cách A vs Cách B — Terminology tự đặt, không phải của mentor

**"Cách A"** (synthetic session: ghép query ngẫu nhiên từ HF dataset) và
**"Cách B"** (sqlmap + Docker capture) là **tên do chúng ta (AI + Bách) tự đặt**
để phân biệt 2 hướng tiếp cận. **Mentor không yêu cầu, không dùng từ này, và
không liên quan.**

Hướng duy nhất mentor nói trong note (Section 4) là:
> *"Dựng một database giả — dùng luôn `deploy/demo_db.py` đã có sẵn trong dự
> án. Viết code đóng vai kẻ tấn công thật sự — chạy đúng thuật toán chia đôi."*

Đây chính là `train/attack_simulator.py` do mentor tạo (đã xóa). Mentor không
gọi nó là Cách gì cả. Khi build lại Nhánh 3, **chỉ nên theo hướng này** — bỏ
qua Cách A và Cách B.

## 5. Cách A của mentor (commit `b658085`) — cũng bị chính mentor nói là sai

Mentor tạo `branch3_v1/` bằng Cách A (lấy query từ HF dataset, ghép session).
Nhưng ngay trong commit message, ổng tự nhận:

| Ổng nói | Dịch |
|---------|------|
| *"misleadingly easy"* | Kết quả dễ một cách đánh lừa |
| *"GRU's job reduces to aggregate an already-correct bag of labels"* | GRU chỉ việc đếm nhãn — không học sequence |
| *"trivially-easy data, not a real signal"* | Data dễ quá mức, không phải tín hiệu thật |
| *"Same failure mode the project already hit once with Branch 1's stacked class"* | Lặp lại lỗi cũ của B1 |

Vì `build_session_dataset.py` lấy các câu tấn công boolean_blind/time_blind từ
HF — mà B1 đã bắt đúng hầu hết từng câu → chuỗi điểm số gần như toàn 1 →
GRU chỉ học "thấy 1 nhiều thì là attack", không cần nhìn sequence.

### Thứ đáng dùng lại từ commit này

**Hard eval** (`train/eval_branch3_hard.py` — đã xóa): dùng
`branch1_no_boolean_blind` (B1 chưa thấy boolean_blind bao giờ, miss 90.2%) để
test B3. Kết quả: B3 vẫn đạt **98.6% recall** trên boolean_blind dù B1 hầu
như không bắt được từng câu. Đây là "first result in the project that actually
demonstrates Branch 3's core claim" — GRU thực sự aggregate weak signal từ B2
thành session-level decision.

Vì vậy khi build lại: **không dùng lại code Cách A của mentor**, nhưng nên
**tái hiện methodology hard eval** — tạo B1 variant thiếu 1 class, test xem B3
có recover được không.

## 6. Kết luận & khuyến nghị

- **Cơ sở khoa học của Nhánh 3 đã được mentor chứng minh** qua Section 4 của
  `data_contract.md` — session-level detection dùng bisection attack với DB thật.
- **Toàn bộ code Nhánh 3 đã bị xóa** để làm lại từ đầu.
- **Mentor đã train sẵn 14 model GRU** (metadata trong `models/branch3_v1*/`)
  — cần tải model weights từ HF (`Jason-42195/VNU-SQLi-Detection-Models`)
  nếu muốn dùng lại.
- **File `tests/test_attack_simulator.py`** đang bị orphan (import file đã xóa).
- **Hướng dẫn chi tiết từ mentor** ở Section 4 để build dataset đúng cách.
