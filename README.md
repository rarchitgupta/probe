# Probe

Probe is an AI-powered browser QA agent. Give it a website and a plain-English
test goal; it plans a bounded workflow, operates Chromium through Playwright,
verifies the outcome, and records evidence.

The current implementation includes:

- semantic, text-first browser observations instead of screenshot-heavy prompts;
- structured planning and browser actions powered by Pydantic AI and DeepSeek;
- execution limits, origin restrictions, and deterministic assertions;
- screenshots, Playwright traces, diagnostics, token usage, and cost reporting;
- PostgreSQL run state, Temporal orchestration, and a separate browser worker.

## Setup

```bash
uv sync
uv run playwright install chromium
cp .env.example .env
docker compose up -d postgres
uv run alembic upgrade head
```

Add your `DEEPSEEK_API_KEY` to `.env`. Langfuse configuration is optional.

## Docker

Start the complete production-style stack:

```bash
docker compose up --build
```

Probe is available at http://localhost:3000, its API at http://localhost:8000,
the MinIO console at http://localhost:9001, and the local Temporal UI at
http://localhost:8233. Compose runs the database migration and creates the
private artifact bucket before starting the API. Set
`PROBE_CONTAINER_DATABASE_URL` to use a remote PostgreSQL database. The `S3_*`
variables support MinIO, Cloudflare R2, AWS S3, and compatible services.

## Run a QA task

```bash
uv run probe run https://www.saucedemo.com/ \
  "Log in and verify that the inventory page loads"
```

Use `--json` for machine-readable output. The API uses Temporal; `--queued`
retains the lightweight in-process queue for standalone CLI runs:

```bash
uv run probe run https://www.saucedemo.com/ \
  "Log in and verify that the inventory page loads" \
  --queued --json
```

Run artifacts are written to `.runs/<task-id>/`. Local task state is stored in
the PostgreSQL service from `compose.yaml`. Set `PROBE_DATABASE_URL` to an async
SQLAlchemy URL for a remote PostgreSQL instance when deployed.

## Development

```bash
uv run ruff check src tests
uv run ty check src tests
uv run pytest
```

Set `PROBE_DIAGNOSTICS=true` in `.env` to retain successful action diagnostics.
Run the Temporal worker outside Docker with
`uv run python -m qa_agent.temporal_worker`.
