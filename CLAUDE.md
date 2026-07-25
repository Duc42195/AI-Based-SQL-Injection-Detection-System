# CLAUDE.md

**Read [`AGENTS.md`](AGENTS.md) at the repo root — that's the full guidance source for this project.** This file only points there to avoid duplication (maintain a single source: `AGENTS.md`).

Quick guardrail reminders: don't commit directly to `main`; don't hardcode config (use `src.utils.load_config`); no `print` (use `get_logger`); don't commit large `data/`·`models/`; don't install heavy libs on your own; `uv run pytest` must be green before committing.
