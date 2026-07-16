---
license: unknown
task_categories:
- text-classification
language:
- en
tags:
- security
- sql-injection
- cybersecurity
- intrusion-detection
- web-security
- anomaly-detection
size_categories:
- 100K<n<1M
pretty_name: VNU SQLi Detection Dataset (Branch 1 multiclass + Branch 2 anomaly)
---

# VNU SQLi Detection Dataset

Data for a 3-branch AI-based SQL Injection detection system, combining 3+ public
sources plus a small synthetic supplement:

- **`nhanh1_train.csv`** — multi-class labels for **Branch 1** (supervised
  classifier). Labels go beyond binary normal/attack: each attack row is
  further tagged with its SQLi sub-technique.
- **`nhanh2_normal.csv`** + **`nhanh2_anomalous_eval.csv`** — benign-only pool
  (+ a held-out anomalous eval set) for **Branch 2** (One-Class anomaly
  detection), using structural/statistical features instead of TF-IDF.

## Labels (Branch 1 only — `nhanh1_train.csv`)

| ID | Name | Meaning |
|---|---|---|
| 0 | `normal` | Benign query / request |
| 1 | `union_based` | `UNION SELECT`-style data exfiltration |
| 2 | `error_based` | Forces a DB error to leak data (`extractvalue`, `updatexml`, ...) |
| 3 | `boolean_blind` | True/false conditional inference (`OR 1=1`, ...) — also the catch-all bucket for attack rows that don't match a more specific rule (see Limitations) |
| 4 | `time_blind` | Response-delay inference (`SLEEP()`, `WAITFOR DELAY`, ...) |
| 5 | `stacked` | A second statement appended via `;` (`; DROP TABLE ...`) — **100% synthetic, see below** |

## Dataset Structure

This repository has 3 files, one for Branch 1 (supervised multiclass) and two
for Branch 2 (anomaly detection, benign-only + a held-out eval set).

### `nhanh1_train.csv` (Branch 1 — supervised multiclass)

**Columns:**
- `id` (int): row index
- `query_raw` (string): original text before canonicalization
- `query_canonical` (string): after URL/hex/`CHAR()` decoding, comment-marker detection, lowercasing
- `has_comment_marker` (0/1): whether a `/* */` or `--` comment was present in the original text
- `label` (int 0-5): class id, see table above
- `label_name` (string): human-readable class name
- `source` (string): originating dataset (see below)
- `split` (`train`/`test`): stratified split, `test_size=0.2`, `random_state=42`

**Size:** 68,159 rows — 54,527 train / 13,632 test.

**Class balance:** `normal`, `union_based`, `boolean_blind`, `time_blind` capped at 15,000 rows each (undersampled from a larger pool); `error_based` kept in full at 7,796 (smaller than the cap); `stacked` kept in full at 363 (fully synthetic, no real-world source has this class — see Limitations).

### `nhanh2_normal.csv` / `nhanh2_anomalous_eval.csv` (Branch 2 — anomaly detection)

Branch 2 trains on 100% benign data (One-Class SVM / Isolation Forest) and does
**not** use TF-IDF — it uses 4 structural/statistical features so it can
generalize to attack syntax it has never seen:

- `length` (int): character length
- `special_char_ratio` (float): fraction of `'";#-=<>()*|%` characters
- `sql_keyword_count` (int): count of SQL keywords (select/union/sleep/...)
- `entropy` (float): Shannon entropy in bits/char

Plus `query_raw`, `query_canonical`, `has_comment_marker`, `source`, and (for
`nhanh2_normal.csv`) `split` (`train`/`test`, `test_size=0.2`, `seed=42`).

- **`nhanh2_normal.csv`**: 91,935 rows (73,548 train / 18,387 test), the full
  benign pool from D1 + D3 (CSIC 2010) + D7 (SR-BH 2020), after the same
  content-based attack-signature filter used for Branch 1's `normal` class,
  deduplicated. **Not capped** — unlike Branch 1, more clean benign data only
  helps Branch 2 estimate the "safe zone" boundary.
- **`nhanh2_anomalous_eval.csv`**: 25,065 rows, D3's anomalous split, held out
  for evaluating false-positive rate / detection rate (not used for training).
  ⚠️ Covers multiple attack types (buffer overflow, XSS, path traversal, etc.),
  not just SQLi — its mean `sql_keyword_count` is actually *lower* than the
  benign pool's, so don't assume it isolates SQLi-detection performance
  specifically; see Limitations.

## Source Datasets

| Source tag | Origin | Notes |
|---|---|---|
| `d1_sqliv3` | SQLiV3 (~30.9K rows, binary-labeled), originally distributed via Kaggle | Accessed via a public GitHub mirror ([nidnogg/sqliv5-dataset](https://github.com/nidnogg/sqliv5-dataset)) |
| `d4_payloadbox` | [payload-box/sql-injection-payload-list](https://github.com/payload-box/sql-injection-payload-list) | Small curated payload list, DBMS-specific files |
| `d7_srbh2020` / `d7_srbh2020_normal` | SR-BH 2020 — a real honeypot capture (12 days, 2020) with multi-label CAPEC attack-type annotations, hosted on [Harvard Dataverse](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/OGOIXX) | See the Dataverse page for the canonical citation. `_normal` suffix = rows the source labeled `Normal=1`, sampled (Nhanh 1) or fully used (Nhanh 2) and content-filtered (see below) |
| `synthetic_stacked` | Generated in this project (template-based, no external source) | The only source of `stacked`-class examples; disclosed as synthetic on purpose |
| `d3_csic2010` | CSIC 2010 HTTP dataset — a widely-used synthetic e-commerce traffic capture, hosted on the [GSI/UdelaR GitLab mirror](https://gitlab.fing.edu.uy/gsi/web-application-attacks-datasets) | Used only in Branch 2 files (`nhanh2_normal.csv` / `nhanh2_anomalous_eval.csv`); URL + POST body extracted from the raw HTTP request blocks |

## How the Labels Were Assigned

1. **Canonicalize** raw text: iteratively URL-decode, decode hex literals (`0x...`) and `CHAR(...)` calls, lowercase, flag (not strip) SQL comments.
2. **Tag** with a fixed-priority rule-based tagger: `stacked > time_blind > error_based > union_based > boolean_blind` (first regex match wins; unmatched attack rows fall back to `boolean_blind`).
3. **Content-filter the `normal` candidate pool**: rows a source dataset called "normal"/benign were still rejected if their canonicalized text matched a known SQLi or OS-command-injection/SSI signature, independent of the source's own label (see Limitations — this filter is not exhaustive).
4. **Balance**: undersample large classes to a fixed per-class cap; keep smaller classes in full.
5. **Split**: stratified train/test, fixed seed.

## Limitations (please read before using for anything beyond an MVP baseline)

- **`stacked` is 100% synthetic.** No example of this technique was found in any of the 3 real-world sources checked (D1, D4, D7) despite trying multiple regex strictness levels. The 363 examples are template-generated (11 prefixes × 11 destructive/privilege-escalation statements × 3 comment terminators) and disclosed as such via `source=synthetic_stacked`.
- **`boolean_blind` is a catch-all bucket** for attack rows that don't match a more specific rule, not a purely precise label. A manual 30-sample review measured **~13% (4/30) of `boolean_blind` rows as clearly mislabeled** by the upstream source (SSRF probes, CRLF/header injection, and even one fully benign form submission that the source dataset had flagged as SQL Injection). Treat this class's precision as noisier than the other 4 attack classes.
- **The content-based `normal` filter is not evasion-proof.** It catches literal attack signatures (SQL keywords, `cat`/`whoami`-style OS commands, Shellshock, SSI injection) but a manually-obfuscated variant (e.g. `cat$jj $jj/etc$jj/passwd` — junk tokens inserted to dodge keyword matching) was found to still slip through during review. Do not assume the `normal` class is adversarially clean.
- **Out-of-scope attack types may still appear in `normal`.** The filter targets SQLi and OS-command/SSI injection specifically; the source honeypot dataset (D7) covers 12 broader attack categories (e.g. XSS, SSRF). Rows matching those other categories were not specifically filtered out and may still be present in the `normal` pool.
- **Multi-label source, single-label output.** D7 (SR-BH 2020) is a multi-label dataset (a request can trigger several attack-category flags at once); this dataset was built by filtering on a single flag (`SQL Injection==1` for attacks, `Normal==1` for the benign candidate pool) and did not otherwise deduplicate against other simultaneously-set flags (a lightweight cross-check found ~0.9% overlap, mostly co-occurring with a "Scanning for Vulnerable Software" flag).

## How to Use

This repo has 3 CSVs with different schemas (Branch 1 vs Branch 2) and no
loading script, so load each file explicitly rather than `load_dataset(repo_id)`
directly (which would try to treat all CSVs as one dataset):

```python
from datasets import load_dataset

nhanh1 = load_dataset("Jason-42195/VNU-SQLi-Detection", data_files="nhanh1_train.csv")["train"]
print(nhanh1[0])
# {'id': 0, 'query_raw': "...", 'query_canonical': "...",
#  'has_comment_marker': 0, 'label': 3, 'label_name': 'boolean_blind',
#  'source': 'd7_srbh2020', 'split': 'train'}

nhanh2_normal = load_dataset("Jason-42195/VNU-SQLi-Detection", data_files="nhanh2_normal.csv")["train"]
nhanh2_eval = load_dataset("Jason-42195/VNU-SQLi-Detection", data_files="nhanh2_anomalous_eval.csv")["train"]
```

Or with pandas, filtering the `split` column yourself:

```python
import pandas as pd

df = pd.read_csv("nhanh1_train.csv")  # or nhanh2_normal.csv
train_df = df[df["split"] == "train"]
test_df = df[df["split"] == "test"]
```

**Branch 1 metric:** F1-macro (not accuracy) — the original per-source class
sizes were extremely imbalanced before undersampling, and `stacked` remains a
tiny synthetic minority class even after balancing.
**Branch 2 metric:** false-positive rate on `nhanh2_normal.csv`'s test split +
detection rate on `nhanh2_anomalous_eval.csv` (keep in mind the eval set spans
multiple attack types, not just SQLi — see note above).

## License

**Mixed — verified per source:**
- **D4 (payload-box): MIT**, confirmed directly on the [source repository](https://github.com/payload-box/sql-injection-payload-list).
- **D7 (SR-BH 2020): CC0 1.0** (public domain dedication), confirmed directly on the [Harvard Dataverse record](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/OGOIXX).
- **D1 (SQLiV3): unclear.** The original Kaggle listing has no license attached (empty license metadata). It was accessed here via a third-party GitHub mirror ([nidnogg/sqliv5-dataset](https://github.com/nidnogg/sqliv5-dataset)) that applies its own MIT license to its repository — that MIT grant covers the mirror's own repo contents, not necessarily the original author's rights over the underlying data, since the mirror maintainer is not the original creator. Treat D1-derived rows as **provenance-unclear** until the original author's terms are confirmed.
- Synthetic rows: generated for this project, no external license constraint.

Given D1 is one of several sources merged into this dataset (not isolated to its own file), the dataset as a whole should be treated as **provenance-unclear** rather than cleanly MIT/CC0, until D1's status is resolved.

## Citation

If you use this dataset, please also cite the original upstream sources listed
above (SQLiV3, payload-box, SR-BH 2020) in addition to this derived release.
