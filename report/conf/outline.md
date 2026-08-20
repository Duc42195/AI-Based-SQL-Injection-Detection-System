# RIVF 2026 Paper — Outline

> Full project history (not just the paper): [`project_history.md`](project_history.md). This file is the writing outline only — section-by-section, mirroring [`rivf2026_paper.tex`](rivf2026_paper.tex), stating what each section should contain.

**Target:** RIVF 2026 (IEEE, https://rivf2026.org/) — 2-column IEEEtran `conference` format.
**Template:** [`report/conf/conference_101719.tex`](conference_101719.tex)
**Submission deadline:** 30 Aug 2026.
**Page budget:** nominally 6 pages (verify RIVF's CFP for the exact limit and whether over-length pages are allowed for a fee — still not confirmed). Current draft is ~4,760 words of body text plus 5 figures and 7 tables — that alone is consistent with ~6 pages already, before the additions below. Get a real Overleaf compile before writing more; no LaTeX engine is available locally to check exactly.

---

## Abstract
150-250 words: problem (SQLi at the DB proxy, blind/zero-day gap), approach (multi-branch AI detector), headline results (Branch 1 F1-macro 0.9907; Branch 2 AUC 0.929; Branch 3 zero observed false positives on held-out sessions; Continual Learning's drift-vs-queue finding). Write last, after every number below is final.

## I. Introduction
Contributions list (4-5 bullets): multi-branch detector at the DB proxy; zero-day leave-one-out study; Session Correlator for blind/multi-step SQLi; the Continual Learning ablation/gate finding. No structural change needed — only the cited numbers move when the sections below change.

## II. Related Work
No change needed.

## III. Proposed System
- **A. System Placement.** DB proxy, "Position B," post-build pre-DB. One figure: architecture diagram (three branches → decision engine) — still a placeholder box, Minh's to draw.
- **B. Canonicalization.** Anti-evasion normalization (`src/preprocessing/canonicalize.py`) — decode common encodings, fold keyword case, mark (not strip) comments.
- **C. Branch 1 — Supervised Multi-Class.** TF-IDF + Logistic Regression, 5 classes. Method description unchanged; compares 4 candidate architectures (§V.A table) on accuracy/latency/size trade-off.
- **D. Branch 2 — Query-Level Anomaly Detection.** Rewrite to the current pipeline: 12 features — the original 4 statistical (`length`, `special_char_ratio`, `sql_keyword_count`, `entropy`) plus `quote_imbalance` and 6 "local peak" features (`same_type_run_ratio`, `max_token_length`, `token_count`, `max_special_run`, `max_digit_run`, `paren_imbalance`) that measure a local run/token rather than a whole-string ratio, so long HTTP-derived parameter strings don't dilute the signal. **What we tried:** a single global One-Class SVM boundary judged genuinely-benign traffic from one data source as anomalous simply for "not looking like" another source; a per-source ensemble (one model per data source, OR'd) was tried next and rejected (FPR rose to ≈41%, too costly); LocalOutlierFactor's local-density notion was adopted instead, since it judges each point against its own neighborhood rather than one global boundary. One sentence only here — the comparison table goes in §V.B.
- **E. Branch 3 — Session-Level Correlation.** Mechanism unchanged: a content check (concatenate session query text, re-score with Branch 1, no retraining) OR'd with a behavior check (aggregate Branch 2's per-query scores), calibrated on TRAIN, evaluated on TEST. Keep the existing GRU→SessionCorrelator redesign narrative (§III.E already covers this well — an earlier sequence-model design collapsed the content signal it needed and was replaced). **Add the session-generation design choice**: the 100-user synthetic target pool used to generate `boolean_blind`/`time_blind` sessions is partitioned into disjoint train-target/test-target subsets *before* generation (rather than splitting sessions after generation), so that a target user probed during calibration is never reused at test time — the more defensible design given the bisection algorithm is deterministic per target. One sentence.
- **F. Decision Engine and Overkill Policy.** Unchanged.
- **G. MLOps / Continual-Learning Design — currently missing from the paper, needs to be added.** §V already reports a "Continual Learning" results subsection (drift monitor, review queue, validation gate) that nothing in §III introduces. Add 3-5 sentences here, before or after F: (1) drift monitoring — PSI over tracked feature/confidence signals against a reference window, alert threshold 0.2; (2) review queue — flagged queries held for confirmation, confirmed labels feed the retrain pool; (3) validation gate — a retrain candidate is promoted only if it matches or beats the champion on FPR/F1 on a fixed validation set, with major-bump (new label) handled differently from minor-bump (same labels). Design/mechanism only; §V already has the evaluation.

## IV. Dataset and Experimental Setup
- **A. Data Sources.** One line per dataset, not one paragraph for all four:
  - **D1 (SQLiV3):** Kaggle SQLi query collection, ~30.9K rows, plain SQL/query text — matches the system's Position-B input directly. License provenance unclear (state in Discussion).
  - **D3 (CSIC 2010):** HTTP traffic corpus, captured as full HTTP requests (scheme+host+path+query/body), not raw SQL — stripped to query-string/body parameters to approximate Position-B input. Used for benign enrichment and, held out, as an anomalous evaluation set; state plainly that its attack rows aren't SQLi-only.
  - **D4 (payload-box):** MIT-licensed SQLi payload strings, 177 payloads, split by DBMS/technique — supplements Branch 1's rarer classes.
  - **D7 (SR-BH 2020):** CC0 honeypot dataset, 527,813 rows, multi-label CAPEC-tagged; re-tagged into SQLi sub-types by the same rule-based tagger as D1/D4; same full-HTTP-request format as D3, same stripping applied.
- **B. Branch 1 Dataset.** Describe the filtering: content-based signature filtering removed mislabeled attacks from the `normal` pool over three rounds; rule-based re-tagger priority order `stacked > time_blind > error_based > union_based > boolean_blind`. SSRF/OS-command payloads are deliberately *not* filtered from Branch 1's `normal` pool (a SQLi-vs-not-SQLi classifier doesn't need that scope) — a stated design choice, not an oversight. **Dataset preparation**: `query_canonical` is deduplicated before the stratified train/test split, so evaluation queries are never verbatim duplicates of training queries; this also lets the class-balancing step draw from a larger pool of distinct rows. **Feature engineering**: TF-IDF vectorization (pull the exact `ngram_range`/vocabulary size from `train/train_branch1.py`/`configs/config.yaml` when drafting — don't guess) feeding Logistic Regression. `stacked` excluded (zero natural samples; synthetic substitutes were trivially separable).
- **C. Branch 2 Dataset.** **Filtering**: benign pool combines D1+D3+D7 after (a) a content-signature filter rejecting any attack-like traffic (broader than Branch 1's SQLi-only filter) and (b) stripping D3/D7 rows to their query-string/body parameters, dropping rows with nothing left (bare static-asset requests). The anomalous evaluation set spans confirmed-SQLi rows from D1+D3+D7 (D7 via its own CAPEC "SQL Injection" column). **Feature engineering**: 12 features (§III.D); log-transform on `length`/`max_token_length`/`max_special_run`/`max_digit_run`; all features scaled before fitting LocalOutlierFactor (`n_neighbors=5`).
- **D. Branch 3 Dataset.** Sessions generated by running the real bisection algorithm (length probe, then per-character ASCII probe) against a self-hosted database — 1,400 sessions across four classes, 1,120 train / 280 test, session-level split. The 100-user target pool for `boolean_blind`/`time_blind` is partitioned into disjoint train/test subsets before generation (§III.E). Collecting an independently-captured dataset (real attack tooling against a deliberately vulnerable application) is noted once, in Conclusion/Future Work, as the intended generalization test — not repeated here as an open caveat.
- **E. Evaluation Protocol.** F1-macro/precision/recall/confusion matrix/ROC (B1); FPR/detection-rate/AUC/threshold sweep (B2); FPR/detection-rate ablation (B3). Seed=42, deterministic. One line: Branch 2's LocalOutlierFactor inference cost (a k-NN lookup against the training set, unlike a fixed linear boundary) has only been benchmarked offline — cite this only after it's re-measured against the live endpoint (see §V.F).

## V. Experimental Results
- **A. Branch 1.** **F1-macro = 0.9907** (`report/metrics/branch1_eval.json`) — update the per-class table and the 4-architecture comparison table (`tab:b1arch`) from this file directly; both improved slightly after the dedup change (§IV.B), don't reuse the older 0.9822-era numbers.
- **B. Branch 2 — needs a full rewrite of numbers, table, and figure.**
  - Headline: **AUC = 0.929**, detection rate ≈80% at a matched ~5% FPR operating point (pull the exact matched-FPR figure from `report/metrics/branch2_eval.json`/`branch2_threshold_sweep.csv` when drafting).
  - **Comparison table** (same shape as `tab:b1arch`, on the same final dataset): One-Class SVM → Isolation Forest → LocalOutlierFactor (chosen), with FPR/detection-rate/AUC columns from `report/metrics/branch2_eval.json`'s `algorithms` block. This table, plus the one sentence in §III.D about the rejected per-domain-ensemble variant, together *is* the "what we tried" answer for this branch — no separate section needed (see note at the end of this file).
  - Figures available but not yet wired into the `.tex`: `branch2_score_dist.png`, `branch2_pr_curve.png`, `branch2_threshold_tradeoff.png` (all in `report/metrics/figures/`) — pick one or two, see the page-budget note at the end.
- **C. Zero-Day Study.** Unchanged — numbers independently cross-checked against `report/metrics/zeroday_experiment/summary.json` and confirmed exact.
- **D. Branch 3.** Update `tab:b3` to:

  | Configuration | FPR | DR bool. | DR time | DR split |
  |---|---:|---:|---:|---:|
  | Content only | 0.0 | 1.0 | 1.0 | 1.0 |
  | Behavior only | 0.0 | 1.0 | 1.0 | **0.457** |
  | Combined | 0.0 | 1.0 | 1.0 | 1.0 |

  (`report/metrics/branch3_eval.json`, under the disjoint train/test target-pool design, §III.E). Present this as the ablation's actual finding, not a caveat to soften: the behavior check alone doesn't fully catch `query_splitting`; the content check does, and the two combined inherit the content check's coverage — each check has a genuine, distinct blind spot the other closes, which is a stronger result than an all-1.0 table would be. Keep the existing zero-day ablation paragraph as-is (content-check detection rate = 0.0 against a classifier genuinely blind to `boolean_blind`, mean attack probability 0.221) — a real, honestly-reported limitation.
- **E. Continual Learning.** Numbers unchanged from the current draft — cross-checked against `report/metrics/continual_learning/RESULTS.md` and confirmed to match.
- **F. Latency Budget.** Needs re-deriving: the current text describes Branch 2 as "sub-millisecond, linear SVM decision" — no longer accurate now that Branch 2 is LocalOutlierFactor (a k-NN lookup, not a fixed boundary). Re-measure against the live `/api/v1/detect` endpoint before restating the 1-2ms budget claim.
- **G. Illustrative Demonstration.** Unchanged.

## VI. Discussion and Limitations
Add: LocalOutlierFactor's model-size/latency trade-off (larger artifact than a fixed-boundary model; k-NN lookup per inference) as a stated cost of the design choice in §III.D. Existing bullets (label noise, dataset licensing, synthetic `stacked` class, threat-model boundaries, adversarial-robustness gap, Branch 3's self-generated-session caveat) otherwise unchanged.

## VII. Conclusion and Future Work
Update Branch 2's cited numbers once §III.D/§V.B are rewritten. Keep the existing GRU→SessionCorrelator methodological note. No structural change.

## References
No change needed.

---

## "What we tried and rejected" — is it worth writing up, where, and does it fit in 6 pages?

**Worth it, but only extending a pattern the paper already uses — not a new section.** The paper already carries this for three branches: Branch 1's 4-architecture comparison table, Branch 3's GRU→SessionCorrelator redesign narrative, and Continual Learning's naive/balanced/starved-rehearsal gate table. Branch 2 is the one branch missing it, despite having the largest experimentation history (OCSVM → a confound feature identified and dropped → a rejected per-domain ensemble → Isolation Forest → LocalOutlierFactor). Fix: one sentence in §III.D (above) + the comparison table in §V.B (above) — matching the existing shape exactly, not a dedicated "ablations" section, which would cost page budget without adding a new kind of evidence.

**What doesn't need writing up:** minor sub-experiments that didn't change a shipped design and aren't cited as evidence for anything — at most a clause in a Limitations bullet, never a paragraph.

**Page budget:** likely already near 6 pages before any of the above (see the top of this file). If a real compile puts it over budget once the fixes land, cut in this order: §V.G Illustrative Demonstration first (weakest evidentiary value, one paragraph) → keep only one of the two Continual-Learning figures (both currently illustrate a point already stated in prose) → only one of the three Branch-2 figures goes in. Confirm RIVF's actual page limit before cutting further.
