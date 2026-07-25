# Streamlit UI Spec + API Contract (for Minh)

> Source of truth for the Streamlit UI + API contract. The backend already has a FastAPI app
> (`deploy/`, see [`deploy/README.md`](../deploy/README.md)). A branch that hasn't trained yet returns
> `status:"not_ready"` (HTTP 200) — the UI renders a placeholder, **no code changes** once
> the real model lands. Endpoints marked 🟢 = real, 🟡 = mock (stable shape, fake
> data until wired to the real thing).

`task` in the URL is always one of: `branch1` | `branch2` | `branch3`.

---

## Sidebar (left menu)

```
🛡️ SQLi Detection
─────────────────
🧪 Test       → pages/1_test.py
📊 Monitor    → pages/2_monitor.py
🏷️ Data       → pages/3_data.py
🎓 Train      → pages/4_train.py
```

---

## 1. 🧪 Test — 3 tabs

### Tab 1 — Simulated database
Shows the `users` table from the demo DB (so the viewer knows what data is being protected).

- 🟢 `GET /api/v1/demo/database`
  ```json
  {"table": "users",
   "columns": ["id","username","email","password","role"],
   "rows": [{"id":1,"username":"admin","email":"admin@corp.vn","password":"S3cr3t!","role":"admin"}, ...],
   "row_count": 5,
   "query_template": "SELECT * FROM users WHERE username = '{input}'"}
  ```
Render with `st.dataframe(rows)`.

### Tab 2 — Test Branch 1 & 2 (single input)
```
Input box:  [ ' OR '1'='1 ]      ▼ Sample attacks (pre-filled dropdown)
[ ▶ Run WITHOUT the model ]   [ 🛡️ Run WITH the model ]
```
Both buttons call **the same endpoint**, differing only in the `protected` flag:

- 🟢 `POST /api/v1/demo/execute`
  ```json
  // request
  {"inputs": ["' OR '1'='1"], "protected": false}
  ```
  ```json
  // response — WITHOUT the model (protected=false): attack SUCCEEDS
  {"protected": false,
   "results": [{"input": "' OR '1'='1",
                "constructed_sql": "SELECT * FROM users WHERE username = '' OR '1'='1'",
                "executed": true, "row_count": 5, "leaked": true,
                "rows": [ ...all users, passwords exposed... ]}],
   "decision": null}
  ```
  ```json
  // response — WITH the model (protected=true): blocked
  {"protected": true,
   "results": [{"input": "' OR '1'='1",
                "constructed_sql": "SELECT * FROM users WHERE username = '' OR '1'='1'",
                "executed": false, "row_count": 0, "leaked": false, "rows": [],
                "branch1": { ...same as /detect... }, "branch2": {"status":"not_ready"}}],
   "decision": {"action": "BLOCK", "reason": "Branch-1 detected attack class ..."}}
  ```
Render: WITHOUT the model → `st.error` + `st.dataframe(rows)` (showcasing the leaked data). WITH the model →
a `decision.action` badge, a bar chart of `branch1.probabilities`, `executed=false`.

### Tab 3 — Test Branch 3 (session, 2 inputs)
Same as Tab 2 but **2 input boxes** → `inputs` has 2 elements (1 session). The backend runs
each query + Branch 3 (session). Branch 3 isn't trained yet → `branch3.status="not_ready"`,
verdict temporarily based on Branch 1 at each step.
```json
{"inputs": ["admin'--", "1; DROP TABLE users"], "protected": true}
```

---

## 2. 📊 Monitor — 3 tabs (one per task)

Each tab (`branch1`/`branch2`/`branch3`) has this layout:
```
Drift (PSI over time)                  [🔁 Retrain]  [⚠️ Alert]*
 ...line chart...                      * only shown when alert=true
▼ Progress log (expander)
```

- 🟡 `GET /api/v1/monitor/drift/{task}`
  ```json
  {"task": "branch1", "metric": "psi", "threshold": 0.2, "alert": false,
   "points": [{"date": "2026-07-10", "value": 0.05}, {"date":"2026-07-11","value":0.08}, ...]}
  ```
  `alert=true` when the latest point > `threshold` → Streamlit shows the ⚠️ button.
- 🟡 `POST /api/v1/monitor/retrain/{task}` → `{"ok":true,"task":"branch1","job_id":"...","status":"queued"}`
  (suggestion: after clicking, redirect the user to the Train page with that job_id — or poll).
- 🟡 `GET /api/v1/monitor/logs/{task}` → `{"task":"branch1","lines":["2026-07-16 10:00 INFO ...", ...]}`

Render: `st.line_chart(points)`; Retrain button via `st.button`; logs via `st.expander` + `st.code`.

---

## 3. 🏷️ Data — 3 tabs (one per task)

Each tab has 2 sections: **Annotated** (already labeled) and **Unannotated** (awaiting labels).
```
[ Annotated: 12,480 ]   [ Unannotated: 320 ]
Unannotated → label each sample:
  query: "1' OR 1=1--"   ( ) normal ( ) union_based ( ) boolean_blind ...  [Save]
```

- 🟡 `GET /api/v1/data/{task}/unannotated?limit=20&offset=0`
  ```json
  {"task":"branch1","count":320,
   "items":[{"id":"u_001","query":"1' OR 1=1--","source":"overkill_queue"}, ...],
   "label_options":["normal","union_based","error_based","boolean_blind","time_blind","stacked"]}
  ```
- 🟡 `GET /api/v1/data/{task}/annotated?limit=20&offset=0`
  ```json
  {"task":"branch1","count":12480,
   "items":[{"id":"a_001","query":"SELECT ...","label":"normal","annotated_at":"..."}]}
  ```
- 🟡 `POST /api/v1/data/{task}/annotate`
  ```json
  // request
  {"id":"u_001","label":"boolean_blind"}
  // response
  {"ok":true,"id":"u_001","label":"boolean_blind","persisted":false}
  ```
Render: 2 `st.metric` widgets for the counts; loop over unannotated samples with `st.radio` +
`st.button("Save")`. `label_options` differs per task (Branch 3 uses
session_classes).

---

## 4. 🎓 Train — 3 tabs (one per task)

```
Split:  Train [70] Valid [15] Test [15]        [▶ Start training]
Loss curve (live)          Logs (live)
Once done → confusion matrix + metrics table (P/R/F1)
```

- 🟡 `POST /api/v1/train/{task}/start`
  ```json
  // request (the 3 numbers must sum to 100)
  {"train": 70, "valid": 15, "test": 15}
  // response
  {"job_id":"job_branch1_ab12","task":"branch1","status":"running","total_epochs":5}
  ```
- 🟡 `GET /api/v1/train/{task}/status/{job_id}` — **poll ~once/sec** while running
  ```json
  {"job_id":"job_branch1_ab12","status":"running","epoch":3,"total_epochs":5,
   "loss_curve":[{"epoch":1,"train_loss":0.42,"valid_loss":0.48},
                 {"epoch":2,"train_loss":0.31,"valid_loss":0.39},
                 {"epoch":3,"train_loss":0.25,"valid_loss":0.34}],
   "logs":["epoch 1/5 train_loss=0.42 ...","epoch 2/5 ...","epoch 3/5 ..."]}
  ```
  `status` ∈ `running` | `done` | `failed`.
- 🟡 `GET /api/v1/train/{task}/result/{job_id}` — call once `status=done`
  ```json
  {"job_id":"job_branch1_ab12","status":"done",
   "labels":["normal","union_based","error_based","boolean_blind","time_blind"],
   "confusion_matrix":[[980,2,1,0,1],[3,610,0,4,1], ...],
   "metrics":{"f1_macro":0.98,"accuracy":0.99,
              "per_class":{"normal":{"precision":0.99,"recall":0.98,"f1":0.985}, ...}},
   "saved_version":"branch1_v2"}
  ```
Render: `st.line_chart(loss_curve)` updated on each poll; `st.code(logs)`;
once done → draw the confusion matrix (heatmap via `st.dataframe`/matplotlib) + `st.table(metrics)`.

**Polling flow (Streamlit):**
```python
job = requests.post(f"{API}/api/v1/train/branch1/start", json=split).json()
ph_chart, ph_log = st.empty(), st.empty()
while True:
    s = requests.get(f"{API}/api/v1/train/branch1/status/{job['job_id']}").json()
    ph_chart.line_chart(pd.DataFrame(s["loss_curve"]).set_index("epoch"))
    ph_log.code("\n".join(s["logs"]))
    if s["status"] != "running":
        break
    time.sleep(1)
res = requests.get(f"{API}/api/v1/train/branch1/result/{job['job_id']}").json()
# draw confusion_matrix + metrics
```

---

## Implementation notes

- **🟡 mock**: fake data (drift, logs, unannotated, simulated train jobs) but
  **stable shape**. Once the real thing is ready (Bach trains it, Duc integrates it), only the
  guts get swapped — Minh doesn't touch the UI.
- **The simulated DB is code with an INTENTIONAL vulnerability** (`deploy/demo_db.py`), sandboxed in a
  throwaway SQLite instance with fake data — purely to demo "without the model, the attack goes through". Not
  used for anything else.
- Select/rollback a model = change `<branch>.active_version` in `configs/config.yaml`.
- `uv run uvicorn deploy.main:app --reload` → try it at `/docs`.
