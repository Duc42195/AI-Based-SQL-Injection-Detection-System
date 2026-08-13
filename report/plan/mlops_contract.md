# MLOps Contract — data versioning, drift, labelling, promotion

> Locked in 28 Jul 2026. Defines the artifacts, schemas and rules for the continual-learning
> loop so every module (and every team member) codes against one standard — the same role
> [`data_contract.md`](data_contract.md) plays for the datasets.
>
> Figures marked **verified** were computed against the data on disk. Figures marked
> *(projected)* are derived from those and are re-stated as verified once
> `train/build_mlops_split.py` has run.

**Scope.** Branch 1 is the subject of the loop. Branch 2 supplies anomaly scores (and is the
source of stream benign traffic); Branch 3 is out of scope.

---

## 1. Versioning rules

Data carries a **`major.minor`** version. Every model records the data version it trained on.

| Dataset change | Bump | Consequence |
|---|---|---|
| More samples, **same label space** | **minor** (2.0 → 2.1) | comparable to the incumbent |
| **New class** — label space changes | **major** (1.0 → 2.0) | no comparable predecessor exists |

```
if candidate.data_major != champion.data_major:
        promote directly              # different label space -> comparison is meaningless
else:
        champion/challenger on frozen golden@major -> shadow -> verdict -> promote | reject
```

**Why the major rule exists.** A model trained without class *X* has never been given the
chance to learn *X*. Scoring it against a model that has seen *X*, on a benchmark containing
*X*, measures the label space rather than model quality. Rather than produce a misleading
number, cross-major comparison is **refused** and the new model is promoted directly.

**Golden is frozen for the lifetime of a major.** Minor bumps add rows to `train`/`stream`
only — never to `golden` — so every within-major comparison is measured on identical rows.

A major bump builds golden as a **superset**:

```
golden@2 = golden@1 (identical rows, unchanged) + held-out rows of the new class
```

Old classes therefore stay on identical rows across the boundary, so *"no regression on
previously-known classes"* remains an exact check even though overall scores are not comparable
across majors.

**Identity.** A data version is content-hashed with `sha256` over its sorted `(id, label)`
pairs, so "model X was trained on data Y" is provable rather than asserted. A version is
**immutable once sealed**.

## 2. State machines

```
data version:   draft ──seal──> sealed              (immutable; hash frozen)
model:          training ──> trained ──> evaluated ──> promoted | rejected ──> archived
promotion path: "direct" (cross-major)   |   "gated" (same-major)
```

`protected: true` marks the baseline (`branch1_v1`, data `1.0`). A demo reset may never modify
or archive a protected artifact.

## 3. Artifacts

All paths resolve through `configs/config.yaml`; nothing below is hardcoded.

| # | Artifact | Location | Form |
|---|---|---|---|
| A | Data-version registry | `data/versions/branch1/registry.json` | JSON |
| B | Run manifest | `models/<ver>/run_manifest.json` | JSON |
| C | Model metadata | `models/<ver>/metadata.json` | JSON (existing file, extended) |
| D | Gate decisions | `report/metrics/continual_learning/decisions.jsonl` | JSONL, append-only |
| E | Drift record | `report/metrics/continual_learning/drift.json` | JSON |
| F | Split manifest | `report/metrics/continual_learning/split_manifest.json` | JSON |
| G | Shadow report | `report/metrics/continual_learning/shadow.json` | JSON |
| H | Review queue | `data/overkill_queue.db` (`decision.queue_path`) | SQLite |
| I | Confirmed labels | `data/processed/confirmed_labels.jsonl` (`continual_learning.new_data_path`) | JSONL, append-only |

**Why files and not a database for A–G.** These are tens of records, append-mostly, and want to
be diffable in git and to sit beside the artifacts they describe. The repo already uses this
pattern (`models/branch1_v1/metadata.json`, preserved by a `.gitignore` exception). SQLite is
used for **H** only, where rows are genuinely mutable (pending → decided) and need paging.

**H and I are already declared in `config.yaml`** (`decision.queue_path`,
`continual_learning.new_data_path`) — implement those paths, do not invent new stores.

### 3.A Data-version registry

```json
{"dataset": "branch1",
 "versions": [
   {"version": "1.0", "state": "sealed", "protected": true,
    "parent": null, "bump": null, "created_at": "…", "reason": "baseline",
    "label_space": ["normal","union_based","error_based","boolean_blind","time_blind"],
    "n_rows": 67796, "content_hash": "sha256:…",
    "partitions": {"train": 27118, "golden": 6779, "stream": 33898},
    "golden_hash": "sha256:…"}]}
```

`golden_hash` is what makes the frozen-benchmark promise auditable: within a major it must
never change.

### 3.B Run manifest — the sealed training run

```json
{"run_id": "<sha256(train_config + data_content_hash + seed)[:12]>",
 "git_sha": "…", "created_at": "…", "status": "running|completed|failed",
 "data_version": "2.0", "data_content_hash": "sha256:…",
 "train_config": {"…full branch1_supervised snapshot…"},
 "split": {"method": "stratified", "seed": 42,
           "train_rows": 0, "valid_rows": 0,
           "train_ids_hash": "sha256:…", "valid_ids_hash": "sha256:…"},
 "metrics": {"f1_macro": 0.0, "per_class": {}},
 "duration_s": 0.0}
```

`run_id` is the **idempotency key**. Training computes it *first* and looks it up: an identical
`(train_config, data, seed)` run that already completed is reported and skipped unless forced.
The `train/valid` split is sealed by id-hash so a run is reproducible; `golden` is never part of
a run — it is the untouched test set, and `valid` exists only for threshold/early-stopping
choices.

### 3.C Model metadata (extension)

The existing file gains: `data_version`, `run_id`, `promotion_path` (`direct|gated`),
`promoted_at`, `state`, `protected`.

### 3.D Gate decision

```json
{"ts": "…", "candidate": "branch1_v2_1", "champion": "branch1_v2",
 "candidate_data": "2.1", "champion_data": "2.0",
 "comparison": "same_major | cross_major_refused",
 "golden_version": "2",
 "metrics": {"candidate": {}, "champion": {}},
 "criteria": {"f1_macro_ok": true, "fpr_ok": true,
              "per_class_ok": false, "failing_classes": ["time_blind"]},
 "verdict": "promote | reject | direct_promote", "reason": "…"}
```

### 3.E Drift record

```json
{"data_version": "2.0", "reference": "train@2.0", "psi_bins": 10, "threshold": 0.2,
 "windows": [{"index": 0, "phase": "A", "n": 1000,
              "psi": {"global": 0.03, "attack_subpop": 0.04, "prediction": 0.02},
              "rates": {"block": 0.048, "anomaly": 0.006, "overkill": 0.002},
              "alert": false}],
 "trigger": {"fired": true, "window_index": 41,
             "signal": "attack_subpop", "sustained_windows": 2}}
```

### 3.H Review queue (SQLite)

```sql
CREATE TABLE review_queue (
  id            TEXT PRIMARY KEY,
  created_at    TEXT NOT NULL,
  query_raw     TEXT NOT NULL,
  query_canonical TEXT NOT NULL,
  source        TEXT NOT NULL,   -- overkill | block | anomaly | low_confidence
  ai_label      TEXT,            -- the AI pre-label (Branch-1 prediction)
  ai_confidence REAL,
  anomaly_score REAL,
  status        TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|corrected|rejected
  final_label   TEXT,
  decided_at    TEXT,
  decided_by    TEXT,
  round_id      TEXT             -- lets a demo reset roll back exactly one round
);
```

### 3.I Confirmed labels (JSONL)

```json
{"id":"…","query_canonical":"…","label":"union_based","label_id":1,
 "ai_label":"union_based","was_corrected":false,"confirmed_at":"…","round_id":"…"}
```

---

## 4. Data partitions

Stratified and seeded, written as a `partition` column. **40 train / 10 golden / 50 stream**;
`valid` is 15 % carved out of `train`.

### 4.0 Deduplication — required before partitioning

`branch1_train.csv` contains **4,277 repeated `query_canonical` texts**, and **69 texts carry
conflicting labels**. Partitioning by row id would scatter copies of one query across `train`
and `golden`: the model would then be scored on text it had trained on. The first build did
exactly this and the invariants caught it (306 texts shared between golden and train, 54
between golden and stream).

So the split deduplicates on `query_canonical` first, and drops conflicting texts outright
rather than resolving them arbitrarily — they are genuine label noise and would silently cap
the achievable score.

**Verified** (`train/build_mlops_split.py`, run 28 Jul):

| Step | Rows |
|---|---:|
| input | 67,796 |
| dropped — 69 conflicting texts | −1,202 |
| dropped — duplicate texts | −3,144 |
| **kept → data version 1.0** | **63,450** |

> ⚠️ **Consequence: `branch1_v1` cannot be the champion.** It was trained on 54,236 rows from
> the old split, which overlap this golden partition — its golden scores would be inflated by
> data it had already seen. The experiment therefore **trains its own champion on `train@1.0`**.
> `branch1_v1` remains the model the service serves; it plays no part in the comparison.

**Verified partitions** (data version 1.0, 63,450 rows):

| Partition | Rows |
|---|---:|
| train | 21,573 |
| valid | 3,807 |
| golden | 6,345 |
| stream (Branch-1 share) | 31,725 |

`stacked` has **0 rows** in this file (excluded by `branch1_supervised.balance.exclude_labels:
[5]`). It is generated on demand by `src/preprocessing/synthetic_stacked.py` → **363** unique
templated payloads, and is the class used for the major-bump demonstration (§8).

### 4.1 Stream = realistic traffic at ~5 % attack

Real SQL traffic is overwhelmingly benign (`data_contract.md` notes real attack rates < 1 %),
so a stream built only from the balanced file would be ~78 % attack and worthless for
measuring FPR or drift. Benign is therefore padded from `data/processed/branch2_normal.csv`.

**Verified benign accounting:**

| Quantity | Rows |
|---|---:|
| `branch2_normal.csv` total | 91,935 |
| — unique by `query_canonical` | 90,650 |
| — excluded: Branch-2's own training rows | 11,152 |
| — excluded: every text already in Branch 1 | 13,856 |
| **available for the stream** | **76,768** |

Branch 1's `normal` class turns out to be drawn from this same CSIC pool (all 13,856 of its
canonical texts appear in it), so it must be excluded too — otherwise stream benign would
duplicate golden benign.

**Verified stream** (`data/processed/mlops_stream.csv`):

| Property | Value |
|---|---|
| rows | **80,808** (81 windows of 1,000) |
| attack rate | **5.00 %** (target 5 %) |
| phase A / phase B | 32,323 / 48,485 |
| class mix | normal 76,768 · boolean_blind 952 · time_blind 941 · union_based 896 · **stacked 727** · error_based 524 |

The new class is **727 of 80,808 queries = 0.9 % of traffic**, which is precisely the regime
§5 warns about: a global feature-drift monitor may never register it.

Phase-ordered: **phase A** contains no new class (establishes a quiet baseline); **phase B**
introduces it. Drift must be *observed* in B after being *verified absent* in A.

### 4.2 Invariants

Asserted by row id and recorded with their results in the split manifest (F):

1. `golden ∩ (train ∪ stream) = ∅`
2. `retrain_pool ∩ golden = ∅`
3. stream benign ∩ Branch-2 training rows = ∅ — that pool is Branch 2's training source, and
   reuse would leak into the anomaly scores the loop depends on
4. stream benign deduplicated by `query_canonical`

A contaminated golden set is the single failure that would invalidate every number in this
contract; see `AGENTS.md` § "Branch 3 — how to build this data correctly", rule 4.

---

## 5. Drift

**Metric:** PSI (`monitoring.drift_metric: psi`). **Reference:** the `train` distribution.
Bin edges are quantiles **fixed from the reference and persisted** — recomputing them per
window would make windows incomparable.

**Bands:** < 0.1 stable · 0.1–0.2 moderate · > 0.2 significant
(`monitoring.psi_alert_threshold: 0.2`).
**Trigger:** threshold breached in ≥ `sustained_windows` (default 2) consecutive windows —
a single-window spike is noise.

**Three populations, computed and reported side by side:**

| Signal | What it sees |
|---|---|
| `global` | the 4 Branch-2 structural features over all traffic |
| `attack_subpop` | the same features over flagged/attack traffic only |
| `prediction` | Branch-1 predicted-class distribution + block/anomaly/overkill rates |

> **Expected finding, to be measured rather than assumed.** At a 5 % attack rate a newly
> appearing class is ≈ 1 % of traffic, so **global PSI may never breach 0.2**. If global stays
> quiet while `attack_subpop` fires, that is itself a reportable result: *low-rate attack drift
> is invisible to global monitoring*, which is an argument for subpopulation-level drift
> tracking. Only `prediction` and `global` are computable without labels in a true production
> setting; `attack_subpop` uses the system's own flags, not ground truth, so it remains
> deployable.

---

## 6. Labelling loop — AI pre-label, human approve

The system never asks a human to label from scratch. Every queued item carries the model's own
prediction as a proposed label; the human accepts or corrects it.

```
stream replay ──> /detect ──> flagged? (OVERKILL | block | anomaly | low-confidence)
                                 │
                                 └─> review_queue row (status=pending)
                                     ai_label = Branch-1 predicted class
                                     ai_confidence, anomaly_score
                                 │
   Data page ── Approve ─────────┤  final_label = ai_label,  was_corrected = false
             ── Correct(label) ──┤  final_label = chosen,    was_corrected = true
             ── Reject ──────────┘  dropped, never trained on
                                 │
                                 └─> append to confirmed_labels.jsonl  ⇒ annotated pool
```

Which population enters the queue is config (`mlops.queue.sources`), defaulting to
`overkill + anomaly + low_confidence` — the cases where the model is *uncertain*, which is
where human review pays for itself.

**`was_corrected` is a metric, not bookkeeping.** The **pre-label acceptance rate** (share of
AI labels approved unchanged) measures model quality on live traffic for free, and is reported.

**Scale caveat — stated wherever these results appear.** The ~87k-query experiment flags
thousands of items; no human labels them all. The **offline experiment auto-confirms** by
revealing ground truth and is reported as **simulated labelling**. The **UI exercises the real
human path** on a sample. Both write the same schema (3.I), so everything downstream is
identical.

## 7. Sealing a version, and the gate

**Sealing.** Pressing *Train* reads the round's confirmed labels; if any exist it seals a new
data version — label space unchanged → **minor**, new class present → **major**. The bump is a
*consequence of what was approved*, never a manual choice. It then computes `run_id`, looks it
up, and trains or reports the existing run.

**Gate criteria** (same-major only; `continual_learning.min_f1`/`max_fpr` are `null`, meaning
"≥ / ≤ the incumbent"):

- `f1_macro(candidate) ≥ f1_macro(champion)`
- `fpr(candidate) ≤ fpr(champion)` — normal misclassified as attack
- no per-class recall drop > `mlops.gate.max_per_class_recall_drop`
- new-class recall ≥ `mlops.gate.min_new_class_recall`

**Shadow.** Before promotion the candidate scores live traffic alongside the champion; the
champion's verdict is enforced, the candidate's is logged only. Reported: agreement rate, the
disagreement matrix (especially *candidate allows / champion blocks*), per-class deltas, and
latency p50/p95.

**Promotion and rollback** are recorded in a **model registry** — `models/registry.json`
(runtime state, gitignored) — with MLflow-style stages:

```
production  — currently served
staging     — trained and evaluated, not serving
archived    — previously served, retained for rollback
```

Resolution order when loading a model:

1. the `production` entry in the model registry, if there is one;
2. otherwise `<branch>.active_version` from `config.yaml` — the declared baseline.

So a fresh clone with no registry serves exactly what config declares, rollback restores the
most recently archived version, and clearing the registry (what `/mlops/reset` does) is a full
revert to the baseline. No serving code is touched in any direction.

> **Superseded design (kept on record).** Promotion originally rewrote
> `branch1_supervised.active_version` *inside `configs/config.yaml`* at runtime. That conflated
> a committed declaration with runtime state: every promotion dirtied the git working tree
> (observed during testing), and rollback was a regex substitution on a tracked file. The
> registry replaces it. Config is now read-only at runtime.

**Why not MLflow?** MLflow's Model Registry would cover the stage/promotion mechanics above,
and its tracking UI would cover run comparison. It does **not** provide dataset versioning with
label-space semantics (§1), the cross-major comparison refusal (§7), drift measurement (§5) or
the review queue (§6) — those are ~1,400 of the ~1,700 lines here and would remain custom
regardless. Adopting MLflow would replace roughly 250 lines of persistence plumbing at the cost
of a heavy dependency and a tracking server. Reasonable for a later iteration; not worth a
rewrite of a verified system before the paper deadline.

---

## 8. The demonstration, and what it may not claim

**Act 1 — major bump, direct promotion.** `stacked` appears in stream phase B → new class →
data 2.0 (6 classes) → train → no comparable predecessor → promoted directly.

> ⚠️ **`stacked` demonstrates the mechanism only; its accuracy must not be reported as a
> detection result.** It is 100 % synthetic — 363 templated payloads — and `config.yaml`
> already records that it reached 100 % recall across all four compared architectures, flagged
> there as *"trivially separable, not a real signal of model quality"*. The genuine zero-day
> evidence for the paper is the existing leave-one-out finding that Branch 1 trained without
> `boolean_blind` misses **90.2 %** of it (`report/metrics/zeroday_experiment/summary.json`).

**Act 2 — minor bump, full gate.** More samples of known classes are confirmed → data 2.1 →
champion/challenger on frozen golden@2 → shadow → verdict → promote.

**Required negative control.** A second candidate trained with rehearsal starved
(`rehearsal_old_fraction ≈ 0`) must be **rejected** by the gate for per-class regression. A gate
that only ever approves demonstrates nothing.

**Required ablation.** A control arm retrained on the *same number* of extra samples but
containing **no new class**. If it closes the gap too, the improvement came from data volume
rather than from learning the new class, and the headline claim does not stand.

---

## 9. Caveats carried into any report

1. `stacked` is synthetic → mechanism only, never a detection number (§8).
2. ~13 % label noise in `boolean_blind` (`data_contract.md` §3.1).
3. Labelling is simulated at experiment scale (§6).
4. Traffic is a **replay** of held-out data, not live production traffic.
5. Stream benign originates from CSIC 2010 HTTP traffic, not from the same source as the
   Branch-1 attack rows — a distribution seam that exists by construction.

## 9b. Implementation notes (found while wiring the service)

Three constraints emerged that the design did not anticipate. They are recorded here
because each one silently breaks the loop if reintroduced.

**Label representation.** `train/train_branch1.py` fits on integer label *ids*, while
`src/continual_learning/trainer.py` fits on label *names*. A model promoted from the
continual-learning path therefore broke `deploy/registry.py`, which assumed integers
(`int(c) for c in clf.classes_` → `ValueError`). The registry now normalises either
representation to names, and `compute_evaluation` coerces both sides — mixing them makes the
label set unsortable and the comparison meaningless.

**Two registries, not one.** The offline experiment originally sealed its versions into
`data/versions/branch1/registry.json`, the same registry the service reads. The gate then
compared a deployed model against a version no deployed model had ever been trained on, and
invented a spurious major-version gap (`1.0 → 2.1`) that made it refuse a comparison it should
have made. The experiment now keeps its lineage in
`report/metrics/continual_learning/version_registry.json`; only the service writes to the
service registry.

**Champion lineage comes from metadata.** A champion's data version is read from its own
`metadata.json`, not from `mlops.baseline.data_version` — reading it from config attributes the
baseline version to whatever happens to be deployed.

**Replay must exceed the baseline.** A replay shorter than
`mlops.drift.baseline_windows × window_size` produces only reference windows, so the chart
compares the baseline against itself. The UI now refuses to interpret such a run.

## 10. Out of scope

Traffic-split A/B with enforcement · scheduled retrain daemon · authentication on admin
actions · Branch 3 · real training behind `/train` for Branch 2/3 (Branch 1 only).
