# RIVF 2026 Paper — Outline & Writing Plan

**Target:** RIVF 2026 (IEEE, https://rivf2026.org/) — 2-column IEEEtran `conference` format.
**Template:** [`report/conf/conference_101719.tex`](conference_101719.tex)
**Submission deadline:** 31 Jul 2026.
**Page budget:** IEEE conference papers are typically **6 pages** (verify RIVF CFP for the exact limit + whether over-length pages are allowed). This is *far* shorter than the internal midterm report [`report/midterm/full_outline.md`](../midterm/full_outline.md) — treat that report as the source pool and compress aggressively.

---

## STATUS (updated 2026-07-24)

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

## 0. Framing decision (read first)

The project designs **three branches** (Branch 1 supervised multi-class, Branch 2 anomaly, Branch 3 session-level). As of now:

- **Branch 1 + Branch 2 + the zero-day leave-one-out study have real experimental results.**
- **Branch 3 (session-level sequence model) has NO implementation and NO results yet** — `src/models/` contains only `branch2_anomaly.py`; there is no `branch3_*.py`. `deploy/routers/branch3.py` returns `not_ready`.
- **Central decision engine + Continual Learning + Concept Drift = design only** (`src/decision/`, `src/continual_learning/`, `src/monitoring/` are empty `__init__.py`).

**Two viable paper framings** — pick before writing (see Open Question at bottom):

- **(A) Ship what's proven.** Paper contribution = a two-branch DB-proxy detector *plus a zero-day generalization study* (the leave-one-out result is the novel empirical hook). Branch 3 + integration presented as **proposed architecture / future work**. Lowest risk — fully backed by existing results, submittable even if Branch 3 slips.
- **(B) Full three-branch.** Requires Branch 3 trained with real session-level metrics before ~29 Jul. Higher risk given the 31 Jul deadline and that Branch 3 code does not exist yet.

**Recommendation:** write to framing **(A)** as the safe baseline; if Branch 3 produces real numbers in time, promote it from "proposed" to a results subsection. Structure below is built so Branch 3 can be upgraded in place without restructuring.

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
  - (If framing B) a session-level sequence branch for blind/multi-step SQLi.

### II. Related Work — ✍️ WRITABLE NOW
- Source: [`full_outline.md`](../midterm/full_outline.md) §1.9 + Table 1.1 + §1.10 Research Gap.
- Compress to ~0.75 col. **Needs real citations** — see "Must do" #5. Fold the Ch.1 theory (CNN/RNN/LSTM/GRU/Transformer/IF/OCSVM) into 2–3 sentences here; a conference paper cannot afford the full tutorial that the internal report has.

### III. Proposed System / Methodology — ✍️ WRITABLE NOW (mostly)
- **A. System placement (DB proxy, Position B)** — ✍️ design. One figure: architecture diagram (3 branches → decision engine). *Figure must be produced (Must-do #6).*
- **B. Canonicalization** — ✍️ `src/preprocessing/canonicalize.py` exists + tested; describe the anti-evasion normalization.
- **C. Branch 1 — supervised multi-class** — ✍️ TF-IDF + Logistic Regression, 5 classes (normal + union/error/boolean-blind/time-blind). Method writable now.
- **D. Branch 2 — query-level anomaly** — ✍️ One-Class SVM / Isolation Forest on 4 statistical features (length, special-char ratio, SQL-keyword count, entropy). Writable now.
- **E. Branch 3 — session-level sequence model** — ⛔/✍️ *design writable now* (GRU/Transformer over `[Branch-1 embedding ⊕ Branch-2 score]` per step). Label it "proposed" until Must-do #1 lands.
- **F. Central decision engine + Overkill policy** — ✍️ decision table (Block/Overkill/Allow) writable now from README; note it is a designed policy, not yet an evaluated component.
- **G. Continual learning loop** — ✍️ design only; keep to a short paragraph or move entirely to Future Work to save space.

### IV. Dataset & Experimental Setup — ✅ (B1/B2) / ⛔ (B3)
- **A. Data sources** — ✅ D1 SQLiV3, D3 CSIC 2010, D4 payload-box, D7 SR-BH; published on HF. Source: [`data_contract.md`](../plan/data_contract.md), README data table.
- **B. Branch 1 dataset** — ✅ 68,159 rows, multi-class relabel, `stacked` dropped (100% synthetic). Note in Limitations.
- **C. Branch 2 dataset** — ✅ 91,935 benign train / 25,065 anomalous eval.
- **D. Branch 3 dataset** — ⛔ **NOT COLLECTED.** Session data (Cách A simulated / Cách B sqlmap+DVWA) does not exist yet. Blocks any B3 result.
- **E. Evaluation protocol** — ✅ metrics defined (F1-macro, precision/recall, FPR, AUC, detection rate, latency). Hardware: RTX 3050 6GB. Seed=42, deterministic.

### V. Experimental Results — ✅ (core) / ⛔ (B3 + integration)
- **A. Branch 1 results** — ✅ **F1-macro = 0.982**; per-class table (n=13,560); 4-architecture comparison; ROC-per-class figure.
  Artifacts: [`branch1_eval.json`](../metrics/branch1_eval.json), [`branch1_architecture_comparison.json`](../metrics/branch1_architecture_comparison.json), [`figures/branch1_roc_per_class.png`](../metrics/figures/branch1_roc_per_class.png).
- **B. Branch 2 results** — ✅ One-Class SVM: **AUC = 0.90, FPR = 0.3%, detection rate = 20.7%** (vs Isolation Forest AUC 0.67); 21-point threshold sweep; PR curve, score distribution, threshold trade-off figures.
  Artifacts: [`branch2_eval.json`](../metrics/branch2_eval.json), [`branch2_threshold_sweep.csv`](../metrics/branch2_threshold_sweep.csv), `figures/branch2_*.png`.
- **C. Zero-day leave-one-out study** — ✅ **THE NOVEL HOOK.** Per excluded class, Branch 1 miss rate vs Branch 2 detection rate vs combined coverage. Key numbers from [`summary.json`](../metrics/zeroday_experiment/summary.json): error_based → B1 miss 0%, but for boolean_blind → B1 miss **90.2%** while combined coverage reaches **94%**; error_based B2 DR **89.7%**. This is the "why two branches beat one" evidence.
  Artifacts: [`zeroday_experiment/`](../metrics/zeroday_experiment/), notebook `train/notebooks/zeroday_experiment_report.ipynb`.
- **D. Branch 3 results** — ⛔ **MUST BE PRODUCED** (Must-do #1–#3) or the section becomes "proposed / future work."
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

## What MUST be done before the paper is complete

Ordered by priority for the 31 Jul deadline. Items #5–#7 are required regardless of framing; #1–#4 are only required for framing (B).

1. **⛔ Implement Branch 3 (session-level model).** No code exists (`src/models/branch3_*.py` missing). Needs: model class (GRU or small Transformer over per-step `[B1 embedding ⊕ B2 score]`), train script, eval script. *Largest single risk item.*
2. **⛔ Build session-level dataset.** At minimum **Cách A** (simulated sessions scripted from D1). Cách B (sqlmap→DVWA capture) is a bonus/comparison, likely infeasible before deadline. Without this, #1 cannot be evaluated.
3. **⛔ Produce real Branch 3 metrics.** Session-level detection rate on blind/query-splitting sessions + FPR on benign sessions; ideally show B3 catches sessions that per-query B1/B2 miss. This is what makes framing (B) worthwhile.
4. **⛔ (Optional) End-to-end / decision-engine measurement.** Integrated verdict on a mixed stream + **inference latency** per query (the paper's methodology promises latency; currently unmeasured end-to-end). Even a small latency table strengthens the paper.
5. **⛔ Real reference list.** Replace all template `\bibitem` placeholders. Verify each citation (per repo TODO note, some report claims need Web-Search verification before submission).
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
- Methodology §§ A–D, F (system placement, canonicalization, Branch 1, Branch 2, decision policy).
- Results §§ A–C (Branch 1, Branch 2, zero-day study) with **real numbers already in `report/metrics/`**.
- Dataset §§ A–C, E.

That is roughly **70–80% of a 6-page paper** already writable with real content. The remaining 20–30% (Branch 3 results, integration/latency, final figures, references) is the "must do" list above.

---

## Open question for the team

**Framing (A) vs (B)?** If the team commits to (B), Branch 3 code + Cách A dataset + eval must land by ~29 Jul to leave time for writing and internal review. If that timeline is unrealistic, lock framing (A) now and present Branch 3 as the proposed extension / future work — the paper is fully submittable either way on the strength of the Branch 1/2 + zero-day results.
