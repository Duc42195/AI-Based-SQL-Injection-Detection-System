# Streamlit UI Spec + API Contract (cho Minh)

> Nguồn sự thật cho giao diện Streamlit + hợp đồng API. Backend đã có app FastAPI
> (`api/`, xem [`api/README.md`](../api/README.md)). Nhánh chưa train trả
> `status:"not_ready"` (HTTP 200) — UI render placeholder, **không đổi code** khi
> model thật xong. Endpoint đánh dấu 🟢 = có thật, 🟡 = mock (shape ổn định, dữ
> liệu giả tới khi nối thật).

`task` trong URL luôn là một trong: `nhanh1` | `nhanh2` | `nhanh3`.

---

## Sidebar (menu trái)

```
🛡️ SQLi Detection
─────────────────
🧪 Test       → pages/1_test.py
📊 Monitor    → pages/2_monitor.py
🏷️ Data       → pages/3_data.py
🎓 Train      → pages/4_train.py
```

---

## 1. 🧪 Test — 3 tab

### Tab 1 — Database giả lập
Hiển thị bảng `users` của DB demo (để người xem biết đang bảo vệ dữ liệu gì).

- 🟢 `GET /api/v1/demo/database`
  ```json
  {"table": "users",
   "columns": ["id","username","email","password","role"],
   "rows": [{"id":1,"username":"admin","email":"admin@corp.vn","password":"S3cr3t!","role":"admin"}, ...],
   "row_count": 5,
   "query_template": "SELECT * FROM users WHERE username = '{input}'"}
  ```
Render bằng `st.dataframe(rows)`.

### Tab 2 — Test Nhánh 1 & 2 (single input)
```
Ô nhập:  [ ' OR '1'='1 ]      ▼ Mẫu tấn công (dropdown điền sẵn)
[ ▶ Chạy KHÔNG model ]   [ 🛡️ Chạy CÓ model ]
```
Cả 2 nút gọi **cùng 1 endpoint**, khác cờ `protected`:

- 🟢 `POST /api/v1/demo/execute`
  ```json
  // request
  {"inputs": ["' OR '1'='1"], "protected": false}
  ```
  ```json
  // response — KHÔNG model (protected=false): tấn công THÀNH CÔNG
  {"protected": false,
   "results": [{"input": "' OR '1'='1",
                "constructed_sql": "SELECT * FROM users WHERE username = '' OR '1'='1'",
                "executed": true, "row_count": 5, "leaked": true,
                "rows": [ ...toàn bộ users, lộ password... ]}],
   "decision": null}
  ```
  ```json
  // response — CÓ model (protected=true): bị chặn
  {"protected": true,
   "results": [{"input": "' OR '1'='1",
                "constructed_sql": "SELECT * FROM users WHERE username = '' OR '1'='1'",
                "executed": false, "row_count": 0, "leaked": false, "rows": [],
                "nhanh1": { ...giống /detect... }, "nhanh2": {"status":"not_ready"}}],
   "decision": {"action": "BLOCK", "reason": "Branch-1 detected attack class ..."}}
  ```
Render: KHÔNG model → `st.error` + `st.dataframe(rows)` (khoe data lộ). CÓ model →
badge `decision.action`, biểu đồ cột `nhanh1.probabilities`, `executed=false`.

### Tab 3 — Test Nhánh 3 (session, 2 input)
Giống Tab 2 nhưng **2 ô nhập** → `inputs` có 2 phần tử (1 session). Backend chạy
từng query + Nhánh 3 (session). Nhánh 3 chưa train → `nhanh3.status="not_ready"`,
verdict tạm dựa trên Nhánh 1 mỗi bước.
```json
{"inputs": ["admin'--", "1; DROP TABLE users"], "protected": true}
```

---

## 2. 📊 Monitor — 3 tab (mỗi tab 1 task)

Mỗi tab (`nhanh1`/`nhanh2`/`nhanh3`) có bố cục:
```
Drift (PSI theo thời gian)             [🔁 Retrain]  [⚠️ Cảnh báo]*
 ...biểu đồ đường...                   * chỉ hiện khi alert=true
▼ Log tiến trình (expander)
```

- 🟡 `GET /api/v1/monitor/drift/{task}`
  ```json
  {"task": "nhanh1", "metric": "psi", "threshold": 0.2, "alert": false,
   "points": [{"date": "2026-07-10", "value": 0.05}, {"date":"2026-07-11","value":0.08}, ...]}
  ```
  `alert=true` khi điểm mới nhất > `threshold` → Streamlit hiện nút ⚠️.
- 🟡 `POST /api/v1/monitor/retrain/{task}` → `{"ok":true,"task":"nhanh1","job_id":"...","status":"queued"}`
  (gợi ý: sau khi bấm, chuyển user sang trang Train với job_id đó — hoặc poll).
- 🟡 `GET /api/v1/monitor/logs/{task}` → `{"task":"nhanh1","lines":["2026-07-16 10:00 INFO ...", ...]}`

Render: `st.line_chart(points)`; nút Retrain `st.button`; log `st.expander` + `st.code`.

---

## 3. 🏷️ Data — 3 tab (mỗi tab 1 task)

Mỗi tab có 2 khu: **Annotated** (đã gán nhãn) và **Unannotated** (chờ gán).
```
[ Annotated: 12.480 ]   [ Unannotated: 320 ]
Unannotated → gán nhãn từng mẫu:
  query: "1' OR 1=1--"   ( ) normal ( ) union_based ( ) boolean_blind ...  [Lưu]
```

- 🟡 `GET /api/v1/data/{task}/unannotated?limit=20&offset=0`
  ```json
  {"task":"nhanh1","count":320,
   "items":[{"id":"u_001","query":"1' OR 1=1--","source":"overkill_queue"}, ...],
   "label_options":["normal","union_based","error_based","boolean_blind","time_blind","stacked"]}
  ```
- 🟡 `GET /api/v1/data/{task}/annotated?limit=20&offset=0`
  ```json
  {"task":"nhanh1","count":12480,
   "items":[{"id":"a_001","query":"SELECT ...","label":"normal","annotated_at":"..."}]}
  ```
- 🟡 `POST /api/v1/data/{task}/annotate`
  ```json
  // request
  {"id":"u_001","label":"boolean_blind"}
  // response
  {"ok":true,"id":"u_001","label":"boolean_blind","persisted":false}
  ```
Render: 2 `st.metric` cho số lượng; vòng lặp mẫu unannotated với `st.radio` +
`st.button("Lưu")`. `label_options` khác nhau theo task (Nhánh 3 dùng
session_classes).

---

## 4. 🎓 Train — 3 tab (mỗi tab 1 task)

```
Split:  Train [70] Valid [15] Test [15]        [▶ Bắt đầu train]
Loss curve (live)          Logs (live)
Sau khi xong → Confusion matrix + bảng metrics (P/R/F1)
```

- 🟡 `POST /api/v1/train/{task}/start`
  ```json
  // request (3 số cộng lại = 100)
  {"train": 70, "valid": 15, "test": 15}
  // response
  {"job_id":"job_nhanh1_ab12","task":"nhanh1","status":"running","total_epochs":5}
  ```
- 🟡 `GET /api/v1/train/{task}/status/{job_id}` — **poll ~1s một lần** khi đang chạy
  ```json
  {"job_id":"job_nhanh1_ab12","status":"running","epoch":3,"total_epochs":5,
   "loss_curve":[{"epoch":1,"train_loss":0.42,"valid_loss":0.48},
                 {"epoch":2,"train_loss":0.31,"valid_loss":0.39},
                 {"epoch":3,"train_loss":0.25,"valid_loss":0.34}],
   "logs":["epoch 1/5 train_loss=0.42 ...","epoch 2/5 ...","epoch 3/5 ..."]}
  ```
  `status` ∈ `running` | `done` | `failed`.
- 🟡 `GET /api/v1/train/{task}/result/{job_id}` — gọi khi `status=done`
  ```json
  {"job_id":"job_nhanh1_ab12","status":"done",
   "labels":["normal","union_based","error_based","boolean_blind","time_blind"],
   "confusion_matrix":[[980,2,1,0,1],[3,610,0,4,1], ...],
   "metrics":{"f1_macro":0.98,"accuracy":0.99,
              "per_class":{"normal":{"precision":0.99,"recall":0.98,"f1":0.985}, ...}},
   "saved_version":"nhanh1_v2"}
  ```
Render: `st.line_chart(loss_curve)` cập nhật trong vòng poll; `st.code(logs)`;
xong → vẽ confusion matrix (heatmap `st.dataframe`/matplotlib) + `st.table(metrics)`.

**Luồng poll (Streamlit):**
```python
job = requests.post(f"{API}/api/v1/train/nhanh1/start", json=split).json()
ph_chart, ph_log = st.empty(), st.empty()
while True:
    s = requests.get(f"{API}/api/v1/train/nhanh1/status/{job['job_id']}").json()
    ph_chart.line_chart(pd.DataFrame(s["loss_curve"]).set_index("epoch"))
    ph_log.code("\n".join(s["logs"]))
    if s["status"] != "running":
        break
    time.sleep(1)
res = requests.get(f"{API}/api/v1/train/nhanh1/result/{job['job_id']}").json()
# vẽ confusion_matrix + metrics
```

---

## Ghi chú triển khai

- **🟡 mock**: dữ liệu giả (drift, log, unannotated, train job mô phỏng) nhưng
  **shape ổn định**. Khi phần thật xong (Bach train, Toi tích hợp), chỉ thay ruột,
  Minh không sửa UI.
- **DB giả lập là code CỐ Ý có lỗ hổng** (`api/demo_db.py`), sandbox trong SQLite
  throwaway với dữ liệu giả — chỉ để demo "không model thì tấn công lọt". Không
  dùng cho gì khác.
- Chọn/rollback model = đổi `<branch>.active_version` trong `configs/config.yaml`.
- `uv run uvicorn api.main:app --reload` → thử tại `/docs`.
