# GitHub Copilot instructions

**Full guidance lives at [`AGENTS.md`](../AGENTS.md) at the repo root — read that before generating/editing code.**

Summary of required rules (details in AGENTS.md):

- Don't commit directly to `main`; work on a `feature/...` branch, merge via PR. `main` must always be green.
- Don't hardcode paths/thresholds/timeouts — read from `configs/config.yaml` via `src.utils.load_config`.
- Don't use `print` in code; use `from src.utils import get_logger`.
- Don't commit large data/models (`data/`, `models/*.pkl|*.pt` are already `.gitignore`d).
- Don't install heavy libs (torch/transformers/...) or change `pyproject.toml`/`uv.lock` without approval.
- Use `uv` to manage the environment; `uv run pytest` must be green before committing.
- Every public function/class: type hints + docstring.
