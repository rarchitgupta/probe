FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY migrations ./migrations
COPY evals ./evals
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable && \
    mkdir -p .runs .eval-runs .eval-reports && \
    chown -R pwuser:pwuser /app

USER pwuser

EXPOSE 8000

CMD ["uvicorn", "qa_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
