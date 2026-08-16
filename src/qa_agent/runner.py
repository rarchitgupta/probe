from __future__ import annotations

import asyncio
import logging
import os
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from langfuse import propagate_attributes
from openai import APITimeoutError
from pydantic_ai import ModelAPIError, RunUsage, UsageLimits
from pydantic_ai.models import Model

from qa_agent.agent import (
    ActionDiagnostic,
    AgentDeps,
    AgentTask,
    ProgressEntry,
    build_step_prompt,
    execute_instructions,
    page_state,
    sanitize_summary,
    spec_agent,
    step_agent,
)
from qa_agent.artifacts import ArtifactPaths
from qa_agent.browser import BrowserSession, InteractiveElement
from qa_agent.llm import (
    DEEPSEEK_SETTINGS,
    MODEL_REQUEST_TIMEOUT_SECONDS,
    deepseek_model,
)
from qa_agent.observability import configure_observability
from qa_agent.policy import ExecutionGuard, ExecutionPolicy

logger = logging.getLogger(__name__)

AGENT_USAGE_LIMITS = UsageLimits(
    request_limit=20,
    tool_calls_limit=15,
    total_tokens_limit=30_000,
)
AGENT_EXECUTION_POLICY = ExecutionPolicy(timeout_seconds=150)
MAX_STEP_ROUNDS = 6


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
    diagnostics: tuple[ActionDiagnostic, ...]
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
    policy: ExecutionPolicy = AGENT_EXECUTION_POLICY,
    usage_limits: UsageLimits = AGENT_USAGE_LIMITS,
    artifact_root: Path = Path(".runs"),
) -> AgentTaskResult:
    load_dotenv()
    keep_diagnostics = os.getenv("QA_AGENT_DIAGNOSTICS", "").lower() in {
        "1",
        "true",
        "yes",
    }
    langfuse = configure_observability() if model is None else None
    artifacts = ArtifactPaths.create(artifact_root, task.task_id)
    guard = ExecutionGuard(policy.for_start_url(str(task.start_url)))
    status: Literal["passed", "failed", "blocked", "error"] = "error"
    final_url: str | None = None
    http_status: int | None = None
    summary: str | None = None
    evidence: tuple[str, ...] = ()
    diagnostics: tuple[ActionDiagnostic, ...] = ()
    usage: dict[str, object] = {}
    error: str | None = None
    deps: AgentDeps | None = None
    run_usage = RunUsage()

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
                    initial_state = page_state(observation)
                    deps = AgentDeps(
                        browser,
                        guard,
                        elements={
                            element.id: element for element in initial_state.elements
                        },
                    )
                    selected_model = model or deepseek_model()
                    trace_context = (
                        propagate_attributes(
                            session_id=task.task_id,
                            metadata={
                                "task_id": task.task_id,
                                "target_host": task.start_url.host,
                            },
                            tags=["browser-qa"],
                            trace_name="browser-qa-task",
                        )
                        if langfuse
                        else nullcontext()
                    )
                    with trace_context:
                        spec_run = await spec_agent.run(
                            task.goal,
                            model=selected_model,
                            model_settings=None if model else DEEPSEEK_SETTINGS,
                            usage_limits=usage_limits,
                            usage=run_usage,
                        )
                        completed_steps = []
                        for step in spec_run.output.steps:
                            progress: list[ProgressEntry] = []
                            evidence_before = len(deps.evidence)
                            for _ in range(MAX_STEP_ROUNDS):
                                observation = await browser.observe()
                                state = page_state(observation)
                                deps.elements = {
                                    element.id: element for element in state.elements
                                }
                                decision_run = await step_agent.run(
                                    build_step_prompt(
                                        step,
                                        completed_steps,
                                        progress,
                                        observation,
                                    ),
                                    model=selected_model,
                                    model_settings=None if model else DEEPSEEK_SETTINGS,
                                    usage_limits=usage_limits,
                                    usage=run_usage,
                                )
                                decision = decision_run.output
                                if decision.failure:
                                    status = "blocked" if decision.blocked else "failed"
                                    summary = sanitize_summary(
                                        decision.failure, deps.sensitive_values
                                    )
                                    break

                                batch_progress, executed = await execute_instructions(
                                    deps, decision.actions
                                )
                                progress.extend(batch_progress)
                                batch_succeeded = all(
                                    entry.success for entry in batch_progress
                                )
                                batch_finished = executed == len(decision.actions)
                                assertion_proved = (
                                    step.kind != "assertion"
                                    or len(deps.evidence) > evidence_before
                                )
                                action_proved = step.kind != "action" or any(
                                    entry.success for entry in progress
                                )
                                assertion_batch_completed = (
                                    step.kind == "assertion"
                                    and bool(batch_progress)
                                    and batch_finished
                                    and batch_succeeded
                                    and all(
                                        entry.effect == "asserted"
                                        for entry in batch_progress
                                    )
                                )
                                if (
                                    (
                                        decision.step_complete
                                        or assertion_batch_completed
                                    )
                                    and batch_succeeded
                                    and batch_finished
                                    and assertion_proved
                                    and action_proved
                                ):
                                    completed_steps.append(step)
                                    break
                                if decision.step_complete and not assertion_proved:
                                    progress.append(
                                        ProgressEntry(
                                            action="assertion_required",
                                            success=False,
                                            error="Run a successful assertion for this step",
                                        )
                                    )
                            else:
                                status = "failed"
                                summary = f"Step {step.id} exceeded its execution limit"

                            if status in {"failed", "blocked"}:
                                break
                        else:
                            status = "passed"
                            summary = f"Completed all {len(completed_steps)} test steps"

                        evidence = tuple(deps.evidence)
                    diagnostics = tuple(deps.diagnostics)
                finally:
                    final_url = browser.page.url if browser.page else final_url
                    try:
                        await browser.screenshot(artifacts.screenshot)
                    except Exception:
                        pass
    except APITimeoutError:
        error = (
            f"Model request timed out after {MODEL_REQUEST_TIMEOUT_SECONDS:g} seconds"
        )
    except ModelAPIError as exc:
        error = (
            f"Model request timed out after {MODEL_REQUEST_TIMEOUT_SECONDS:g} seconds"
            if isinstance(exc.__cause__, APITimeoutError)
            else f"{type(exc).__name__}: {exc}"
        )
    except TimeoutError:
        error = f"Execution timed out after {policy.timeout_seconds:g} seconds"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    if deps:
        diagnostics = tuple(deps.diagnostics)
    usage = asdict(run_usage)
    if usage.get("cost") is not None:
        usage["cost"] = str(usage["cost"])
    if status == "passed" and not keep_diagnostics:
        diagnostics = ()

    result = AgentTaskResult(
        task_id=task.task_id,
        status=status,
        start_url=str(task.start_url),
        final_url=final_url,
        http_status=http_status,
        summary=summary,
        evidence=evidence,
        diagnostics=diagnostics,
        usage=usage,
        error=error,
        artifact_directory=str(artifacts.run),
    )
    artifacts.write_result(asdict(result))
    if langfuse:
        try:
            langfuse.flush()
        except Exception:
            logger.exception("Langfuse flush failed")
    return result
