# Thiết kế Branch 3 — Session Correlator (bản xoá hẳn GRU)

> Tổng hợp từ `report/plan/data_contract.md` §4.0–4.2 + `src/models/branch3_session.py` + `train/calibrate_branch3.py` + `deploy/routers/branch3.py` + bản viết lại của mentor (thứ tự Decision Engine, đổi tên Session Correlator).
> Mục đích: hình dung **hệ thống hiện tại** dễ dàng (nhiều mermaid). Không phải doc chính — doc chính vẫn là `data_contract.md §4.2`.

---

## 0. Vị trí hệ thống — DB Proxy

```mermaid
flowchart LR
    REQ["Request"] --> BE["Backend build SQL"]
    BE --> PROXY["DB PROXY — hệ thống này"]
    PROXY --> DB["Database"]
```

Proxy nhận câu SQL **sau khi backend build xong**, trước khi tới DB thật. Toàn bộ 3 nhánh chạy ngay tại đây trên từng câu `query`.

## 0.1. Canonicalization (đầu vào chung)

Mọi query đi qua đều được chuẩn hóa trước (`src/preprocessing/canonicalize.py`): giải mã encoding (URL/hex/CHAR()), chuẩn hóa hoa/thường từ khóa SQL, đánh dấu (không xóa) comment `/* *//*--`. Kết quả `query_canonical` là input chung cho cả 3 nhánh.

---

## 1. Thứ tự các lớp — Nhánh 1 → Nhánh 2 → Session Correlator (lớp CUỐI)

Branch 1 và Branch 2 chạy **real-time, theo từng câu**, ngay khi request tới. Session Correlator (Branch 3) là **lớp cuối cùng**, xét trên kết quả tích lũy của Branch 1 + Branch 2 qua **nhiều câu trong cùng session** → về mặt kiến trúc nó nằm SAU 2 nhánh kia, không chạy song song hay trước.

```mermaid
flowchart LR
    subgraph PerQuery ["Chạy real-time, từng câu"]
        B1["Branch 1<br/>Supervised multi-class<br/>TF-IDF + LogReg<br/>5 lớp → label + attack_prob<br/>F1-macro 0.982"]
        B2["Branch 2<br/>Anomaly (One-Class SVM)<br/>4 đặc trưng thống kê<br/>chỉ train benign → score<br/>AUC 0.90"]
    end
    subgraph Session ["Lớp cuối — cả session"]
        B3["Session Correlator (Branch 3)<br/>content OR behavior<br/>xét kết quả TÍCH LŨY của B1+B2"]
    end
    subgraph Decision ["Decision engine"]
        D["fuse_decision →<br/>BLOCK / OVERKILL / ALLOW"]
    end

    B1 --> B3
    B2 --> B3
    B1 --> D
    B2 --> D
    B3 --> D
```

> **Bảng quyết định (thứ tự 3 lớp, đúng bản mentor):**

| Nhánh 1 (từng câu) | Nhánh 2 (từng câu) | Session Correlator (cả session) | Hành động |
|---|---|---|---|
| lớp tấn công | — (chưa xét tới) | — (chưa cần xét) | **BLOCK** ngay câu đó, ghi log |
| normal | anomaly = 1 | — (chưa cần xét) | **OVERKILL** — giữ lại chờ Admin xác nhận; hết giờ → deny mặc định |
| normal | anomaly = 0 | phát hiện session là tấn công (content **hoặc** behavior fire) | **BLOCK/OVERKILL cả session** — leo thang dù từng câu riêng lẻ đã "sạch" |
| normal | anomaly = 0 | session sạch (hoặc chưa đủ dữ liệu) | **ALLOW** |

Nói cách khác: B1 và B2 quyết định số phận **từng câu** ngay lập tức; Session Correlator là lớp giám sát bổ sung phía sau, có quyền **lật ngược** quyết định "cho qua" của 1 câu nếu nhìn vào cả bối cảnh session mới thấy là tấn công.

> **Ghi chú kỹ thuật (không đổi ý nghĩa logic):** trong code thật `fuse_decision()` (deploy/routers/detect.py:40), Session Correlator được kiểm tra **trước tiên trong hàm** — đây chỉ là tối ưu short-circuit để trả kết quả sớm, không thay đổi thứ tự logic: nó vẫn là lớp xét **trên kết quả tích lũy** của B1+B2.

> **Điểm mấu chốt (Finding 2):** Branch 1 chặn mọi query có `attack_prob ≥ 0.5` (decision_threshold) ngay ở tầng đơn-query → Session Correlator chỉ "đáng nghĩ tới" cho session mà Branch 1 **không nhận ra per-query** (như boolean_blind bị blind). `time_blind` (chuỗi `SLEEP()`) bị Branch 1 bắt ~100% ở request #1 → thực tế không bao giờ chạm tới Branch 3.

---

## 2. Kiến trúc Session Correlator — cơ chế ghép, ví dụ cụ thể

> **Trả lời trực tiếp câu hỏi "ghép cái gì?":** KHÔNG phải ghép các field trong 1 request. Nó ghép **nhiều query từ nhiều request khác nhau, trải dài trong 1 session** — mỗi request chỉ mang 1 câu SQL. "Session" = 1 chuỗi request liên tiếp của cùng 1 người dùng/IP (gom theo `session_id` hoặc IP + cửa sổ thời gian nghỉ 1800s ≈ 30 phút).

> (Một hướng khác — ghép nhiều field trong **CÙNG 1 request**, như form login có cả username + password cùng vào 1 câu `WHERE` — đã thử riêng trong Experiment A1 và thấy **KHÔNG cần**: từng field kiểm tra riêng lẻ đã bắt được payload (0.87–0.99 attack probability), nên cơ chế đó không được đưa vào Session Correlator.)

**Ví dụ cụ thể** với DB demo (`deploy/demo_db.py`), bảng `users(id, username, email, password, role)`, backend build kiểu `SELECT * FROM users WHERE username = '{input}'`. Kẻ tấn công muốn lấy password của `alice` bằng **boolean-blind** — không thể làm trong 1 request, phải dò từng bit qua rất nhiều request, tất cả thuộc cùng 1 session:

- **Request 1** (dò độ dài): `zzz' OR ((SELECT LENGTH(password) FROM users WHERE username='alice') > 8)--`
- **Request 2-4...** (nhị phân dò độ dài): `> 4, > 6, > 7...` cho tới khi xác định đúng độ dài (vd: 10 ký tự).
- **Từ request ~5** (dò từng ký tự bằng ASCII, ~7 request/ký tự): `zzz' OR ((SELECT ASCII(SUBSTR(password,1,1)) FROM users WHERE username='alice') > 100)--`, rồi `> 108`, `> 104`... đến khi xác định đúng ký tự đầu, rồi sang ký tự 2...
- Một session hoàn chỉnh có thể lên tới **30+ request riêng lẻ**, mỗi request là 1 dòng trong log của Nhánh 1/Nhánh 2.

```mermaid
flowchart TD
    S["Một session<br/>(danh sách query theo thứ tự thời gian)"]

    S -->|"nối (concatenate) TOÀN BỘ text"| CC
    S -->|"score từng query bằng Branch 2"| BC

    subgraph CC ["Content Check — Branch 1"]
        C1["canonicalize từng query"]
        C2["concat → 1 chuỗi text dài"]
        C3["branch1_v1 (như cũ, không retrain)<br/>→ attack_prob = 1 − P(normal)"]
        C4{"attack_prob ≥ content_threshold?"}
        C1 --> C2 --> C3 --> C4
    end

    subgraph BC ["Behavior Check — Branch 2"]
        B1a["branch2_v1 score mỗi query<br/>(round 6 số, chống FP)"]
        B2a["mean_score<br/>& fraction_above<br/>(phần query > per_query_threshold)"]
        B3a{"mean ≥ mean_threshold<br/>HOẶC<br/>fraction ≥ fraction_threshold?"}
        B1a --> B2a --> B3a
    end

    CC --> F
    BC --> F

    F["fires_content OR fires_behavior?"]
    F -->|Có| ATTACK["is_attack = true<br/>session_label = class / anomalous_session"]
    F -->|Không| OK["is_attack = false → benign"]
```

**Vì sao OR, không dựa 1 check:** mỗi check bù blind-spot cho check kia
- **Content check** bắt: text trông "lexically attack" nhưng cấu trúc không nổi bật (VD probe boolean_blind yếu, từng bước 0.44–0.47 dưới ngưỡng đơn-query, nhưng **nối nhiều bước** sẽ đẩy lên).
- **Behavior check** bắt: text trông mơ hồ về lexical nhưng **cấu trúc lạ** (nested `OR`/subquery → special_char_ratio, keyword_count cao) → dù Branch 1 không nhận class cũng vẫn anomalous.
- **Lỗ hổng thật (đã thú nhận):** kẻ tấn công né **CẢ HAI** — mimic lexical benign + mimic shape benign → không phải lỗi fix được, nằm ở Limitations.

---

## 2.5. Làm rõ "0.5 ăn luôn" vs "0.338 content check" — HAI ngưỡng, HAI tầng

Đây là điểm hay nhầm nhất. Cùng một model `branch1_v1`, **dùng ở 2 chỗ khác nhau với 2 ngưỡng khác nhau** → nhìn tưởng mâu thuẫn, thực ra không.

### Tầng 1 — Per-query (decision engine, live): ngưỡng `0.5`
- `deploy/routers/detect.py:fuse_decision` xét **TỪNG QUERY đơn lẻ**.
- Nếu một query có `attack_prob ≥ decision_threshold (0.5)` → **BLOCK ngay**, Branch 3 **KHÔNG bao giờ được gọi** cho query đó.
- → Câu "B1 prob > 0.5 ăn luôn không cần Branch 3" đúng **ở tầng này**.

### Tầng 2 — Session-level content check (SessionCorrelator): ngưỡng `~0.338`
- Chỉ xảy ra khi **MỌI query riêng lẻ đều < 0.5** — nếu không thì đã bị chặn ở tầng 1 rồi. Nghĩa là session này **đã lọt qua được Branch 1 per-query**.
- Lúc này Branch 3 mới được gọi và content check làm 3 việc:
  1. **Nối (concatenate) TOÀN BỘ text** của session → 1 chuỗi dài (không phải 1 query nữa).
  2. Chạy **cùng `branch1_v1`** lên chuỗi nối đó.
  3. So `attack_prob` với `content_threshold` (~0.338 — calibrate riêng, **THẤP hơn 0.5**).

### Vì sao nối lại giúp ích (trả lời "sao mà tăng lên được?")
Một probe yếu riêng lẻ chỉ 0.44–0.47 (đã < 0.5 nên lọt qua tầng 1). Nhưng một session boolean-blind thật có **2 phase**:
- Phase length-bisection: ~5 bước probe **yếu** (0.44–0.47).
- Phase extract-char: ~7 bước/ký tự probe **mạnh** (0.66–0.70).

Khi nối cả session, các probe **mạnh** (của phase extract) trộn vào → `attack_prob` của chuỗi nối bị **đẩy lên**: 0.593 ở 10 bước, 0.666 ở 32 bước. Vượt ngưỡng 0.338 → content check bắt được session dù từng query đều "quá yếu" để bị chặn riêng.

> ⚠️ Lưu ý chính xác (ghi chính xác hơn trong data_contract §4.2): nếu chỉ nối **đúng các bước yếu** (riêng phase length-bisection, không có probe mạnh) thì sẽ không vượt 0.5 một mình (dừng ở 0.45–0.46). Điều đẩy lên là **có probe mạnh trộn vào**, không phải "nhiều mảnh yếu tích lũy". Chính vì thế mà **Behavior check (Branch 2)** tồn tại — nó bắt được cả trường hợp session chỉ gồm toàn bước yếu (mean_score 2.171 ≫ mean_threshold −4.465).

### Bảng so sánh 2 tầng

| | Tầng 1 (per-query) | Tầng 2 (session content check) |
|---|---|---|
| Nơi chạy | decision engine (`fuse_decision`) | SessionCorrelator |
| Input | **1 query** | **cả session nối thành 1 chuỗi** |
| Model | `branch1_v1` | `branch1_v1` (cùng) |
| Ngưỡng | `0.5` | `~0.338` (calibrate riêng) |
| Khi nào xét | mọi query | chỉ khi mọi query lọt qua tầng 1 |
| Hành động | BLOCK | content check → is_attack |

```mermaid
flowchart TD
    Q["1 query trong session (attack_prob ĐƠN-QUERY)"]
    Q -->|">= 0.5 → chặn ngay<br/>(Branch 3 không gọi)"| B1BLOCK["BLOCK (tầng 1)"]
    Q -->|"< 0.5 → lọt qua tầng 1"| JOIN["Nối CẢ session → chuỗi dài"]
    JOIN --> S1["branch1_v1 trên chuỗi nối<br/>attack_prob (session)"]
    S1 -->|">= content_threshold ≈ 0.338"| CATCH["Content check bắt → is_attack"]
    S1 -->|"< 0.338"| B2C["Behavior check (Branch 2)<br/>mean / fraction"]
    B2C -->|"fires"| CATCH2["is_attack (behavior)"]
    B2C -->|"không fires"| OK["benign"]
```

> Vì `content_threshold` (0.338) < ngưỡng per-query (0.5) nên một session "yếu-toàn-bộ" vẫn có thể bị content check bắt ở **tầng session** — thứ mà bạn không bao giờ bắt được bằng cách chấm từng query riêng lẻ. Đó chính là giá trị của Branch 3.

---

## 3. Vì sao phải "OR" và vì sao nối text lại hoạt động (Finding 1 + Experiment)

```mermaid
sequenceDiagram
    participant R as Request 1..N
    participant B1 as branch1_v1
    participant BR as SessionCorrelator

    Note over R: boolean_blind session của 1 user<br/>phase length-bisect (~5 bước, "yếu") +<br/>phase extract-char (~7 bước/ký tự, "mạnh")
    loop length-bisection
        R->>B1: probe yếu (0.44–0.47 /1 query)
    end
    loop character-extraction
        R->>B1: probe mạnh (0.66–0.70 /1 query)
    end

    BR->>BR: concat toàn bộ N query
    BR->>B1: score trên chuỗi nối dài
    Note right of BR: các probe mạnh trộn vào →<br/>đẩy attack_prob qua 0.5<br/>(0.593 ở 10 bước, 0.666 ở 32)

    BR->>BR: cũng tính behavior check (mean/fraction B2)
```

- **Finding 1 (information bottleneck đã đo):** Branch 1 output là xác suất lớp (lossy), KHÔNG phải content embedding. 2 bước bisection chỉ khác bound (`>79` vs `>103`) có TF-IDF cosine **0.961** nhưng xác suất gần như giống → GRU đọc chuỗi xác suất là sai hướng. SessionCorrelator dùng **text thật** (concat) chứ không dùng chuỗi xác suất.
- **Finding 3 (độ dài session):** session thật có thể **~120 → ~1800 request**, gấp xa `max_session_len=64` của GRU cũ → GRU padded cố định sai hình dạng. SessionCorrelator vô hạn chiều dài.

---

## 4. Session định nghĩa & cách nó được sinh ra (Cách A)

```mermaid
flowchart LR
    subgraph Def ["Session ="]
        D1["session_id có sẵn (CSIC cookie)"]
        D2["hoặc (client_ip + idle_gap ≤ 1800s)"]
    end

    subgraph Gen ["Cách A — sinh data (train/attack_simulator.py)"]
        DB["deploy/demo_db.py<br/>(SQLite + ASCII/SLEEP, self-hosted)"]
        A["attack_simulator<br/>- boolean_blind: oracle = row_count<br/>- time_blind: oracle = elapsed time"]
        POOL["generate_synthetic_user_pool()<br/>100 user (chỉ cho training-data)"]
        POOL --> A
        A --> DB
    end

    subgraph Out ["data/processed/branch3_sessions_cach_a.csv"]
        O["1,400 session = 350/class<br/>1,120 train / 280 test (chia theo session)<br/>4 class: benign, boolean_blind, time_blind, query_splitting"]
    end

    Gen --> Out
```

> **Bài học KHÔNG được lặp lại (AGENTS.md):**
> 1. Phải **execute thật** bisection, không template i.i.d. (bản đầu Cách A → 97% F1 sai lý do).
> 2. Phải dùng pool user LỚN (100) — pool 5 user cố định → chỉ 5 trace lặp ~70 lần → model memorize (memorization trap). Đã verify: 100 user → 100 trace khác nhau.
> 3. `query_splitting` là heuristic (fragment 1 payload thật), vì không có tham số thứ 2 để probe thật — chờ Cách B thay thế.
> 4. **Same-target leakage (audit Day 1 của tôi):** vì train & test cùng pool 100 user + bisection deterministic → 52/~101 target trùng giữa 2 split, ~1633 query trùng → `DR=1.0` là **lạc quan**, cần re-caveat; đây là lý do **Cách B bắt buộc**.

---

## 5. "Training" = Calibration (không gradient) — luồng thật

```mermaid
flowchart TD
    START["uv run python train/calibrate_branch3.py"] --> LOAD
    LOAD["Nạp branch3_sessions_cach_a.csv<br/>+ branch1_v1 + branch2_v1"] --> CAL

    subgraph CAL ["SessionCorrelator.calibrate(TRAIN split)"]
        P["per_query_threshold:<br/>percentile 90% score benign"]
        M["mean_threshold / fraction_threshold:<br/>max(TPR−FPR) trên nhãn TRAIN"]
        C["content_threshold:<br/>max(TPR−FPR), gap 0.172–0.45 → ~0.338"]
    end

    CAL --> EVAL["Đánh giá ablation trên TEST split<br/>(content-only / behavior-only / combined)"]
    EVAL --> OUT["models/branch3_v2/metadata.json (chỉ threshold)<br/>+ report/metrics/branch3_eval.json"]
```

Kết quả hiện tại (TEST, Cách A):

| Config | FPR (benign) | DR boolean | DR time | DR splitting |
|---|---:|---:|---:|---:|
| Content-only | 0.0 | 1.0 | 1.0 | 1.0 |
| Behavior-only | 0.0 | 1.0 | 1.0 | 1.0 |
| Combined | 0.0 | 1.0 | 1.0 | 1.0 |

> ⚠️ Đọc kèm caveat: self-generated, calibration+eval trên data trùng target (audit Day 1) → đây là sanity trên generator của chính mình, **không phải** generalization. Kết quả có ý nghĩa thật với **boolean_blind hard-mode** (Branch 1 no-boolean → vẫn DR=1.0 nhờ behavior check gộp B2).

---

## 6. Luồng Live API — `/branch3/session`

```mermaid
sequenceDiagram
    participant C as Client (Streamlit)
    participant R as FastAPI /branch3/session
    participant REG as deploy/registry.py
    participant COR as SessionCorrelator

    C->>R: POST /branch3/session {queries:[...]}
    R->>REG: registry.branch3()
    REG-->>R: SessionCorrelator (thresholds từ metadata.json + B1/B2)
    R->>COR: score(queries)
    COR->>COR: canonicalize từng query + concat
    COR-->>R: {session_label, is_attack, detail (content/behavior/mean/fraction)}
    R-->>C: Branch3Response
```

**Ghi chú hệ thống hiện tại (liên quan Day 4 của bạn):**
- **Endpoint `/detect` (xử lý 1 câu 1 lần) hiện chỉ gọi Session Correlator với đúng 1 câu làm "session"** (`run_branch3([request.query])`, detect.py:79) — nghĩa là lớp thứ 3 này tồn tại trong code nhưng **chưa tự động phát huy trên luồng chính**, vì chưa có **Session Store** gom nhiều request theo thời gian. Muốn dùng đúng sức mạnh Session Correlator phải gọi riêng `POST /branch3/session` với cả session đã gom sẵn.
- `SessionRequest.queries` yêu cầu `min_length=1` → **empty session bị chặn bởi Pydantic** (cần kiểm tra behavior mong muốn).
- **Không có logic phân nhóm/ranh giới session** trong `deploy/` — client tự truyền danh sách query. `session_idle_gap_seconds: 1800` hiện **dead code** (dòng config chưa có live logic nào dùng); cần wire hoặc đánh dấu dead/future-work ở Day 4.
- Các lỗ hổng live đã liệt kê (outline.md): empty, single-query, mixed attack types, concurrent/overlapping, adversarial input, thread-safety registry lazy-loader.

---

## 7. Lịch sử thiết kế — vì sao bỏ GRU (tóm tắt)

```mermaid
stateDiagram-v2
    [*] --> GRU_design: thiết kế ban đầu
    GRU_design --> CachA_v1: dataset i.i.d. (sample payload thật)
    CachA_v1 --> CachA_v2: real bisection vs real DB (pool 100 user)
    CachA_v2 --> Diagnose: "F1=1.0" đáng ngờ → diagnostic 7/8
    Diagnose --> Finding_1: probability là lossy (cosine 0.961)
    Diagnose --> Finding_2: B1 chặn per-query trước → B3 hiếm reach được
    Diagnose --> Finding_3: session dài tùy biến (120–1800) ≠ max_len 64
    Finding_1 --> SessionCorrelator: dùng TEXT thật, không chuỗi xác suất
    Finding_2 --> SessionCorrelator
    Finding_3 --> SessionCorrelator
    SessionCorrelator --> [*]: content OR behavior, chỉ calibrate
```

---

## 8. Nơi đọc thêm
- `src/models/branch3_session.py` (module docstring 1–74 + class) — cơ chế chi tiết nhất.
- `report/plan/data_contract.md` §4.0 (cơ chế tấn công bisection), §4.1 (Cách A), **§4.2 (thiết kế mới — doc chính)**.
- `train/calibrate_branch3.py`, `src/models/branch3_features.py` — luồng calibrate + helper.
- `report/metrics/branch3_eval.json` — kết quả + caveat.
- `report/conf/outline.md` (~dòng 14) — danh sách lỗ hổng Day 4.