# PROJECT PROPOSAL: AI-BASED SQL INJECTION DETECTION SYSTEM
### (AI-Based SQL Injection Detection System) — Revision V9 (24 Jul: 3 clear milestones — see Section 0)
### Role split: Duc = polish Branch 1 + integration, Bach = Branch 2 (trained, being verified), Minh = Streamlit, Diep = Support/Report

## 0. Timeline (updated 24 Jul — IMPORTANT, read before the other sections)

**⚠️ 3rd revision (24 Jul) — 3 clear milestones:**

| Milestone | Date | Content | Scope |
|---|---|---|---|
| **SUBMISSION DEADLINE** | **Sat 25 Jul, 23:59** | **Branch 1 + Branch 2**: code, metrics, model, report (Version 1) must be fully complete | Unchanged from the previous plan — Branch 3/the full system stays out of scope |
| **Conference report metrics** | **Sun 26 Jul** | Polish metrics/figures/tables specifically for the conference report (RIVF, Version 2) — one buffer day after the main deadline to refine the figures | No new code, just reviewing/re-presenting existing figures |
| **Full source code** | **31 Dec 2026** | Branch 3 + integrated system (API/`deploy/`, central processing engine, Continual Learning...) — see Section 13 (Future Work) | **Far out, not urgent** — ~5 months available, no need for a day-by-day plan right now |
| Submit RIVF 2026 paper | 31 Jul 23:59 | 6-page IEEE paper via EDAS | Separate track, unchanged |
| RIVF results notification | 15 Oct | — | — |
| RIVF camera-ready | 11 Nov | — | Should have at least part of Branch 3 done before this milestone |
| RIVF 2026 conference | 18-20 Dec | VinUniversity, Hanoi | The full source code deadline (31 Dec) lands after the conference — acceptable; the conference presents Version 2's results (2 branches + Branch 3 design) |

**Why Branch 3 was cut:** confirmed in practice (21 Jul) — Branch 3 currently has **nothing built** (no Docker lab, no session data, no model), with only 5 days left. Trying to keep Branch 3 in scope would leave all 3 branches half-finished. Decision: **nail 2 branches solidly** rather than half-finish all 3. Branch 3 remains part of the project's design/theoretical contribution (Sections 1, 3, 4.3) but is clearly marked as **not experimentally implemented** in the 25 Jul submission — see Section 13 (Future Work).

**Good news on Branch 2:** a real-world check (21 Jul) showed Branch 2 is **not a bottleneck** — the entire pipeline (build data from HF + train Isolation Forest/OCSVM) finishes in **~75 seconds**. The earlier "missing model" issue was just because the `.joblib` file isn't committed (intentional, to avoid large files in git), not a training-time shortfall.

**2nd revision (same day, 21 Jul) — drop the system entirely, write 2 report versions:** after confirming Branch 1+2 were solid, decided **not to build the API/central processing engine/Streamlit** for the 25 Jul submission — replaced by `train/notebooks/demo_detect.ipynb` (written + tested, loads the real models, takes a query, returns a verdict; 19/20 correct on a random sample sanity-check). Also writing **2 parallel report versions**:
- **[`report/plan/ban1_scope_hien_tai.md`](ban1_scope_hien_tai.md)** — exactly what was actually built (2 branches + notebook), due 25 Jul. *(24 Jul: moved into `report/plan/` during the repo restructure)*
- **`report/midterm/ban2_hoan_chinh.md`** — the full vision (3 branches + integrated system), Branch 3/API clearly marked as design/Future Work; used as a source for the conference report (Sun 26 Jul), the real conference paper lives in `report/conf/`. *(24 Jul: moved into `report/final/`; renamed to `report/midterm/` since this is the mid-term report — Branch 3 + the full system have a separate hard deadline of 31 Dec 2026, so it isn't "final".)* *(Note added during the English-translation pass: this file no longer exists on disk after a later restructure — reference kept as a filename pointer, not a working link.)*

---

## 1. Problem Statement and Project Objectives

**Context:** SQL Injection (SQLi) is one of the most dangerous and common web security vulnerabilities. Traditional solutions (hard-coded-rule WAFs) struggle with novel attack variants (zero-day) and are prone to False Positives.

**Objective:** Build an intelligent gatekeeper system at the Database layer. Full design comprises **3 parallel branches** (supervised, per-query anomaly detection, and **session-level/sequence** over query chains) combined with a **Continual Learning** mechanism and an **Overkill (hold & verify)** policy — but **the 25 Jul submission only experimentally implements the first 2 branches** (see Section 0 for why).

**Contributions — clearly distinguishing what's done (25 Jul) vs. design/Future Work:**
1. **[IMPLEMENTED]** Branch 1 (supervised multi-class, F1-macro=0.982) + Branch 2 (anomaly detection, OCSVM AUC=0.90) combined on the same canonicalization pipeline, demonstrated via a demo notebook (`train/notebooks/demo_detect.ipynb`) — the API/integrated system is Future Work (see Section 13).
2. **[DESIGN — Future Work]** Branch 3 — a hierarchical model over sessions/query chains, addressing a gap that all 11 surveyed Related Work sources overlook: **temporal query splitting** attacks (Boolean/Time-based Blind SQLi) where each individual query looks valid and the pattern only shows up across a sequence. The architecture is fully designed (Section 4.3) but **has no data/experiments** as of the 25 Jul submission.
3. **[DESIGN — Future Work]** A Continual Learning loop from Admin feedback (the Overkill policy) — basic 2-branch decision logic exists, but the full retrain loop isn't implemented.

---

## 2. Related Work
*(See the separate "Related Work Survey" file — already has full citations [1]-[11]. Key point: no source models the relationship between multiple queries within the same session for the SQLi problem — this is the gap Branch 3 fills.)*

---

## 3. System Architecture and Data Flow (Real-time Pipeline) — updated for 3 branches

> ⚠️ **The diagram below is the full 3-branch design.** The 25 Jul submission only experimentally implements **Branch 1 + Branch 2** and the corresponding reduced decision path (the first 2 lines of "Central Processing Engine"); **Branch 3 and the 3rd decision line ("Branch 1+2 clean + Branch 3...") are Future Work**, with no experiments yet.

```
[User Request] ──> [Web Backend] ──> [Database Proxy / AI Agent] ──> [Database]
                                            │
                                (Canonicalization → Interception & Analysis)
                                            │
                    ┌───────────────┬───────────────┬────────────────┐
                    ▼               ▼               ▼
              [Branch 1: SQLi] [Branch 2: Anomaly] [Branch 3: Session]
              (per-query,       (per-query,        (last K queries in the
               supervised)       unsupervised)      session/IP/time window)
                    │               │               │
                    └───────────────┴───────────────┘
                                     ▼
                          [Central Processing Engine]
              - Branch 1 = Attack                → Block immediately, log it
              - Branch 1 clean + Branch 2 anomalous
                → HOLD (Overkill), await Admin confirmation
              - Branch 1+2 clean + Branch 3 detects an anomalous sequence pattern
                → HOLD the whole session (extended Overkill), may block the entire session
              - Everything clean                  → Allow
                                     │
                          [Fail-safe if the AI service times out/errors]
                                     │
                          [Continual Learning: labels from the Admin queue
                           → new data store → periodic retrain]
```

**Session Store (new technical component for Branch 3):** requires a cache (in-memory or Redis) storing the last K SQL statements/embeddings keyed by session/IP, with a TTL to auto-expire old sessions. This is a technical departure from V2 — the previous system was fully stateless per-request, and now needs short-lived state.

---

## 4. Data Scoping and Technical Approach

### 4.1 Model architecture choice for Branch 1 (per-query)
Unchanged from V2: compares DistilBERT vs. TF-IDF/char n-gram + Gradient Boosting vs. a lightweight CNN with a custom SQL tokenizer (referencing a lightweight architecture from the Related Work survey — ~69K parameters, tens of times faster than DistilBERT). Chosen based on measured F1/latency, not defaulting to a transformer.

**Experimental result (16 Jul) — locked in: TF-IDF + Logistic Regression.** Compared 4 candidates on a 13,632-row test set, **6 classes including `stacked`** (`train/compare_branch1_architectures.py`, full results in `report/metrics/branch1_architecture_comparison.json` + `train/notebooks/model_comparison_branch1.ipynb`):

| Model | F1-macro | p50 latency | Size | Train time |
|---|---|---|---|---|
| **TF-IDF + LogReg** (chosen) | 0.985 | **0.5 ms** | 3.9 MB | 10 s |
| TF-IDF + LightGBM | **0.993** | 60 ms | 6.0 MB | 264 s |
| DistilBERT | 0.992 | 2.8 ms (GPU) | 256 MB | 1443 s |
| CNN + SQL-tokenizer | 0.987 | **0.3 ms** | **116 KB** (28K params) | 10 s |

Reason for choosing LogReg: the F1 gap between the 4 models is negligible (0.985–0.993), while LightGBM is ~120x slower (60 ms — too high for a real-time proxy), and DistilBERT costs 256 MB + needs a GPU + 24 minutes to train without beating F1. CNN is a good fallback candidate (fastest/smallest) if stronger feature learning is needed later.

**⚠️ Finding after training (16 Jul) — `stacked` dropped from the dataset:** all 4 models hit F1 ~0.99 and the `stacked` class (363 synthetic samples) hit **100% recall on all 4** → a sign the data is **too easy to distinguish** (repeated template structure), NOT a genuine quality signal. Decision: **exclude `stacked` from training** (`branch1_supervised.balance.exclude_labels: [5]` in `config.yaml`), keep the generation code (`synthetic_stacked.py`) for reuse once real data exists from the Docker lab/sqlmap (Day 5-6). Dataset now **5 classes, 67,796 rows**.

**Correct F1-macro after dropping `stacked`: 0.9822** (`models/branch1_v1/`, architecture unchanged — TF-IDF+LogReg). Note: the first retrain incorrectly reported F1=0.8185 due to a `classification_report` bug (hardcoded all 6 labels even though `stacked` was no longer in the data → sklearn scored the missing label 0, skewing the macro-average) — fixed in both `train_branch1.py` and `compare_branch1_architectures.py` (details: `data_contract.md` Section 3.3). The confusion matrix shows the only notable confusion is `normal ↔ boolean_blind` (matches the ~13% label noise measured in the `boolean_blind` bucket) — this F1 figure still shouldn't be read as "near-perfect", the real test is the adversarial set (Day 7).

### 4.2 Branch 2: Per-query anomaly detection (unchanged from V2)

### 4.3 Branch 3 (NEW): Session-level / Sequence Model

**Hierarchical architecture:**
```
Query 1 ─┐
Query 2 ─┼─> [Layer 1: lightweight per-query encoder] ─> embedding q1, q2, q3...
Query 3 ─┘   (reuses the encoder already chosen for Branch 1 — not retrained)
                                    │
                                    ▼
                     [Layer 2: lightweight Sequence Model]
                     (trained on the embedding sequence per session)
                                    │
                                    ▼
                     Session-level anomaly score
```

**Layer-2 model choice — needs comparative experimentation (see the 2-week plan):**
| Option | Pros | Cons |
|---|---|---|
| 1-layer GRU | Lightweight, naturally handles variable-length sequences | Sequential processing, hard to parallelize |
| Temporal 1D-CNN | Very fast, parallelizes well | Fixed context window, weaker on long sequences |
| Small Transformer encoder (2 layers, self-attention) | Captures long-range relationships between queries in the sequence | Heavier than the two options above |

### 4.4 Data for Branch 3 — collected using real attack tooling (more credible than a simulation script)
- **Vulnerable Docker lab:** stand up DVWA/WebGoat in a local container, used internally purely for training-data collection.
- **Malicious session (real, not simulated):** run `sqlmap --technique=B` (boolean-blind) and `--technique=T` (time-blind) against the lab, capturing all traffic via a man-in-the-middle proxy (mitmproxy/Burp Suite) placed between sqlmap and the lab app → full request/response logs, real format, with timestamps.
- **Ground-truth sanity check:** only keep sessions where sqlmap **reports successful data extraction** — avoid labeling a failed attack session as positive.
- **Supplemental malicious sessions (from WAF-A-MoLE):** when running WAF-A-MoLE to generate the adversarial test set for Section 7 (Branch 1/2), log the full sequence of consecutive mutation attempts — reused, no extra collection effort.
- **Benign sessions:** grouped by existing cookies in CSIC 2010 (D3), or a simple crawler browsing DVWA normally — more realistic than randomly concatenating disconnected queries.
- **Session boundary:** explicitly defined as session ID (or IP) + a 30-minute idle threshold — needs to be stated clearly in the report, since this is a common point of pushback.

**2-tier labeling schema (Hierarchical Labeling) — a new element to cover in the Methodology:**
Since no existing SQLi dataset has session-level labels, the project defines its own 2-tier schema, matching the hierarchical architecture:
- Query tier (per-query, same as D1): 0 = Normal, 1 = SQLi.
- Session tier (new): 0 = Benign, 1 = Blind Boolean-based, 2 = Blind Time-based, 3 = Query-splitting/multi-step.

### 4.5 Branch 1 data source update — added D7, addressed class imbalance (15 Jul)

Real-world verification on D1 (SQLiV3) showed the dataset is too sparse for multi-class classification: **0 `stacked` samples**, and the `boolean_blind` class is just a "catch-all" for payloads not matching the other 4 rules (including unrelated DDL statements). Additional sources needed:

- **D7 — SR-BH 2020** ([Harvard Dataverse](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/OGOIXX)): a real honeypot, 12 days of collection (2020), multi-label CAPEC. 527,813 rows, 250,285 rows with the original `SQL Injection` label.
- After re-tagging ourselves (not trusting the original labels — found label noise, including static-asset rows mistagged as SQLi): added `union_based` +83,189, `error_based` +7,423, `boolean_blind` +126,926, `time_blind` +32,747.
- **`stacked` = 0 samples across D1+D4+D7** (tried both strict and loose regex) → no public source contains this technique. Fix: **synthetically generated 363 unique samples** (templated from 11 prefixes × 11 destructive/privilege-escalation statements × 3 comment suffixes — a real measured count, not the initial ~1-2K estimate), tagged with source `synthetic_stacked` and clearly noted in Limitations (Section 7) — this is self-generated data, not real collection. Its much smaller scale than the other classes (~15K) is a limitation worth stating clearly.
- **Balancing strategy:** undersample the large classes (`union_based`, `boolean_blind`, `time_blind`) down to a similar order of magnitude (~15,000/class), keep all of `error_based` (~7,800, not enough to undersample). Use **F1-macro** as the primary metric for Branch 1 (Accuracy doesn't reflect performance correctly given the original imbalance).
- Full detailed figures (per-source table, specific label-noise examples): see `data_contract.md`.

**Update 15 Jul — finished building `data/processed/branch1_train.csv`:** cross-checking D7's original label flags (a multi-label dataset) looked good in aggregate (99.1% of `SQL Injection=1` rows carry no other flag; 0% of `Normal=1` rows conflict with another flag) — **but manually reading the actual content of `Normal=1` samples found a more serious problem**: some rows contain `sleep(15)` (real time-blind SQLi) and a Shellshock payload (`() {{ :;}}; /bin/sleep 15`) that SR-BH itself mistagged `Normal=1`, despite not conflicting with any of its own flags. Cross-checking flags alone isn't enough — only reading content catches this.
- Fix: added a content-based filter (`matches_any_attack_signature`, independent of the source label) applied to every row destined for `normal` before accepting it.
- **3 consecutive sanity-check rounds each found more variants slipping through:** round 1 removed 1,561 rows; manual review in round 2 found `&cat /etc/passwd&` (using `&` instead of `;`) and SSI injection slipping through → broadened the regex, **2,731 rows removed in total** (~9.8%); round 3 found a **deliberately evasive fuzzer variant** (`cat$jj $jj/etc$jj/passwd`, inserting junk tokens between keywords) still slipping through. **Decided to stop patching the regex** — this is an unbounded-variant evasion problem, and the right place to handle it is canonicalization + an adversarial set (Day 7), not endless static dataset-filter patching. Logged as an accepted risk for the MVP.
- **Label noise isn't limited to the `normal` side:** manual review of 30 `boolean_blind` samples (the catch-all bucket) found **~13% (4/30) clearly wrong** — SSRF, CRLF/header injection, one fully-benign row that SR-BH itself tagged `SQL Injection=1`. This is a **measured** figure, not an estimate, and needs to go into the report's Limitations (Section 7).
- Remaining limitation: the filter only targets SQLi + OS command injection/SSI, **doesn't cover all 12 of SR-BH's attack categories** (XSS, SSRF can still leak into `normal`) — acceptable for Branch 1 (SQLi-only concern), but **Branch 2 (anomaly, needs a much cleaner benign pool) will need to do this more rigorously** when its turn comes (Day 5-6).
- Final result: **68,159 rows** (train 54,527 / test 13,632, stratified, seed=42), 15,000/class for the 3 large classes, all of `error_based` (7,796) and `stacked` (363) kept. A full ~100-sample-per-class manual sanity-check still hasn't been done (only a small 15-20/class sample reviewed so far) — should be added before finalizing figures for the report.
- Added XSS to the shared filter (`<script>`, `javascript:`, `onerror=/onload=`) after finding more instances in the sample — rebuilding Branch 1 removed **2,892** noisy normal rows in total (up from 2,731).
- The dataset is now public on Hugging Face: [Jason-42195/VNU-SQLi-Detection](https://huggingface.co/datasets/Jason-42195/VNU-SQLi-Detection). Licenses verified: D4 (payload-box) = MIT, D7 (SR-BH 2020) = CC0 1.0 (confirmed directly from Harvard Dataverse); **D1 (SQLiV3) remains unclear** — the original Kaggle page has no assigned license, and the GitHub mirror self-applies MIT to their own repo but it's unclear they have rights over the underlying data itself. The combined dataset (including D1) should be treated as **provenance-unclear**, not clean MIT/CC0, until further verified.

**Update 15 Jul (continued) — started on Branch 2 data:** refactored code — split the D1/D3/D4/D7 loading functions out into a shared module `src/preprocessing/data_sources.py` (avoids the two branches having two different definitions of "clean normal"). Branch 2 uses **statistical/structural features** (length, special-character ratio, SQL keyword count, entropy — `src/preprocessing/statistical_features.py`), not TF-IDF, since it needs to generalize to syntax it has never seen (zero-day). No count cap (unlike Branch 1) — takes all clean normal data from D1+D3+D7.
- Result: **91,935 benign rows** (train 73,548/test 18,387) after filtering (~7.4% of candidates removed) + dedup (removed ~113K more duplicates — many repeated static assets in D3/D7); kept **25,065 anomalous rows (D3)** separately for later FPR/detection-rate evaluation (not used for training).
- ⚠️ Important finding for evaluation time: the D3-anomalous set contains **many attack types** (not just SQLi — buffer overflow, XSS, path traversal...), so its average `sql_keyword_count` is **lower** than even the normal set (0.13 vs 0.35). Isolating the SQLi subset within D3-anomalous is needed for an accurate read on zero-day SQLi detection, or this benchmark should be treated as "general anomaly detection".
- **Branch 3: not started yet** — depends on real traffic from the Docker lab + sqlmap (Day 8-9); decided not to build fake data before real traffic exists.

---

## 5. Fusion and Decision Mechanism — updated for 3 branches

| Branch 1 | Branch 2 | Branch 3 (session) | Action |
|---|---|---|---|
| Attack (1) | — | — | **Block immediately**, log it |
| Valid (0) | Anomalous | — | **HOLD** the query, await Admin confirmation (Overkill) |
| Valid (0) | Normal | Anomalous sequence | **HOLD the whole session**, flag as suspicious, await Admin confirmation |
| Valid (0) | Normal | Normal | **Allow** |

---

## 6. Model Evaluation
Same as V2 (P/R/F1, FPR, latency, adversarial testing), plus: **a dedicated Branch 3 evaluation** on the collected session set (Section 4.4) per the 2-tier label schema — specifically measuring the ability to correctly detect each type (Boolean-based/Time-based/Query-splitting) that Branch 1+2 miss (this is the metric that "proves the value" of Branch 3, so it should be done carefully, and it also demonstrates the value of the self-collected dataset — a contribution that can be presented separately from the modeling work).

---

## 7. Risks, Limitations, and Extended Threat Model

### 7.1 Query Splitting — 2 forms to distinguish

**Form 1 — Horizontal split (split across parameters, same request):** mostly already handled by where the system is deployed (Position B — the Proxy sees the SQL statement AFTER the backend has already built it), since Branch 1/2 always see the complete statement after parameter concatenation. Only dangerous for architectures that filter at the input/WAF layer before the query is built — not this project's architecture.

**Form 2 — Temporal split (split over time, across multiple requests):** this is the form genuinely dangerous to the old 2-branch architecture, since each individual query is syntactically valid. Examples: Blind Boolean-based (binary-searching one character at a time across hundreds of consecutive requests, with systematically-varying literal values), Time-based Blind (inferring via response delay instead of content). The signal only shows up when viewed as a sequence — **this is why Branch 3 is needed.**

### 7.2 Extended threat model — other cases worth noting for scope

| Attack type | Description | In scope? |
|---|---|---|
| Second-order SQLi | Payload stored safely in request A, triggered in request B in a different session, possibly days apart | **Out of scope** (even for Branch 3) — noted in Limitations |
| Out-of-band (OOB) SQLi | Data exfiltrated via a separate DNS/HTTP channel, not through the response | **Out of scope** — needs separate network/DNS monitoring |
| HTTP Parameter Pollution | Backend/WAF read different values for a duplicate parameter name | Risk reduced by the Proxy's Position B — worth stating as a rationale for this placement |
| Stacked queries (`; DROP...`) | A second statement injected after `;` in one request | Already within Branch 1's capability — just needs canonicalization to not accidentally strip `;` |

### 7.3 Data crafted to evade the 2 branches (kept from V2)
4 categories: syntactically-equivalent transformations, encoding, statistical mimicry, payload splitting. See WAF-A-MoLE [7] for a detailed technical spec and automated generation tooling.

### 7.4 Other risks
Single point of failure at the Proxy, latency overhead, and **a new risk from Branch 3:** need to ensure the Session Store doesn't fill up/overflow memory under a large number of concurrent sessions — needs a clear TTL/eviction policy.

---

## 8. Continual Learning (unchanged from V2, extended to accept labels from Branch 3 too)
When Admin confirms a HOLD (from Branch 2 or Branch 3), label it and store it in the new-data pool → periodic retrain (rehearsal) → validation gate before promotion.

## 9. Concept Drift — Google's lightweight MLOps approach (unchanged from V2)

## 10. Deployment Plan
Same as V2 (FastAPI + CTranslate2 if using a transformer). Addition: need to choose a Session Store technology (in-memory dict/LRU for the MVP, or Redis if sharing state across multiple Proxy instances is needed).

---

## 11. DETAILED PLAN (13 Jul – 25 Jul) — 4 people, running in parallel

**Staffing — Day 1-8 (13-20 Jul, already happened):**
- **Duc** — Data + Branch 1 training (done: `models/branch1_v1/`, F1-macro=0.9822, 5 classes) → built the API scaffold (`deploy/main.py`, `deploy/routers/`).
- **Bach** — Branch 2 (Anomaly), independent (Isolation Forest + One-Class SVM, tuning, audit).
- **Minh** — Streamlit (scaffold + demo/admin pages).
- **Diep** — Support/report (RIVF paper paused for now — see Section 0).

**Day 9-13 assignments (21-25 Jul) — ONLY 5 DAYS LEFT, minimum scope (2nd revision, system dropped entirely):**

| Role | Main task |
|---|---|
| **Duc** | **Deeper metrics** (added a full ROC curve for Branch 2) + wrote & tested **`train/notebooks/demo_detect.ipynb`** (loads the real models, takes a query, returns a verdict — done, 19/20 correct on the sample) + helped Diep with figures/data for the 2 report versions |
| **Bach** | Rigorously verify Branch 2's results (OCSVM: FPR=0.3%, detection rate=20.7%, AUC=0.90) — is it convincing enough for the report; provide detailed figures/explanations to Diep |
| **Minh** | System/Streamlit **postponed** — switched to helping with charts/visualizations (ROC curve, confusion matrix, architecture diagram) for the report |
| **Diep** | Writing **2 parallel report versions**: [`ban1_scope_hien_tai.md`](ban1_scope_hien_tai.md) (exactly the 2 completed branches) + `ban2_hoan_chinh.md` (the full 3-branch vision, Branch 3 marked as Future Work) |

**Day 14 (Sun 26 Jul) — added (24 Jul):** the whole team spends 1 buffer day polishing **metrics specifically for the conference report** (Version 2) — reviewing figures, adding any missing charts/tables, no new code.

**The detailed day-by-day/per-person table lives in `ke_hoach_2_tuan.csv`** (56 rows, Day 1-14, ending 26 Jul) — see Section 14 for how it's updated automatically via Claude Code.

**Summary of the main flow (full detail in the CSV):**
- *Day 1-8 (done):* Duc handled D1 → trained Branch 1 → built the API. Bach handled D3 → trained/evaluated Branch 2. Minh built the Streamlit scaffold. Diep wrote the report's opening sections.
- *Day 9 (21 Jul, that day):* Verified Branch 2 (fixed the missing model + added a ROC curve); wrote + tested the demo notebook; rewrote the outline for both report versions (approved).
- *Day 10-11 (22-23 Jul):* Helped supply figures/charts for the report; Diep wrote Version 1 (Method/Results) then started Version 2.
- *Day 12 (24 Jul):* Buffer day for fixes, finishing Version 2 (Threat model/Discussion/Conclusion), reviewing both versions.
- *Day 13 (25 Jul, SATURDAY — SUBMISSION DEADLINE):* Submitted the notebook + both report versions.

**On the RIVF 2026 paper (31 Jul):** paused for now (Section 0) — will be re-planned in detail **after the 25 Jul deadline**, once it's clear how much time/manpower is left and whether Branch 3 can get any further work done before 31 Jul.

---

## 12. Risks (updated 21 Jul per the new deadline)

**Biggest risk eliminated:** previously worried Bach would be blocked by Branch 3 (Docker lab/sqlmap taking many days) — now that **Branch 3 has been fully cut from scope**, that critical path no longer exists.

**Risk further reduced (2nd revision):** dropped the API/central processing engine/Streamlit from the 25 Jul scope entirely (replaced by a simple demo notebook, already written + tested) — no more risk of complex system integration in a short timeframe. The main remaining risk is now just: **writing 2 quality report versions in 4 days**.

**Branch 2 is no longer a risk** — verified in practice (21 Jul): the full build+train pipeline runs in ~75 seconds, and a full ROC curve has been added. What's left is just checking whether the figures are convincing enough for the report.

**Suggestion if still short on time by Day 12 (24 Jul):** cut in this priority order — (1) Version 2 (the full one) can be thinner in the Future Work section if pressed for time; (2) don't cut: Version 1 (current scope) must be complete, the demo notebook must run correctly, submitted on time on 25 Jul.

---

## 13. Future Work — what was cut from the 25 Jul submission (final deadline: 31 Dec 2026)

**Context:** to make the 25 Jul deadline with only 5 days, the project **narrowed its experimental scope to 2 branches** (Branch 1 + Branch 2). The items below remain part of the project's design/contribution (see Sections 1, 3, 4.3) but **have no experiments** in this submission. **Clear milestone (24 Jul): everything on this list must be done before 31 Dec 2026** — not urgent (≈5 months), but a hard deadline, not "whenever there's time". At least part of Branch 3 should be finished before the RIVF camera-ready (11 Nov) if a full presentation at the conference (18-20 Dec) is wanted — the rest can be finished after the conference, as long as it's before 31 Dec.

1. **Integrated system (API + central processing engine + Streamlit demo) — newly cut (21 Jul, 2nd revision).** Previously planned for 25 Jul, now replaced by `train/notebooks/demo_detect.ipynb` (loads a model, takes a query, returns a verdict — simple combined logic, not a real central processing engine). Needed: package the FastAPI app (`deploy/main.py`, `deploy/routers/` — scaffold already exists, needs finishing), a full central processing engine (a real Overkill queue), a Streamlit demo connected to the real API.
2. **Branch 3 (Session-level / Sequence Model) — entirely.** This is the project's main theoretical contribution (addressing the temporal-query-splitting gap that Related Work overlooks) but **nothing has been implemented** as of 21 Jul: no Docker lab, no session data, no model. Needed: stand up the lab (DVWA/WebGoat) → collect real traffic via sqlmap → 2-tier labeling → compare Layer-2 architectures (lightweight GRU/CNN/Transformer) → train + evaluate.
3. **Full Continual Learning** — the pipeline from Overkill-queue labeling → rehearsal-based retrain → validation gate. The 25 Jul version only has basic decision logic (BLOCK/OVERKILL/ALLOW), no continual-learning loop.
4. **Production Concept Drift monitoring** — periodic PSI/KL-divergence logging, FPR/Recall over time, model versioning + rollback.
5. **Production-grade Session Store** (TTL/eviction, Redis) — needed once Branch 3 exists.
6. **Latency/throughput benchmarking under real load** — the 25 Jul version only tests functional correctness, hasn't measured throughput under heavy load.
7. **Multi-round adversarial hardening** (repeated WAF-A-MoLE generate-test-retrain cycles for Branch 1).
8. **Large-scale manual label sanity-checking** (~100+/class, cross-validated by multiple people) — currently only a small sample reviewed (15-30/class).
9. **Official dataset publication** — D1 (SQLiV3)'s license is unclear (see `data_contract.md`), needs verification/replacement before citing it widely.
10. **Comparison against more SOTA baselines** — for an extended (journal) version if aiming for a stronger publication after the conference.

---

## 14. Progress-tracking file and how it's updated automatically

The detailed plan (13 days × 4 people, 13 Jul-25 Jul, with deliverables) lives in `ke_hoach_2_tuan.csv` — each row is one task with columns: `Day, Date, Weekday, Owner, Role, Task, Dependency, Deliverable, Status`. Use the command in `Prompt_Claude_Code_Cap_Nhat_Ke_Hoach.md` to have Claude Code ask for your role, determine the current date, check which deliverables already exist in the repo, and automatically update the `Status` column + sync a summary into this proposal file.

---

## 15. Progress update log (automatic — Claude Code appends here)

*(This section is left empty and gets a new line automatically each time the plan-update command runs — see `Prompt_Claude_Code_Cap_Nhat_Ke_Hoach.md`. Each run appends a line like: `[YYYY-MM-DD, Role: X] Today's work: ... | Done: ... | Overdue: ...`)*

[2026-07-14, Role: Duc] Today's work: Fully cleaned D1; wrote the canonicalization pipeline; locked in the Branch 1 architecture (blocked by Day 1 - Duc not yet finished) | Done: Nothing | Overdue: Day 1 - Duc (lock in the data contract; download raw D1; quick-test Branch 1 architectures) — no deliverable exists yet (`data_contract.md`, `data/raw/d1_sqliv3_raw.csv`, `notebooks/model_comparison_branch1.ipynb`)

[2026-07-16, Role: Duc] Today's work (Day 4): Evaluate Branch 1 (P/R/F1) + start setting up the Docker lab | Done: (catching up on previous days) compared 4 Branch 1 architectures → locked in TF-IDF+LogReg (F1-macro 0.985, p50 0.5ms), trained `models/branch1_v1/`, `reports/branch1_eval.json`, `notebooks/model_comparison_branch1.ipynb`; off-plan: also finished building `data/processed/branch2_normal.csv` (91,935 benign rows) for Branch 2 | Overdue/remaining: `docker/dvwa/docker-compose.yml` (Docker lab setup for Branch 3 — not done); full 100-sample-per-class manual sanity-check; note the suspiciously high F1 (data too easy, no adversarial testing yet)

[2026-07-16, Role: Duc] Notified Bach: Bach's Day 1-2 tasks (`data/raw/d3_csic2010_raw.csv`, `data/processed/branch2_normal.csv`) are **already done** — Duc did them together while building Branch 1+2 data (see Section 3.2 of `data_contract.md`). Bach does NOT need to redo them, can start directly from Day 3. Note: the 4 statistical features (length, special_char_ratio, sql_keyword_count, entropy — `src/preprocessing/statistical_features.py`) are already columns in `branch2_normal.csv`, ready to use for Day 3 (feature extraction) instead of building TF-IDF/embeddings from scratch, or still try a different approach if a comparison is wanted. `branch2_anomalous_eval.csv` (25,065 D3-anomalous rows) is already prepared for FPR/detection-rate evaluation on Day 5. All data is already public on HF: https://huggingface.co/datasets/Jason-42195/VNU-SQLi-Detection

[2026-07-17, Role: Duc] Reassignment starting Day 5: swapped tracks between Duc and Bach — Duc switches to all of MLOps (central processing engine, Session Store, API, benchmarking, Continual Learning, Concept Drift), Bach takes on all of Branch 3 (Docker lab, sqlmap, session data, training) in addition to the already-finished Branch 1+2. Minh (Streamlit) and Diep (Support) unchanged. Updated `ke_hoach_2_tuan.csv` (Day 5-13) and Sections 11-12 of this document. Reason: Bach finished Branch 2 early and has training experience, Duc is already actively working on the API (branch `feature/api-backend-mlops`).

[2026-07-17, Role: Duc] SCOPE REDUCTION (user request): confirmed RIVF 2026 (checked the real site) — submission deadline 31 Jul 2026, 6-page IEEE paper, EDAS, conference 18-20 Dec at VinUniversity. 3 new milestones: (1) 28 Jul = finish training all 3 branches + demo (Continual Learning/Concept Drift/production Session Store/load benchmarking NOT required — pushed to Future Work), (2) 31 Jul = submit the RIVF paper, (3) before 18 Dec (targeting camera-ready 11 Nov) = finish the full system. Added Section 0 (timeline), rewrote Sections 11-12, added Section 13 (Future Work, 9 items). Updated `ke_hoach_2_tuan.csv` from 56 to 76 rows (Day 1-19): trimmed Day 5-14, added Day 15-16 (finalize MVP), Day 17-19 (writing + submission sprint — Diep starts writing sections from Day 5, not all at the end).

[2026-07-21, Role: Duc] URGENT DEADLINE CHANGE (user request): the real deadline is this Saturday (25 Jul), not 28 Jul. Aggressively narrowed scope: only Branch 1 (polishing) + Branch 2 (already checked — real-world verification shows it's NOT a bottleneck, the full build+train pipeline runs in ~75 seconds; fixed the missing model.joblib, retrained: OCSVM FPR=0.3%, detection rate=20.7%, AUC=0.90). Branch 3 CUT ENTIRELY from the 25 Jul scope (confirmed no Docker lab/session data/model exists yet) — moved fully into Future Work, kept in the project's design/theoretical contribution. Detailed planning for the RIVF 2026 paper (31 Jul) paused for now, will resume after 25 Jul. Updated: header (V8), Section 0 (new timeline), Section 1 (contributions — distinguishing done/Future Work), Section 3 (diagram note), Sections 11-13 (plan/risks/Future Work rewritten), Section 14 (CSV row count). `ke_hoach_2_tuan.csv`: 76 → 52 rows (Day 1-13, old Day 14-19 removed).

[2026-07-21, Role: Duc] PLAN CHANGE #2 (same day, after the outline was approved): dropped the entire system (API/central processing engine/Streamlit) from the 25 Jul scope, not just Branch 3. Replaced with: (1) deeper metrics — added a full ROC curve for Branch 2 (`train/train_branch2.py`), (2) `notebooks/demo_detect.ipynb` — written AND SUCCESSFULLY TESTED (loads the real Branch 1+2 models, takes a query, returns a verdict; caught one real bug — AnomalyDetector needs a numpy array, not a plain list; sanity-check 19/20 correct on a random sample, the one mismatch is a known limitation), (3) 2 parallel report versions — `report/ban1_scope_hien_tai.md` (skeleton created, 2-branch scope) and `report/ban2_hoan_chinh.md` (skeleton created, full 3-branch + system vision, clearly marking which parts are Future Work). Updated Sections 0, 11, 12, 13 (added a new Future Work item, "Integrated system"). Rewrote `ke_hoach_2_tuan.csv` Day 9-13 for this scope.

[2026-07-24, Role: Duc] PLAN CHANGE #3 — 3 clear milestones: (1) Sat 25 Jul 23:59 = Branch 1+2 code/metrics/model/report (Version 1) must be done — unchanged from the previous plan; (2) Sun 26 Jul = polish metrics specifically for the conference report (Version 2), 1 buffer day with no new code; (3) 31 Dec 2026 = hard deadline for the full source code (Branch 3 + integrated system, all of Section 13's Future Work) — far out, not urgent. Finding: the repo underwent a major restructure (unclear by whom) — `api/`→`deploy/`, `scripts/`+`notebooks/`→`train/`, `De_xuat...md`/`data_contract.md`/`ke_hoach_2_tuan.csv`/`ban1_scope_hien_tai.md`→`report/plan/`, `ban2_hoan_chinh.md`→`report/final/`, `reports/`→`report/metrics/`. Found `report/final/Dàn ý.md` already in place (722 lines, English, Chapter 1 Intro→Related Work→Research Gap) and `report/final/Template(1).docx` — looks like preparation for writing the official report against a specific template. Updated Section 0 (3 milestones), Section 11 (added Day 14), Section 13 (31 Dec deadline), fixed file paths for the new structure. `ke_hoach_2_tuan.csv`: 52→56 rows, added Day 14 (26 Jul, conference metrics).
