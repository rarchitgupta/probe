# QA Agent

An AI-powered browser QA agent, starting with a deterministic Playwright
execution kernel.

## Inspect a page

```bash
uv run qa-agent inspect https://example.com
```

Each inspection writes its result, screenshot, and Playwright trace beneath
`.runs/<task-id>/`.
