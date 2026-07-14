FROM python:3.12-slim AS base

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PATH="/app/.venv/bin:$PATH"

FROM base AS prod-deps

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

FROM base AS dev-deps

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --extra dev

FROM prod-deps AS prod

COPY src/ src/
COPY api/ api/
COPY configs/ configs/
COPY main.py .

CMD ["python", "main.py"]

FROM dev-deps AS dev

COPY src/ src/
COPY api/ api/
COPY configs/ configs/
COPY scripts/ scripts/
COPY tests/ tests/
COPY main.py .

CMD ["python", "main.py"]
