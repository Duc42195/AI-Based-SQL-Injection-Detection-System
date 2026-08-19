# RIVF 2026 Paper — Outline & Writing Plan

> 📜 **Full project history** (not just the paper): [`project_history.md`](project_history.md) — the "what was tried, what changed, when" log, organized by Branch 1/2/3, decision engine, MLOps. This file (`outline.md`) is the **writing outline only** — it mirrors [`rivf2026_paper.tex`](rivf2026_paper.tex)'s actual section structure with what still needs to change in each section. No more writability tracking (✅/✍️/⛔) — everything below is either "matches the current `.tex`" or "needs this specific edit."

**Target:** RIVF 2026 (IEEE, https://rivf2026.org/) — 2-column IEEEtran `conference` format.
**Template:** [`report/conf/conference_101719.tex`](conference_101719.tex)
**Submission deadline:** 30 Aug 2026.
**Page budget:** nominally 6 pages — **still unverified against RIVF's actual CFP** (open since 24 Jul). See "Page budget" section near the bottom — current draft is likely already at or near 6 pages before the fixes below are applied.

---

## ⚠️ Open items before the paper is done (read this first)

### 1. Two confirmed data-validity findings — need a decision, not just a re-word

Both were flagged as *risks* in the original audit plan; both are now **confirmed findings** sitting in reports that nothing else points to yet.

- **Branch 3 (Session Correlator): same-target train/test leakage — CONFIRMED.** `report/metrics/audit_branch3/audit_report.md` (Bách, Sprint-1 Day-1, `train/audit_branch3_data_validity.py`): 65/70 `boolean_blind` and 67/70 `time_blind` TEST sessions are **byte-identical copies** of TRAIN sessions. Cause: train and test draw from the same 100-user synthetic pool, and the bisection algorithm is deterministic per target — same target ⇒ identical query trace. Thresholds are calibrated on TRAIN and evaluated on TEST, but TEST substantially overlaps TRAIN for two of the three attack classes. **This means §V.D's FPR=0.0/DR=1.0 is optimistic — a sanity check on the mechanism against its own generator, not evidence of generalization.** This is worse than the caveat currently in the `.tex` ("drawn from the same generation process"), which reads as a modeling-family caveat, not an explicit overlap disclosure.
  - Options: (a) re-split by target user (no user shared between TRAIN/TEST) and re-run `calibrate_branch3.py` — cheap, days not weeks; (b) keep the current numbers but rewrite §V.D's "reading narrowly" paragraph to state the overlap explicitly rather than gesture at "same process"; (c) treat Cách A as sanity-check-only and wait for Cách B (independent `sqlmap` traffic, Bách Sprint-1 Day 2-3) as the real generalization evidence. The audit report itself recommends (c) as the resolution path, with (b) as the minimum before submission if (c) doesn't land in time.
  - Not yet reflected in `plan.csv` (Task 76 still shows "Not started" even though the audit is done) — sync that too.
- **Branch 1: cross-split duplicate leakage — CONFIRMED.** `report/plan/plan_branch1_audit.md` / `report/metrics/audit_branch1/audit_report.md` (Bách, 14 Aug): 949 distinct query texts appear in **both** train and test out of 67,796 rows (4,277 total duplicate copies). Audit's own words: F1-macro = 0.982 is "slightly optimistic" as a result. Fix is cheap (dedupe `query_canonical` before splitting, retrain/re-eval) but explicitly **not yet done — deferred to you** ("chờ mentor chốt" in the audit report).
- Both are exactly the "will a reviewer trust this data?" risk the original plan flagged before either audit ran. They're no longer hypothetical. Recommend deciding + fixing (not just re-caveating) before either number is finalized in the `.tex` — a caveat sentence that says "not yet validated" is honest; a caveat sentence next to a number known to be measurably inflated is not.

### 2. Branch 2 numbers in the `.tex` are stale

`rivf2026_paper.tex` still describes Branch 2 as One-Class SVM (AUC=0.90, FPR=0.3%, DR=20.7%, 4 features, 91,935-row benign pool). Actual state on `main` since PR #24 (19 Aug): **LocalOutlierFactor** (`n_neighbors=5`), 12 features, D3/D7 stripped of URL scheme/host/path before featurization, benign+anomalous pools rebuilt to span D1+D3+D7. Current result: **DR @ matched FPR=5% = 80.6%, AUC = 0.929** (`report/metrics/branch2_eval.json`, `models/branch2_v1/metadata.json`). Touches: Abstract, §III.D, §IV.C, §V.B (table `tab:b2` + Fig `fig:b2`), Conclusion. Detail in the outline entries below.

### 3. §III has no MLOps/Continual-Learning design subsection

§V "Continual Learning" reports results (drift monitor, review queue, validation gate) for a mechanism the paper never introduces to the reader in §III (Proposed System). Needs a new §III.G, 3-5 sentences, before the existing decision-engine subsection or right after it — see outline entry below.

### 4. Branch 2's latency claim likely contradicts the algorithm switch

§V.F (Latency Budget) currently says Branch 2 is "four scalar feature computations plus a linear One-Class SVM decision, sub-millisecond." LOF is a k-NN lookup against the full training set, not a fixed linear boundary — `report/plan/data_contract.md` §3.4 records an **offline benchmark of ~15-18 ms/query**, explicitly flagged there as needing re-measurement against the live `/api/v1/detect` endpoint before citing an end-to-end number. The current 1-2 ms budget claim needs to be re-derived, not just left as-is.

---

## Section-by-section outline (mirrors `rivf2026_paper.tex`)

### Abstract
Update once Branch 2 numbers (item 2) and the Branch 3 leakage caveat (item 1) are settled — the abstract currently states Branch 2's AUC=0.90/FPR=0.3% and a Branch-3 sentence that will need the same "preliminary" framing tightened once the leakage finding is folded in. Keep it dense; write last.

### I. Introduction
Contributions bullet list (4 items, `.tex` lines ~74-80) is otherwise fine as a summary; bullet 1 (mentions Branch 2 as "benign-only anomaly detector") doesn't need to change, only its cited numbers elsewhere do.

### II. Related Work
No changes needed.

### III. Proposed System
- **A. System Placement.** Text is fine. Figure is still a placeholder box (Minh, architecture diagram) — remains the one open figure with no numbers depending on it, lowest urgency of the open items.
- **B. Canonicalization.** No changes needed.
- **C. Branch 1 — Supervised Multi-Class.** Text describes the method (TF-IDF + LogReg, 4-architecture comparison) correctly; only the *headline F1* is contingent on the leakage-dedup decision (item 1).
- **D. Branch 2 — Query-Level Anomaly Detection — needs a rewrite.** Replace the "4 lightweight statistical features... Isolation Forest / One-Class SVM" description with the current pipeline: 12 features (original 4 statistical + `quote_imbalance` + 6 "local peak" features — `same_type_run_ratio`, `max_token_length`, `token_count`, `max_special_run`, `max_digit_run`, `paren_imbalance` — added because whole-string ratios get diluted by the long parameter strings D3/D7 produce), LocalOutlierFactor chosen over One-Class SVM / Isolation Forest because the benign pool spans 3 structurally distinct sources (D1/D3/D7) and a single global decision boundary flagged genuinely benign D1/D7 traffic as anomalous just for "not looking like D3" — LOF's local-density notion avoids this. **This is also the natural home for a short "what we tried and rejected" note** (see the dedicated section below) — one sentence, mirroring how §III.E already handles Branch 3's GRU-to-SessionCorrelator story, not a new subsection.
- **E. Branch 3 — Session-Level Correlation.** Mechanism description is accurate and doesn't need to change. The "reading these numbers narrowly" caveat (currently in §V.D, could arguably live here too) needs the leakage finding folded in explicitly (item 1) — don't just soften language, state the overlap.
- **F. Decision Engine and Overkill Policy.** No changes needed.
- **G. NEW — MLOps / Continual-Learning Design.** Add before or after F. 3-5 sentences introducing the three mechanisms §V's "Continual Learning" subsection reports on, since nothing currently does: (1) drift monitoring — PSI over tracked feature/confidence signals against a reference window, alert threshold 0.2; (2) review queue — flagged queries held for confirmation, confirmed labels feed the retrain pool; (3) validation gate — a retrain candidate is only promoted if it matches or beats the champion on FPR/F1 on a fixed validation set, with major-bump (new label) vs. minor-bump (same labels) handled differently. Keep it to design/mechanism only — the evaluation is what §V already reports.

### IV. Dataset and Experimental Setup
- **A. Data Sources — needs each dataset described explicitly**, not folded into one paragraph. One clear line per dataset: what it is, size, content format (raw SQL text vs. full HTTP request), role, license status.
  - **D1 (SQLiV3):** Kaggle SQLi query collection, ~30.9K raw rows, plain SQL/query text (matches the system's Position-B input directly), license provenance unclear (flag in Discussion, already done).
  - **D3 (CSIC 2010):** HTTP traffic corpus, captured as **full HTTP requests** (scheme+host+path+query/body), not raw SQL — required a URL-stripping step (`_strip_url_wrapper`, item 2) to approximate Position-B input; used for benign enrichment and, held out, as a mixed-attack-type anomalous evaluation set (state plainly: not SQLi-only).
  - **D4 (payload-box):** MIT-licensed SQLi payload strings, small (177 payloads), split by DBMS/technique; used to supplement Branch 1's rarer classes (`stacked`, `time_blind`).
  - **D7 (SR-BH 2020):** CC0 honeypot dataset, 527,813 rows, multi-label CAPEC-tagged (not SQLi-specific); re-tagged into SQLi sub-types via the same rule-based tagger as D1/D4 (priority order in §IV.B below); also a full-HTTP-request format like D3, same URL-stripping fix applies.
- **B. Branch 1 Dataset — needs the filtering method described explicitly**, not just the row count.
  - **Filtering:** content-based signature filtering (independent of source labels) removed mislabeled attacks from the `normal` pool over three iterative rounds; rule-based re-tagger priority order for multi-label sources: `stacked > time_blind > error_based > union_based > boolean_blind` (data_contract.md §3). SSRF/OS-command payloads (owasp.org callbacks, `/etc/passwd`, Shellshock — 1,640 rows) are **not** filtered from Branch 1's `normal` pool by design decision (acceptable for a SQLi-vs-not-SQLi classifier); this is a deliberate scope choice worth one sentence, not an oversight.
  - **Known issue pending a decision (item 1):** 949 texts leak across train/test after dedup was skipped; F1=0.982 should be described as pending that fix, or the fix should land before the number is finalized.
  - **Feature engineering:** TF-IDF vectorization (character/word n-grams — pull the exact `ngram_range`/vocab size from `train/train_branch1.py` or `configs/config.yaml` when drafting, don't guess) feeding Logistic Regression. Note the `stacked` class exclusion (0 natural samples, synthetic substitutes trivially separable) as a feature/label-engineering decision, not just a dataset note.
- **C. Branch 2 Dataset — needs the filtering + feature engineering described explicitly.**
  - **Filtering:** benign pool combines D1+D3+D7 after (a) content-signature filtering rejecting *any* attack-like traffic (broader than Branch 1's SQLi-only filter) and (b) URL-stripping D3/D7 rows to isolate query-string/body parameters, dropping rows with nothing left after stripping (bare static-asset requests). Anomalous eval set now spans D1+D3+D7 confirmed-SQLi rows (D7 via its own CAPEC "SQL Injection" column), not D3 alone as before — this closes the earlier "D3 eval mixes non-SQLi attack types" caveat for at least the D1/D7 portion.
  - **Feature engineering:** 12 features total — original 4 (`length`, `special_char_ratio`, `sql_keyword_count`, `entropy`) + `bigram_entropy` (kept in the feature vector but identified as a domain-confound artifact rather than a real signal — worth one sentence as a "what we tried and found didn't hold up" note, see below) + `quote_imbalance` (unmatched quote count) + 6 "local peak" features added because D3/D7's longer parameter strings dilute whole-string ratios: `same_type_run_ratio`, `max_token_length`, `token_count`, `max_special_run`, `max_digit_run`, `paren_imbalance`. Log-transform applied to `length`/`max_token_length`/`max_special_run`/`max_digit_run`; all features scaled before LOF.
  - **Result:** DR@FPR5%=80.6%, AUC=0.929 (up from 26.2%/0.792 pre-fix); per-source DR: D1=78.5%, D3=66.9%, D7=84.0%.
- **D. Branch 3 Dataset.** Mechanism description (real bisection algorithm against a self-hosted DB) stays accurate — but the closing caveat must state the confirmed same-target leakage (item 1), not just "session data is synthetic."
- **E. Evaluation Protocol.** No structural change; add one line noting Branch 2's LOF latency is an *offline* benchmark pending live re-measurement (item 4), consistent with how Branch 3's caveats are handled elsewhere in this section.

### V. Experimental Results
- **A. Branch 1.** Numbers pending the leakage-dedup decision (item 1).
- **B. Branch 2 — needs a full rewrite of the numbers, table, and figure.**
  - New headline: DR@FPR5%=80.6%, AUC=0.929 (LocalOutlierFactor).
  - **This is the right place for a compact "what we tried" comparison table**, mirroring `tab:b1arch`'s pattern exactly: One-Class SVM (baseline, pre-fix) → per-domain ensemble (tried, failed: FPR≈41%) → Isolation Forest, 12-feature (DR=61.4%, AUC=0.837) → LocalOutlierFactor, chosen (DR=80.6%, AUC=0.929). 4-5 rows, same shape as the existing Branch-1 table — this single table *is* the answer to "what did we try and reject," scoped to the one branch that actually needs it (see dedicated section below).
  - Figures already regenerated (19 Aug) but **not yet wired into the `.tex`**: `branch2_score_dist.png`, `branch2_pr_curve.png` exist in `report/metrics/figures/` alongside the currently-used `branch2_threshold_tradeoff.png`. Pick one or two, not all three, per the page-budget note below.
- **C. Zero-Day Study.** No changes — independently confirmed clean by the audit (`audit_branch3_data_validity.py` Mảng 3: report numbers match `summary.json` exactly).
- **D. Branch 3.** Ablation table (`tab:b3`) numbers stay the same (0/70 FPR, DR=1.0 across configs) — the recalibration (`content_threshold` now 0.3383) didn't change the headline. What **must** change is the "reading these numbers narrowly" paragraph: state the confirmed same-target train/test overlap explicitly (item 1), not the current generic "same generation process" framing.
- **E. Continual Learning.** The `% TODO` comment above `tab:cl` (pending Bách's leakage audit) can now be **resolved, not just left pending** — the audit (Mảng 2) found the `stacked`-class golden/stream split has zero template overlap. Update the comment to state the audit passed, or remove it and fold "audited clean, no leakage" into the existing caveat paragraph as a positive statement.
- **F. Latency Budget.** Needs re-derivation once Branch 2's LOF cost is measured against the live endpoint (item 4) — the current "1-2 ms, sub-millisecond Branch 2" framing is very likely wrong now.
- **G. Illustrative Demonstration.** No content change needed; flagged in the page-budget section below as the cheapest cut if the paper is over length.

### VI. Discussion and Limitations
Add: (a) LOF's model-size/latency trade-off (data_contract.md §3.4 has ready-to-use wording: larger artifact than OCSVM/IsolationForest, k-NN lookup per inference instead of a fixed boundary); (b) Branch 3's leakage finding, stated plainly rather than folded into the existing "self-generated sessions" bullet; (c) Branch 1's pending dedup decision, one sentence, if not fixed before submission.

### VII. Conclusion and Future Work
Update Branch 2's cited numbers once §III.D/§V.B are rewritten (item 2). No structural change otherwise.

### References
No changes needed.

---

## "What we tried and rejected" — is it necessary, where does it go, does it blow the page budget?

**Necessary, but selectively — extend a pattern the paper already uses, don't add a new section.** The paper already documents three rejected/superseded approaches, each in the subsection where it's relevant: Branch 1's 4-architecture comparison (`tab:b1arch`), Branch 3's GRU→SessionCorrelator redesign story (§III.E + a paragraph in the Conclusion), and Continual Learning's naive-vs-balanced-vs-starved-rehearsal ablation (`tab:cl`). This is a real strength — it reads as measured rigor, not indecision — and reviewers tend to reward exactly this pattern. The one branch missing it entirely is **Branch 2**, despite its algorithm journey (4-feature OCSVM → bigram_entropy confound discovered → quote_imbalance → per-domain ensemble tried and failed → 12-feature Isolation Forest → LocalOutlierFactor) being the single largest experimentation effort in the project. That gap should close with the same shape already used elsewhere: **one short sentence of narrative in §III.D + a compact comparison table in §V.B** (outlined above) — not a new "Experiments" or "Ablations" section, which would duplicate structure that already exists per-branch and cost page budget without adding a new kind of evidence.

**What doesn't need writing up:** minor sub-experiments that didn't change a shipped decision and aren't cited as evidence for anything (e.g. Branch 3's same-request multi-field-concatenation test, or the 3-source-single-model-vs-ensemble intermediate step) — at most one clause in a Limitations bullet, not prose. The bar: does this rejected approach explain *why* the current design looks the way it does to a skeptical reader? If yes, one sentence + maybe a table row. If it's just "we also tried X," leave it in `project_history.md`/`data_contract.md`, which already exist for exactly this and aren't page-limited.

**Page budget: likely already at or near 6 pages, before any of the above.** No LaTeX engine is available locally to compile an exact count (still true as of this session), but the current draft's body is ~4,760 words plus 5 figures and 7 tables — that combination is consistent with roughly 6 IEEEtran two-column pages on its own. Adding the Branch 2 rewrite (bigger table, more text), the new §III.G, and the fleshed-out §IV.A/B/C will add real length. Recommended order:
1. **Get an actual Overleaf compile now** — everything above is an estimate; don't keep writing blind.
2. If already at/over budget, cut in this order (cheapest evidentiary loss first): §V.G Illustrative Demonstration (one paragraph, weakest evidence) → pick only one of `cl_drift_windows.png`/`cl_control_ablation.png` to keep as a figure, since both illustrate points already stated in prose → only one of the three Branch-2 figures (§V.B) goes in.
3. Check RIVF's CFP for whether over-length pages are allowed for a fee — open since 24 Jul, still unresolved, worth five minutes before cutting content that took real experimentation to produce.

---

## Where things stand — pointers, not duplicated here

- Full historical narrative (all branches, MLOps, by date): [`project_history.md`](project_history.md).
- Live per-person/per-sprint task plan: [`report/plan/plan.csv`](../plan/plan.csv) — use the **`/check-plan`** skill rather than reading it cold.
- Audit reports referenced above: [`report/metrics/audit_branch3/audit_report.md`](../metrics/audit_branch3/audit_report.md), [`report/plan/plan_branch1_audit.md`](../plan/plan_branch1_audit.md).
- Branch 2/3 pipeline detail: [`report/plan/data_contract.md`](../plan/data_contract.md) §3.4 (Branch 2 scope fix + LOF switch), §4.2 (Branch 3 GRU→SessionCorrelator redesign).
