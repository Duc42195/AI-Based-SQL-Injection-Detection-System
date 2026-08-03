# Research Proposal: A Multi-Branch AI System for SQL Injection Detection at the Database Proxy

**Prepared for:** RIVF 2026 (Research, Innovation and Vision for the Future), IEEE, VinUniversity, Hanoi.
**Status of this document:** internal, full-scope reference — **not** a required RIVF submission artifact. RIVF's only submission requirement is the 6-page IEEE paper via EDAS (confirmed from [rivf2026.org/call-for-papers.html](https://rivf2026.org/call-for-papers.html)); this proposal exists so the team and advisors have one clean, English, formally-structured description of the *entire* project scope — including the parts the paper cannot claim as proven results yet — in one place, superseding the informal running changelog in [`report/plan/De_xuat_SQLi_Detection_AI.md`](../plan/De_xuat_SQLi_Detection_AI.md).

**Relationship to the conference paper:** [`report/conf/rivf2026_paper.tex`](rivf2026_paper.tex) reports only what is experimentally proven — Branch 1, Branch 2, and the zero-day leave-one-out study (**framing (A)**, locked with the team) — and presents Branch 3 and system integration as future work. This proposal describes the **whole intended system**, tags every component as done/in-progress/planned, and gives the roadmap by which the rest gets built. Read the paper for "what we can defend to reviewers today"; read this document for "what the project is".

---

## 1. Motivation and Problem Statement

Web applications are a primary attack surface because their back-end databases hold the data attackers want. SQL Injection (SQLi) — unsanitized user input concatenated into a SQL statement — remains one of the oldest and most damaging vulnerabilities in this surface, capable of disclosing, altering, or destroying data and of escalating privileges.

Rule-based Web Application Firewalls (WAFs), the dominant deployed defense, rely on predefined signatures. They are fast and interpretable against known attacks, but two structural weaknesses persist:

1. **Zero-day and obfuscated payloads** bypass static rule sets, which require continual manual updates.
2. **Query-level analysis is fundamentally blind to multi-step attacks.** Boolean-blind SQLi, time-blind SQLi, and query-splitting attacks distribute their malicious signal across many individually-innocuous queries in a single session; no single query, read in isolation, reveals the attack.

Machine learning offers a path past the first weakness (learning patterns from data rather than hand-written rules) but, as deployed in most published work, not the second — because it is still applied one query at a time.

## 2. Research Objectives

1. Detect known SQLi attack categories with high accuracy and low false-positive rate, at query-level, using supervised learning.
2. Detect unknown/zero-day attack shapes via anomaly detection trained exclusively on benign traffic — independent of any attack taxonomy.
3. Detect session-level, multi-step attacks (blind SQLi, query-splitting) that are invisible to any single-query analysis, via a sequence model over the session.
4. Combine the three signals into one decision policy that fails safely (hold-and-verify rather than silently allow) on ambiguous cases.
5. Close the loop: let administrator-confirmed decisions feed continual retraining, and monitor the deployed models for concept drift over time.
6. Quantify, empirically, where query-level detection's blind spots actually are — not just build the session-level branch on faith, but measure the gap it is meant to close.

## 3. Scope

**In scope:** Union-based, Error-based, Boolean-blind, Time-blind, and Stacked-query SQL Injection at query level; and, by design, temporal query-splitting across a session (blind SQLi spread over many requests).

**Out of scope**, independent of how much of the design is eventually implemented:
- Second-order SQLi (payload stored in one request, triggered in a later, unrelated request — potentially days apart, likely outside any session window).
- Out-of-band SQLi (data exfiltrated via a side channel — DNS/HTTP — the proxy never observes).
- Non-SQL web attacks (XSS, CSRF) and network-layer intrusion detection.
- HTTP Parameter Pollution is mitigated as a side effect of the system's placement (Section 5.1) but not addressed by design.

## 4. Related Work (summary)

Traditional defenses — input validation, parameterized queries, rule-based WAFs (ModSecurity, OWASP CRS) — are covered in the paper's Related Work section along with the ML/DL literature (TF-IDF/SVM/RF/XGBoost classifiers, CNN/RNN/LSTM/GRU/Transformer sequence models, DistilBERT, Isolation Forest, One-Class SVM, and adversarial-evasion tooling such as WAF-A-MoLE). Full citations live in the paper's bibliography and are reused here rather than duplicated: [`rivf2026_paper.tex`](rivf2026_paper.tex), §II.

**The gap this project targets:** across the surveyed literature, detection is almost universally applied per-query. No surveyed source models the relationship *between* multiple queries within the same session for the SQLi problem specifically — which is exactly the failure mode that lets blind SQLi and query-splitting through. This is the gap Branch 3 is designed to fill, and Section 8 below reports a leave-one-out experiment that quantifies how large that gap actually is using only the two branches implemented so far.

## 5. Proposed System

### 5.1 System Placement: The Database Proxy

The detector sits at "Position B": it inspects the SQL statement *after* the application has finished building it, but *before* it reaches the database server. This has two benefits: it sees a canonical, final view of what will actually execute (removing ambiguity from application-layer string-building), and it mitigates HTTP Parameter Pollution as a side effect of not needing to interpret raw HTTP parameters itself.

### 5.2 Architecture Overview

```
[User Request] → [Web Backend] → [Database Proxy / AI Agent] → [Database]
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
                      [Central Decision Engine]
          - Branch 1 = attack class          → BLOCK immediately, log
          - Branch 1 clean + Branch 2 anomalous
            → OVERKILL: hold, await Admin confirmation, deny on timeout
          - Branch 1+2 clean + Branch 3 flags an anomalous session pattern
            → HOLD the whole session (extended Overkill)
          - Everything clean                  → ALLOW
                                 │
                      [Fail-safe if the AI service errors/times out]
                                 │
                      [Continual Learning: Admin-confirmed labels
                       → new-data store → periodic, gated retrain]
```

### 5.3 Canonicalization

Before feature extraction, each statement is normalized to reduce syntactic evasion: common encodings (URL, hex, `CHAR()`/`ASCII()`) are decoded, SQL keyword casing is folded, and comment sequences (`/* */`, `--`) are **marked as a feature, not deleted**. Implemented: [`src/preprocessing/canonicalize.py`](../../src/preprocessing/canonicalize.py), tested.

### 5.4 Branch 1 — Supervised Multi-Class Classification — **[IMPLEMENTED, evaluated]**

Classifies each query into `normal` or one of four SQLi categories (`union_based`, `error_based`, `boolean_blind`, `time_blind`; a fifth category, `stacked`, has no real-world data available and was excluded from the reported training run — Section 7). Four candidate architectures (TF-IDF+Logistic Regression, TF-IDF+LightGBM, DistilBERT, CNN+SQL-tokenizer) were compared on F1-macro, latency, and model size; **TF-IDF + Logistic Regression was selected** (F1-macro = 0.982, p50 latency ≈ 0.5 ms, 3.9 MB on disk) as the best trade-off — the F1 spread across all four candidates is small, while the heavier candidates cost 100×+ more latency or a GPU + 256 MB on disk for no measurable gain.

### 5.5 Branch 2 — Query-Level Anomaly Detection — **[IMPLEMENTED, evaluated]**

Trained exclusively on benign traffic (no attack labels at all), Branch 2 learns the "normal region" of query behavior from four lightweight statistical features (length, special-character ratio, SQL-keyword count, Shannon entropy) and emits a continuous anomaly score. One-Class SVM was selected over Isolation Forest (AUC 0.90 vs 0.67, at a lower FPR of 0.3% vs 0.63%). Because it never sees attack labels, this branch is, in principle, able to flag attack shapes Branch 1 was never trained on — the property directly measured in Section 8. Its score also feeds Branch 3 as an input feature.

### 5.6 Branch 3 — Session-Level Sequence Model — **[IMPLEMENTED offline; not yet wired into the live API]**

**Why it's needed:** Boolean-blind and time-blind SQLi work by sending many individually-valid-looking queries and inferring database contents from small differences in response content or timing across the sequence. No single query in such a sequence needs to look anomalous; the signal is in the *pattern across queries*. Section 8's zero-day study gives direct evidence for this: when `boolean_blind` is withheld from training, the two query-level branches together still miss the overwhelming majority of its queries.

**Architecture (built):**
```
Query 1 ─┐
Query 2 ─┼─> [Layer 1: per-query encoder, reused from Branch 1 — not retrained]
Query 3 ─┘                      │
                                 ▼
                  [Layer 2: single-layer GRU over the session]
                  input per step = [Branch-1 embedding ⊕ Branch-2 anomaly score]
                                 │
                                 ▼
                     Session-level attack-type score (4-way: benign /
                     boolean_blind / time_blind / query_splitting)
```

**Result:** F1-macro = **1.0** on a 280-session held-out test set (`report/metrics/branch3_eval.json`), and F1-macro = **1.0** again in a deliberately harder setting where session steps are scored using a Branch-1 variant that has never seen `boolean_blind` and misses 90.2% of it per-query (`branch3_eval_hard.json`) — evidence the session-level signal is not just inheriting an already-correct per-step Branch-1 call. Model: single-layer GRU, `src/models/branch3_session.py`, trained via `train/train_branch3.py`.

**⚠️ Read this result narrowly.** The test set is small (280 sessions) and self-generated; a perfect 1.0 F1-macro on such a set is a strong proof-of-concept for the architecture, not yet evidence of generalization to real, unseen attacker behavior. Session data was built via `train/attack_simulator.py`, which runs the **real bisection algorithm sqlmap itself uses** (bisect on string length, then per-character on ASCII code point, ~7 probes/character) against a **real, self-hosted SQLite demo database** (`deploy/demo_db.py`) — every probe is a genuine SQL statement with a genuine true/false outcome (real row-count difference, or a real measured `SLEEP()` delay), not a templated guess. This is a substantial upgrade over pure simulation, but it is still **"Cách A"**: attacker and target are both run locally by the team. **"Cách B" — real `sqlmap` driving DVWA/WebGoat in Docker, captured via mitmproxy/Burp — has not been started.** The `query_splitting` class still uses heuristic fragmentation rather than a grounded attack trace, and extraction is capped at 4 characters (kept short to bound session length and, for time-blind, real wall-clock generation time).

### 5.6.1 Data plan for Cách B (not yet executed)

Stand up a network-isolated vulnerable lab (DVWA/WebGoat in Docker); drive it with `sqlmap --technique=B` (Boolean-blind) and `--technique=T` (time-blind); capture full request/response traffic through an intermediate proxy (mitmproxy/Burp Suite). Only sessions where `sqlmap` reports **successful data extraction** would be kept as positive, to avoid labeling failed attack attempts as ground truth. Benign sessions would be grouped from CSIC 2010's existing session cookies, or from normal-mode crawling of the same lab. The two-tier label schema already used for Cách A (per-query: 0 = normal, 1 = SQLi; session: 0 = benign, 1 = blind Boolean-based, 2 = blind time-based, 3 = query-splitting/multi-step) carries over unchanged. A **production Session Store** (in-memory for an MVP, Redis if the proxy runs as multiple instances) with a TTL/eviction policy remains a prerequisite for serving Branch 3 live — the offline training pipeline does not need it, but the deployed API does, and it has not been built (Section 10).

### 5.7 Central Decision Engine and the Overkill Policy — **[fusion logic implemented and wired; Branch 3 input still stubbed]**

| Branch 1 | Branch 2 | Branch 3 (session) | Action |
|---|---|---|---|
| Attack class | — | — | **BLOCK** immediately, log it |
| `normal` | Anomalous | — | **OVERKILL** — hold, await Admin confirmation, deny by default on timeout |
| `normal` | Normal | Anomalous sequence | **HOLD the whole session** (extended Overkill), may block the entire session |
| `normal` | Normal | Normal | **ALLOW** |

`deploy/routers/detect.py:fuse_decision` implements this matrix for real, including Branch-3 session escalation taking precedence when available, and graceful degradation (e.g. `UNKNOWN` if Branch 1 itself is unavailable). It is exercised end-to-end today, but since `deploy/routers/branch3.py` still always returns `not_ready` (Section 10), the live system currently only ever resolves via the first three rows of the table — the Branch-3 escalation path is implemented but dormant until Branch 3 is wired in.

### 5.8 Continual Learning — **[implemented and evaluated as a full offline experiment]**

Administrator confirmations on held (Overkill) requests are labeled and stored in a new-data pool (`src/decision/queue.py`, SQLite-backed, tested); a scheduled retrain mixes new data with a rehearsal sample of old data (to avoid catastrophic forgetting); a **validation gate** (`src/continual_learning/gate.py`) only promotes the retrained model if it matches or beats the currently-deployed model's F1/FPR on a fixed held-out test set, with a distinct path for "major bump" (a genuinely new class, where no comparable predecessor exists) versus "minor bump" retrains.

**This loop has been run end-to-end as an offline experiment** (`train/run_continual_learning_experiment.py`, results in `report/metrics/continual_learning/RESULTS.md`), replaying a held-out stream (80,808 queries, 5% attack rate) with a new class (`stacked`, entering at ~1% of traffic) and simulated labelling. Findings worth carrying into the paper/report:

- **The review queue — not the drift monitor — is what surfaces a novel class.** All 727 `stacked` occurrences were caught by the review queue; every one of five distribution-drift signals tested stayed below its alert threshold throughout, including the closest signal (confidence on flagged traffic, PSI 0.19 against a 0.2 threshold).
- **How the confirmed-label pool is assembled matters more than how much data there is.** Retraining on the raw confirmed pool *degrades* the model (F1-macro 0.9425, most flagged queries being benign false positives skews the pool toward `normal`); balancing the pool first is what earns promotion (F1-macro 0.9623, FPR cut by 64%, from 0.0631 to 0.0225, with no per-class regression).
- **A no-new-class ablation control** (same +254 rows, but drawn only from already-known classes) recovers 0.000 recall on the new class versus 0.726 for the real candidate — confirming the gain is attributable to learning the class, not just to having more data.
- **Shadow deployment** (candidate logged, champion still enforced) showed 98.85% agreement and only 13 queries where the candidate would have allowed something the champion blocked — no unsafe divergence found before promotion.

Caveats stated plainly in the results: labelling was **simulated** (ground truth stood in for a human reviewer) rather than run with real Admin review; traffic was a **replay** of held-out data, not live production traffic; and the `stacked` class itself is 100% synthetic, so its 0.726 recall demonstrates the promotion *mechanism*, not a real zero-day detection result — the genuine zero-day evidence remains the `boolean_blind` leave-one-out finding in Section 8.

### 5.9 Concept Drift Monitoring — **[implemented and evaluated — see 5.8]**

Periodic PSI tracking on feature distributions and on predicted-class/confidence distributions (`src/monitoring/drift.py`, tested), plus model versioning by directory (`src/continual_learning/versioning.py`) to support fast rollback. The offline experiment above **is** the evaluation of this component; its main finding is a considered negative result (drift monitoring does not catch a rare new class — see 5.8) rather than a simple pass/fail, which is itself a useful, reportable conclusion about where this technique's strengths actually lie (gradual population shift, not rare novel classes).

## 6. Datasets

| ID | Dataset | License | Used for |
|---|---|---|---|
| D1 | SQLiV3 (Kaggle mirror, ~30.9K rows) | **Provenance unclear** — no explicit license on the original listing; a GitHub mirror self-applies MIT, which does not establish the mirror holds redistribution rights over the underlying data | Branch 1 |
| D3 | CSIC 2010 (HTTP traffic) | Public research dataset | Branch 2 benign enrichment + held-out anomalous evaluation set |
| D4 | payload-box | MIT (confirmed) | Branch 1 multi-class enrichment |
| D7 | SR-BH 2020 (honeypot, 527,813 rows, Harvard Dataverse) | CC0 1.0 (confirmed) | Branch 1 (majority of per-class volume via sub-type re-tagging) + Branch 2 benign pool |

Combined, cleaned datasets are published on Hugging Face (`Jason-42195/VNU-SQLi-Detection`) rather than committed to the repo. **Branch 3's session-level dataset exists for Cách A** (1,400 sessions: 1,050 from real bisection-attack traffic against a self-hosted demo DB, 350 from heuristic query-splitting simulation) — Cách B (real `sqlmap` against a Dockerized DVWA/WebGoat lab) is the still-open item, see Section 5.6.1. Until D1's licensing is resolved, the combined dataset should be treated as provenance-unclear, not as cleanly MIT/CC0-licensed, in any public release.

## 7. Known Data-Quality Findings (measured, not assumed)

Two independent, measured label-noise issues were found during data construction and are carried into the paper's Discussion rather than glossed over:

- **Mislabeled attacks inside the `normal` pool** of the D7 honeypot data — caught only by manual content reading, not by cross-checking D7's own multi-label flags (which looked clean in aggregate). Fixed via three iterative rounds of content-based signature filtering; each round's manual review found a new evasive variant slipping through, which is why iteration was deliberately stopped rather than continued indefinitely — the correct long-term fix is canonicalization plus an adversarial test set, not unbounded dataset patching.
- **~13% measured mislabeling** in the `boolean_blind` catch-all class (30-sample manual audit) — SSRF payloads, CRLF/header injection, and one fully benign row.
- **The `stacked` class has zero naturally-occurring examples** across all three sources (D1, D4, D7). 363 synthetic samples were templated to represent it, but every candidate architecture achieved 100% recall on them — a sign of trivial separability from repeated template structure, not a genuine quality signal — so `stacked` was excluded from the reported Branch 1 training run.

## 8. Zero-Day Generalization Study (the empirical bridge to Branch 3)

To quantify, rather than assume, where query-level detection's blind spots are, a leave-one-out protocol was run: for each SQLi category, that category is withheld from Branch 1's training set, both branches are retrained, and every held-out query is scored by both. Two well-defined outcomes are reported per class: Branch 1's **miss rate** (fraction predicted `normal`, i.e. bypassing supervised detection) and Branch 2's **detection rate** on the same queries.

| Unseen class | B1 miss rate | B2 detection rate |
|---|---|---|
| `union_based` | 2.5% | 0.5% |
| `error_based` | 0.0% | 89.7% |
| `boolean_blind` | **90.2%** | 5.4% |
| `time_blind` | 0.3% | 12.7% |

Structurally distinctive unseen attacks (`union_based`, `error_based`, `time_blind`) are still caught by supervised classification as *some* attack class, even when their specific label was never trained on. **`boolean_blind` is the failure case**: it is lexically close to legitimate queries, so withholding it causes a 90.2% bypass rate, and the benign-only anomaly branch recovers only 5.4% of them independently. Neither query-level branch reliably covers blind SQLi it hasn't seen — this is the direct, measured motivation for Branch 3's session-level approach, since blind SQLi's signal is a property of the *sequence*, not of any single query in it.

> **Note on `combined_coverage`:** an earlier draft of the underlying experiment (`report/metrics/zeroday_experiment/summary.json`) reports a third `combined_coverage` figure per class; those values are internally inconsistent with the two columns above (they do not reconstruct as their union) and should be recomputed from raw predictions before being cited anywhere, including in this document.

## 9. Evaluation Protocol

Branch 1: per-class Precision/Recall/F1, F1-macro (headline metric, chosen because Accuracy would be distorted by the underlying class imbalance), confusion matrix, per-class ROC. Branch 2: FPR and detection rate at a fixed operating threshold, AUC, average precision, and a 21-point threshold sweep to support a deployment-time threshold choice. Both: p50 inference latency and on-disk model size as deployment-relevant secondary metrics. All experiments deterministic (seed = 42); hardware: RTX 3050 (6 GB). Branch 3: session-level F1-macro/confusion matrix over the 4-way label (benign/boolean_blind/time_blind/query_splitting) plus the "hard mode" comparison against a Branch-1 variant blind to `boolean_blind`, per the two-tier label schema (Section 5.6) — done for Cách A; repeating this protocol on Cách B data, once collected, is the natural next evaluation.

## 10. Current Implementation Status

| Component | Status |
|---|---|
| Canonicalization | ✅ Implemented, tested |
| Branch 1 (supervised multi-class) | ✅ Implemented, trained, evaluated (F1-macro = 0.982) |
| Branch 2 (query-level anomaly) | ✅ Implemented, trained, evaluated (OCSVM AUC = 0.90, FPR = 0.3%) |
| Zero-day leave-one-out study | ✅ Complete (Section 8) |
| Illustrative query→verdict demo | ✅ `train/notebooks/demo_detect.ipynb`, 19/20 correct on a random sample |
| **Branch 3 (session-level sequence model)** | ✅ Implemented, trained, evaluated **offline** — GRU, F1-macro = 1.0 on both standard and "hard mode" held-out sessions (Section 5.6). Cách A only (real bisection attack against a real self-hosted demo DB); Cách B (real `sqlmap` + Dockerized DVWA/WebGoat) not started. Small (280-session), self-generated test set — a strong proof-of-concept, not yet a generalization claim |
| **Central Decision Engine (fusion logic)** | ✅ Implemented and wired (`deploy/routers/detect.py:fuse_decision`) — real, not conceptual; Branch-3 escalation path exists but is dormant while Branch 3's router is stubbed |
| **Continual Learning** (drift, review queue, retrain gate, versioning) | ✅ Implemented and evaluated as a full offline experiment (Section 5.8) — 198 tests passing across `src/continual_learning/`, `src/monitoring/drift.py`, `src/decision/queue.py`. Labelling simulated; traffic is a replay, not live production traffic |
| Live API: Branch 3 serving (`deploy/routers/branch3.py`) | ⛔ Explicit stub — always returns `not_ready`, not yet loading the trained model via the registry |
| Live API: Admin overkill queue (`deploy/routers/admin.py`) | ⛔ Explicit stub — empty queue, no persistence, despite the real tested `src/decision/queue.py` existing |
| Live API: Drift/monitor dashboard (`deploy/routers/monitor.py`) | ⛔ Mock data — deterministic fake series, not reading the real `src/monitoring/drift.py` |
| Production Session Store (TTL/eviction, Redis) | ⛔ Not started — needed to serve Branch 3 live across multiple requests; not needed for the offline training pipeline above |
| Adversarial robustness evaluation (WAF-A-MoLE) | ⛔ Not run — all current results are on clean test splits; treat F1/AUC figures as an upper bound, not evidence of evasion-robustness |

## 11. Expected Contributions

1. A multi-branch SQLi detector at the database proxy, combining supervised multi-class classification and benign-only anomaly detection under one decision policy, evaluated on a combined public dataset with a documented, measured account of the label-noise problems found during construction.
2. A leave-one-out zero-day study that quantifies — rather than assumes — how far query-level detection generalizes to attack categories it has never seen, and identifies exactly which category (`boolean_blind`) query-level detection cannot cover.
3. A session-level sequence model addressing a gap not covered by the surveyed related work — no reviewed source models inter-query relationships within a session for SQLi specifically — trained and evaluated (offline, Cách A) directly against the failure mode Section 8 measures, reaching F1-macro = 1.0 on held-out sessions including a deliberately adversarial "hard mode" evaluation.
4. A continual-learning loop evaluated end-to-end (offline replay), with a considered negative result on drift monitoring (misses a rare new class) contrasted against a review queue that catches it, and a measured demonstration that confirmed-pool balancing — not just more data — is what earns safe model promotion.
5. (Planned) A self-collected, two-tier-labeled session dataset built from real `sqlmap` traffic against a Dockerized vulnerable lab (Cách B), to compare against the current real-bisection-but-self-hosted Cách A data — itself a contribution independent of the modeling work, if completed.

## 12. Project Timeline and Milestones

**RIVF 2026 milestones (external, fixed):**

| Date | Milestone |
|---|---|
| 31 Jul 2026, 23:59 | RIVF 2026 paper submission (EDAS) |
| 15 Oct 2026 | RIVF results notification |
| 11 Nov 2026 | RIVF camera-ready deadline — Branch 3 offline results already exist (Section 5.6); decide whether to upgrade the camera-ready from framing (A) to include them, and whether Cách B data collection is worth attempting before this date |
| 18–20 Dec 2026 | RIVF 2026 conference, VinUniversity, Hanoi |

**Internal project milestones:**

| Date | Milestone |
|---|---|
| 25 Jul 2026 | Branch 1 + Branch 2 code, metrics, model, and course report (Version 1) frozen |
| 26 Jul 2026 | Buffer day: polish metrics/figures specifically for the conference-facing report (Version 2) — no new code |
| 31 Jul 2026 | RIVF paper submitted (see `report/conf/outline.md`'s day-by-day plan for the paper-writing critical path) |
| 31 Dec 2026 | **Full source code deadline** — Branch 3, the integrated system (`deploy/` API, central decision engine, Streamlit demo), Continual Learning, and Concept Drift monitoring, i.e. everything marked ⛔ in Section 10. Far out relative to today, but a hard deadline, not an open-ended aspiration. |

Between 31 Jul and 11 Nov, the priority order for the remaining ⛔ items (Section 10) is: (1) wire Branch 3's trained model into `deploy/routers/branch3.py` and the Admin/monitor routers into their real `src/` counterparts — the model and the loop already exist, this is integration work, not new research; (2) attempt Cách B (Docker lab + `sqlmap`) if time allows, to validate Branch 3 beyond its self-hosted Cách A data; (3) a production Session Store and adversarial (WAF-A-MoLE) evaluation, which have no external deadline pressure before 31 Dec.

## 13. Team and Roles

Roles as of the most recent internal planning revision (24 Jul 2026); see [`report/plan/De_xuat_SQLi_Detection_AI.md`](../plan/De_xuat_SQLi_Detection_AI.md) §0/§11 for the full history of how this split evolved under deadline pressure.

- **Bach Luong-Chi** — Branch 2 (anomaly detection: training, tuning, verification); Branch 3 owner going forward (Docker lab, `sqlmap` data collection, session model).
- **Minh-Duc Do-Xuan ("Duc")** — Branch 1 (data, training) + integration/MLOps (`deploy/` API scaffold, decision engine, versioning).
- **Diep Dinh-Ngoc** — Report writing and cross-team support.
- **Minh Nguyen-Quang** — Streamlit demo interface; supported report figures/visualizations during the 25 Jul crunch.
- **Advisors:** Linh Dinh-Van, Thai Kim-Dinh.

## 14. Risks and Mitigations

- **Branch 3 generalization risk:** the model exists and scores F1-macro = 1.0 offline, but only on a small, self-generated (Cách A) test set — this is a proof-of-concept result, not yet evidence it generalizes to real, independently-captured attacker traffic. Mitigation: state the result with its caveats plainly wherever it's cited (Section 5.6); treat Cách B collection as the validation step, not as optional polish.
- **Integration risk:** Branch 3, the review queue, and drift monitoring are all validated offline but not yet wired into the live `deploy/` API (Section 10) — three routers are still explicit stubs. Mitigation: this is scoped, bounded integration work against components that already work and are already tested, not open research risk.
- **Dataset licensing (D1):** unresolved provenance. Mitigation: treat the combined dataset as provenance-unclear in any public release until resolved; do not present it as cleanly MIT/CC0-licensed.
- **Adversarial robustness gap:** no evaluation yet against deliberately evasive input (e.g. WAF-A-MoLE-generated). Mitigation: explicitly flagged as a limitation in the paper rather than implied to be solved; scheduled as future work, not urgent relative to Branch 3.
- **Label-noise ceiling on reported F1:** the true, clean-label ceiling for Branch 1's task is unknown given the measured noise in `boolean_blind` and the original D7 `normal` pool. Mitigation: both noise sources are reported as measured limitations rather than omitted.

## References

Full bibliography reused from and kept in sync with [`rivf2026_paper.tex`](rivf2026_paper.tex) — see that file's `thebibliography` block rather than duplicating citations here.
