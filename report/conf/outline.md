# RIVF 2026 Paper — Outline & Writing Plan

**Target:** RIVF 2026 (IEEE, https://rivf2026.org/) — 2-column IEEEtran `conference` format.
**Template:** [`report/conf/conference_101719.tex`](conference_101719.tex)
**Submission deadline:** 30 Aug 2026 (moved from the original 31 Jul).
**Page budget:** IEEE conference papers are typically **6 pages** (verify RIVF CFP for the exact limit + whether over-length pages are allowed). This is *far* shorter than the internal midterm report [`report/midterm/full_outline.md`](../midterm/full_outline.md) — treat that report as the source pool and compress aggressively.

---

## STATUS (updated 2026-08-07 — supersedes the 24 Jul status below, kept for the historical record)

**Branch 3 now has a real implementation and real, held-out results — the picture in the 24 Jul status and the "Framing decision" section immediately below (§0) is out of date.** Summary of what changed (full account: `report/plan/data_contract.md` §4.2):

- A GRU sequence-model design for Branch 3 was built and initially reported F1-macro = 1.0. A follow-up diagnostic session found that result was very likely inflated by two real bugs in its own training/eval pipeline, and — independent of those bugs — that its core premise (feeding Branch 1's classifier *probability* output per session step) didn't hold up: it measurably collapsed the content signal that distinguishes consecutive session steps, and the live decision engine blocks most real sessions per-query before a session-level model ever sees enough steps to matter.
- Branch 3 was redesigned as **`SessionCorrelator`** (`src/models/branch3_session.py`) — not a trained model. It re-uses Branch 1's classifier (content check, on concatenated session text) and Branch 2's anomaly detector (behavior check, aggregating its per-query scores) exactly as already trained, correlating the two signals per session with four calibrated thresholds.
- **Real, held-out results** (disjoint 280-session TEST split): FPR (benign) = 0.0; detection rate 1.0 across `boolean_blind`/`time_blind`/`query_splitting` for all three ablation configurations (content-only/behavior-only/combined). A zero-day ablation shows the content check's real limitation (0.0 detection rate against a classifier genuinely blind to the class) — reported honestly, not hidden.
- **Follow-up (8 Aug):** `content_threshold` (the content check's cutoff) is now calibrated separately per-session from TRAIN data, rather than reusing Branch 1's single-query 0.5 threshold as a placeholder — closing the one case (`boolean_blind` sessions containing only their weak length-bisection steps, which concatenate to 0.45-0.46) where the content check alone used to fall just short of 0.5. This raised content-only `query_splitting` detection from 0.971 to 1.0 at no FPR cost; the behavior check already covered this case independently, so this is redundancy, not a new capability. Full account: `report/plan/data_contract.md` §4.2.
- **Wired into the live API** — `POST /api/v1/branch3/session` returns a real verdict, not the earlier `not_ready` stub.
- **This changes the framing recommendation:** framing **(B)** (full three-branch, §0 below) is now realistic and arguably the stronger paper — real, honestly-ablated Branch 3 results plus the redesign-diagnosis story itself (§0/§III.E) is a legitimate methodological contribution, not just "session model added." This is a call for whoever is driving the paper (SA/PM) to confirm, not something this update decides unilaterally.

---

## STATUS (updated 2026-07-24 — historical, see above for current status)

**Framing LOCKED = (A)** ship-what's-proven. Full draft written: [`report/conf/rivf2026_paper.tex`](rivf2026_paper.tex) (IEEEtran, compiles on Overleaf; `pdflatex` not installed locally). Full-scope companion document (all 3 branches, tagged done/planned, RIVF milestones, team roles): [`report/conf/research_proposal.md`](research_proposal.md) — not a submission requirement, just the single source of truth for the whole vision. Short Vietnamese version (~3 pages): [`report/conf/research_proposal_vn.md`](research_proposal_vn.md).

- **#4 end-to-end latency → estimated, not blocked.** Presented as a latency *budget* (~1–2 ms/query) derived from measured per-branch costs (B1 = 0.5 ms; B2 = 4 features + linear SVM). Labeled as an estimate in the paper.
- **#5 references → DONE.** 11 refs reused from the mid-term report ([`full_outline.md`](../midterm/full_outline.md) References). Cross-check against the team's original survey before camera-ready.
- **#6 figures → DONE.** B1/B2 figures wired via `\graphicspath{{../metrics/figures/}}` (`branch1_roc_per_class.png`, `branch2_threshold_tradeoff.png`). Note: `report/branch-1-2-metrics-20260724T142758Z-1-001/` is a byte-identical duplicate of `report/metrics/figures/` (verified by checksum) — looks like a leftover Drive-download extraction, not a separate source; safe to delete once confirmed unneeded, left untouched for now. **Still TODO: architecture diagram** (paper uses a framed placeholder box so it compiles now — see Day 2 below).
- **#7 authors → DONE.** Real names in place: Bach Luong-Chi (RMIT University Vietnam), Minh-Duc Do-Xuan, Diep Dinh-Ngoc, Minh Nguyen-Quang (International School, VNU), advisors Linh Dinh-Van and Thai Kim-Dinh (International School, VNU) listed as co-authors — 6 authors total, within IEEEtran's default 6-author layout. Per-author `[TODO: dept/major]`, `[TODO: email or ORCID]` placeholders remain (deliberately not fabricated — see Day 2 below); Bach's campus city (Hanoi vs. Ho Chi Minh City) also marked `[TODO: city]`.

**Remaining hard blockers before submission (31 Jul):** (a) architecture diagram; (b) fill per-author dept/email/city placeholders; (c) confirm RIVF page limit; (d) proof-read + ensure no IEEE template guidance text remains. **Not a blocker but should land if time allows:** (e) rerun the zero-day experiment with the now-fixed `combined_coverage` formula (Bach, Sat 25 Jul — see Day-by-day plan) so §V-C can optionally cite a correct combined-coverage number; the paper is fully submittable without it since only the miss-rate/detection-rate columns are currently cited.

> **Zero-day `combined_coverage` bug — ROOT CAUSE FOUND & FIXED (2026-07-24, this session).** The old formula in `train/run_zeroday_experiment.py` (line ~203) computed `(preds_branch1 == 0) | (flags_branch2 == 1)` — i.e. it OR'd "**Branch 1 MISSED it**" with "Branch 2 caught it", instead of "**Branch 1 CAUGHT it**" (`preds_branch1 != 0`) OR "Branch 2 caught it". That inversion is exactly why the numbers didn't add up (e.g. boolean_blind: B1 catches 9.8% + B2 DR 5.4% "cannot union to 94%" — the old formula wasn't measuring real combined coverage at all). **Code is fixed**; `summary.json` still holds the OLD (wrong) numbers until the experiment is rerun. **This is the "something in `src`/`train` that must be done" before the paper's zero-day section (§V-C) can cite `combined_coverage` — see Day-by-day plan below, assigned to Bach.** The paper currently reports only the two well-defined columns (B1 miss rate, B2 detection rate), so it is *not* blocked on this rerun — but the corrected combined-coverage number would strengthen §V-C if ready in time.
>
> **Side effect that also matters:** rerunning this script is also how the 5 zero-day model weights (`models/branch1_no_*`, `models/branch2_zeroday`) get regenerated — those `.joblib` files are currently missing locally (only `metadata.json` survived; the main `branch1_v1`/`branch2_v1` weights are fine and already on HF). One rerun fixes both problems at once.

---

## Day-by-day plan to the 31 Jul deadline

**⚠️ Scheduling note:** the RIVF deadline (31 Jul) overlaps the *separate* course deliverables — **midterm report due Sat 25 Jul**, **presentation Tue 28 Jul** (slides + code + model demo). Days 25–28 below are shared with those deadlines.

**⚠️ Role split (added 2026-07-24, run in parallel, not sequentially):**
- **Diep + Minh → midterm report** (urgent, due Sat 25 Jul), **then also slides** for the Tue 28 Jul presentation, working at the same time as Bach's track below — not blocked on it.
- **Bach → rerun `train/run_zeroday_experiment.py`** (bug just fixed, see STATUS above): regenerates the 5 missing zero-day model weights AND produces the corrected `combined_coverage` numbers. Then push all 7 models (2 production + 5 zero-day variants) to HF (`Jason-42195/VNU-SQLi-Detection-Models`) so the presentation demo doesn't depend on local-only files. Fast (~a few minutes total per earlier timing: branch1 ~15s/variant, branch2 ~75s).

Under framing (A), **no further model training or new code is required for the paper's core claims** — Branch 1/2 results and the zero-day study (miss-rate/detection-rate columns) are already final regardless of the rerun above. The rerun only upgrades `combined_coverage` from "known-buggy, unused" to "correct, citable" — a strengthening, not a blocker. The remaining paper work is otherwise writing/design/admin. If Branch 3 unexpectedly produces real results before 29 Jul, it can be added as a Results subsection (see Section 0 framing note) — but do not plan on it; it is not on this critical path.

| Day | Date | Paper (writing/design) | Code / other |
|---|---|---|---|
| 1 | Fri 24 Jul | Author block locked (done today); outline + full draft exist; **`combined_coverage` bug found + fixed in code** (this session) | — |
| 2 | Sat 25 Jul | Diep/Minh: **midterm report** (due tonight — top priority). Architecture diagram + author dept/email/ORCID collection continue in spare cycles if any | **Bach: rerun zero-day experiment** (fixed script) → corrected `combined_coverage` + regenerate 5 missing model weights → push all 7 models to HF |
| 3 | Sun 26 Jul | Compile on Overleaf, fix any LaTeX errors, check actual page count against RIVF's limit (confirm exact number from CFP — template default 6 pages). Decide whether to cite the corrected `combined_coverage` in §V-C now that it's available | Verify rerun results look sane (spot-check against the old miss-rate/DR columns, which don't change) |
| 4 | Mon 27 Jul | Diep/Minh: continue midterm report polish + **start slides** in parallel (architecture, B1/B2 results, zero-day findings, live demo pulling models from HF) | — |
| 5 | Tue 28 Jul | **Presentation** (slides + code + model demo) — *competing priority with paper track* | — |
| 6 | Wed 29 Jul | Incorporate advisor feedback (Linh Dinh-Van, Thai Kim-Dinh); final citation/format check against IEEE style; remove all remaining template guidance text | If Branch 3 has real numbers by now, decide whether to upgrade Section V-D — otherwise leave as-is |
| 7 | Thu 30 Jul | Buffer day: proofread once more, verify all `[TODO:]` placeholders are filled, test-compile the exact submission package (PDF + any required source files) | — |
| 8 | Fri 31 Jul | **Submit** (check RIVF's submission-portal timezone / AoE cutoff ahead of time, don't assume) | — |

---

## 0. Framing decision (read first) — ⚠️ historical, see STATUS above

**This section reflects the 24 Jul state and is kept for the record. As of 7 Aug, Branch 3 has a real implementation and real held-out results (STATUS above) — the premise "Branch 3 has NO implementation" below no longer holds.**

The project designs **three branches** (Branch 1 supervised multi-class, Branch 2 anomaly, Branch 3 session-level). As of 24 Jul:

- **Branch 1 + Branch 2 + the zero-day leave-one-out study have real experimental results.**
- **Branch 3 (session-level sequence model) has NO implementation and NO results yet** — `src/models/` contains only `branch2_anomaly.py`; there is no `branch3_*.py`. `deploy/routers/branch3.py` returns `not_ready`.
- **Central decision engine + Continual Learning + Concept Drift = design only** (`src/decision/`, `src/continual_learning/`, `src/monitoring/` are empty `__init__.py`).

**Two viable paper framings** — pick before writing (see Open Question at bottom):

- **(A) Ship what's proven.** Paper contribution = a two-branch DB-proxy detector *plus a zero-day generalization study* (the leave-one-out result is the novel empirical hook). Branch 3 + integration presented as **proposed architecture / future work**. Lowest risk — fully backed by existing results, submittable even if Branch 3 slips.
- **(B) Full three-branch.** Requires Branch 3 trained with real session-level metrics before ~29 Jul. Higher risk given the 31 Jul deadline and that Branch 3 code does not exist yet.

**24 Jul recommendation (superseded):** write to framing **(A)** as the safe baseline; if Branch 3 produces real numbers in time, promote it from "proposed" to a results subsection. Structure below is built so Branch 3 can be upgraded in place without restructuring.

**Current recommendation (7 Aug, numbers updated 8 Aug):** Branch 3 has real, held-out, honestly-ablated results (FPR=0.0, DR 1.0 across all three ablation configs on a disjoint TEST split) plus a legitimate methodological narrative (an earlier GRU design's suspicious F1=1.0 was diagnosed and replaced — `report/plan/data_contract.md` §4.2). **Framing (B) is now realistic** — upgrade §III.E, §IV.D, §V.D per the inline notes added below. Final call belongs to whoever is driving the paper.

---

## Legend

- ✅ **DONE** — real results/artifacts exist; can write now with actual numbers.
- ✍️ **WRITABLE NOW** — design/theory/method; no experiment required, can draft immediately.
- ⛔ **BLOCKED** — needs work (code and/or experiments) before it can be written truthfully.

---

## Section-by-section outline (IEEE structure)

### Abstract + Keywords — ✍️ WRITABLE NOW (finalize last)
- 150–250 words. Problem (SQLi at DB proxy, blind/zero-day gap), approach (multi-branch AI detector), headline results (Branch 1 F1-macro 0.982; Branch 2 zero-day coverage). Keywords: SQL injection, anomaly detection, intrusion detection, session-level analysis, machine learning security.
- *Write after Results are locked so the numbers match.*

### I. Introduction — ✍️ WRITABLE NOW
- Source: [`full_outline.md`](../midterm/full_outline.md) Introduction/Background + Research Objectives + Scope. Compress to ~0.75 col.
- Must state the **gap**: query-level detectors miss blind/query-splitting SQLi; rule-based WAFs miss zero-days and inflate FPR.
- End with an explicit **contributions bullet list** (3–4 items). Only claim what results back:
  - A multi-branch SQLi detector positioned at the DB proxy (post-build, pre-DB).
  - A **zero-day leave-one-out evaluation** quantifying how query-level anomaly detection recovers attacks unseen by the supervised branch.
  - (Framing B) a session-level detection mechanism (Session Correlator) for blind/multi-step SQLi, with real held-out results and an honest account of an earlier, more complex design that didn't hold up to ablation.

### II. Related Work — ✍️ WRITABLE NOW
- Source: [`full_outline.md`](../midterm/full_outline.md) §1.9 + Table 1.1 + §1.10 Research Gap.
- Compress to ~0.75 col. **Needs real citations** — see "Must do" #5. Fold the Ch.1 theory (CNN/RNN/LSTM/GRU/Transformer/IF/OCSVM) into 2–3 sentences here; a conference paper cannot afford the full tutorial that the internal report has.

### III. Proposed System / Methodology — ✍️ WRITABLE NOW (mostly)
- **A. System placement (DB proxy, Position B)** — ✍️ design. One figure: architecture diagram (3 branches → decision engine). *Figure must be produced (Must-do #6).*
- **B. Canonicalization** — ✍️ `src/preprocessing/canonicalize.py` exists + tested; describe the anti-evasion normalization.
- **C. Branch 1 — supervised multi-class** — ✍️ TF-IDF + Logistic Regression, 5 classes (normal + union/error/boolean-blind/time-blind). Method writable now.
- **D. Branch 2 — query-level anomaly** — ✍️ One-Class SVM / Isolation Forest on 4 statistical features (length, special-char ratio, SQL-keyword count, entropy). Writable now.
- **E. Branch 3 / Session Correlator** — ✅ **writable now with real content.** Not a trained model: a content check (concatenate session queries, re-score with Branch 1's existing classifier — no retraining) OR'd with a behavior check (aggregate Branch 2's existing per-query scores). Worth including the redesign story itself as a methodological point: an earlier GRU design over `[Branch-1 probability ⊕ Branch-2 score]` per step reported a suspicious F1=1.0, was diagnosed via a concrete information-bottleneck measurement (TF-IDF cosine similarity 0.961 between two session steps vs. near-identical post-classifier probabilities) plus two real evaluation-pipeline bugs, and was replaced. Full account: `report/plan/data_contract.md` §4.2. This subsection is the strongest candidate to also carry a "why simpler beat more complex here" discussion point for §VI.
- **F. Central decision engine + Overkill policy** — ✍️ decision table (Block/Overkill/Allow) writable now from README; note it is a designed policy, not yet an evaluated component.
- **G. Continual learning loop** — ✍️ design only; keep to a short paragraph or move entirely to Future Work to save space.

### IV. Dataset & Experimental Setup — ✅ (B1/B2) / ⛔ (B3)
- **A. Data sources** — ✅ D1 SQLiV3, D3 CSIC 2010, D4 payload-box, D7 SR-BH; published on HF. Source: [`data_contract.md`](../plan/data_contract.md), README data table.
- **B. Branch 1 dataset** — ✅ 68,159 rows, multi-class relabel, `stacked` dropped (100% synthetic). Note in Limitations.
- **C. Branch 2 dataset** — ✅ 91,935 benign train / 25,065 anomalous eval.
- **D. Branch 3 / Session Correlator dataset** — ✅ **Cách A collected and used.** 1,400 sessions (1,050 from a real bisection algorithm against a self-hosted demo DB, 350 heuristic query-splitting fragmentation), 1,120 train / 280 test, session-level split (no leakage). Cách B (real `sqlmap` + Dockerized DVWA/WebGoat) still not started — state as the generalization caveat (§VI), not a blocker (§V.D already has real numbers on Cách A).
- **E. Evaluation protocol** — ✅ metrics defined (F1-macro, precision/recall, FPR, AUC, detection rate, latency). Hardware: RTX 3050 6GB. Seed=42, deterministic.

### V. Experimental Results — ✅ (core) / ⛔ (B3 + integration)
- **A. Branch 1 results** — ✅ **F1-macro = 0.982**; per-class table (n=13,560); 4-architecture comparison; ROC-per-class figure.
  Artifacts: [`branch1_eval.json`](../metrics/branch1_eval.json), [`branch1_architecture_comparison.json`](../metrics/branch1_architecture_comparison.json), [`figures/branch1_roc_per_class.png`](../metrics/figures/branch1_roc_per_class.png).
- **B. Branch 2 results** — ✅ One-Class SVM: **AUC = 0.90, FPR = 0.3%, detection rate = 20.7%** (vs Isolation Forest AUC 0.67); 21-point threshold sweep; PR curve, score distribution, threshold trade-off figures.
  Artifacts: [`branch2_eval.json`](../metrics/branch2_eval.json), [`branch2_threshold_sweep.csv`](../metrics/branch2_threshold_sweep.csv), `figures/branch2_*.png`.
- **C. Zero-day leave-one-out study** — ✅ **THE NOVEL HOOK.** Per excluded class, Branch 1 miss rate vs Branch 2 detection rate vs combined coverage. Key numbers from [`summary.json`](../metrics/zeroday_experiment/summary.json): error_based → B1 miss 0%, but for boolean_blind → B1 miss **90.2%** while combined coverage reaches **94%**; error_based B2 DR **89.7%**. This is the "why two branches beat one" evidence.
  Artifacts: [`zeroday_experiment/`](../metrics/zeroday_experiment/), notebook `train/notebooks/zeroday_experiment_report.ipynb`.
- **D. Branch 3 / Session Correlator results** — ✅ **real, held-out numbers exist.** On the disjoint 280-session TEST split, calibrated on TRAIN only: FPR (benign) = 0.0; detection rate `boolean_blind`=1.0, `time_blind`=1.0, `query_splitting`=1.0, for ALL THREE configurations (content-only/behavior-only/combined) — `content_threshold` is now calibrated per-session from TRAIN data rather than reusing Branch 1's single-query 0.5, closing the one prior content-only gap (`query_splitting` was 0.971 pre-calibration; see `report/plan/data_contract.md` §4.2's 8-Aug follow-up). Report all three configurations regardless — the ablation is the point, not just the headline number (`report/metrics/branch3_eval.json`). Pair with the zero-day ablation (`branch3_eval_hard.json`): content-check detection rate drops to 0.0 against a classifier genuinely blind to `boolean_blind` — a real, stated limitation, include it rather than omit it.
- **E. End-to-end / decision-engine results** — ⛔ no integrated evaluation exists; either produce a small demo/latency measurement (Must-do #4) or scope out.
- **F. Illustrative demonstration** — ✍️/✅ can show a worked example (payload → per-branch scores → verdict) using the live API `POST /api/v1/detect` and `train/notebooks/demo_detect.ipynb`.

### VI. Discussion & Limitations — ✍️ WRITABLE NOW
- Source: [`full_outline.md`](../midterm/full_outline.md) Ch.5. Honest, high-value section for reviewers:
  - Label noise in D1; dataset licensing; `stacked` class synthetic → dropped.
  - Threat-model boundaries (OOB/second-order/XSS/CSRF out of scope).
  - **Adversarial robustness gap** — WAF-A-MoLE adversarial eval not run (state plainly).
  - **Session data is largely synthetic / not yet collected** — state that Branch 3 evaluation is preliminary or proposed.

### VII. Conclusion & Future Work — ✍️ WRITABLE NOW
- Summary of contributions (mirror Intro bullets). Future work: Branch 3 real evaluation, Cách A↔B session-data comparison, continual-learning loop, concept-drift monitoring, adversarial hardening.

### References — ⛔ needs real bibliography
- Template ships placeholder `\bibitem`s. Must replace with real, verified citations (Must-do #5).

---

## What MUST be done before the paper is complete — ⚠️ items #1–#3 DONE as of 7 Aug, kept for the historical record

Ordered by priority for the original 31 Jul deadline (now 30 Aug — see STATUS at top). Items #5–#7 are required regardless of framing.

1. **✅ DONE — Implement Branch 3 (`SessionCorrelator`, not a GRU).** `src/models/branch3_session.py`, calibration script `train/calibrate_branch3.py`, zero-day ablation `train/eval_branch3_hard.py`. See STATUS at top / `report/plan/data_contract.md` §4.2 for why the original GRU plan changed.
2. **✅ DONE — Session-level dataset.** Cách A (1,400 sessions, real bisection algorithm against a self-hosted demo DB + heuristic query-splitting). Cách B (sqlmap→DVWA capture) still not attempted — real remaining gap, not a blocker for framing (B).
3. **✅ DONE — Real Branch 3 metrics.** FPR=0.0, detection rate 1.0 on a disjoint TEST split, with the content-only/behavior-only/combined ablation plus a zero-day limitation ablation (`report/metrics/branch3_eval.json`, `branch3_eval_hard.json`).
4. **⛔ (Optional) End-to-end / decision-engine measurement.** Integrated verdict on a mixed stream + **inference latency** per query (the paper's methodology promises latency; currently unmeasured end-to-end). Even a small latency table strengthens the paper.
5. **⛔ Real reference list.** Replace all template `\bibitem` placeholders. Verify each citation (per repo TODO note, some report claims need Web-Search verification before submission). Consider adding 2-3 new citations surfaced while diagnosing Branch 3 (fragmented/split SQLi technique; behavioral session-trace detection for slow/low-and-slow attacks) if §III.E or §VI cites them.
6. **⛔ Figures for the paper.** (a) System architecture diagram (does not exist as a paper-ready figure). (b) Re-export existing PNGs at IEEE column width / readable font sizes — current figures were made for the internal report, check legibility at 3.5 in width.
7. **⛔ Author metadata.** Fill IEEEtran author blocks (names, affiliation = VNU, emails/ORCID); write title + abstract; **remove all red template guidance text** (the template warns papers may be rejected if it remains).

### Nice-to-have (skip if time-constrained)
- Adversarial robustness eval (WAF-A-MoLE) — currently a stated *gap*; running it would close a Limitation but is not required.
- Cách B sqlmap session capture + A↔B comparison.
- Continual-learning demo (≥1 retrain cycle with drift).

---

## What can be written RIGHT NOW (no blockers)

Draft these immediately — they are backed by existing results or are pure design/method:

- Abstract (draft; finalize numbers last), Introduction, Related Work, Discussion & Limitations, Conclusion.
- Methodology §§ A–F (system placement, canonicalization, Branch 1, Branch 2, Session Correlator, decision policy) — all real now, including E.
- Results §§ A–D (Branch 1, Branch 2, zero-day study, **Branch 3 / Session Correlator**) with **real numbers already in `report/metrics/`**.
- Dataset §§ A–E — all real now, including D.

That leaves mainly integration/latency measurement, final figures, and references as the remaining "must do" items above — framing (B) (full three-branch) is realistic for the 30 Aug deadline.

---

## Open question for the team — ⚠️ largely resolved as of 7 Aug, see STATUS at top

**Framing (A) vs (B)?** (24 Jul framing, kept for the record.) If the team commits to (B), Branch 3 code + Cách A dataset + eval must land in time for writing and internal review. **As of 7 Aug this has landed** — real, held-out, honestly-ablated Branch 3 results exist. Framing (B) is now the recommended target; confirm with whoever is driving the paper (SA/PM) before finalizing §I's contributions list.
