from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from qa_agent.artifacts import ArtifactPaths
from qa_agent.assertions import BrowserAssertion
from qa_agent.browser import (
    BrowserSession,
    ClickAction,
    FillAction,
    InteractiveElement,
    PageObservation,
)
from qa_agent.policy import ExecutionGuard, ExecutionPolicy, PolicyViolation


@dataclass(frozen=True)
class ElementTarget:
    role: str
    name: str


@dataclass(frozen=True)
class ClickStep:
    action: Literal["click"]
    target: ElementTarget


@dataclass(frozen=True)
class FillStep:
    action: Literal["fill"]
    target: ElementTarget
    value: str


ScenarioAction = ClickStep | FillStep
ScenarioStep = ScenarioAction | BrowserAssertion


@dataclass(frozen=True)
class ScenarioTask:
    task_id: str
    start_url: str
    steps: tuple[ScenarioStep, ...]


@dataclass(frozen=True)
class ScenarioStepResult:
    index: int
    operation: str
    success: bool
    target: ElementTarget | None = None
    expected: str | None = None
    actual: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class ScenarioResult:
    task_id: str
    status: Literal["passed", "failed", "error"]
    start_url: str
    http_status: int | None
    steps: tuple[ScenarioStepResult, ...]
    error: str | None
    artifact_directory: str


class TargetResolutionError(Exception):
    pass


def resolve_target(
    observation: PageObservation,
    target: ElementTarget,
) -> InteractiveElement:
    matches = [
        element
        for element in observation.elements
        if element.role == target.role and element.name == target.name
    ]
    if not matches:
        raise TargetResolutionError(
            f'No visible {target.role!r} named {target.name!r}'
        )
    if len(matches) > 1:
        raise TargetResolutionError(
            f'Found {len(matches)} visible {target.role!r} elements named {target.name!r}'
        )
    return matches[0]


async def execute_scenario(
    task: ScenarioTask,
    *,
    artifact_root: Path = Path(".runs"),
    policy: ExecutionPolicy = ExecutionPolicy(),
) -> ScenarioResult:
    artifacts = ArtifactPaths.create(artifact_root, task.task_id)
    step_results: list[ScenarioStepResult] = []
    http_status: int | None = None
    error: str | None = None

    guard = ExecutionGuard(policy.for_start_url(task.start_url))
    try:
        async with asyncio.timeout(guard.remaining_seconds):
            async with BrowserSession(trace_path=artifacts.trace) as session:
                guard.check_url(task.start_url)
                http_status = await session.navigate(task.start_url)
                guard.check_url(session.page.url if session.page else task.start_url)
                for index, step in enumerate(task.steps, start=1):
                    result = await _execute_step(session, guard, index, step)
                    step_results.append(result)
                    if not result.success:
                        break
                try:
                    await session.screenshot(artifacts.screenshot)
                except Exception:
                    pass
    except TimeoutError:
        error = f"Execution timed out after {policy.timeout_seconds:g} seconds"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    if error:
        status: Literal["passed", "failed", "error"] = "error"
    elif step_results and not step_results[-1].success:
        status = "failed"
    else:
        status = "passed"

    result = ScenarioResult(
        task_id=task.task_id,
        status=status,
        start_url=task.start_url,
        http_status=http_status,
        steps=tuple(step_results),
        error=error,
        artifact_directory=str(artifacts.run),
    )
    artifacts.write_result(asdict(result))
    return result


async def _execute_step(
    session: BrowserSession,
    guard: ExecutionGuard,
    index: int,
    step: ScenarioStep,
) -> ScenarioStepResult:
    try:
        guard.check_url(session.page.url if session.page else "")
        if isinstance(step, (ClickStep, FillStep)):
            guard.record_action()
    except PolicyViolation as exc:
        return ScenarioStepResult(
            index=index,
            operation=step.action if isinstance(step, (ClickStep, FillStep)) else "policy",
            success=False,
            target=step.target if isinstance(step, (ClickStep, FillStep)) else None,
            error=str(exc),
        )

    if isinstance(step, (ClickStep, FillStep)):
        try:
            element = resolve_target(await session.observe(), step.target)
        except TargetResolutionError as exc:
            return ScenarioStepResult(
                index=index,
                operation=step.action,
                success=False,
                target=step.target,
                error=str(exc),
            )
        action = (
            ClickAction("click", element.id)
            if isinstance(step, ClickStep)
            else FillAction("fill", element.id, step.value)
        )
        action_result = await session.execute(action)
        error = action_result.error
        if action_result.success:
            try:
                guard.check_url(session.page.url if session.page else "")
            except PolicyViolation as exc:
                error = str(exc)
        return ScenarioStepResult(
            index=index,
            operation=step.action,
            success=action_result.success and error is None,
            target=step.target,
            error=error,
        )

    assertion_result = await session.assert_that(step)
    return ScenarioStepResult(
        index=index,
        operation=assertion_result.assertion,
        success=assertion_result.success,
        expected=assertion_result.expected,
        actual=assertion_result.actual,
        error=assertion_result.error,
    )
