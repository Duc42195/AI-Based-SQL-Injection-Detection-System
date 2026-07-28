# Streamlit demo UI

Front-end for the SQLi detection system. It talks to the FastAPI service in
[`deploy/`](../deploy/) over HTTP only — it never loads models directly, so the
UI and the API can run on different machines.

## Run

Two processes, in two terminals (the API must be up first):

```bash
# 1. backend
uv run uvicorn deploy.main:app --reload --port 8000

# 2. frontend
uv run streamlit run app/streamlit_app.py
```

Then open <http://localhost:8501>. Requires the `frontend` extra:

```bash
uv sync --extra frontend --extra dev
```

Point the UI at a different backend with:

```bash
SQLIDS_API_URL=http://some-host:8000 uv run streamlit run app/streamlit_app.py
```

Otherwise the URL is derived from `api.host`/`api.port` in
[`configs/config.yaml`](../configs/config.yaml).

## Pages

| Page | What it does | Data |
|---|---|---|
| 🧪 **Test** | Demo DB table; run a query with/without the model; 2-query session test | **real** (Branch 1 + 2) |
| 📊 **Monitor** | Drift chart, alert badge, retrain button, logs — per branch | mock |
| 🏷️ **Data** | Annotated/unannotated pools, labelling form — per branch | mock |
| 🎓 **Train** | Split selection, live loss curve + logs, confusion matrix + metrics | simulated |
| 📈 **Metrics** | Real evaluation reports from `report/metrics/*_eval.json` | **real** |

### What's real vs. not

- **Real:** Branch 1 (supervised multiclass) and Branch 2 (One-Class SVM anomaly)
  inference, the fused BLOCK/OVERKILL/ALLOW decision, the vulnerable demo
  database (injections genuinely succeed when the model is off), and all
  evaluation metrics.
- **Not yet:** Branch 3 returns `not_ready` — the weights exist
  (`models/branch3_v1/model.pt`) but the router isn't wired to them yet.
  Monitor/Data pages serve mock data; the Train page simulates a run rather than
  retraining the real models (real training lives in `train/train_branch*.py`).

Pages degrade gracefully: a branch that isn't ready renders a placeholder
instead of erroring, and the sidebar always shows live backend status.

## Files

```
app/
├── streamlit_app.py   # entry point = Test page
├── api_client.py      # all HTTP calls to the backend (one function per action)
├── cache.py           # cached read-through wrappers (TTL per endpoint)
├── state.py           # every session-state key, with typed accessors
├── ui.py              # shared rendering helpers (verdict badge, branch cards)
└── pages/             # Streamlit multipage: Monitor, Data, Train, Metrics
```

Add a new backend call in `api_client.py`, not inline in a page — that keeps the
API surface in one place.

## State model

Streamlit re-runs the **entire script on every interaction**. Three rules follow
from that, and the app is built around them:

### 1. Anything that must outlive a click goes in `state.py`

`st.button` returns `True` only during the run its click triggered. So this
loses the result on the very next interaction:

```python
if st.button("Run"):
    st.error("BLOCK")     # gone as soon as anything else is clicked
```

Instead, store it and render from the store:

```python
if st.button("Run"):
    state.set_demo_run(mode, state.DemoRun(...))
run = state.get_demo_run(mode)
if run:
    render(run)           # survives every re-run
```

`tests/test_app_pages.py::test_button_scoped_rendering_loses_the_result` pins the
naive failure, and `test_result_survives_unrelated_interaction` pins the fix.

**Every** key is declared in `state.py` — never write a bare
`st.session_state["something"]` in a page. Two kinds are distinguished:

| Kind | Owner | Key prefix | How to read |
|---|---|---|---|
| Widget state | Streamlit | `sqli.w.…` via `state.widget_key(...)` | the widget's return value |
| App state | this module | `sqli.…` via accessors | `state.get_*()` |

Current app state: the last Test run per mode, one `TrainJob` per task, a
show-once `Feedback` per scope, and the Data page's pagination offset.

### 2. Reads are cached, writes invalidate

`st.tabs` renders *all* tabs each run (the browser only hides inactive ones), so
an uncached read in a 3-tab page fires 3 requests per interaction — for tabs
nobody opened. Every read goes through `cache.py`; measured: **3 backend calls
instead of 12** across 4 renders, and flat as interactions grow. Writes call
`api_client` directly, then invalidate (e.g. `cache.invalidate_annotations()`).

### 3. Never block the script thread

Streamlit is single-threaded per session, so `while True: time.sleep(...)`
freezes every page and tab until it returns. The Train page polls inside
`@st.fragment(run_every=...)`, so only that fragment re-runs; when the job
finishes it calls `st.rerun(scope="app")` to leave the polling loop.

## Testing

Pages are tested headlessly with Streamlit's `AppTest` and a mocked backend, so
`uv run pytest` needs no running API:

```bash
uv run pytest tests/test_app_pages.py tests/test_app_state.py -q
```
