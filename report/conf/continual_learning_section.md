# Continual Learning under Versioned Data — paper-ready sections

> Drop-in material for `rivf2026_paper.tex`, written in the paper's existing voice.
> Every number is verified against `report/metrics/continual_learning/` (run 28 Jul 2026);
> reproduce with `train/build_mlops_split.py` then `train/run_continual_learning_experiment.py`.
> Figures: `report/metrics/figures/cl_*.png`.

---

## Abstract — sentence to insert

> We additionally evaluate a continual-learning loop under versioned data and report a
> negative result with direct operational consequence: a previously unseen attack class
> constituting 0.9\% of traffic triggers **no** distribution-drift alarm across five monitored
> signals, while confidence-based review routing surfaces every instance of it — indicating
> that at realistic attack rates, human-in-the-loop triage rather than drift monitoring is the
> mechanism that detects novel classes.

---

## III. Proposed System — new subsection

### III-F. Data Versioning and the Promotion Gate

Retraining a deployed detector on newly labelled traffic raises a question that accuracy
metrics alone cannot answer: *when is a candidate model comparable to the one it would
replace?* We attach a `major.minor` version to the training data and record, for every model,
the data version it was trained on. Adding samples within an unchanged label space is a
**minor** bump; introducing a class changes the label space and is a **major** one.

The distinction is not bookkeeping. A model trained before class $X$ existed has never been
given the opportunity to learn $X$; scoring it against a model that has seen $X$, on a
benchmark containing $X$, measures the benchmark's composition rather than the models. Our
gate therefore **refuses** cross-major comparison and promotes the new model directly,
recording the refusal, rather than emitting a number that would invite the wrong conclusion:

$$
\text{if } \mathrm{major}(d_\text{cand}) \neq \mathrm{major}(d_\text{champ}) \Rightarrow
\text{promote directly; else compare on the frozen benchmark.}
$$

Within a major version the evaluation set is **frozen**: minor bumps add rows only to the
training and stream partitions, never to the benchmark, so every within-major comparison is
computed over identical rows. A major bump extends the benchmark as a *superset* — the
previous benchmark rows unchanged, plus held-out rows of the new class — so that "no
regression on previously-known classes" remains an exact comparison across the boundary even
though aggregate scores are not comparable.

Each data version is identified by a SHA-256 digest over its sorted $(\text{id},
\text{label})$ pairs, making the binding between a model and its training data verifiable
rather than asserted, and each training run is keyed by a digest over
$(\text{configuration}, \text{data digest}, \text{seed})$ so that repeated runs are detected
instead of silently repeated.

A candidate is promoted only if, on the frozen benchmark, it does not reduce F1-macro, does
not increase the false-positive rate, loses no more than $\varepsilon = 0.02$ recall on any
known class, and reaches at least 0.80 recall on any newly introduced class.

### III-G. Review Routing and Pre-Labelling

Queries whose verdict is uncertain — those held by the Overkill policy, flagged as anomalous,
or classified below a confidence threshold — are routed to a review queue. Each entry carries
the model's own prediction as a **proposed label**, so the reviewer's task is acceptance or
correction rather than annotation from scratch. Whether a proposal was corrected is retained,
making the **pre-label acceptance rate** an observable measure of model quality on live
traffic. Confirmed labels accumulate into the next data version, which determines the bump
and hence the promotion path.

---

## IV. Dataset and Experimental Setup — new subsection

### IV-E. Continual-Learning Protocol

**Partitioning.** The Branch-1 corpus is partitioned 40/10/50 into training, benchmark
("golden") and replay-stream partitions, stratified by class, with a further 15\% of the
training partition held out for validation. Deduplication by canonical text is applied
*before* partitioning: the corpus contains 4,277 repeated texts and 69 texts carrying
conflicting labels, and partitioning by row identifier scattered copies of the same query
across the training and benchmark partitions. This is measurable leakage — an initial build
placed 306 texts in both — and the deduplicated corpus retains 63,450 rows. For the same
reason the deployed Branch-1 model cannot serve as the incumbent in this experiment: it was
trained on rows now assigned to the benchmark, so a fresh incumbent is trained on the
training partition alone.

**Replay stream.** Evaluating drift on the class-balanced corpus would be misleading, since
real traffic is overwhelmingly benign. We therefore construct a stream at a **5\% attack
rate** by padding with benign queries drawn from the CSIC 2010 pool, excluding both
Branch-2's own training rows (whose reuse would leak into the anomaly scores the loop
consumes) and every text already present in the Branch-1 corpus. The result is 80,808 queries
across 81 windows of 1,000. The stream is phase-ordered: phase A contains no new class and
establishes a baseline; phase B introduces one at window 33.

**New class.** `stacked` queries are introduced as the novel class, comprising 727 stream
occurrences (0.9\% of traffic). This class is synthetic — 363 templated payloads sampled with
replacement — and is used to exercise the *mechanism* of a major bump. Its recall is
consequently **not** reported as a detection result; the paper's zero-day evidence remains the
leave-one-out study of Section~V.

**Drift signals.** PSI is computed per window against a reference fixed on the first ten
stream windows, with quantile bin edges fitted once on that reference and reused thereafter.
Referencing the training distribution instead is incorrect here and was measured to be so: the
corpus is $\approx$78\% attack against a 95\%-benign stream, and PSI read $\approx$1.0 from the
first window, reporting the construction difference rather than drift. Five signals are
tracked: structural features over all traffic and over flagged traffic only, the
predicted-class distribution, and top-class confidence over all and over flagged traffic. The
alert threshold is the conventional PSI $= 0.2$, requiring two consecutive breaching windows.

---

## V. Experimental Results — new subsections

### V-E. Drift Monitoring at a Realistic Attack Rate

Table~\ref{tab:drift} reports every monitored signal across both phases.

**Table \ref{tab:drift}.** PSI per signal. Phase A is the quiet period after the reference
window; phase B contains the new class. Threshold $= 0.2$.

| Signal | Phase A mean | Phase B mean | Phase B max | Alarm |
|---|---:|---:|---:|:--:|
| Structural features, all traffic | 0.0069 | 0.0077 | 0.0127 | — |
| Structural features, flagged only | 0.0445 | 0.0495 | 0.1157 | — |
| Predicted-class distribution | 0.0059 | 0.0090 | 0.0280 | — |
| Confidence, all traffic | 0.0111 | 0.0108 | 0.0234 | — |
| Confidence, flagged only | 0.0613 | 0.0757 | 0.1896 | — |

**No signal raises an alarm.** The most responsive, confidence restricted to flagged traffic,
peaks at 0.1896 in phase B — but already reaches 0.13 during phase A, when nothing has
changed. Lowering the threshold to capture the former would therefore also fire on the latter.
Restricting to flagged traffic concentrates the novel class roughly twentyfold relative to the
full stream, and even that is insufficient.

The result is a straightforward consequence of arithmetic that we believe is under-stated in
practice: at a 5\% attack rate a novel *class* is a fraction of a fraction of traffic, and
aggregate distribution statistics are dominated by the benign majority. Over the same stream,
confidence-based review routing surfaced **all 727** instances. We conclude that at realistic
attack rates, drift monitoring is the wrong instrument for detecting a novel class, and
uncertainty-based triage is the right one; drift monitoring retains its value against gradual
population shift, which is a different phenomenon.

*Figure: `cl_drift_windows.png`.*

### V-F. Label Review

Of 80,808 replayed queries, 21,934 were routed for review. The **pre-label acceptance rate was
46.0\%**: the model's proposed label survived review in fewer than half of the cases, which is
expected given that the queue selects precisely the queries about which it is least certain.
At this scale review is simulated, with ground truth substituted for a human annotator; the
same code path is exercised by a human in the interactive system.

### V-G. Promotion Decisions

The new class produces a major bump, and the gate declined the comparison and promoted
directly, as specified. The subsequent minor bump admits a genuine comparison, and we
evaluate two candidates trained on *identical* confirmed traffic differing only in how the
retraining pool was assembled (Table~\ref{tab:gate}).

**Table \ref{tab:gate}.** Promotion outcomes on the frozen benchmark (golden@2).

| Candidate | Pool rows | F1-macro | FPR | Outcome |
|---|---:|---:|---:|---|
| Incumbent (data 2.0) | 21,671 | 0.9573 | 0.0638 | — |
| Naive pool (raw confirmed) | 43,351 | 0.9425 | — | **rejected** |
| Balanced pool | 24,291 | **0.9623** | **0.0225** | **promoted** |
| Starved rehearsal (1\% retained) | 469 | 0.8315 | 0.1284 | **rejected** |

Retraining directly on confirmed traffic **degrades** the model: because the majority of
flagged queries are benign false positives, the pool skews toward `normal` and attack recall
falls (boolean-blind $-0.109$, stacked $-0.055$), and the gate rejects it. Balancing the same
confirmed traffic by class before retraining yields a candidate that improves F1-macro and
reduces the false-positive rate by **64\%** (0.0631 $\to$ 0.0225) with no per-class
regression. That two candidates derived from the same labelled data are separated by pool
construction alone is, in our view, the practically important finding of this section.

The starved-rehearsal candidate is a negative control: trained almost exclusively on the new
class, it forgets boolean-blind ($-0.508$ recall) and is rejected. A gate that only ever
approves would not evidence anything.

*Figure: `cl_gate_outcomes.png`.*

**Table \ref{tab:clperclass}.** Per-class recall, incumbent versus promoted candidate.

| Class | Incumbent (1.0) | Promoted (2.1) |
|---|---:|---:|
| `normal` | 0.9369 | **0.9775** |
| `union_based` | 0.9869 | 0.9876 |
| `error_based` | 1.0000 | 1.0000 |
| `boolean_blind` | 0.9864 | 0.9757 |
| `time_blind` | 0.9993 | 0.9993 |
| `stacked` | — (unseen) | 0.7260 |

### V-H. Ablation and Shadow Deployment

To establish that the improvement on the new class reflects *learning that class* rather than
the addition of data, a control was retrained on the same 254 additional rows drawn
exclusively from classes already known. It attains **0.000** recall on the new class, against
**0.726** for the candidate. The effect is therefore attributable to the class rather than to
volume.

*Figure: `cl_control_ablation.png`.*

Prior to promotion the candidate was run in shadow over phase B, with the incumbent's verdict
enforced and the candidate's recorded only. The two agreed on **98.85\%** of queries, and the
candidate permitted **13** queries the incumbent blocked, indicating no unsafe divergence.

---

## VI. Discussion and Limitations — additions

**Drift monitoring has a detection floor.** Our measurements indicate that distribution-based
drift monitoring does not detect a novel attack class at $\approx$1\% of traffic, under any of
five signal definitions including subpopulation-restricted ones. Practitioners deploying such
monitors against rare-class emergence should calibrate expectations accordingly, and treat
uncertainty routing as the primary detector. We did not explore windowed cumulative statistics
(e.g.\ CUSUM) or per-class conditional monitoring, either of which might lower this floor;
this is left to future work.

**Feedback-loop bias in confirmed data.** Labels harvested from a model's own flagged traffic
are not a random sample of production traffic — they over-represent the model's false
positives. Retraining on them naively degraded the model in our experiment, and the effect was
large enough for the promotion gate to reject the candidate. Class balancing was sufficient
here; whether importance weighting or stratified acceptance performs better is untested.

**The synthetic new class.** `stacked` payloads are templated and were sampled with
replacement to reach the target rate. They are adequate for exercising the versioning and
promotion mechanism, and we deliberately draw no detection conclusion from the 0.726 recall
figure. A study using a genuinely novel, naturally occurring attack family would strengthen
the drift finding in particular, since a structurally distinctive family might well breach a
threshold that these payloads do not.

**Simulated annotation.** Ground truth substitutes for a human reviewer at experiment scale.
The 46.0\% acceptance rate therefore measures model–ground-truth agreement on uncertain
queries, not human behaviour; real reviewers introduce their own error and latency.

**Replayed traffic.** The stream is a replay of held-out data with a synthetic temporal
ordering, not a live capture, and its benign portion originates from CSIC 2010 HTTP traffic
while attack rows come from D1/D4/D7 — a distribution seam present by construction.

---

## VII. Conclusion — sentence to insert

> Finally, we constructed a versioned continual-learning loop in which comparison across a
> label-space change is refused rather than approximated, and used it to show that a novel
> attack class at 0.9\% of traffic evades five distinct drift signals while being fully
> captured by uncertainty-based review routing — and that how a retraining pool is assembled
> from reviewed traffic determines whether the resulting model is an improvement or a
> regression.

---

## Reproduction

```bash
uv run python train/build_mlops_split.py               # partitions + replay stream
uv run python train/run_continual_learning_experiment.py
uv run python train/plot_continual_learning.py         # figures
```

Artifacts land in `report/metrics/continual_learning/` (`drift.json`,
`experiment_results.json`, `decisions.jsonl`, `shadow.json`, `split_manifest.json`,
`RESULTS.md`) and `report/metrics/figures/cl_*.png`.
