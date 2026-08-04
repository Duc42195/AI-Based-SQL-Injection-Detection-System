---
name: check-plan
description: Check real progress against report/plan/plan.csv - what's slipping and what to do about it, personalized to who's asking. Use when the user says "check plan" or asks for a project status/progress check.
---

# Check Plan

Do not just open `report/plan/plan.csv` and summarize it. The goal is to evaluate **real
progress** against the schedule and give a **concrete recommendation** — a status dump without
a "so what" is not a completed check.

## Step 0 — Identify who's asking

Before reporting anything, determine which team member is running this check:

1. Check persistent memory for an established identity for the current user (a `user`-type
   memory recording their name/role in this project).
2. If no identity is recorded, **ask directly**: "Which team member are you?" — offer the
   roster from `AGENTS.md`'s "Project roles" table (currently: Duc, Bach, Diep, Minh,
   Dr. Linh Dinh-Van, Dr. Thai Kim-Dinh). Don't guess or assume based on git config alone —
   confirm with the user.
3. Save the answer to memory (as a `user` memory) so future sessions don't need to ask again.

## Step 1 — Read the plan

Read `report/plan/plan.csv` (schema: `Sprint, TaskID, Task, Owner, Role, Dependency,
Deliverable, Status`).

**Known instability:** this repo's working directory can be switched to a different branch by
concurrent activity (other sessions/teammates working in the same clone). Before trusting the
working tree's copy of `plan.csv`, run `git branch --show-current` — if it isn't `main` (or
isn't the branch you expect), read the file via `git show origin/main:report/plan/plan.csv`
instead of the working tree.

## Step 2 — Evaluate real progress (not just the Status column)

1. What's today's date, and which `Sprint` does that fall in?
2. For tasks in the current or earlier sprints: does `Status` actually match reality? Check the
   real `Deliverable` — does the file exist, does the branch have commits, do tests pass — not
   just the CSV text, since `Status` is manually maintained and can lag reality in either
   direction.
3. Identify what's slipping: tasks whose sprint has started or ended but are still "Not
   started," missing deliverables, dependencies (`Task N` references) blocking a later task.
4. Cross-reference live signals when relevant — e.g. recent commits/branches matching a
   person's assigned task — rather than trusting `Status` alone.

## Step 3 — Personalize the report

- If the identified user (Step 0) is a specific team member (not Duc/PM): lead with **their
  own** tasks and status first, then a brief team-wide overview.
- If the identified user is Duc (PM/SA): give the full team view directly.

## Step 4 — Report

Give a concrete recommendation, not a status dump:
- What's on track.
- What's slipping, and why (if determinable).
- What to do about it — re-scope, reassign, flag to a specific person, or nothing (if it's
  simply too early in the sprint to be behind).

If you find a bug in the plan itself while checking (bad dates, broken dependency references,
etc.), fix it and say so — don't just report around it.
