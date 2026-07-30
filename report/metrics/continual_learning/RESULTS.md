# Continual-learning experiment — results

> Produced by `train/build_mlops_split.py` + `train/run_continual_learning_experiment.py`,
> run 28 Jul 2026. Design and invariants: [`report/plan/mlops_contract.md`](../../plan/mlops_contract.md).
> Figures: `report/metrics/figures/cl_*.png`.

## Setup

| | |
|---|---|
| Data version 1.0 | 63,450 rows, 5 classes (train 21,573 · valid 3,807 · **golden 6,345** · stream 31,725) |
| Replay stream | 80,808 queries, 81 windows × 1,000, **5.00 % attack** |
| New class | `stacked`, entering at window 33 — **727 queries = 0.9 % of traffic** |
| Champion | trained on `train@1.0`; F1-macro **0.9819**, FPR **0.0631** on golden@1 |

`branch1_v1` is *not* used as the champion: it trained on rows now in golden, so its scores
there would be inflated. The experiment trains its own champion on `train@1.0`.

---

## 1. Drift monitoring — the negative result

**No signal fires.** Five signals were tracked against a reference of the first 10 stream
windows, threshold PSI = 0.2:

| Signal | Phase A mean | Phase B mean | Phase B max | Fired |
|---|---:|---:|---:|:--:|
| Structural features, all traffic | 0.0069 | 0.0077 | 0.0127 | no |
| Structural features, flagged only | 0.0445 | 0.0495 | 0.1157 | no |
| Predicted-class distribution | 0.0059 | 0.0090 | 0.0280 | no |
| Confidence, all traffic | 0.0111 | 0.0108 | 0.0234 | no |
| **Confidence, flagged only** | 0.0613 | **0.0757** | **0.1896** | no (closest) |

**A new attack class at ~1 % of traffic is invisible to distribution drift.** Even restricted
to flagged traffic — a ~20× concentration — confidence PSI peaks at 0.19 against a 0.2
threshold. Lowering the threshold to catch it would mean alerting on phase A too, where the
same signal already reaches 0.13.

The practical consequence: **the review queue, not the drift monitor, is what surfaces a novel
class.** Routing low-confidence and anomalous queries to a human caught all 727 instances while
every distribution monitor stayed silent. Drift monitoring earns its place against gradual
population shift, not against a rare new class.

*Figure:* `cl_drift_windows.png`

## 2. Labelling

21,934 queries were flagged and reviewed. **Pre-label acceptance rate: 46.0 %** — the model's
proposed label survived review in fewer than half of the cases it was unsure about, which is
expected given the queue deliberately selects the cases where it is least confident.

At this scale labelling is **simulated**: ground truth stands in for the reviewer. The UI
exercises the identical path with a human on a sample.

## 3. Act 1 — major bump, direct promotion

`stacked` is a new label, so data **1.0 → 2.0** is a major bump. No comparable predecessor
exists, and the gate **refused the comparison and promoted directly**
(`comparison: cross_major_refused`) rather than producing a number that would have measured
the benchmark rather than the models.

## 4. Act 2 — minor bump, and why the pool matters

Both candidates saw the *same* confirmed traffic; only how the pool was assembled differed.

| Candidate | Pool | F1-macro | FPR | Verdict |
|---|---:|---:|---:|---|
| Champion (data 2.0) | 21,671 | 0.9573 | 0.0638 | incumbent |
| Naive — raw confirmed | 43,351 | 0.9425 | — | **REJECT** (F1 ↓; boolean_blind −0.109, stacked −0.055) |
| **Balanced confirmed** | 24,291 | **0.9623** | **0.0225** | **PROMOTE** |
| Starved rehearsal (1 % old data) | 469 | 0.8315 | 0.1284 | **REJECT** (boolean_blind −0.508) |

Retraining on raw confirmed traffic **degrades the model**: most flagged queries are benign
false positives, so the pool skews toward `normal` and attack recall falls. Balancing the
confirmed pool first is what earns promotion — and it cuts FPR by **64 %** (0.0631 → 0.0225)
with no per-class regression.

The starved-rehearsal candidate is the negative control: it forgets `boolean_blind` almost
entirely (−0.508 recall) and is rejected. A gate that only ever approves would demonstrate
nothing.

*Figure:* `cl_gate_outcomes.png`

### Per-class recall, champion → promoted

| Class | Champion (1.0) | Promoted (2.1) |
|---|---:|---:|
| normal | 0.9369 | **0.9775** |
| union_based | 0.9869 | 0.9876 |
| error_based | 1.0000 | 1.0000 |
| boolean_blind | 0.9864 | 0.9757 |
| time_blind | 0.9993 | 0.9993 |
| stacked | — (unknown) | 0.7260 |

*Figure:* `cl_per_class_recall.png`

## 5. Ablation — was it the class, or just more data?

A control was retrained on the **same +254 rows** drawn only from classes the model already
knew:

| Arm | Extra rows | Recall on the new class |
|---|---:|---:|
| Control — no new class | 254 | **0.000** |
| Candidate — with new class | 254 | **0.726** |

The gain is attributable to learning the class, not to data volume. Without this arm the
headline result would not stand.

*Figure:* `cl_control_ablation.png`

## 6. Shadow

Replaying phase B with the champion enforced and the candidate logged: **98.85 % agreement**,
and the candidate allowed only **13** queries the champion blocked — no unsafe divergence
before promotion.

---

## Caveats

1. **`stacked` is 100 % synthetic** — 363 templated payloads, sampled with replacement to reach
   727 occurrences. It demonstrates the major-bump *mechanism*; its 0.726 recall is **not** a
   detection result. The genuine zero-day evidence is the existing `boolean_blind`
   leave-one-out finding (90.2 % miss) in `report/metrics/zeroday_experiment/`.
2. Labelling is simulated at experiment scale (§2).
3. Traffic is a **replay** of held-out data, not live production traffic.
4. ~13 % label noise in `boolean_blind` (`report/plan/data_contract.md`).
5. Stream benign originates from CSIC 2010 HTTP traffic while the attack rows come from
   D1/D4/D7 — a distribution seam that exists by construction.
6. Deduplication dropped 3,144 duplicate texts and 69 conflicting-label texts before
   partitioning; without it, golden overlapped train and every comparison would have been
   inflated.
