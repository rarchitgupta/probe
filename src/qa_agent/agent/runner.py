from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack, nullcontext
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Literal

from langfuse import propagate_attributes
from openai import APITimeoutError
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from pydantic_ai import ModelAPIError, RunUsage, UnexpectedModelBehavior, UsageLimits
from pydantic_ai.models import Model
from typesafe_sdk import (
    AsyncTypeSafeClient,
    TypeSafeAPITimeoutError,
    TypeSafeError,
)

from qa_agent.agent.jev import JEV_DECISION_VERSION, JEV_MODEL, JevSelector
from qa_agent.agent.loop import run_plan
from qa_agent.agent.planning import (
    AgentTask,
    ProgressEntry,
    page_state,
    sanitize_summary,
    spec_agent,
    validate_task_inputs,
)
from qa_agent.agent.runtime import ActionDiagnostic, AgentDeps
from qa_agent.artifacts import ArtifactPaths
from qa_agent.browser.session import BrowserSession
from qa_agent.configuration import PROMPT_VERSION, AgentConfiguration
from qa_agent.environments import EnvironmentProfile, resolve_environment
from qa_agent.failures import FailureCategory
from qa_agent.llm import (
    DEEPSEEK_MODEL_NAME,
    DEEPSEEK_PLANNER_SETTINGS,
    DEEPSEEK_SETTINGS,
    MODEL_REQUEST_TIMEOUT_SECONDS,
    deepseek_model,
)
from qa_agent.observability import configure_observability
from qa_agent.policy import ExecutionGuard, ExecutionPolicy, PolicyViolation

logger = logging.getLogger(__name__)

AGENT_USAGE_LIMITS = UsageLimits(
    request_limit=45,
    tool_calls_limit=15,
    total_tokens_limit=100_000,  # Temporary budget for testing longer QA Demo flows.
)
AGENT_EXECUTION_POLICY = ExecutionPolicy(timeout_seconds=150)
ProgressHandler = Callable[[ProgressEntry], Awaitable[None]]
FinalPageHandler = Callable[[Page], Awaitable[None]]


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
    title: str | None = None
    duration_ms: int | None = None
    failure_category: FailureCategory | None = None
    configuration: AgentConfiguration | None = None


async def execute_agent_task(
    task: AgentTask,
    *,
    model: Model | None = None,
    policy: ExecutionPolicy = AGENT_EXECUTION_POLICY,
    usage_limits: UsageLimits = AGENT_USAGE_LIMITS,
    artifact_root: Path = Path(".runs"),
    event_handler: ProgressHandler | None = None,
    final_page_handler: FinalPageHandler | None = None,
    environment: EnvironmentProfile | None = None,
) -> AgentTaskResult:
    keep_diagnostics = os.getenv("PROBE_DIAGNOSTICS", "").lower() in {
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
    title: str | None = None
    evidence: tuple[str, ...] = ()
    diagnostics: tuple[ActionDiagnostic, ...] = ()
    usage: dict[str, object] = {}
    error: str | None = None
    failure_category: FailureCategory | None = None
    deps: AgentDeps | None = None
    run_usage = RunUsage()
    duration_ms: int | None = None
    use_jev = model is None and os.getenv("PROBE_DECISION_MODEL") == "jev"
    configuration = AgentConfiguration(
        model=(
            str(getattr(model, "model_name", type(model).__name__))
            if model
            else DEEPSEEK_MODEL_NAME
        )
        + (f" + {JEV_MODEL}" if use_jev else ""),
        prompt_version=(
            f"{PROMPT_VERSION}+jev{JEV_DECISION_VERSION}" if use_jev else PROMPT_VERSION
        ),
    )
    jev_selector: JevSelector | None = None
    try:
        resolved_environment = resolve_environment(environment, str(task.start_url))
        async with asyncio.timeout(guard.remaining_seconds):
            async with BrowserSession(
                trace_path=artifacts.trace,
                video_path=artifacts.video,
                headers=resolved_environment.headers,
                cookies=resolved_environment.cookies,
                viewport=resolved_environment.viewport,
            ) as browser:
                execution_started = perf_counter()
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
                        secrets=resolved_environment.secrets,
                        sensitive_values=set(resolved_environment.secrets.values()),
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
                                "model": configuration.model,
                                "prompt_version": configuration.prompt_version,
                                "model_config_version": configuration.model_config_version,
                            },
                            tags=["browser-qa"],
                            trace_name="browser-qa-task",
                        )
                        if langfuse
                        else nullcontext()
                    )
                    with trace_context:
                        spec_goal = task.goal
                        if resolved_environment.secrets:
                            aliases = ", ".join(
                                f"{{{{secret:{name}}}}}"
                                for name in resolved_environment.secrets
                            )
                            spec_goal += (
                                "\nAvailable secret placeholders (copy literally when "
                                f"needed): {aliases}"
                            )
                        spec_run = await spec_agent.run(
                            spec_goal,
                            model=selected_model,
                            model_settings=None if model else DEEPSEEK_PLANNER_SETTINGS,
                            usage_limits=usage_limits,
                            usage=run_usage,
                        )
                        title = spec_run.output.title
                        task_inputs = validate_task_inputs(
                            spec_run.output,
                            task.goal,
                            set(resolved_environment.secrets),
                        )
                        deps.task_inputs = task_inputs
                        deps.sensitive_values.update(
                            task_input.value
                            for task_input in task_inputs.values()
                            if task_input.sensitive and task_input.value in task.goal
                        )
                        async with AsyncExitStack() as stack:
                            if use_jev:
                                client = await stack.enter_async_context(
                                    AsyncTypeSafeClient(model=JEV_MODEL, timeout=5.0)
                                )
                                jev_selector = JevSelector(client)
                            status, summary = await run_plan(
                                spec_run.output,
                                deps,
                                model=selected_model,
                                model_settings=None if model else DEEPSEEK_SETTINGS,
                                usage=run_usage,
                                usage_limits=usage_limits,
                                jev_selector=jev_selector,
                                event_handler=event_handler,
                            )
                        failure_category = deps.failure_category

                        evidence = tuple(deps.evidence)
                    diagnostics = tuple(deps.diagnostics)
                finally:
                    duration_ms = round((perf_counter() - execution_started) * 1000)
                    final_url = browser.page.url if browser.page else final_url
                    if final_page_handler and browser.page:
                        await final_page_handler(browser.page)
                    try:
                        await browser.screenshot(artifacts.screenshot)
                    except Exception:
                        pass
    except APITimeoutError:
        failure_category = FailureCategory.MODEL_TIMEOUT
        error = (
            f"Model request timed out after {MODEL_REQUEST_TIMEOUT_SECONDS:g} seconds"
        )
    except ModelAPIError as exc:
        if isinstance(exc.__cause__, APITimeoutError):
            failure_category = FailureCategory.MODEL_TIMEOUT
            error = f"Model request timed out after {MODEL_REQUEST_TIMEOUT_SECONDS:g} seconds"
        else:
            failure_category = FailureCategory.MODEL_ERROR
            error = f"{type(exc).__name__}: {exc}"
    except UnexpectedModelBehavior as exc:
        failure_category = FailureCategory.MODEL_ERROR
        error = f"{type(exc).__name__}: {exc}"
    except TypeSafeAPITimeoutError as exc:
        failure_category = FailureCategory.MODEL_TIMEOUT
        error = f"TypeSafeAPITimeoutError: {exc}"
    except TypeSafeError as exc:
        failure_category = FailureCategory.MODEL_ERROR
        error = f"{type(exc).__name__}: {exc}"
    except TimeoutError:
        failure_category = FailureCategory.EXECUTION_TIMEOUT
        error = f"Execution timed out after {policy.timeout_seconds:g} seconds"
    except PolicyViolation as exc:
        failure_category = FailureCategory.POLICY_VIOLATION
        error = str(exc)
    except PlaywrightError as exc:
        failure_category = FailureCategory.BROWSER_ERROR
        error = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        failure_category = FailureCategory.INFRASTRUCTURE_ERROR
        error = f"{type(exc).__name__}: {exc}"

    if deps:
        diagnostics = tuple(deps.diagnostics)
        if title:
            title = sanitize_summary(title, deps.sensitive_values)
    usage = asdict(run_usage)
    if usage.get("cost") is not None:
        usage["cost"] = str(usage["cost"])
    if jev_selector:
        jev_usage = jev_selector.usage()
        usage["llm"] = {
            "requests": usage["requests"],
            "input_tokens": usage["input_tokens"],
            "cost": usage["cost"],
        }
        usage["jev"] = jev_usage
        usage["requests"] += jev_selector.requests
        usage["input_tokens"] += jev_selector.input_tokens
        usage["cost"] = str(
            Decimal(str(usage["cost"] or 0)) + Decimal(str(jev_usage["cost"]))
        )
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
        title=title,
        duration_ms=duration_ms,
        failure_category=failure_category,
        configuration=configuration,
    )
    artifacts.write_result(asdict(result))
    if langfuse:
        try:
            langfuse.flush()
        except Exception:
            logger.exception("Langfuse flush failed")
    return result
