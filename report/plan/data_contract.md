# Data Contract — Branch 1 (multi-class) & Branch 3 (session)

> Locked in on Day 1 (13 Jul). Defines the target schema for processed data so every team member (and later code) uses the same standard. The figures below are verified against the actually-downloaded data, not estimates.

> 📦 **Processed data is downloaded from here, not in the git repo:** https://huggingface.co/datasets/Jason-42195/VNU-SQLi-Detection (`branch1_train.csv`, `branch2_normal.csv`, `branch2_anomalous_eval.csv`). See the repo root README.md, section "Processed data — where to download".

---

## 0. Dataset numbering — what D1 through D7 actually are (investigated 26/8)

The internal D-numbers used throughout this file have gaps (D2, D5 never
appear) that aren't explained anywhere else, and the paper (`rivf2026_paper.tex`)
renumbers the 4 sources it actually cites (D1-D4) sequentially for clean
prose — a DIFFERENT scheme from this file's. Both are legitimate, just not
the same numbering; traced via git log to avoid guessing:

| # (this file) | What | Status |
|---|---|---|
| D1 | SQLiV3 (Kaggle mirror) | Have, since Day 1 (`2bead06`, 14/7) |
| D2 | — | **Never assigned to anything, at any point in this repo's history.** |
| D3 | CSIC 2010 (HTTP traffic) | Have, since Day 1 |
| D4 | payload-box | Have, since Day 1 |
| D5 | — | **Never assigned to anything, at any point in this repo's history.** |
| D6 | Reserved for real captured attacker traffic ("Docker-lab/sqlmap traffic" — `configs/config.yaml`'s `exclude_labels` comment: *"re-enable [stacked] once real stacked-query examples are available (e.g. from D6 Docker-lab/sqlmap traffic)"*) | **Had a name and a purpose, never executed** — this is Branch 3's never-started "Cách B" (§5). Filled 26/8 by Superviz25 — see §6. |
| D7 | SR-BH 2020 (Harvard Dataverse honeypot) | Added AFTER Day 1, once D1 alone proved too sparse for multi-class |

The paper's own D2 = this file's D3 (CSIC 2010) — cosmetic renumbering only,
unrelated to the D2 gap above.

---

## 1. Raw data downloaded (Day 1)

| File | Source | Verified figures |
|---|---|---|
| `data/raw/d1_sqliv3_raw.csv` | [nidnogg/sqliv5-dataset](https://github.com/nidnogg/sqliv5-dataset) (mirror of Kaggle SQLiV3) | 30,918 rows parsed successfully (1 row failed due to an unescaped comma — original row 19293); original labels: **19,517** label=0, **11,347** label=1; found **15 null rows**, **46 duplicate texts**, **15 fully-duplicate rows** |
| `data/raw/csic2010/normalTrafficTraining.txt` | [GSI/UdelaR GitLab mirror](https://gitlab.fing.edu.uy/gsi/web-application-attacks-datasets) | **36,000** raw HTTP requests |
| `data/raw/csic2010/normalTrafficTest.txt` | same | **36,000** raw HTTP requests |
| `data/raw/csic2010/anomalousTrafficTest.txt` | same | **25,065** raw HTTP requests |
| `data/raw/d3_csic2010_raw.csv` | The 3 files above packaged via `train/fetch_and_wrap_d3_csic2010.py` | **97,065** rows (72,000 normal + 25,065 anomalous), columns: `id, split, label, raw_request`. Has a `Cookie: JSESSIONID=...` header → used for session grouping in Branch 3 (Cách B benign). |
| `data/raw/sr_bh_2020/data_capec_multilabel.csv` | **D7 — [SR-BH 2020](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/OGOIXX)** (real honeypot, 12 days, 2020, multi-label CAPEC) | **527,813** real rows (not ~1 million as the initial 10MB-sample estimate suggested — attack distribution is uneven over time within the file, so front-of-file sampling was badly skewed). Column `66 - SQL Injection`: **250,285** rows (47.4% — **not the real traffic ratio**, correcting an earlier claim). `000 - Normal`: 152,587 rows. **Fields need URL-decoding before tagging** (`request_http_request`, `request_body`) — skipping this step seriously skewed the tagging results on the first run. |
| `data/raw/payload_box/*.txt` | D4 — payload-box | 177 raw payload rows (5 files by DBMS + burp-intruder combined) |

**D1 notes (to handle on Day 2 — canonicalization/cleaning):**
- Malformed CSV rows (unescaped commas/quotes in the text) → must parse with the `csv` module using `quoting=csv.QUOTE_ALL` or fix the bad rows by hand; don't use default `pd.read_csv`.
- Remove 15 null rows + 15 fully-duplicate rows.
- The original class ratio (63%/37%) doesn't reflect real traffic (<1% attack) → report Precision/Recall at low FPR, not just Accuracy.

**D3 note:** this is raw HTTP requests (with headers, cookies, body), **not plain SQL queries**. Requires a parameter-extraction step (query string / POST body) before canonicalization, same as D1.

---

## 2. Target schema — Branch 1 (Supervised, multi-class)

File: `data/processed/branch1_train.csv` (Day 2 deliverable).

| Column | Type | Description |
|---|---|---|
| `id` | int | Unique, incrementing ID |
| `query_raw` | str | Original, unprocessed text (kept for audit) |
| `query_canonical` | str | After canonicalization: decode encodings (URL/hex/CHAR), fold SQL keyword case |
| `has_comment_marker` | int (0/1) | Flag for `/* */` or `--` present (comment is NOT stripped, only flagged — anti-evasion feature) |
| `label` | int (0-5) | Multi-class label — see label table in Section 3 |
| `label_name` | str | Human-readable label name (`normal`, `union_based`, ...) |
| `source` | str | Row origin: `d1_sqliv3`, `d1_benign_enriched_csic`, `d4_payloadbox`, `d7_srbh2020`, `synthetic_stacked` |
| `split` | str | `train` / `test` / `adversarial_test` — **fixed from the start, never re-randomized across runs** (seed=42, see `configs/config.yaml: project.random_seed`) |

### 2.1. Combined actual distribution (D1 + D4 + D7, tagged via `src/preprocessing/multiclass_tagger.py`, URL-decoded before tagging)

| Label | D1 | D4 | D7 (SR-BH) | **Total available** | **Target for training** |
|---|---:|---:|---:|---:|---:|
| `normal` | 19,517 | – | 152,587 (not yet merged) | 19,517+ | ~15,000-20,000 |
| `union_based` | 2,213 | 16 | 83,189 | 85,418 | ~15,000 (undersampled) |
| `error_based` | 373 | 0 | 7,423 | 7,796 | keep all (~7,800) |
| `boolean_blind` | 8,619 | 145 | 126,926 | 135,690 | ~15,000 (undersampled) |
| `time_blind` | 141 | 16 | 32,747 | 32,904 | ~15,000 (undersampled) |
| `stacked` | 0 | 0 | 0 | **0** | **363** (**synthetically generated** — the entire pool comes from `src/preprocessing/synthetic_stacked.py`, 11 prefixes × 11 statements × 3 terminators; no real source has any) |

**3 confirmed issues to handle on Day 2:**
1. **`stacked` = absolute zero** across all 3 sources (tried both strict and loose regex) → had to hand-write synthetic payloads from a template (`'; DROP TABLE...`, `'; EXEC xp_cmdshell...`), tagged `source=synthetic_stacked`, and clearly flagged in the report as self-generated data, not real collection.
2. **`boolean_blind` is the catch-all bucket and has real noise** — manual sanity-checking of an SR-BH sample found a fully-benign row (`/blog/wp-includes/js/comment-reply.min.js?ver=4.9.5`) still carrying SR-BH's own original `SQL Injection=1` label. **Don't treat SR-BH's original labels as ground truth** — our own tagger is applied on top regardless, and hand sanity-checking ~100 samples/class before training is mandatory (original Section 3).
3. **Severe natural class imbalance** (`boolean_blind`/`union_based` are 17-350x larger than `error_based`) → undersample the large classes down to a similar order of magnitude (~15K), use **F1-macro** as the primary metric, not Accuracy.

## 3.1. Actual build results (`train/build_branch1_dataset.py`, run 15 Jul)

**Quality check on D7's original labels before merging** (SR-BH is multi-label — one row can carry multiple attack flags at once):
- Of the 250,285 rows with `SQL Injection=1`: **99.1% are "pure"** (no other attack flag set); **0.9% cross-contaminated** (mostly co-occurring with `310 - Scanning for Vulnerable Software` — plausible, not an error).
- Of the 152,587 rows with `Normal=1`: **0% conflict** with any **other label flag** in SR-BH. But this only compares flags, **it doesn't check content**.

**⚠️ Manual sanity-checking of actual content (not just flag comparison) found a more serious issue:** among 5-20 hand-read `Normal=1` rows from D7, some contained `sleep(15)` (time-blind SQLi) and `cat /etc/passwd`, `() {{ :;}}; /bin/sleep 15` (Shellshock CVE-2014-6271) — **real attacks that SR-BH itself mislabeled `Normal=1`**, despite not conflicting with any of its own other flags. This is **real label noise at the content level**, not just cross-contamination between flags.
- **Fix:** added a `matches_any_attack_signature()` function (`src/preprocessing/multiclass_tagger.py`) — a filter independent of the source label, checking whether the canonicalized content matches any of the SQLi attack regexes (5 types) or OS command injection/Shellshock patterns. Applied to every row tagged `is_attack=False` before accepting it into the `normal` pool.
- **Round 1 result:** 1,561 mislabeled `Normal=1` rows removed.
- **Round 2 sanity-check (manual review, 30/class, different seed):** found additional variants that slipped through — `&cat /etc/passwd&` (using `&` instead of `;` to separate commands; round-1 regex only caught `;cat`) and `<!--#exec cmd="ls /"-->` (SSI injection). Broadened the regex (`[;&|]` instead of just `;`, added an SSI pattern) → **2,731 rows removed in total** (~9.8% of the candidate normal pool, nearly double round 1).
- **Round 3 sanity-check:** still found deliberately evasive variants slipping through — `cat$jj $jj/etc$jj/passwd` (a fuzzer inserting junk tokens `$jj` between keywords to dodge keyword matching). **Decided to stop patching the regex here** — this is an unbounded-variant evasion problem; the right place to handle it is the canonicalization step + an adversarial test set (Day 7), not endless iteration on this static filter. Logged as an accepted residual risk for the MVP.
- **Remaining limitation (out of scope, not addressed):** SR-BH has 12 attack categories; the filter only targets SQLi + OS command injection/SSI — XSS (`<script>alert(1)</script>`), SSRF callbacks (`owasp.org`) still leak into the `normal` pool. Acceptable for Branch 1 (SQLi-only concern), but **needs more rigor when building the benign pool for Branch 2** (the anomaly detector is far more sensitive to benign noise).

**Distribution after build + filtering (68,159 rows, train=54,527 / test=13,632, stratified, seed=42):**

| Label | Available (D1+D4+D7+synthetic, post-filter) | Taken into train+test |
|---|---:|---:|
| `normal` | 26,771 (19,517 D1 + ~7,254 D7 normal after removing 2,731 noisy rows) | 15,000 |
| `union_based` | 85,826 | 15,000 |
| `error_based` | 7,796 | 7,796 (kept all) |
| `boolean_blind` | 134,057 | 15,000 |
| `time_blind` | 34,017 | 15,000 |
| `stacked` | 363 | 363 (kept all) |

**Attack-side label sanity-check (30/class, not just the `normal` side):** `union_based`, `error_based`, `time_blind`, `stacked` all came back **30/30 clearly correct** (since the regex matches something specific by nature). `boolean_blind` (the catch-all bucket) was different — of 30 samples reviewed: **~26/30 (87%) reasonable** (real boolean logic or clear SQLi probing), **~4/30 (13%) clearly wrong** — SSRF callbacks, CRLF/header injection, and one fully-benign row (`wp-comments-post.php`, a normal form submission) that SR-BH self-tagged `SQL Injection=1`. Confirms: **label noise exists on both sides** (not just `normal`), concentrated in the `boolean_blind` bucket — recorded as a measured limitation (~13%), not an estimate.

File: `data/processed/branch1_train.csv` (68,159 rows, columns per the Section 2 schema). **Not yet through a full ~100-sample-per-class manual sanity-check** (only a small 15-20/class sample reviewed so far) — should be done before citing final numbers in the report, but reliable enough to start baseline training (Day 3).

⚠️ **Correction:** the SQLi share across the full SR-BH set (527,813 rows) is **47.4%**, not the low, traffic-representative ratio originally assumed (a quick estimate from the first 10MB of the file was skewed by uneven attack distribution over time). SR-BH is useful for its **diversity of real payloads**, not for representing "real-world ratio".

**Principle:** `query_canonical` is produced by `src/preprocessing/canonicalize.py` (Day 2) — a pure function, easy to test, no I/O dependency.

---

## 3.2. Branch 2 build results (`train/build_branch2_dataset.py`, run 15 Jul)

**Architecture decision:** reuses the same benign-filtering module (`matches_any_attack_signature`, `data_sources.py`) as Branch 1 instead of writing a separate pipeline — avoids two diverging "sources of truth" for what counts as clean normal traffic. Differences from Branch 1: **no count cap** (Branch 2 doesn't need class balance; more normal data is better for estimating the "safe zone"), and **no TF-IDF** — uses 4 statistical/structural features instead (`length`, `special_char_ratio`, `sql_keyword_count`, `entropy` — see `src/preprocessing/statistical_features.py`) because Branch 2 needs to generalize to syntax it has never seen, so it can't rely on specific keywords.

**Sources:** D1 (30,789) + both D3 CSIC2010 normal splits (97,065, URL+body extracted from raw HTTP via `load_d3()`) + all of D7's `Normal=1` (not sampled, unlike Branch 1) → 402,870 candidate rows total before filtering.

**Results:**
| Step | Rows |
|---|---:|
| Initial candidates (D1+D3+D7 normal) | ~528,724 |
| After `matches_any_attack_signature` filter | 204,934 (39,153 removed, ~7.4%) |
| After dedup on `query_canonical` | **91,935** (112,999 more duplicates removed — D3/D7 have many repeated static-asset URLs) |
| Train / Test (seed=42) | 73,548 / 18,387 |

File: `data/processed/branch2_normal.csv` (91,935 rows) + `data/processed/branch2_anomalous_eval.csv` (25,065 rows of D3 anomalous data, kept separate for FPR/detection-rate evaluation on Day 5-6, not used for training).

**⚠️ Finding from comparing features across the two sets (worth noting for real train/eval):** the `anomalous` set (D3) has a **lower** average `sql_keyword_count` than the normal set (0.13 vs 0.35) despite being longer (137 vs 92 chars). Reason: D3 "anomalous" contains **many attack types** (buffer overflow, XSS, path traversal, CRLF...), not just SQLi — `sql_keyword_count` isn't a strong signal for this whole test set. Isolating the SQLi subset within D3 anomalous is needed for an accurate read on Branch 2's zero-day SQLi detection ability, or this should be treated as a "general anomaly detection" benchmark rather than SQLi-specific.

**Also found:** `length` has very large outliers (max 5,370 chars in the normal pool) — worth normalizing/log-transforming this feature before training Isolation Forest, to avoid outliers dominating distance calculations.

---

## 3.3. Dropping the `stacked` class from training + fixing an F1-macro bug (16 Jul)

**Reason for dropping `stacked`:** after comparing 4 architectures (Section 4.1 of `De_xuat_SQLi_Detection_AI.md`), all 4 models hit **100% recall** on the `stacked` class — even though this class is **100% synthetic** (363 templates). This signals the data is trivially separable (the template repeats the same `; DROP/INSERT/...` structure), not a genuine quality signal. Decision: exclude it from the training set, keep the generation code (`src/preprocessing/synthetic_stacked.py`) for reuse once real data exists (e.g. from the Docker lab/sqlmap, Day 5-6).

**Implementation:** added `branch1_supervised.balance.exclude_labels: [5]` to `config.yaml`; `train/build_branch1_dataset.py` reads this to (a) skip the `synthetic_stacked` source at load time, (b) defensively filter any row whose label is in `exclude_labels` after tagging. New dataset: **67,796 rows, 5 classes** (train 54,236 / test 13,560).

**⚠️ Real bug found while retraining:** after dropping `stacked`, `train/train_branch1.py` reported F1-macro dropping from 0.985 to **0.8185** — looked like the data had gotten worse, but a manual verification script gave **0.982** (matching expectations). Root cause: the old code hardcoded `LABEL_ORDER = sorted(LABEL_NAMES.keys())` (always all 6 static labels) and passed it into `classification_report(labels=LABEL_ORDER, ...)` — once label 5 (`stacked`) no longer appeared in the data, sklearn still counted it as a class with `f1-score=0` (0 support), incorrectly dragging down the macro average. **Fixed** in both `train_branch1.py` and `compare_branch1_architectures.py`: the label list is now computed **from the actual data** (`sorted(set(y_true) | set(y_pred))`), not hardcoded against a static schema. Worth remembering: any time classes are added/removed, re-check for hardcoded label lists feeding `classification_report`/`confusion_matrix`.

**Correct F1-macro for the 5-class model: 0.9822** (`models/branch1_v1/metadata.json`, TF-IDF + LogReg, architecture unchanged).

---

## 3.4. Branch 2 scope fix + estimator switch (19 Aug) — resolves the §3.2 SQLi-isolation caveat

Follow-up to §3.2's flagged caveat ("D3 anomalous contains many attack types, not just SQLi") and to the 16-17/08 domain-confound bug fix (`configs/config.yaml` `branch2_anomaly` comments, `train/build_branch2_data.py` docstring). Full narrative: [`report/conf/project_history.md`](../conf/project_history.md) §3. Short version:

1. **System-scope finding**: the system is deployed at "Position B" (DB proxy, receives the SQL statement *after* the backend has built it — `report/plan/De_xuat_SQLi_Detection_AI.md` §5.1), so production input is always query/parameter text, never a raw HTTP request. D1 (SQLiV3) already matches this. D3 (CSIC 2010) and D7 (SR-BH 2020) were captured as full HTTP requests — the scheme/host/path portion is routing noise that measurably dilutes whole-string features (`special_char_ratio` effect size |d|=1.69 on D1 vs only |d|=0.12 on D3).
2. **Fix**: `train/build_branch2_dataset.py` now strips the scheme/host/path off D3/D7 rows (`_strip_url_wrapper`), keeping only query-string/body parameters — the closest available proxy to Position-B input for HTTP-captured sources. Rows with nothing left after stripping (bare static-asset requests) are dropped. The anomalous eval set now also includes D1 + D7 attack rows (previously D3 only) — D7's `load_d7` already isolates its "SQL Injection" CAPEC column, so these are confirmed-SQLi, not D3's mixed-attack-type problem.
3. **New features**: 6 "local peak" features added to `statistical_features.py` (`same_type_run_ratio`, `max_token_length`, `token_count`, `max_special_run`, `max_digit_run`, `paren_imbalance`) — measure a local run/token instead of a whole-string ratio, so they aren't diluted by the long legitimate parameter strings D3/D7 produce even after the URL strip.
4. **Estimator switch**: `one_class_svm` → `local_outlier_factor` (`n_neighbors=5`). The benign pool now spans 3 structurally distinct sub-populations (D1/D3/D7); a single global OCSVM/IsolationForest boundary judged "not like D3" as anomalous even for genuinely benign D1/D7 traffic. LOF's local-density notion avoids this. Compared against OCSVM, IsolationForest (incl. `max_samples=1.0`), GaussianMixture, EllipticEnvelope — LOF won clearly.

**Result** (`report/metrics/branch2_eval.json`, official `models/branch2_v1`): **DR @ matched FPR=5% = 80.6%, AUC = 0.929** (up from 26.2% / 0.792 pre-fix). Per-source DR: D1=78.5%, D3=66.9%, D7=84.0%, `ssrf_moved_from_benign`=59.3%.

**Trade-off worth stating in Limitations**: LOF's fitted model retains the full training feature matrix (not a compact set of parameters like OCSVM/IsolationForest) — larger model artifact, and every inference call does a k-NN lookup against the training set rather than a fixed decision boundary. Measured latency was comparable to IsolationForest in an offline benchmark (~15-18 ms/query on this hardware) but this should be re-measured against the live `/api/v1/detect` endpoint before citing an end-to-end number in the paper.

---

## 3. Multi-class label table (Branch 1) — applied via a rule-based tagger

Priority order when a payload matches multiple signals: **stacked > time_blind > error_based > union_based > boolean_blind**.

| Code | Name | Meaning | Main signal (regex, case-insensitive) |
|---|---|---|---|
| `0` | `normal` | Valid query | Doesn't match rules 1-5 |
| `1` | `union_based` | Merges data from another table via `UNION SELECT` | `UNION\s+(ALL\s+)?SELECT` |
| `2` | `error_based` | Forces the DB to leak data via an error | `EXTRACTVALUE\|UPDATEXML\|FLOOR\(RAND\|CAST\(.*AS\|CONVERT\(` |
| `3` | `boolean_blind` | Infers via true/false conditions | `(OR\|AND)\s+\d+\s*=\s*\d+`, `'\s*OR\s*'?1'?\s*=\s*'?1` (catch-all bucket for remaining attack payloads matching no other rule) |
| `4` | `time_blind` | Infers via response delay | `SLEEP\(\|BENCHMARK\(\|WAITFOR\s+DELAY\|PG_SLEEP\(` |
| `5` | `stacked` | Chains a second statement via `;` | `;\s*(DROP\|INSERT\|UPDATE\|DELETE\|EXEC\|TRUNCATE\|CREATE\|GRANT\|ALTER)` |

**Mandatory sanity-check (Day 2):** take a random sample of ~100 payloads/class, manually check the tagger's accuracy rate — record the figures in the report (Section 6.2). These are automatic labels, not "gold" labels — this must be stated transparently.

**Expected imbalance:** `stacked` and `time_blind` are likely rare in D1 → supplement by filtering D4 (payload-box, split by DBMS) through the same regex set, and document this clearly in the data contract once done.

---

## 4. Target schema — Branch 3 (Session-level)

Target schema below; actual file is `data/processed/branch3_sessions_cach_a.csv` (built 26/7 — see Section 4.1 for the real methodology and how it differs from this original target).

| Column | Type | Description |
|---|---|---|
| `session_id` | str | Original `session_id` (if available) or `f"{client_ip}_{window_start}"` |
| `step_index` | int | Query order within the session (starting at 0) |
| `query_raw` / `query_canonical` | str | Same as the Branch 1 schema |
| `branch1_label` | int (0-5) | Per-query label inherited from Branch 1 (not re-inferred) |
| `branch2_anomaly_score` | float | Continuous anomaly score from Branch 2 (benign-only trained) |
| `timestamp` | float/ISO8601 | Request time — used to compute the session window |
| `session_label` | int (0-3) | **Session-level** label — repeated on every row of the session (decided at implementation time; see Section 4.1) |
| `session_source` | str | `A_real_db` (real bisection attack against a real DB, Section 4.1), `A_simulated` (heuristic fragmentation, `query_splitting` only), or `B_sqlmap_docker` (real captured traffic, not done) |

**Session definition:** an existing `session_id` (CSIC cookie) OR `(client_ip, idle_gap <= 1800s)` — per `configs/config.yaml: branch3_session.session_idle_gap_seconds`.

**Session label table** (matches `configs/config.yaml: branch3_session.session_classes`):

| Code | Name | Meaning |
|---|---|---|
| `0` | `benign` | Session has no attack intent |
| `1` | `boolean_blind` | Sequence of queries probing true/false (binary search across multiple requests) |
| `2` | `time_blind` | Sequence of queries probing via response delay |
| `3` | `query_splitting` | Attack payload split across multiple consecutive requests |

### 4.0 Attack mechanism — why this data is scientifically grounded, not templated

This section documents the actual mechanics of boolean-blind and time-blind SQLi, since the dataset (Section 4.1) is built by literally executing this mechanism against a real database rather than approximating it. Useful as the methodology basis for the final report.

**How the vulnerability is created.** Consider a single UI input field (e.g. a "username" lookup box). A vulnerable backend builds its SQL statement by directly concatenating the raw user input into a query template:

```
SELECT * FROM users WHERE username = '<user input>'
```

The DBMS itself does nothing wrong here — it has no concept of "user input" versus "original code"; it simply executes whatever complete SQL string it receives. The vulnerability is entirely in the backend's string-concatenation step, which happens *before* the DBMS ever sees the query. A normal input like `admin` produces `WHERE username = 'admin'` and returns exactly one row. An attacker input like `zzz' OR (1=1)--` produces `WHERE username = 'zzz' OR (1=1)--'`, and because `1=1` is unconditionally true, the `OR` makes the WHERE clause true for *every* row — the DBMS faithfully returns the entire table, which is exactly the behavior `deploy/demo_db.py`'s own `leaked` flag (row_count > 1) is built to catch.

**How boolean-blind extraction works.** An attacker who cannot see the `password` column directly (the page never displays it) can still extract it one bit at a time by asking yes/no questions through the same injection point:

```
zzz' OR (ASCII(SUBSTR(password,1,1)) > 79) --
```

This asks the DBMS: "is the first character's ASCII code greater than 79?" If true, the OR leaks rows (a full page response); if false, zero rows (a "not found" response). The attacker observes only *whether rows came back* — never the actual password — but that single true/false bit is enough. Repeating with a **bisection (binary search)** on the comparison bound narrows the true value in roughly `log2(94) ≈ 7` requests per character (94 ≈ the printable ASCII range), converging to the exact character. The process repeats per character position until enough of the string is recovered. A password of even a few characters therefore requires several dozen sequential, systematically-related requests — this is the "session" Branch 3 is trying to recognize.

**Time-blind is the same algorithm with a different oracle.** When the response page gives no visible difference between true and false, the attacker instead makes the DBMS *delay* on a true condition and measures wall-clock response time:

```
zzz' OR (SELECT CASE WHEN (ASCII(SUBSTR(password,1,1))>79) THEN SLEEP(5) ELSE 0 END) --
```

A ~5-second response means true; a near-instant response means false. The bisection logic is identical — only the oracle (row count vs. elapsed time) differs.

**Why this can't be approximated with templates.** Each request's payload is a function of *every prior request's outcome* in that same session (the comparison bound only makes sense in light of the narrowing search range so far). A dataset built by sampling unrelated real attack payloads i.i.d. — or by hand-writing a plausible-looking template — does not reproduce this dependency structure, and a session-level model trained on it would not be learning the actual pattern a real attack produces. The only way to get a scientifically valid trace is to run the real algorithm against a real (if disposable) database and record what actually happens. See Section 4.1 for how this is implemented (`train/attack_simulator.py` against `deploy/demo_db.py`).

## 4.1. Actual build results — Cách A (revised 26/7: real bisection attack against a real DB)

**This section describes the SECOND version of the Cách A pipeline.** The first version (sample real per-query attack examples i.i.d.) is kept below in 4.1.1 as a record of why it was replaced — the short version: it produced high scores for the wrong reasons, twice.

File: `data/processed/branch3_sessions_cach_a.csv` (1,400 sessions / ~25,000 rows, 350/class, 1,120 train / 280 test sessions, split at the session level, seed=42). Same schema as 4.1.1 (5 `branch1_prob_*` columns + `branch1_label` + `branch2_anomaly_score` + `gap_seconds` + `timestamp`, labels repeated on every row), but `benign`/`boolean_blind`/`time_blind` are now generated completely differently.

**Construction — `boolean_blind`/`time_blind` run a REAL bisection attack against a REAL database**, not a template or a guess:
- `deploy/demo_db.py` (the project's existing intentionally-vulnerable SQLite demo, already wired into the live Test-page) gained two additive SQLite functions it doesn't have natively: `ASCII()` and `SLEEP()` — matching what real MySQL/PostgreSQL blind-SQLi payloads use. Purely additive; the live API/tests are unaffected.
- `train/attack_simulator.py` runs the actual algorithm sqlmap uses: bisect on `LENGTH(password)` to find the string length, then for each character position bisect on `ASCII(SUBSTR(password,pos,1))` to find its code point. Every probe is a real SQL statement (`zzz' OR (<condition>)--`, the same "OR" trick `demo_db.py`'s own `leaked` flag already assumed) executed by real SQLite — the true/false oracle is a genuine row-count difference (`boolean_blind`) or genuine measured elapsed time (`time_blind`, via the real `SLEEP()` call — not a guessed gap range). ~7 requests/character, matching the real-world bisection figure from the research this session (see the "how does Branch 3 attack work" discussion). Extraction is capped at the first 4 characters (`branch3_session.cach_a.real_db.max_extract_chars`) to keep session length and (for time-blind) real wall-clock generation time reasonable.
- `benign` sessions are real legitimate lookups (`SELECT * FROM users WHERE username = '<name>'`) against the same real DB.
- `query_splitting` is unchanged from 4.1.1 (heuristic token-fragmentation) — no second vulnerable parameter exists to realistically probe across, and no real per-query "splitting" label exists anywhere to build a bisection-style attack from.

**⚠️ First diversity bug, caught before reporting results:** the bisection algorithm is deterministic given a target value, so attacking `deploy/demo_db.py`'s fixed 5-row user table meant only **5 distinct traces existed, each repeated ~70 times** across the 350 "sessions" — confirmed by extracting the target username from each session's queries and diffing bound-sequences byte-for-byte (sessions targeting the same user were identical). A model trained on that is memorizing 5 examples, not learning to generalize. Fixed with `generate_synthetic_user_pool()` — a separate, larger (100-user, `branch3_session.cach_a.real_db.synthetic_user_pool_size`), randomly-generated table used **only** for training-data generation via `deploy.demo_db.execute_raw(..., seed_rows=...)`; the live Test-page demo's fixed 5 rows are completely untouched. Re-verified: 100 unique target users → 100 unique bisection bound-sequences among the 350 sessions.

**Result: F1-macro = 1.0, FPR(benign) = 0.0, detection rate = 1.0 for all three attack types** (`report/metrics/branch3_eval.json`). Given the project's own history of misleadingly-perfect scores (Section 3.3's `stacked` class, and 4.1.1 below), a perfect score triggered the same skepticism — three checks before trusting it:
1. **Diversity re-confirmed** (100 unique traces, not repeats) — ruled out memorization.
2. **Content-only ablation** (drop `gap_seconds`, keep only Branch-1 probabilities + Branch-2 score): **still F1 = 1.0.** Not a timing shortcut.
3. **Timing-only ablation** (drop all Branch-1/2 content, keep only `gap_seconds`): F1 drops to **0.66**, and completely misses `time_blind` (DR = 0.0) — timing alone is informative but not sufficient, confirming the full model is combining signals, not keying off one trivially-separable feature.
4. **Hard-mode** (`train/eval_branch3_hard.py`, re-scoring `boolean_blind` steps with `models/branch1_no_boolean_blind` — the zero-day variant that has never seen `boolean_blind` and misses 90.2% of it per-query): **still F1 = 1.0, boolean_blind recall = 1.0.** Even with Branch 1 genuinely blind to the attack pattern, real diverse targets, and real measured timing, Branch 3 still detects every session — via the aggregated Branch-2 anomaly signal across ~30 real steps, not per-query recognition.

**Why content alone is enough:** every `boolean_blind`/`time_blind` session shares the same underlying attack *structure* regardless of which of the 100 users is targeted — a length-bisection phase (~5 steps) followed by a character-extraction phase (~7 steps/char) — so the *sequence shape* of Branch-1/Branch-2 signals is consistent within a class even though the specific values extracted differ every time. This is a legitimate structural signature of an automated, repetitive attack campaign, not an artifact — real intrusion-detection systems rely on exactly this kind of "burst of structurally similar requests" signal.

**Honest caveat carried forward from the "how does Branch 3 attack work" discussion:** `time_blind` payloads contain a literal `SLEEP()` call, which `branch1_v1` recognizes correctly on essentially every single step (confirmed: 11,218/11,218 `time_blind` rows classified as `time_blind` by Branch 1 alone in the non-hard-mode dataset). **In the live decision engine, a session like this gets BLOCKED on request #1 and never reaches Branch 3 at all** — this session type doesn't currently represent a scenario that would ever exercise Branch 3 in practice. `boolean_blind`'s hard-mode result is the one that actually matters for the paper's claim; `time_blind`'s perfect score should be reported with this caveat, not without it.

**Known limitations still present:** `query_splitting` remains on the heuristic-fragmentation approach (Cách B — real sqlmap traffic against a Docker lab — would replace it with something grounded); the demo DB's single injectable parameter means there's no realistic "probe multiple parameters across a session" scenario to build; `max_extract_chars=4` means sessions don't demonstrate full-password extraction, only the bisection pattern's first few characters.

### 4.1.1. Superseded first-pass build (kept for the record)

The first version of this dataset sampled REAL per-query attack examples **i.i.d.** from `branch1_train.csv` for `boolean_blind`/`time_blind` (no relationship between consecutive queries in a session — just N random same-labeled payloads with a guessed gap range), and used a guessed `gap_seconds` range per session type rather than anything measured. This produced **97.15% F1-macro, 100% DR on boolean_blind/time_blind** for the wrong reason: those sessions sample payloads `branch1_v1` was trained on and already classifies correctly per-query most of the time, so the GRU's task reduced to "aggregate a bag of already-correct per-step labels" — not a test of Branch 3's value proposition. Same failure pattern as Section 3.3's `stacked` class: a high score from data that's accidentally too easy. Superseded by the real-bisection approach in 4.1 above once the "how does Branch 3 attack work" discussion clarified that Branch 3 is only reachable, in the live decision engine, for sessions that evade per-query detection — meaning the scenario itself has to reflect that, not just produce a high number.

---

## 4.2. Branch 3 redesign: GRU → Session Correlator (diagnostic session, 7 Aug)

**Trigger.** Questioning why Branch 3's per-step input used Branch 1's classifier *output* rather than its content led to three findings that, together, replaced the GRU sequence-model design entirely — not just its input features.

**Finding 1 — information bottleneck (measured).** Branch 1's 5-class probability output collapses distinguishing content: two `boolean_blind` bisection steps differing only in comparison bound (`>79` vs `>103`) have TF-IDF cosine similarity **0.961** on the raw vectorizer output but near-identical probabilities after the classifier (`[0.215,0.092,0.018,0.507,0.168]` vs `[0.193,0.086,0.016,0.551,0.154]`). Root cause traced to a design drift: the original spec (`config.yaml`, `README.md`, `src/models/__init__.py`) said *"content embedding (Branch 1 encoder)"*; the implementation (commit `b658085`) used the classifier's output instead, reasoning in its own docstring that a linear model has "no separate embedding to persist" — conflating "no hidden layer" (true) with "no embedding stage" (false: TF-IDF vectorization *is* the encoder; the classifier's output is a lossy projection trained to separate attack type, not preserve content).

**Finding 2 — production reality check.** The live decision engine (`deploy/routers/detect.py:fuse_decision`) blocks on any single query with Branch-1 attack-probability ≥ `decision_threshold` (0.5) — Branch 3 was never consulted for that decision. Combined with `train/eval_branch3_hard.py`'s own (superseded) docstring confirming `branch1_v1` already recognizes most real `boolean_blind`/`time_blind` bisection probes per-query, most such sessions would be blocked at step 1-2 in production, long before a session-level GRU could see enough steps to aggregate anything.

**Finding 3 — no principled fixed session length exists.** `max_session_len: 64` was never justified against a real bound. The actual bound is set by `session_idle_gap_seconds` (1800s) combined with `attack_step_gap_seconds` ([1,15]s) — a session can legitimately run **~120 to ~1800 requests**, dwarfing 64 (itself already short of a single full password extraction, ~103 steps for a 14-char password at ~7 probes/character). A fixed-length padded GRU is structurally the wrong shape for this problem.

**⚠️ The GRU's earlier "F1-macro = 1.0" results (§4.1) should not be re-cited as evidence.** Two real bugs were found in this GRU's own training/eval pipeline during this session: `collate_fn` sliced the leading (padding) end of a sequence instead of the trailing (real-step) end, and `eval_branch3_hard.py`'s padding-mask/shuffle-test logic had the equivalent bug. Both were fixed, and the corrected shuffle-test F1 drop was only 0.012 — far short of what the pre-fix "F1=1.0, robust to shuffling and to a boolean_blind-blind Branch 1" claims implied. The §4.1 numbers were very likely produced under the buggy pipeline (the GRU may have been learning session step-*count*, which correlates with class by construction, rather than content pattern) and are superseded by everything below.

**Redesign: `SessionCorrelator` (`src/models/branch3_session.py`), not a trained model.** Two independent checks, OR'd together, each re-using an already-trained branch as-is:

- **Content check** — concatenate the session's raw query text (whole strings, no character slicing) and re-score with Branch 1's *existing* classifier (no retraining). Validated empirically (Experiment A2, below): a single `boolean_blind` probe can sit just under the 0.5 threshold (measured 0.459 at step 1 on `branch1_v1`), but concatenating more real steps pushes it up (0.593 at 10 steps, 0.666 at 32). **Precise mechanism, checked directly (not assumed):** concatenating only the WEAK steps together does not cross the threshold on its own — a real session's first 5 steps (the length-bisection phase, `LENGTH(password) > N`, each individually 0.44-0.47) stay at 0.45-0.46 when concatenated among only themselves. What actually pushes the combined score over 0.5 is that growing `k` starts mixing in the STRONG steps (the character-extraction phase, `ASCII(SUBSTR(password,pos,1)) > N`, each individually already 0.66-0.70 on its own) — the average shifts because strong evidence is blended in, not because many weak pieces of evidence reinforce each other. In isolation, the content check would not rescue a session that stopped after the length-bisection phase (never reaching character extraction). Separately confirmed: concatenation is tolerant of scale (tested up to ~5,800 concatenated characters, no classifier degradation) and does **not** rescue a genuinely zero-day-blind classifier — re-run with `branch1_no_boolean_blind` (never seen the class), attack probability stayed 0.16-0.22 regardless of how many steps were concatenated (`report/metrics/branch3_eval_hard.json`) — stated as a limitation, not reframed as a strength.

  **This gap is covered by the behavior check, checked directly — not left as an open risk.** Taking ONLY those same 5 weak-per-content-check steps and running them through the behavior check alone (Branch 2's per-query score, unaffected by Branch 1's confidence): `mean_score = 2.171` against a calibrated `mean_threshold = -4.465` — fires clearly, not marginally. Branch 2 scores structural shape (length, special-char ratio, keyword count, entropy), not attack type, so even the "weak" length-bisection queries — nested `OR`/subquery syntax, well outside normal single-value lookups — register as anomalous independent of whether Branch 1 recognizes the specific attack class. This is *why* the two checks are OR'd rather than relying on either alone: each covers the other's blind spot (content check for structurally-unremarkable-but-lexically-attack-like text; behavior check for lexically-ambiguous-but-structurally-odd text). The one gap genuinely NOT covered by this design: an attacker evading BOTH checks simultaneously (content mimicking benign lexical patterns AND structure mimicking benign statistical shape) — this is a real, acknowledged limitation of reusing only Branch 1 + Branch 2's existing signals, not something `SessionCorrelator`'s architecture can close without a new, independent signal; it belongs in the paper's Limitations, not as an open bug to fix.
- **Behavior check** — aggregate Branch 2's per-query anomaly scores (`mean`, `fraction_above_threshold`) across the session. Branch 2 runs exactly as trained, per single query, in its original feature distribution; only the already-computed scores are aggregated afterward, so there is no train/inference distribution mismatch at all here (unlike the content check, which ventures outside Branch 1's single-query training length but was shown not to degrade). Validated empirically (Experiment B): benign vs. attack separates with AUC 0.998-1.0 using only these two statistics, no retraining.

Two smaller sub-questions surfaced and were resolved along the way, worth recording since they looked like promising directions that didn't pan out:

- **Same-request multi-field concatenation** (the real "Fragmented SQL Injection" technique — e.g. a login form's `username`+`password` both landing in one `WHERE` clause) was tested directly (Experiment A1: 12 real payloads split via `_fragment_text` into two fields, plus the textbook `admin' --` example) against `branch1_v1`. Every case was already caught looking at **each field alone** (0.87-0.99 attack probability) — the technique doesn't evade this project's trained char n-gram model, so no field-concatenation mechanism was built.
- The 3 fields already built on the (unmerged) `feature/branch3-multi-field` branch (`username`, `product_search`, `category_filter`) are 3 **independent, different-table, different-query** endpoints, designed for a *temporal* recon-across-fields scenario — not the same-request field-concatenation scenario above. That branch was not merged into this redesign; its bug fixes (`BooleanBlindAttacker` targeting, `collate_fn`, `eval_branch3_hard.py` mask/shuffle) remain historically relevant to the superseded GRU but are not needed by `SessionCorrelator`.

**Real, held-out results (`train/calibrate_branch3.py`, thresholds calibrated on the 1,120-session TRAIN split, evaluated on the 280-session TEST split, zero leakage):**

| Configuration | FPR (benign) | DR `boolean_blind` | DR `time_blind` | DR `query_splitting` |
|---|---:|---:|---:|---:|
| Content-only | 0.0 | 1.0 | 1.0 | 1.0 |
| Behavior-only | 0.0 | 1.0 | 1.0 | 1.0 |
| Combined | 0.0 | 1.0 | 1.0 | 1.0 |

**Follow-up (8 Aug): `content_threshold` calibrated separately from Branch 1's single-query threshold.** After the initial merge, a further diagnostic (Experiment D1) measured benign TEST sessions' concatenated content probability topping out at **0.172** — a wide margin below the weak-`boolean_blind`-only concatenation's 0.45-0.46 (see above). `SessionCorrelator.calibrate()` now picks `content_threshold` from the same TRAIN split as the other three thresholds (max `TPR - FPR` search, identical method), instead of reusing Branch 1's single-query `decision_threshold` (0.5) as a placeholder. Calibrated value: **0.338** (this run; depends on the TRAIN split, expected to land in the 0.172-0.45 gap). Effect measured on the same disjoint TEST split: content-only `query_splitting` detection rate rose from 0.971 to **1.0**, FPR unchanged at 0.0 — the content check now independently catches the weak-`boolean_blind` case the behavior check was previously relied on to cover alone (both checks now redundantly cover it; see `TestSessionCorrelatorContentAndBehaviorBothCoverWeakSteps` in `tests/test_branch3_session.py`). This does not change Finding 2's zero-day limitation: re-run against `branch1_no_boolean_blind`, mean attack probability (0.220) still sits below even this lower threshold — a session-level threshold only helps when Branch 1 recognizes the class but the per-step signal is individually weak, not when Branch 1 has never seen the class at all.

**Incidental data bug found while implementing the above:** one `query_splitting` TRAIN session (`cachA_query_splitting_0157`, step 2) has a fragment whose text is literally the string `"null"` — a legitimate WordPress content fragment, not a missing value — which pandas' default `read_csv` silently parses as `NaN` (it's in pandas' default NA-sentinel list). This was latent and harmless as long as no code read `query_canonical` text during calibration; it surfaced as a crash the moment `calibrate()` started needing session text for the new `content_threshold` search. Fixed at every read site of `branch3_sessions_cach_a.csv` (`train/calibrate_branch3.py`, `train/eval_branch3_hard.py`, `tests/test_branch3_session.py`) with `pd.read_csv(..., keep_default_na=False, na_values=[])`.

**⚠️ Read this narrowly, same caveat as §4.1's Cách A data always carried:** these are self-generated sessions (real bisection algorithm against a self-hosted demo DB), not independently-captured attacker traffic (Cách B, still not started). Near-perfect separation here is expected given both branches were built around this exact generation process — it is not evidence of generalization to novel evasive traffic. `query_splitting` sessions' predicted attack-type label comes out as whichever real class (`union_based`/`error_based`) the reconstructed fragments happen to contain, since Branch 1 has no `query_splitting` class of its own — expected, not an error.

**Two implementation bugs found and fixed while wiring this into the live API** (`deploy/routers/branch3.py`, `deploy/registry.py`) — recorded because both would have silently shipped wrong behavior if only the offline eval script had been checked:

1. **Label-schema collision.** The content check's predicted attack type was looked up by indexing Branch 1's numeric class id (0=normal,1=union_based,2=error_based,3=boolean_blind,4=time_blind) into the *session-level* class-name list (0=benign,1=boolean_blind,2=time_blind,3=query_splitting) — same integers, different meaning, so id 3 silently returned "query_splitting" for an actual `boolean_blind` detection. Fixed by using `src.preprocessing.multiclass_tagger.LABEL_NAMES` (Branch 1's own schema) directly; the now-unused session-schema parameter was removed from `SessionCorrelator` rather than left as a trap.
2. **Rounding mismatch at the calibrated threshold.** `per_query_threshold` is calibrated against `branch2_anomaly_score` values already rounded to 6 decimals in the CSV; benign per-query scores cluster on very few distinct values, so the calibrated threshold routinely lands *exactly* on one of them. Live-recomputed (unrounded) scores differ from the rounded CSV values by float64 noise, which flipped "equal to the threshold" into "greater than it" for most of a benign session's steps — a real false positive, caught by testing the live endpoint end-to-end, not by the offline eval alone. Fixed by rounding every Branch-2 score to 6 decimals at the single shared computation point (`src.models.branch3_features.branch2_scores_for_texts`), matching the precision already persisted everywhere else.

Neither bug showed up in `train/calibrate_branch3.py`'s own offline metrics — both only appeared when the live `/branch3/session` endpoint was exercised directly, which is why that end-to-end check is listed as mandatory verification, not optional polish.

**Follow-up (20 Aug): the "zero leakage" claim above (line ~275) was wrong — audited, root-caused, and fixed.** Bách's data-validity audit (`train/audit_branch3_data_validity.py`, `report/metrics/audit_branch3/audit_report.md`) found the TRAIN/TEST split was not actually disjoint for two of the three attack classes: `boolean_blind`/`time_blind` bisection is deterministic given a target user (already noted in §4.1's "first diversity bug" above — that fix used a bigger 100-user pool, but never controlled which split each target landed in), and the split itself was decided by shuffling `session_id` *after* generation, oblivious to which user a session had targeted. Result: **65/70 `boolean_blind` and 67/70 `time_blind` TEST sessions were byte-identical to a TRAIN session.** `benign` (random-username-per-step, not one fixed target) and `query_splitting` (no target user involved) were unaffected — 0/70 either way.

**Fix** (`train/build_session_dataset.py`): partition the 100-user pool into disjoint train-target/test-target subsets (80/20) *before* generating boolean_blind/time_blind sessions, instead of splitting session IDs after the fact — so a target user can never be sampled for both splits. Dataset regenerated (seed 42, same config), re-audited clean: **0/70 byte-identical for every class.** `SessionCorrelator` recalibrated on the fixed data (`train/calibrate_branch3.py`, `train/eval_branch3_hard.py`): **FPR=0.0 / DR=1.0 unchanged** for `boolean_blind`/`time_blind`/`query_splitting` — the memorization concern the audit raised does not hold up empirically; the content check generalizes across unseen targets because Branch 1 recognizes the injection *syntax* (bisection structure), not the specific username/password values, which is exactly the "why content alone is enough" mechanism already documented in §4.1 above. The still-valid, unrelated caveat from the paragraph above this one — self-generated Cách A sessions, not independently-captured attacker traffic (Cách B) — still applies and is unaffected by this fix.

## 6. D6 — Superviz25 integration (26/8)

**Found:** [kaggle.com/datasets/grgorqutel/superviz25-sql-injection-detection-dataset](https://www.kaggle.com/datasets/grgorqutel/superviz25-sql-injection-detection-dataset)
(file mtime 13 Oct 2025, i.e. it existed months before this project's July
survey — not a "too new to find" case; more likely just low-visibility:
obscure account, generic non-"sql injection"-led title). Fills the D6 slot
this file always reserved for real captured attacker traffic (§0/§5) — the
dataset is 3.69M rows of REAL sqlmap runs (verified: `tamper_method` column
values are literal sqlmap tamper-script names — `randomcase`,
`space2comment`, `equaltolike`, ...) against a real DB (OurAirports
`airport`/`regions` schema), not a synthetic template.

**Schema:** `full_query, label(0/1), user_inputs, attack_stage, tamper_method,
attack_status, statement_type, query_template_id, attack_id, attack_technique,
split`. Two things make this source NOT a drop-in load like D1/D3/D4/D7:

1. **The source's own `split` column is unusable for supervised training**:
   `train` = 100% `label=0` (335,306 rows, zero attacks), `test` = everything
   else — a 1-class/anomaly-style split, not a stratified supervised one.
   Ignored entirely; `load_d6_superviz25` (`src/preprocessing/data_sources.py`)
   does its own reservoir sampling + the callers (`build_branch1_dataset.py`/
   `build_branch2_dataset.py`) do their own split.
2. **`attack_technique` values `inline` and `insider` are dropped, not
   loaded, at all**: `inline` (1,389 rows) is a canary/fuzz-probe payload
   (`'"<>` style) that doesn't map to any of Branch 1's 5 classes. `insider`
   (1,089 rows) was hand-inspected and found to be plain session-init SQL
   (`SET NAMES utf8mb4`, `SET AUTOCOMMIT = 0`) mislabeled as an attack — same
   category of problem as SR-BH's mistagged `Normal=1` rows (§3.1), just the
   mirror direction (a false attack label instead of a false normal label).
   The remaining 5 techniques (`union/error/boolean/time/stacked`) map 1:1
   onto Branch 1's existing schema and ARE trusted as ground truth directly —
   **not** re-derived via `multiclass_tagger.tag_query`'s regex signatures,
   unlike every other source. Reason: rows are real sqlmap output for a
   KNOWN technique (ground truth by construction) and several are
   tamper-mangled in ways that can break a hand-written regex (e.g. a
   `multiplespaces`-tampered `SLEEP (5)` failing to match `SLEEP\(`) —
   re-tagging from content would silently corrupt exactly the evasive
   variants this source is valuable for.

**Leakage risk found and handled:** `attack_id` (275 values) groups a whole
sqlmap campaign's rows contiguously (verified: 100% row-contiguous) — e.g.
`boolean-156` is 6,475 rows of one bisection run against one target,
differing only in the comparison bound each step. A plain per-row
stratified split (what every other source uses) would let near-duplicate
successive probe queries from the same campaign land on both sides of
train/test — the same leakage SHAPE as the exact-duplicate leakage the
Branch-1 audit already found and fixed (§3.1, Mảng 2: 949 identical texts
straddling the split), just for near-duplicates instead of exact ones, and
the same shape as the Branch-3 target-user leakage found and fixed 20/8
(§4.2). Fixed via `_group_aware_split` (`train/build_branch1_dataset.py`):
D6's attack rows are split by whole `attack_id` campaign (shuffled, greedy
fill to the target test fraction per label), never mid-campaign; every other
source keeps the original stratified per-row split.

**Zero-shot check BEFORE retraining** (`train/eval_zeroshot_superviz25.py`,
`report/metrics/superviz25_zeroshot_eval.json`, stratified sample, no
retraining) — run first specifically to decide whether retraining was
warranted at all:

| Stratum | n | Branch 1 flag rate | Branch 2 flag rate |
|---|---:|---:|---:|
| benign (plain) | 3000 | 1.10% (FPR) | 69.27% (FPR) |
| benign, contains legitimate `UNION SELECT` | 2000 | 0.00% (FPR) | 94.70% (FPR) |
| union | 1500 | 20.73% (DR) | 88.13% |
| error | 1500 | 25.33% (DR) | 82.27% |
| boolean | 1500 | 65.27% (DR) | 81.00% |
| time | 1500 | 17.07% (DR) | 83.60% |
| stacked | 1500 | 10.53% (DR) | 86.20% |

One hypothesis going in was WRONG and is recorded as such rather than
quietly dropped: legitimate benign `UNION SELECT` queries were expected to
trip Branch 1's `union_based` signal (no such benign example exists in
D1/D3/D7) — measured FPR was 0.00%, not elevated. What WAS a real problem:
**Branch 2's FPR was 69-95%** — the LOF model had never seen benign traffic
this structurally complex (real joins/subqueries/geo functions against the
airport schema, vs. D1/D3/D7's simple parameter lookups), so it flagged most
of it regardless of true label, making its "detection rate" numbers on this
dataset meaningless (it wasn't discriminating anything). Branch 1's
detection rate on `stacked`/`time` (10.5%/17.1%) was also far below the
in-domain ~0.98 F1-macro — real sqlmap tamper-script evasion is measurably
harder than the clean D1/D4/D7 payloads Branch 1 was trained on.

**Retrain (26/8)** — D6 added to both branches (`d6_benign_cap=50000`,
`d6_attack_technique_cap=20000` per class, `configs/config.yaml`); `stacked`
un-excluded (`branch1_supervised.balance.exclude_labels: []`, was `[5]`) now
that ~20k REAL stacked examples exist — the synthetic-only exclusion reason
(§3.3: 100% templated, trivially separable) no longer applies once real data
does, exactly the condition that exclusion said it was waiting on;
`synthetic_stacked.py`'s output is no longer loaded here (still used by
`train/build_mlops_split.py`). Branch 1 test F1-macro (all classes, all
sources) dropped **0.9822 → 0.9180** — expected and reported honestly: the
prior number was measured on an easier, less-evasive attack distribution;
this one includes real tamper-script evasion.

**Held-out D6 check AFTER retraining** (`train/eval_d6_holdout.py`,
`report/metrics/d6_holdout_eval.json` — scores the REAL split="test" rows
`build_branch1_dataset.py`/`build_branch2_dataset.py` already wrote, not a
fresh sample, so this is genuinely held-out, not re-sampled-with-overlap-risk):

| | Before (zero-shot) | After (retrained, held-out) |
|---|---:|---:|
| Branch 2 FPR on D6 benign | 69.3-94.7% | **7.27%** (n=7018) |
| Branch 1 FPR on D6 benign | 1.10% | 6.92% (n=1820) |
| Branch 1 DR — union | 20.7% | **75.79%** |
| Branch 1 DR — error | 25.3% | **99.17%** |
| Branch 1 DR — boolean | 65.3% | **97.07%** |
| Branch 1 DR — time | 17.1% | **93.37%** |
| Branch 1 DR — stacked | 10.5% | **90.31%** |

Branch 2's aggregate eval (`report/metrics/branch2_eval.json`, now over the
D1+D3+D7+D6 pool): LOF AUC=0.9151, DR@matched-FPR5%=0.7766 — essentially
unchanged from the pre-D6 0.929/80.6% (§3.4) despite now covering a much
broader, structurally harder benign distribution, i.e. the fix didn't trade
away prior performance to absorb D6.

Branch 1's FPR on D6 benign rose slightly (1.10% -> 6.92%) alongside the
large detection-rate gains — a real, measured trade-off (more aggressive
against evasive attacks, marginally less specific on this source's benign
edge cases), stated here rather than left implicit.

**Branch 3 — recalibrated, not redesigned** (`train/calibrate_branch3.py`,
re-run against the new `branch1_v1`/`branch2_v1`; Branch 3's own session
dataset, §4.1/§4.2, is unaffected by D6): FPR=0.0, DR=1.0 for
`boolean_blind`/`time_blind`/`query_splitting` (combined), matching the
pre-retrain result — confirms the Session Correlator design (reuses
Branch 1 + Branch 2's live artifacts, no separate weights of its own) holds
up unchanged when the underlying branches are retrained; only its
thresholds needed recalibrating (content_threshold 0.5000 -> 0.5394), which
`calibrate()` already does automatically.

**Not done as part of this integration (deliberately out of scope, RIVF
deadline 30/8):** D6's `attack_id` campaign grouping is real multi-step
session structure at a much larger scale than Cách A's self-generated
sessions (§4.1) — a plausible substitute for Branch 3's still-never-started
Cách B (real sqlmap+Docker traffic, see §5 below), but building that is a
separate, heavier piece of work not attempted here. D1's license-provenance
question (research_proposal.md, "needs verification/replacement") is also
unaffected — D6 was added alongside D1, not as its replacement.

---

## 7. D4 dropped + a real RNG-independence bug found and fixed (27/8)

**Decision: drop D4 (payload-box) from Branch 1.** Only 124 raw payloads (union_based/boolean_blind/time_blind only — 0 error_based, 0 stacked), contributing 16 of 90,000 final training rows — negligible next to D6's per-class volume. Dropping it brings the TOTAL distinct raw sources across the whole system down to exactly 4: D1 (SQLiV3), D3 (CSIC2010, Branch 2 only), D6 (Superviz25), D7 (SR-BH 2020) — Branch 1 uses D1+D6+D7, Branch 2 uses D1+D3+D6+D7. Verified this wasn't just assumed harmless: retrained `tfidf_logreg` with D4 removed and found a **~6-point F1 drop that had nothing to do with D4** (see below) — a real bug caught in the process of checking, not something D4's removal itself caused.

**Bug found: `_undersample()` and `_group_aware_split()` (`train/build_branch1_dataset.py`) shared ONE `random.Random(seed)` instance across a `for label in sorted(...)` loop.** `.sample()`/`.shuffle()`'s number of internal draws depends on the input size, so changing an EARLIER label's pool size (D4 only ever touched union_based/boolean_blind/time_blind) shifted the RNG's state before it reached a LATER label — `stacked` (processed last, label id 5) swung from 83.5% to 54.6% recall purely from this ordering artifact, even though D4 contributed zero stacked rows and stacked's own candidate pool (16,555 rows, 100% from D6) barely changed. Confirmed by reproducing the swing, then fixing it (each label gets its own `random.Random(f"{seed}:{label}")`) and confirming the result is now stable and reproducible across 5+ rebuild attempts. Same class of bug as the hardcoded-`LABEL_ORDER` F1-macro bug already found once (§3.3) — "looks fine until something upstream changes."

**A second, deeper finding surfaced once the RNG bug was fixed: `stacked`'s F1 is genuinely low (0.471) and genuinely sample-dependent, for a real, understood reason — not further noise.** With the fix applied (seed=42, deterministic, reproduced identically 3+ times), `stacked` test split drew from only **8 of 45 available D6 `stacked` campaigns** (a consequence of the campaign-level group-split — §6's leakage fix — combined with `stacked` having comparatively few, size-uneven campaigns). Those 8 happened to be recon-heavy: recon-stage `stacked` rows are correctly classified only **28.1%** of the time vs **100%** for exploit-stage rows (same recon/exploit mechanism as §6), so a small, by-chance campaign sample dominates the aggregate metric. Dominant confusion: **1,552 of 3,212 `stacked` test rows predicted `time_blind`**. This is reported as a measured, mechanistically-understood result — not re-rolled to a more favorable seed, consistent with this project's fixed-seed-throughout convention (never re-randomize to chase a better number).

**Corrected, final Branch 1 numbers (`models/branch1_v1`, seed=42, D4 removed, RNG bug fixed):** F1-macro = **0.8352** (90,000 rows: 71,705 train / 18,295 test). Per-class F1: normal 0.872, union_based 0.982, error_based 0.993, boolean_blind 0.973, time_blind 0.721, stacked 0.471. `error_based`/`union_based`/`boolean_blind` remain robust; `time_blind`/`stacked` carry the recon/campaign-variance problem above. Per-class ROC-AUC stays high across all six classes (0.983-0.999) even where F1 is low — ranking quality (attack vs benign) holds up; the confusion is specifically between two attack sub-types, not attack vs benign.

**Implication for future work:** the right fix for `stacked`'s specific fragility is a LARGER campaign pool per class (more of D6's real campaigns admitted, currently capped at `d6_attack_technique_cap: 20000` per technique in `configs/config.yaml`), not re-seeding. Left for post-RIVF work (full-code deadline 31/12).

**TF-IDF/LogReg retuned (27/8) — the config had never been re-tuned for the harder D6-era data.** `branch1_supervised.tfidf` (`ngram_min:2, ngram_max:4, max_features:50000`) was chosen back when all 4 architectures scored ~0.99 (pre-D6) and was simply carried forward — never re-tuned once D6 made the problem harder. `train/grid_search_branch1_tfidf.py` (16-config curated grid, then 2 follow-up rounds narrowing on the winning direction) found a clear, monotonic trend: **shorter n-grams do better** on this harder data — F1-macro: (2,4)=0.8352 -> (1,4)=0.8499 -> (1,3)=0.8623 -> **(1,2)=0.8941**. Adding `C=10` (up from LogisticRegression's default 1.0) pushed it further to **0.8977**. Tested (1,1) too: it pushes `stacked` recall to 0.82 but trades away `normal`'s F1 (0.82 vs 0.91), a worse overall macro-F1 (0.8715) — so (1,2) is the real optimum, not just "shorter is always better." Adopted as the new production config (`configs/config.yaml`, `train/train_branch1.py`, `train/compare_branch1_architectures.py` all updated to read `C` from config instead of hardcoding LogisticRegression's default).

**Result:** F1-macro **0.8352 -> 0.8977** (+6.25 points). Per-class F1: normal 0.911, union_based 0.986, error_based 0.993, boolean_blind 0.984, time_blind 0.812 (was 0.721), **stacked 0.700 (was 0.471)**. Confusion `stacked`->`time_blind` dropped from 1,552 to 921 of 3,212 test rows — better, though still the dominant remaining error (same recon/campaign-composition mechanism as above, not resolved by this tuning, just made less severe). Re-verified the recon/exploit split specifically (§7's original finding, re-checked against this retrained model rather than left stale): recon-stage `stacked` rows correctly predicted as `stacked` rose **28.1% -> 54.8%**; exploit-stage stayed 100%. Overall D3 detection (any attack class, all 5 mapped techniques combined): exploit 99.9%->100.0%, recon 88.4%->94.0%. `rivf2026_paper.tex` initially still cited the pre-retune 28.1%/88.4% figures after this retrain — caught and fixed during a full re-read requested explicitly ("soát lại") rather than left stale, alongside one direct contradiction (Discussion still said stacked F1 "down to 0.471" after Table II had already been updated to 0.700) and two dangling `Section~\ref{sec:discussion}` cross-references pointing at content that section never actually contained. Bonus: vocabulary shrank from 50,000 to **5,037** terms — the deployed model is now smaller (~0.4MB vs ~4MB) and no slower, not a size/accuracy trade-off. All ROC-AUCs rose too (min, `stacked`, 0.934 -> 0.965). Full production Table~b1arch/b1perclass numbers in `rivf2026_paper.tex` updated to match. `word`-analyzer and longer n-grams (up to (3,6)) were also tested and are worse than the current char_wb (1,2) — a real char-level, short-substring signal, not an artifact of under-search.

**Side effect: re-ran the full 4-architecture comparison with the retuned TF-IDF config (shared by logreg + LightGBM only; DistilBERT/CNN use their own tokenizers, unaffected).** LightGBM's latency dropped **60.1ms -> 3.0ms** (~20x) purely from the smaller vocabulary (5,037 vs 50,000 terms) — the exact reason LightGBM was ruled out for a real-time proxy no longer holds. Final numbers: logreg (chosen) 0.898 / 0.5ms / 0.4MB; LightGBM 0.962 / 3.0ms / 4.5MB; DistilBERT 0.965 / 2.8ms / 256MB; CNN 0.749 / 0.3ms / 152KB. DistilBERT and LightGBM are now within 0.3 points of each other, both at similar latency — LightGBM is the more interesting alternative to logreg going forward (near-DistilBERT accuracy, a fraction of the size/train-time, comparable latency to logreg itself). Production kept as logreg (simplicity, smallest footprint) but this is flagged in the paper as a choice that could reasonably go the other way now.

**Knock-on effect: Session Correlator recalibration + one weakened (not broken) redundancy case.** Recalibrating `SessionCorrelator` against the retrained `branch1_v1` (`train/calibrate_branch3.py`) moved `content_threshold` from ~0.34 (post-D6, pre-D4-fix) to **0.6506** — Table-level results unchanged (FPR=0.0, DR=1.0/1.0/1.0 combined, same as every prior calibration). But `tests/test_branch3_session.py`'s `TestSessionCorrelatorContentAndBehaviorBothCoverWeakSteps` — a regression test whose own docstring says "if this starts failing, the OR'd-checks-resilient claim must be re-verified before citing it" — did start failing, and was re-verified rather than silently patched: for the ONE specific session this test illustrates, per-step attack probabilities rose (0.44-0.47 → 0.52-0.55, the retrained model is slightly more suspicious of these steps) but the threshold rose more, so content-check ALONE no longer independently rescues this particular session (0.541 vs threshold 0.6506) — only the behavior check does now. The paper's actual cited number (content-only DR=1.0 aggregated across all 70 boolean_blind TEST sessions) is unaffected — some other session(s) still clear the threshold — but the REDUNDANCY story for this one illustrative case narrowed from "both checks independently cover it" to "only one does." Test updated to assert the new, real behavior (`test_weak_content_steps_fire_via_behavior_check`), not loosened to hide it.

---

## 5. Remaining work related to this contract (out of Day 1 scope)

- [x] Write `src/preprocessing/canonicalize.py` matching the `query_canonical` + `has_comment_marker` columns above (Day 2).
- [x] Write the rule-based multi-class tagger (Section 3) + manual sanity-check (Day 2, before Day 3 training).
- [x] Extract parameters from D3's `raw_request` (query string/POST body) before canonicalizing — `load_d3()` in `src/preprocessing/data_sources.py` (15 Jul).
- [x] Build `data/processed/branch2_normal.csv` (Section 3.2, 15 Jul).
- [ ] Supplement D4 (payload-box) for rare classes once the real distribution is measured.
- [x] Actually train Isolation Forest for Branch 2 — done 16/7, superseded by LOF 19/08 (§3.4), retrained again 26/8 with D6 (§6).
- [x] Branch 3 Cách A (simulated) session dataset + GRU model — see Section 4.1 (26 Jul).
- [ ] Branch 3 Cách B (real sqlmap + Docker-lab traffic) — still not started as originally scoped (a live Docker lab). D6/Superviz25 (§6) is real sqlmap traffic with real multi-query campaign structure (`attack_id`) and could plausibly substitute, but that integration hasn't been attempted — flagged, not done.
