# QA Agent

An AI-powered browser QA agent, starting with a deterministic Playwright
execution kernel.

## Run a QA task

```bash
uv run qa-agent run https://www.saucedemo.com/ \
  "Log in and verify that the inventory page loads"
```

Add `--json` for machine-readable output. Each run writes its result,
screenshot, and Playwright trace beneath `.runs/<task-id>/`.

## Inspect a page

```bash
uv run qa-agent inspect https://example.com
```

Each inspection writes its result, screenshot, and Playwright trace beneath
`.runs/<task-id>/`.
