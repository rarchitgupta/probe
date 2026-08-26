# Probe Roadmap

Probe is an AI-powered browser QA agent and a portfolio project for modern
full-stack, AI, backend, and infrastructure engineering. The goal is not to build
every possible browser feature; it is to demonstrate a small number of important
production concepts well.

## Current foundation

- [x] Playwright browser automation with isolated contexts
- [x] Text-first semantic observations and structured Pydantic AI outputs
- [x] Bounded planning, deterministic actions, assertions, and execution policy
- [x] DeepSeek integration with token, request, action, and timeout limits
- [x] Langfuse traces, screenshots, Playwright traces, usage, and cost reporting
- [x] Async SQLAlchemy, SQLite, Alembic, and a single-worker queue
- [x] FastAPI API and Next.js interface with live run events and results
- [x] Pytest unit and browser integration suites in CI
- [x] Versioned evaluation cases with independent final-state grading

## 1. Evaluation harness and public benchmark

Build a repository-native evaluation system before adding more agent behavior.

- [x] Define versioned JSON cases with goals, capability tags, and hidden expected
  browser outcomes.
- [x] Start with a SauceDemo suite covering login, inventory, cart, and checkout.
  Record it as an external dependency and do not make paid public-site runs a hard
  pull-request gate.
- [x] Run the real model and browser path, then grade the final browser state
  independently of the agent's own `passed` claim.
- [x] Repeat trials to measure nondeterminism and classify false passes, false
  failures, timeouts, blocked tasks, and infrastructure errors.
- [x] Report success and false-pass rates, model requests, tokens, cache usage,
  cost, and median/p95 agent latency.
- [x] Generate portable, versioned JSON reports containing the suite, trials,
  aggregate metrics, model/runtime metadata, commit, and artifact paths.
- [x] Compare compatible JSON reports against a baseline and flag quality
  regressions while reporting cost and performance deltas.
- [x] Expose suite execution, JSON output, and baseline comparison through
  `probe eval`.
- [ ] Validate cases in normal CI and run paid smoke benchmarks through a manual
  GitHub Action.

Target command:

```bash
uv run probe eval evals/suites/saucedemo-smoke.json --trials 3 \
  --baseline .eval-reports/baseline.json
```

Completion means Probe has a reproducible public report comparing at least two
model or prompt configurations across a small set of meaningful SauceDemo flows.

## 2. Reliability, safety, and product polish

Use benchmark failures—not speculation—to choose the next browser capabilities.

- [x] Add stable failure categories and prompt/model configuration versioning.
- [x] Add cancellation and reruns for queued, running, and completed tasks.
- [x] Replace frontend polling with Server-Sent Events for one-way live progress.
- [x] Record local WebM replays, persist artifact metadata, and serve range-enabled
  playback while preserving screenshots and Playwright traces.
- [x] Enforce same-origin navigation, action/time bounds, and redact values entered
  during runs from summaries and diagnostics.
- [x] Add reusable test-environment inputs for headers, cookies, viewport, and named
  environment-variable secret references.
- [ ] Later, generate frontend types from FastAPI's OpenAPI schema to prevent API
  drift.
- [ ] Before exposing Probe beyond localhost, block private-network SSRF targets and
  add a small prompt-injection evaluation case.

## 3. Durable queue and production data

Keep the current `asyncio.Queue` until Probe needs multiple processes or restart-safe
execution, then make one deliberate infrastructure transition.

- [ ] Move application data from SQLite to PostgreSQL when concurrent workers need
  it; retain Alembic migrations.
- [ ] Move screenshots, videos, and traces to S3-compatible object storage rather
  than the relational database.
- [ ] Separate the API and browser worker processes.
- [ ] Evaluate Temporal when runs must survive process restarts and need durable
  retries, cancellation, scheduling, and workflow history.
- [ ] If adopted, model a browser run as one bounded Temporal activity or child
  workflow—not one retryable activity per click.
- [ ] Add idempotent submission, worker draining, concurrency limits, backpressure,
  and recovery tests.

Do not add Celery, Redis, Kafka, RabbitMQ, and Temporal together. One durable
execution system is enough.

## 4. Observability and deployment

- [ ] Add structured logs and OpenTelemetry correlation across API, queue, database,
  model, and browser execution while retaining Langfuse for agent traces.
- [ ] Export practical metrics: queue depth, success and false-pass rates, latency,
  browser crashes, token usage, and cost.
- [ ] Containerize the backend, frontend, and Playwright worker with pinned versions.
- [ ] Provide Docker Compose for local production-like deployment.
- [ ] Deploy the API and workers to Kubernetes with health checks, resource limits,
  graceful shutdown, and queue-based autoscaling.
- [ ] Add object-retention cleanup, backup/restore notes, and short operational
  runbooks for model, browser, database, and worker failures.

## 5. Portfolio and open-source release

- [ ] Publish an architecture diagram and a concise explanation of the deterministic
  versus probabilistic boundaries.
- [ ] Add the benchmark methodology, results, costs, limitations, and regression
  examples to the README.
- [ ] Record a short demo showing submission, live events, evidence, replay, and a
  detected regression.
- [ ] Add a threat model and architecture decisions for evals, Temporal, browser
  isolation, and artifact storage.
- [ ] Publish versioned releases and container images with deployment instructions.

## Explicitly deferred

- Multi-agent planner/executor/verifier systems
- Screenshot-first prompting or vision on every step
- Vision fallback until evaluations demonstrate a semantic-DOM failure it solves
- LLM judges for outcomes that deterministic browser checks can verify
- RAG, embeddings, or `pgvector` without a real retrieval feature
- Multi-tenancy, billing, and enterprise RBAC
- A Go microservice added only to advertise Go
- CAPTCHA or bot-protection bypass

## References

- [Anthropic: Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- [Langfuse evaluation concepts](https://langfuse.com/docs/evaluation/core-concepts)
- [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/)
