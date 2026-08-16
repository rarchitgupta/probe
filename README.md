# Probe

Probe is an AI-powered browser QA agent. Give it a website and a plain-English
test goal; it plans a bounded workflow, operates Chromium through Playwright,
verifies the outcome, and records evidence.

The current implementation includes:

- semantic, text-first browser observations instead of screenshot-heavy prompts;
- structured planning and browser actions powered by Pydantic AI and DeepSeek;
- execution limits, origin restrictions, and deterministic assertions;
- screenshots, Playwright traces, diagnostics, token usage, and cost reporting;
- a persistent SQLite task store and a single-worker `asyncio.Queue`.

## Setup

```bash
uv sync
uv run playwright install chromium
cp .env.example .env
```

Add your `DEEPSEEK_API_KEY` to `.env`. Langfuse configuration is optional.

## Run a QA task

```bash
uv run probe run https://www.saucedemo.com/ \
  "Log in and verify that the inventory page loads"
```

Use `--json` for machine-readable output. Use `--queued` to persist the task in
SQLite and execute it through the single background worker:

```bash
uv run probe run https://www.saucedemo.com/ \
  "Log in and verify that the inventory page loads" \
  --queued --json
```

Run artifacts are written to `.runs/<task-id>/`. Queued task state is stored in
`.probe/probe.db` by default.

## Inspect a page

```bash
uv run probe inspect https://example.com
```

This records the page's compact semantic controls, screenshot, console and
network failures, and Playwright trace without invoking an LLM.

## Development

```bash
uv run ruff check src tests
uv run ty check src tests
uv run python -m unittest discover -s tests -v
```

Set `PROBE_DIAGNOSTICS=true` in `.env` to retain successful action diagnostics.
