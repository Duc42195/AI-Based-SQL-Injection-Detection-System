# API Backend — Guide for Streamlit (Minh)

> 📄 **4-page UI spec (Test / Monitor / Data / Train) + full API contract:**
> [`report/docs/streamlit_ui_spec.md`](../report/docs/streamlit_ui_spec.md). The doc below covers
> the core surface (health / detect / branch 1-3 / metrics / admin).

> FastAPI backend for the SQLi detection system. **Branch 1 and Branch 2 run FOR REAL**
> right now; Branch 3 returns `status:"not_ready"` (HTTP 200, **not an error**) until
> its router is wired to `models/branch3_v1/`. **The response shape stays stable** → Minh
> builds the UI once, and once the real model lands the data just shows up —
> **no code changes needed**.
>
> A Streamlit UI already consumes this API: see [`app/README.md`](../app/README.md).

## 1. Running the backend

```bash
# from repo root
uv run uvicorn deploy.main:app --reload --port 8000
```

- Swagger UI (try it out, view the schema): <http://localhost:8000/docs>
- Quick health check: `curl localhost:8000/health`

CORS is already open (`api.cors_origins: ["*"]` in `configs/config.yaml`), so Streamlit
calling from a different port (default 8501) isn't blocked.

## 2. Endpoints

| Method | Path | Body | Used by Streamlit page |
|---|---|---|---|
| GET  | `/health` | – | 3-branch status badge |
| POST | `/api/v1/detect` | `{"query": "..."}` | **query test page + 3-branch results page** (one call, returns a verdict) |
| POST | `/api/v1/branch1/predict` | `{"query": "..."}` | Branch 1 debug only |
| POST | `/api/v1/branch2/score` | `{"query": "..."}` | Branch 2 debug only (real anomaly score) |
| POST | `/api/v1/branch3/session` | `{"queries": ["...","..."]}` | (stub) Branch 3 |
| GET  | `/api/v1/metrics/{branch}` | – | **Metrics page** (P/R/F1) — `branch1`/`branch2`/`branch3` |
| GET  | `/api/v1/admin/overkill-queue` | – | **Admin page** (queue — currently empty) |
| POST | `/api/v1/admin/overkill/{id}/confirm` | – | Approve button (stub) |
| POST | `/api/v1/admin/overkill/{id}/reject` | – | Reject button (stub) |

> **Recommendation:** use `POST /api/v1/detect` as the main endpoint. It runs all 3 branches
> + applies the decision matrix and returns **one verdict** (`BLOCK` / `OVERKILL` / `ALLOW` / `UNKNOWN`).

## 3. Response shape

### `POST /api/v1/detect`

```json
{
  "query_canonical": "admin' or 1=1 union select password from users --",
  "branch1": {
    "status": "ready",
    "label_name": "boolean_blind",
    "is_sqli": true,
    "confidence": 0.48,           // top-class probability
    "attack_probability": 0.97,   // = 1 - P(normal); is_sqli is thresholded on this
    "threshold": 0.5,
    "probabilities": {"normal": 0.03, "union_based": 0.46, "boolean_blind": 0.48, ...}
  },
  "branch2": {
    "status": "ready",
    "query_canonical": "admin' or 1=1 union select password from users --",
    "anomaly_score": -3.94,       // higher = more anomalous
    "is_anomaly": false
  },
  "branch3": {"status": "not_ready", "session_label": null, "is_attack": null},
  "decision": {"action": "BLOCK", "reason": "Branch-1 detected attack class 'boolean_blind' ..."}
}
```

**Branch 2 note:** it only sees *structural shape* (length, entropy, special-char ratio,
SQL-keyword count) — not attack content. A short classic payload like `' OR '1'='1` looks
structurally ordinary and scores as **not** anomalous; that's expected. Branch 2 exists to
catch zero-days/odd-shaped traffic, while Branch 1 handles known payload content.

**Display note:** the `is_sqli` flag is based on `attack_probability` (the combined
probability of all attack classes = `1 - P(normal)`), **not** `confidence`. So `confidence`
can be < `threshold` while `is_sqli` is still `true` (when probability is split across
multiple attack classes). Display `attack_probability` next to `threshold` for clarity.

`decision.action`:
- `BLOCK` — Branch 1 detected an attack class (or Branch 3 flagged the session as an attack).
- `OVERKILL` — Branch 1 = Normal but Branch 2 flagged an anomaly → waits for Admin.
- `ALLOW` — normal (Branch 1 Normal and Branch 2 sees no anomaly).
- `UNKNOWN` — Branch 1 failed to load.

### `GET /api/v1/metrics/{branch}`

```json
{"status": "ready", "source": "report/metrics/branch1_eval.json", "metrics": { ...F1/precision/recall... }}
```
If no report exists yet → `{"status": "not_ready", "detail": "..."}`. The UI should check `status` first.

## 4. Calling from Streamlit (example)

> The Streamlit app in [`app/`](../app/) already wraps every endpoint in
> `app/api_client.py` — use `from app import api_client; api_client.detect(q)` rather than
> re-writing the calls. The raw example below is for reference.

```python
import requests

API = "http://localhost:8000"

def detect(query: str) -> dict:
    r = requests.post(f"{API}/api/v1/detect", json={"query": query}, timeout=10)
    r.raise_for_status()
    return r.json()

res = detect("admin' OR 1=1 --")
st.write("Action:", res["decision"]["action"])
st.write("Reason:", res["decision"]["reason"])

n1 = res["branch1"]
if n1["status"] == "ready":
    st.metric("Type", n1["label_name"])
    st.progress(n1["attack_probability"])
else:
    st.info("Branch 1 not ready yet")

n2 = res["branch2"]
if n2["status"] == "ready":
    st.metric("Anomalous", "YES" if n2["is_anomaly"] else "NO")
    st.caption(f"score = {n2['anomaly_score']:+.3f} (higher = more anomalous)")

# Branch 3 — render a placeholder while not_ready; no changes needed once it lands
if res["branch3"]["status"] == "not_ready":
    st.caption("branch3: not wired up yet")
```

## 5. Conventions for backend devs (Duc/Bach)

- One router file per branch in `deploy/routers/` (`branch2.py` → Bach, `branch3.py` → Duc).
- Once a real model is ready: load it via `deploy/registry.py` (add a function like `branch1`'s) and
  populate the response fields — **don't rename/retype existing fields** (Minh depends on them).
- Select/rollback a model by changing `<branch>.active_version` in `configs/config.yaml`
  (don't hardcode model paths).
- `uv run pytest tests/test_api.py` must be green before committing.
