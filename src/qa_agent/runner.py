from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic_ai import UsageLimits
from pydantic_ai.models import Model

from qa_agent.agent import AgentDeps, AgentTask, browser_agent, build_agent_prompt
from qa_agent.artifacts import ArtifactPaths
from qa_agent.browser import BrowserSession, InteractiveElement
from qa_agent.llm import DEEPSEEK_SETTINGS, deepseek_model
from qa_agent.policy import ExecutionGuard, ExecutionPolicy

AGENT_USAGE_LIMITS = UsageLimits(
    request_limit=20,
    tool_calls_limit=15,
    total_tokens_limit=30_000,
)


@dataclass(frozen=True)
class InspectionTask:
    task_id: str
    url: str


@dataclass(frozen=True)
class InspectionResult:
    task_id: str
    status: Literal["completed", "error"]
    started_at: str
    finished_at: str
    requested_url: str
    final_url: str | None
    title: str | None
    http_status: int | None
    elements: tuple[InteractiveElement, ...]
    console_errors: tuple[str, ...]
    failed_requests: tuple[str, ...]
    error: str | None
    artifact_directory: str


@dataclass(frozen=True)
class AgentTaskResult:
    task_id: str
    status: Literal["passed", "failed", "blocked", "error"]
    start_url: str
    final_url: str | None
    http_status: int | None
    summary: str | None
    evidence: tuple[str, ...]
    usage: dict[str, object]
    error: str | None
    artifact_directory: str


async def execute_inspection(
    task: InspectionTask,
    *,
    artifact_root: Path = Path(".runs"),
) -> InspectionResult:
    started_at = datetime.now(UTC).isoformat()
    artifacts = ArtifactPaths.create(artifact_root, task.task_id)
    final_url: str | None = None
    title: str | None = None
    http_status: int | None = None
    elements: tuple[InteractiveElement, ...] = ()
    error: str | None = None

    async with BrowserSession(trace_path=artifacts.trace) as browser:
        try:
            http_status = await browser.navigate(task.url)
            observation = await browser.observe()
            final_url = observation.url
            title = observation.title
            elements = observation.elements
        except Exception as exc:
            final_url = browser.page.url if browser.page else None
            error = f"{type(exc).__name__}: {exc}"
        try:
            await browser.screenshot(artifacts.screenshot)
        except Exception:
            pass

    result = InspectionResult(
        task_id=task.task_id,
        status="error" if error else "completed",
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        requested_url=task.url,
        final_url=final_url,
        title=title,
        http_status=http_status,
        elements=elements,
        console_errors=tuple(browser.console_errors),
        failed_requests=tuple(browser.failed_requests),
        error=error,
        artifact_directory=str(artifacts.run),
    )
    artifacts.write_result(asdict(result))
    return result


async def execute_agent_task(
    task: AgentTask,
    *,
    model: Model | None = None,
    policy: ExecutionPolicy = ExecutionPolicy(),
    usage_limits: UsageLimits = AGENT_USAGE_LIMITS,
    artifact_root: Path = Path(".runs"),
) -> AgentTaskResult:
    artifacts = ArtifactPaths.create(artifact_root, task.task_id)
    guard = ExecutionGuard(policy.for_start_url(str(task.start_url)))
    status: Literal["passed", "failed", "blocked", "error"] = "error"
    final_url: str | None = None
    http_status: int | None = None
    summary: str | None = None
    evidence: tuple[str, ...] = ()
    usage: dict[str, object] = {}
    error: str | None = None

    try:
        async with asyncio.timeout(guard.remaining_seconds):
            async with BrowserSession(trace_path=artifacts.trace) as browser:
                try:
                    start_url = str(task.start_url)
                    guard.check_url(start_url)
                    http_status = await browser.navigate(start_url)
                    final_url = browser.page.url if browser.page else None
                    guard.check_url(final_url or "")
                    observation = await browser.observe()
                    deps = AgentDeps(browser, guard)
                    selected_model = model or deepseek_model()
                    run = await browser_agent.run(
                        build_agent_prompt(task, observation),
                        deps=deps,
                        model=selected_model,
                        model_settings=None if model else DEEPSEEK_SETTINGS,
                        usage_limits=usage_limits,
                    )
                    status = run.output.status
                    summary = run.output.summary
                    evidence = tuple(run.output.evidence)
                    usage = asdict(run.usage)
                    if usage.get("cost") is not None:
                        usage["cost"] = str(usage["cost"])
                finally:
                    final_url = browser.page.url if browser.page else final_url
                    try:
                        await browser.screenshot(artifacts.screenshot)
                    except Exception:
                        pass
    except TimeoutError:
        error = f"Execution timed out after {policy.timeout_seconds:g} seconds"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    result = AgentTaskResult(
        task_id=task.task_id,
        status=status,
        start_url=str(task.start_url),
        final_url=final_url,
        http_status=http_status,
        summary=summary,
        evidence=evidence,
        usage=usage,
        error=error,
        artifact_directory=str(artifacts.run),
    )
    artifacts.write_result(asdict(result))
    return result
