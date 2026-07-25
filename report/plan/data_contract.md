# Data Contract — Branch 1 (multi-class) & Branch 3 (session)

> Locked in on Day 1 (13 Jul). Defines the target schema for processed data so every team member (and later code) uses the same standard. The figures below are verified against the actually-downloaded data, not estimates.

> 📦 **Processed data is downloaded from here, not in the git repo:** https://huggingface.co/datasets/Jason-42195/VNU-SQLi-Detection (`branch1_train.csv`, `branch2_normal.csv`, `branch2_anomalous_eval.csv`). See the repo root README.md, section "Processed data — where to download".

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

File: `data/processed/branch3_sessions_labeled.csv` (Day 8 deliverable, once D1 is labeled + sqlmap capture is done).

| Column | Type | Description |
|---|---|---|
| `session_id` | str | Original `session_id` (if available) or `f"{client_ip}_{window_start}"` |
| `step_index` | int | Query order within the session (starting at 0) |
| `query_raw` / `query_canonical` | str | Same as the Branch 1 schema |
| `branch1_label` | int (0-5) | Per-query label inherited from Branch 1 (not re-inferred) |
| `branch2_anomaly_score` | float | Continuous anomaly score from Branch 2 (benign-only trained) |
| `timestamp` | float/ISO8601 | Request time — used to compute the session window |
| `session_label` | int (0-3) | **Session-level** label — only set on the session's last row, or repeated on every row (decided at implementation time) |
| `session_source` | str | `A_simulated` (simulation script) or `B_sqlmap_docker` (real traffic) |

**Session definition:** an existing `session_id` (CSIC cookie) OR `(client_ip, idle_gap <= 1800s)` — per `configs/config.yaml: branch3_session.session_idle_gap_seconds`.

**Session label table** (matches `configs/config.yaml: branch3_session.session_classes`):

| Code | Name | Meaning |
|---|---|---|
| `0` | `benign` | Session has no attack intent |
| `1` | `boolean_blind` | Sequence of queries probing true/false (binary search across multiple requests) |
| `2` | `time_blind` | Sequence of queries probing via response delay |
| `3` | `query_splitting` | Attack payload split across multiple consecutive requests |

---

## 5. Remaining work related to this contract (out of Day 1 scope)

- [x] Write `src/preprocessing/canonicalize.py` matching the `query_canonical` + `has_comment_marker` columns above (Day 2).
- [x] Write the rule-based multi-class tagger (Section 3) + manual sanity-check (Day 2, before Day 3 training).
- [x] Extract parameters from D3's `raw_request` (query string/POST body) before canonicalizing — `load_d3()` in `src/preprocessing/data_sources.py` (15 Jul).
- [x] Build `data/processed/branch2_normal.csv` (Section 3.2, 15 Jul).
- [ ] Supplement D4 (payload-box) for rare classes once the real distribution is measured.
- [ ] Actually train Isolation Forest for Branch 2 (not done yet — dataset just built), evaluate FPR/detection rate on `branch2_anomalous_eval.csv`.
- [ ] Branch 3: not started yet — depends on the Docker lab + sqlmap traffic (Day 8-9 per the plan); shouldn't build fake data before real traffic is available.
