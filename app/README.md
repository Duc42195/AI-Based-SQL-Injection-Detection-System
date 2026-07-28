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
├── ui.py              # shared rendering helpers (verdict badge, branch cards)
└── pages/             # Streamlit multipage: Monitor, Data, Train, Metrics
```

Add a new backend call in `api_client.py`, not inline in a page — that keeps the
API surface in one place.
