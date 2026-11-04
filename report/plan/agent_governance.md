# Agent Governance — the slim version

**Status:** proposal (not yet implemented) · **Date:** 2026-08-14 · **Owner:** Duc

Adapted from an enterprise MLOps platform's agent-governance model (SK Vision, `vision-platform`),
which governs AI agents on **three axes**:

| Axis | Question it answers | Their mechanisms |
|---|---|---|
| 1 · Context | What does the agent **know**? | `CLAUDE.md` · `contracts/` (SSOT) · ADR · Team AI Playbook · 6-page LLM-Wiki |
| 2 · Action | What can the agent **do**? | permission allowlist · slash commands · 14 CI gates |
| 3 · External | How does it touch **other systems**? | Jira DC + self-hosted GitLab, glued by branch-name convention + CI auto-transition |

That model is sized for a corporate platform team: a Jira project key, a PAT in CI variables,
customer IP that must never reach an LLM, 38+ numbered ADRs. We are six people, one public
GitHub repo, public datasets, and a paper deadline. **The axes transfer; most of the machinery
does not.**

This document is the trimmed version: **10 mechanisms → 6**, of which 3 already exist here in
some form, 3 are genuinely missing, and 4 are dropped outright.

---

## 1. What we keep, what we drop

### Axis 1 — Context (what the agent knows)

| Their mechanism | Our situation | Verdict |
|---|---|---|
| `CLAUDE.md`, nested per directory | `CLAUDE.md` → `AGENTS.md`, plus `.github/copilot-instructions.md` | **Keep as-is.** One root rule file is right at this size; nested per-directory rule files are overhead we would not maintain. |
| `contracts/` folder as SSOT (OpenAPI, ports, DB schema) | Three de-facto contracts already exist: `deploy/schemas.py`, `configs/config.yaml`, `report/plan/{data,mlops}_contract.md` | **Keep, don't relocate.** Creating a `contracts/` folder would just move files. What is missing is the *rule*: code follows the contract, never the reverse — changing a contract requires a decision entry (§2.1). |
| **ADR** — one numbered file per architecture decision (Status / Context / Decision / Consequences / Rejected alternatives) | Missing. ~10 real decisions have already been made and their rationale is scattered across `data_contract.md` §4.2, `mlops_contract.md`, and commit messages | **Adopt, shrunk to one file.** See §2.1. This is the highest-value gap: the recurring cost here has been re-deriving or re-litigating settled decisions. |
| Team AI Playbook — GREEN/AMBER/RED data classes, ZDR accounts, token discipline | Public datasets (D1–D6), no customer IP, no NDA | **Drop.** Replace with one line in `AGENTS.md`: public data only; no secrets in the repo; `.env` stays ignored. |
| LLM-Wiki — 6 pages (`decisions-log`, `learnings`, `business-domain`, `open-questions`) | The *function* (surviving `/clear` and context compaction) is real, but the pages already have homes | **Drop the structure, keep the function.** `decisions-log` → `decisions.md` (§2.1) · `learnings` → the "learned the hard way" section already in `AGENTS.md` · `business-domain` → `data_contract.md` · `open-questions` → `plan.csv`. Six new files would be five more things to keep in sync. |

### Axis 2 — Action (what the agent can do)

| Their mechanism | Our situation | Verdict |
|---|---|---|
| Allowlist in `.claude/settings.json`; **`git push` blocked** — a human decides | `.claude/settings.local.json` exists but is per-machine (ignored globally, never shared) and has accreted ~60 entries including `Bash(git push *)`, `Bash(git merge *)`, `Bash(gh pr *)` | **Adopt.** See §2.2. Today the repo's own first rule — "don't commit directly to `main`" — has *no* mechanism behind it, and the local allowlist actively permits the opposite. |
| 14 CI gates (`ruff`, `mypy`, `import-linter`, `pytest`, `gitleaks`, branch-name, …) | **Zero CI.** `.github/` contains only `copilot-instructions.md`. "`uv run pytest` must be green before committing" is honour-system | **Adopt, 14 → 3.** See §2.3. Three gates cover the rules we actually wrote down; the other eleven guard problems we don't have. |
| Slash commands `/gates`, `/new-slice`, `/wiki` | One skill: `/check-plan` | **Adopt `/gates` only.** `/new-slice` presupposes a repeating use-case scaffold we don't have; `/wiki` collapses into the single decisions file. Two skills total. |

### Axis 3 — External systems

| Their mechanism | Our situation | Verdict |
|---|---|---|
| Self-hosted GitLab: remote + CI runner + Merge Request | GitHub: same three roles | **Nothing to do** — direct mapping. |
| Jira DC, PAT in CI variables, CI auto-transitions `To Do → In Progress → Release` | `report/plan/plan.csv` is the tracker; branch names already carry the sprint (`…-s1`) | **Radically simplified.** No PAT, no API, no auto-transition. The glue becomes: the PR description names a `TaskID` from `plan.csv`, and **the same PR updates that row's `Status`**. One convention replaces an integration. |
| Two human locks: merge the MR · promote the model | Merge is a written rule with no enforcement; model promotion is *already* human — the gate prepares a verdict, a person promotes | **Keep verbatim.** This is the most transferable idea in the whole document, and §2.2 + §2.3 are exactly what put teeth in lock #1. |

---

## 2. The three things to build

### 2.1 `report/plan/decisions.md` — ADR, one file

Not one file per decision. One table, newest first, ~8 lines per entry:

```markdown
## D-011 · Model version lives in models/registry.json, not config.yaml
Status: Accepted (2026-08-13) · Supersedes: D-007
Context: promote() rewrote branch1_supervised.active_version in a tracked file, so every
  promotion dirtied the working tree and rollback was a regex substitution.
Decision: config declares the baseline; models/registry.json holds runtime state
  (production/staging/archived). Registry wins, config is the fallback.
Consequences: + a fresh clone serves exactly what config says; + clearing the registry is a
  complete rollback. − one more state file to reset in the demo.
Rejected: adopt MLflow Model Registry — see D-010.
```

**The distinction worth stealing:** `AGENTS.md` is *current law* ("do this, never that").
`decisions.md` is the *court record* ("why that law exists"). Never delete an entry — change
your mind by adding a new one that says `Supersedes: D-0xx`.

Seed it with the decisions already made, whose rationale currently only exists in prose:
Branch 3 GRU → SessionCorrelator · content threshold calibrated separately from B1's 0.5 ·
no MLflow · registry-not-config · dedup by `query_canonical` before partitioning ·
`major.minor` with new-class-⇒-major and direct promotion · 50/40/10 partition at ~5% attack ·
golden is frozen · label ids *and* names both normalised in `deploy/registry.py` ·
RIVF framing (B) + CL.

That is ~10 entries, one afternoon, and it retires roughly the same amount of duplicated
rationale from the two contract documents.

### 2.2 `.claude/settings.json` — a shared allowlist, committed

The current file is `settings.local.json`: machine-local, git-ignored, unreviewed, and it
grants `git push *` / `git merge *`. Commit a small shared one instead:

- **allow** `uv run *`, `git status/diff/log/switch/branch`, `ruff`, `pytest`
- **deny** `git push` to `main`, `git merge` into `main`, `git commit` on `main`,
  any `--force`, and `gh pr merge`

Agents prepare work up to the PR; a person merges. `settings.local.json` stays per-machine for
personal conveniences, but it may not be where the safety rules live.

### 2.3 `.github/workflows/ci.yml` — three gates

| Gate | Enforces | Cost |
|---|---|---|
| `pytest` | AGENTS.md rule 7 — "red tests = no commit" (227 tests today) | zero new deps |
| no-`print` | AGENTS.md rule 3 — `src/`, `deploy/` use `get_logger` | zero new deps, one `grep` |
| no data/model blobs | AGENTS.md rule 4 — nothing large committed | zero new deps, one `git diff --stat` check |

Deliberately **not** adopted: `mypy` (no type-check baseline, would flood), `import-linter`
(no layered architecture to protect), `gitleaks` (GitHub push protection already covers this,
and there are no secrets), branch-name enforcement (a review comment is enough at six people),
`ruff` (a new dev dependency, and a first run on an unlinted codebase produces noise nobody
will triage before 30 Aug — revisit in December).

`/gates` runs the same three locally, so the answer to "will CI pass?" is one command.

> **A finding, not a proposal.** The written rule says no `print` in `src/`, `deploy/` **and
> `train/`** — but `train/` has 16 (in `download_hf_dataset.py`, `compare_branch1_architectures.py`,
> `run_zeroday_experiment.py`), all deliberate human-facing result summaries. The rule and the
> code have quietly diverged. Scope the gate to `src/` + `deploy/`, where the rule is true, and
> amend `AGENTS.md` to say `train/` scripts may print result tables. This is precisely the drift
> a gate exists to catch.

---

## 3. Cost and sequencing

| Piece | Effort | Blocks anyone? |
|---|---|---|
| `decisions.md` + 10 seeded entries | ~2 h | No — additive |
| `.claude/settings.json` | ~20 min | No — affects agents, not humans |
| `.github/workflows/ci.yml` (3 gates) | ~1 h | **Yes** — red CI blocks teammates' PRs |
| `/gates` skill | ~20 min | No |
| `AGENTS.md` edits (link the mechanisms, fix the `print` rule, add the `TaskID`-in-PR convention) | ~30 min | No |

One PR, roughly half a day.

**Timing.** The RIVF deadline is 30 Aug — 16 days out — and the sprint is mid-flight. Turning
on CI now means a teammate's in-progress PR can go red on a rule they haven't read yet. Two
sane options: land the whole set now and tell the team in the same message, or land everything
except the workflow and switch CI on after the paper. The gates themselves are cheap either
way; the disruption is entirely in the CI one.

---

## 4. Summary

Six mechanisms, not ten:

1. `AGENTS.md` — current law (exists)
2. Contracts as SSOT — `schemas.py`, `config.yaml`, the two `*_contract.md` (exists; needs the "code follows contract" rule stated)
3. `decisions.md` — why the law says what it says (**new**)
4. Shared allowlist — agents can't push or merge to `main` (**new**)
5. Three CI gates — soft rules become hard (**new**)
6. Two human locks — merge the PR, promote the model (exists; 4 and 5 give lock #1 teeth)

Dropped: the AI Playbook, the six-page wiki, one-file-per-ADR, Jira/PAT automation, nested
`CLAUDE.md`, and eleven of fourteen gates.
