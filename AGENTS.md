# AGENTS.md — Guide for AI Assistants & New Contributors

> This file is the **shared source of guidance** for every AI assistant (Copilot, Cursor, Claude, Codex, Aider...) and for developers who just cloned the repo. **Read this whole file before touching any code.** Goal: contribute correctly and **don't break the project**.

---

## ⛔ CRITICAL rules (read first)

1. **DO NOT commit directly to `main`.** Every change goes on its own branch (`feature/...`), merged via PR. `main` must always be runnable (tests pass).
2. **DO NOT hardcode** paths / thresholds / timeouts. Everything lives in [`configs/config.yaml`](configs/config.yaml), read via `src.utils.load_config`.
3. **DO NOT use `print`** in `src/`, `deploy/`, `train/` code. Use logging: `from src.utils import get_logger`.
4. **DO NOT commit data / large models.** `data/` and `models/*.pkl|*.pt|...` are already `.gitignore`d. Only commit code + config + `.gitkeep`.
5. **DO NOT install heavy libraries** (torch, transformers, ctranslate2...) or change versions in `pyproject.toml` without asking the repo owner first. See [Dependencies](#dependencies).
6. **DO NOT change the schema** in `config.yaml` (rename/remove keys) without updating every place that uses it — it'll break elsewhere.
7. **Run `uv run pytest` before committing.** Red tests = no commit.

---

## Project context

An AI-based **SQL Injection** detection system, deployed at the Database Proxy layer. **Three-branch** architecture (details in [README.md](README.md)):
- **Branch 1** — Supervised multi-class classifier (Normal + SQLi variants).
- **Branch 2** — Anomaly detection (trained on benign traffic only).
- **Branch 3** — Session-level sequence model (main contribution).

Tight deadline (14 days) → **prioritize an end-to-end MVP** over perfecting every individual part.

---

## Project roles

| Person | Role |
|---|---|
| Duc | Solution Architect, Project Manager, Writer, Researcher (lead — coordinates, makes architecture/framing calls, writes, and does research as needed) |
| Bach | Researcher (owns Branch 3 data/model work end-to-end) |
| Diep | Writer |
| Minh | Writer |
| Dr. Linh Dinh-Van, Dr. Thai Kim-Dinh | Reviewer (advisors, RIVF paper co-authors) |

---

## Keep these in sync

The same facts (deadlines, framing, team roles, branch status) are duplicated across a few
files on purpose — each one serves a different audience — but that means **any status change
must be checked against all of them**, not just the one you're currently editing:

| File | What it owns |
|---|---|
| `README.md` | Architecture, decision logic, install/run/config — technical overview only, no roles or status |
| `AGENTS.md` (here) | "Project roles" table (sole owner) + contributor/agent rules |
| `report/plan/ke_hoach_2_tuan.csv` | Day-by-day/sprint task tracker — the live plan, sole owner of current status/progress |
| `report/conf/outline.md`, `report/conf/research_proposal.md` | RIVF paper status/framing (as of 2026-07-30 these are known stale — flagged separately, not fixed by this checklist) |

**Rule of thumb:** when a core fact changes (a deadline, a role, a branch's status), grep the
whole repo for the *old* value/string before considering the change done. Don't rely on a fixed
mental list of "files that matter" — new docs get added over time and a remembered list goes
stale just like the facts it's meant to protect.

---

## "Check plan" — what Duc means by this

When Duc says **"check plan"**, he means: read `report/plan/ke_hoach_2_tuan.csv` and evaluate
**actual progress against the sprint schedule** — not just open the file, and not just check
git/branch state in isolation. Concretely:

1. What's the current date, and which sprint/day does that fall in per the CSV?
2. For each row at or before today: is the `Status` column actually reflected in reality (check
   the real deliverable — file exists, tests pass, branch has commits — not just the CSV text,
   since the CSV isn't updated automatically)?
3. **What's slipping** — tasks past their date still "Not started", deliverables that don't
   exist yet, dependencies that block a later row?
4. **What to do about it** — a concrete recommendation (re-scope, reassign, flag to the team),
   not just a status dump.

Cross-reference with live signals when relevant (e.g., recent commits/branches matching a
person's assigned task) rather than trusting the CSV's `Status` field alone, since it's
manually maintained and can lag reality in either direction.

---

## Environment setup

The project uses [`uv`](https://docs.astral.sh/uv/) (no manual pip/venv). Python **3.12**.

```bash
uv sync --extra dev                              # core stack + pytest
uv sync --extra gbm --extra transformer --extra dev   # + XGBoost/LightGBM + torch/transformers
```
- **NVIDIA GPU** available → torch uses CUDA automatically. Still runs without a GPU (just slower).
- **Don't run `pip install`** outside of `uv`.

## Run & test

```bash
uv run python main.py    # health check: load config + log banner
uv run pytest            # run the full test suite (must be green before committing)
uv run pytest tests/test_config.py -q   # run a single file
uv run uvicorn deploy.main:app --reload    # run the API backend (docs: /docs)
uv run streamlit run app/streamlit_app.py  # run the demo UI (needs the API up; --extra frontend)
```

**API backend** (`deploy/`) already has a real app: `deploy/main.py` (app + CORS), `deploy/registry.py`
(loads models per `<branch>.active_version` in config), `deploy/schemas.py` (Pydantic
contract), `deploy/routers/` (one file per branch — the branch owner edits their own file).
A branch that hasn't been trained yet returns `status:"not_ready"` instead of crashing.
Contract + guide for Streamlit: [`deploy/README.md`](deploy/README.md). **Don't rename or
retype existing response fields** — the frontend depends on them. The URL prefix stays
`/api/v1/...` (per `config.yaml`), independent of directory names.

**MLOps / continual learning** — spec: [`report/plan/mlops_contract.md`](report/plan/mlops_contract.md).
Data carries a `major.minor` version; a new class is a **major** bump and makes
champion/challenger comparison invalid, so the gate refuses it and promotes directly. Four
rules that are easy to break by accident:

1. **Never train on `golden`.** It is the frozen benchmark; contaminating it invalidates every
   comparison. `train/build_mlops_split.py` asserts this before writing anything.
2. **Deduplicate by `query_canonical` before partitioning**, not by row id — the corpus has
   4,277 repeated texts that otherwise straddle train and golden.
3. **The offline experiment writes its own registry** under `report/metrics/continual_learning/`.
   Writing into `data/versions/` mixes experiment lineage with what is deployed.
4. **A model may emit integer label ids or label names** (the two trainers differ);
   `deploy/registry.py` normalises both. Don't reintroduce `int(c)` on `clf.classes_`.

Promotion and rollback are each one flip of `branch1_supervised.active_version`.

---

## Directory structure (don't put files in the wrong place)

```
configs/config.yaml      # ALL configuration parameters
src/                     # CORE SHARED LIBRARY (imported by both train/ and deploy/)
  src/preprocessing/     #   canonicalization + tokenization
  src/models/            #   Branch 1 / 2 / 3
  src/decision/          #   decision logic + Overkill queue
  src/continual_learning/#   labeling, retraining, validation gate
  src/monitoring/        #   drift, versioning, rollback
  src/utils/             #   config loader + logging (REUSE THIS, don't rewrite)
train/                   # offline pipeline: build dataset, train, compare, generate metrics
  train/notebooks/       #   experiments (branch prefix: exp/...)
deploy/                  # FastAPI service (formerly api/) — main.py, registry.py, routers/
app/                     # Streamlit demo UI — talks to deploy/ over HTTP only (api_client.py)
report/                  # documentation & results
  report/plan/           #   proposal, plan, data_contract, scope
  report/midterm/        #   mid-term report (25 Jul, Branch 1+2 only) + manifest + template
  report/conf/           #   conference submission (RIVF...) — .tex paper + outline + related log
  report/metrics/        #   eval JSON/CSV + figures (paths.reports_dir; generated by train/)
  report/docs/           #   specs (Streamlit UI...)
tests/                   # pytest — one test_*.py file per module
data/  models/           # DO NOT commit contents (only .gitkeep)
```

---

## Coding conventions

- **Type hints + docstrings** on every public function/class.
- Import config: `from src.utils import load_config; cfg = load_config()`; read via `cfg.get_path("section.key")`.
- Import logger: `from src.utils import get_logger; logger = get_logger(__name__)`.
- Time-consuming steps (train/retrain/benchmark) → **log progress clearly**.
- Write **pytest** tests for new logic; required for: canonicalization, decision logic, validation gate.
- Adding a new parameter → **add it to `config.yaml`**, don't hardcode. Can be overridden at runtime via the `SQLIDS_<SECTION>_<KEY>` environment variable.

---

## Git workflow (lightweight trunk-based)

1. `git switch main && git pull`
2. `git switch -c feature/<phase-name>` (e.g. `feature/branch2-anomaly` **for non-sprint work**; see below for sprint work)
3. Code, commit often in small chunks; write clear commit messages (Vietnamese or English, either is fine).
4. `git push -u origin feature/<phase-name>`
5. Open a **PR on GitHub** → review → **Squash and merge** → delete the branch.
6. Branch prefixes and naming:
   - **`feature/`** (new functionality)
   - **`fix/`** (bug fix)
   - **`exp/`** (experimental notebook, disposable)
   - **Sprint-based code work** (for the RIVF 30-Aug sprint): include sprint number in the branch name for tracking.
     - Format: `feature/feat-{description}-s{sprint}` (e.g., `feature/feat-branch3-eval-s1`, `feature/feat-cl-references-s2`)
     - Or for bug fixes: `fix/{description}-s{sprint}` (e.g., `fix/combined-coverage-s1`)
     - Experiments during the sprint: `exp/{description}` (no sprint number needed, they're disposable)

**Never** merge with red tests. **Never** force-push to `main`.

---

## Dependencies

- Adding a **lightweight** lib (sklearn utils, small helpers) → add to `[project.dependencies]` in `pyproject.toml` + `uv sync`, explain why in the PR.
- Adding a **heavy** lib (torch, transformers, ctranslate2, large model weights) → **ask the repo owner first**. Put it under `[project.optional-dependencies]` (`transformer`/`inference` group), not in core.
- Commit `uv.lock` together with any dependency change so the environment stays reproducible.

---

## Data

- Datasets are **public** (see table D1–D6 in [README.md](README.md)); **do not commit** data files to the repo.
- No real data yet for some part → use public data as a placeholder, **cite the source clearly** and mark it `TODO` to replace later.

## Trained models

- **Don't retrain unless necessary** — the real models (`branch1_v1`, `branch2_v1`) are already on HF: `hf download Jason-42195/VNU-SQLi-Detection-Models --local-dir models/`. See the README.md section "Trained models — where to download".
- If you do retrain (e.g. after changing training code), **remember to push the new version to HF** (`hf upload Jason-42195/VNU-SQLi-Detection-Models models/branch1_v1 branch1_v1 --repo-type model`) so the whole team shares one version instead of everyone having a different local model.

---

## Branch 3 (session-level) — how to build this data correctly

Session-level attacks (boolean-blind / time-blind) have a real, executable algorithm behind them — bisection search, ~7 requests per character (full mechanism: `report/plan/data_contract.md` Section 4.0). Learned the hard way, more than once, building this branch:

1. **Don't sample or template it — execute it for real.** Each request's payload depends on every prior response in that session (the comparison bound only makes sense given the search range narrowed so far). Sampling unrelated real attack payloads i.i.d., or hand-writing a plausible-looking sequence, does not reproduce that dependency. Run the actual bisection algorithm (`train/attack_simulator.py`) against a real, disposable target (`deploy/demo_db.py`) and record what genuinely happens — real row counts, real measured timing (SQLite needed `ASCII()`/`SLEEP()` added since it lacks them natively).
2. **Watch for the memorization trap.** A deterministic algorithm run against a small fixed ground-truth set (e.g. 5 seeded users) produces that many distinct traces, repeated — not real diversity, and a model trained on it memorizes rather than generalizes. Before trusting any result, extract the target/ground-truth from each generated session and count distinct traces. Use a large randomized pool for training-data generation specifically (`generate_synthetic_user_pool`) — never repurpose a live demo's small fixed seed data for this.
3. **A session type only matters if it can actually reach Branch 3 in the live decision engine.** Branch 1 blocks immediately on any per-query attack detection — a session type Branch 1 already recognizes on every single step (confirmed case: `time_blind`'s literal `SLEEP()` syntax gets caught ~100% of the time) never reaches Branch 3 in production, no matter how good Branch 3's score on it looks. Check real per-query Branch 1 predictions across a session before treating results on that class as meaningful.
4. **Never trust a suspiciously perfect score without ablations.** This project has hit "100%/near-100% for the wrong reason" more than once (Branch 1's `stacked` class; Branch 3's first two data-generation attempts). Before reporting any Branch 3 result: drop the timing feature and re-check, drop the content features and re-check, re-verify ground-truth diversity. If removing an entire feature group barely changes the score, or diversity turns out to be near-zero, the score doesn't mean what it looks like.
5. Full methodology, mechanism walkthrough, and current results: `report/plan/data_contract.md` Sections 4.0–4.1 (4.1.1 keeps the superseded first attempt on record — read it too, it's the fastest way to see what NOT to do).

---

## "Definition of done" for a change

- [ ] Code has type hints + docstrings, uses logging (no `print`).
- [ ] New parameters have been added to `config.yaml` (no hardcoding).
- [ ] Corresponding test written/updated; `uv run pytest` is green.
- [ ] No large files committed (`git status` is clean for `data/`, `models/`).
- [ ] Done on its own branch, PR opened against `main`.
