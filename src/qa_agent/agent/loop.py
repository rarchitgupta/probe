"""Budgeted execution of an advisory plan with a bounded browser trajectory."""

from collections import Counter, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from pydantic_ai import RunUsage, UsageLimits
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from qa_agent.agent.planning import (
    ProgressEntry,
    RegionContainsCheck,
    TestSpec,
    build_step_prompt,
    page_state,
    sanitize_summary,
    step_agent,
)
from qa_agent.agent.runtime import AgentDeps, execute_check, execute_instructions
from qa_agent.failures import FailureCategory

MAX_AGENT_ROUNDS = 40


@dataclass(frozen=True)
class Transition:
    before: str
    after: str
    actions: tuple[tuple[str, str | None], ...]


def repetition_feedback(history: deque[Transition], fingerprint: str) -> str | None:
    if not history:
        return None
    actions = [action for item in history for action in item.actions][-20:]
    counts = Counter(action for action in actions if action[0] != "wait")
    if counts:
        (action, target), count = counts.most_common(1)[0]
        if count >= 5:
            severity = (
                "Persistent repetition"
                if count >= 12
                else "Repeated loop"
                if count >= 8
                else "Possible loop"
            )
            return (
                f"{severity}: {action} ({target}) occurred {count} times in the last "
                f"{len(actions)} actions, even if the viewport changed. "
                "Check successful_field_updates and the current page. Continue only if "
                "this makes task progress; otherwise choose another action, complete the "
                "current step if justified, or report the obstacle."
            )
    latest = history[-1]
    if (
        latest.actions
        and sum(
            item.before == item.after == fingerprint and item.actions == latest.actions
            for item in history
        )
        >= 2
    ):
        return (
            "The same actions left the page unchanged repeatedly. Check the page text "
            "and scroll direction; choose another approach or report the obstacle."
        )
    return None


async def run_plan(
    spec: TestSpec,
    deps: AgentDeps,
    *,
    model: Model,
    model_settings: ModelSettings | None,
    usage: RunUsage,
    usage_limits: UsageLimits,
    event_handler: Callable[[ProgressEntry], Awaitable[None]] | None = None,
) -> tuple[Literal["passed", "failed", "blocked"], str]:
    history: deque[Transition] = deque(maxlen=20)
    progress: deque[ProgressEntry] = deque(maxlen=8)
    attempted_checks: set[tuple[int, str]] = set()
    verified_steps: set[int] = set()
    cursor = 0
    feedback: str | None = None
    for _ in range(MAX_AGENT_ROUNDS):
        observation = await deps.browser.observe()
        deps.elements = {item.id: item for item in page_state(observation).elements}
        step = spec.steps[cursor]
        if step.check is not None:
            check_key = (step.id, observation.fingerprint)
            if check_key not in attempted_checks:
                attempted_checks.add(check_key)
                result = await execute_check(deps, step.check)
                entry = ProgressEntry(
                    action=step.check.assertion,
                    target=(
                        ", ".join([step.check.anchor, *step.check.expected])
                        if isinstance(step.check, RegionContainsCheck)
                        else step.check.expected
                    ),
                    success=result.success,
                    effect="asserted" if result.success else None,
                    error=result.error,
                )
                progress.append(entry)
                if event_handler:
                    await event_handler(entry)
                if result.success:
                    verified_steps.add(step.id)
                    cursor += 1
                    deps.successful_field_updates.clear()
                    if cursor == len(spec.steps):
                        required = {
                            item.id for item in spec.steps if item.check is not None
                        }
                        if verified_steps == required:
                            deps.failure_category = None
                            return (
                                "passed",
                                f"Completed all {len(spec.steps)} test steps",
                            )
                        return "failed", "Not all planned checks were verified"
                    continue
                feedback = (
                    f"The pinned {step.check.assertion} check failed: {result.error}. "
                    "Change the observable page state before it is checked again."
                )
            else:
                feedback = (
                    "The pinned check already failed on this unchanged page. Do not retry "
                    "or weaken it; scroll, navigate, wait for a real change, or report failure."
                )
        decision = (
            await step_agent.run(
                build_step_prompt(
                    step,
                    spec.steps[:cursor],
                    list(progress),
                    observation,
                    deps.task_inputs,
                    remaining_steps=spec.steps[cursor + 1 :],
                    feedback=feedback
                    or repetition_feedback(history, observation.fingerprint),
                    sensitive_values=deps.sensitive_values,
                    successful_field_updates=sorted(deps.successful_field_updates),
                ),
                model=model,
                model_settings=model_settings,
                usage=usage,
                usage_limits=usage_limits,
            )
        ).output
        feedback = None
        if decision.failure:
            deps.failure_category = (
                deps.failure_category or FailureCategory.ACTION_FAILURE
            )
            return (
                "blocked" if decision.blocked else "failed",
                sanitize_summary(decision.failure, deps.sensitive_values),
            )
        deps.failure_category = None
        batch, executed = await execute_instructions(deps, decision.actions)
        after = await deps.browser.observe()
        for entry in batch:
            entry.target = (
                sanitize_summary(entry.target, deps.sensitive_values)
                if entry.target
                else None
            )
            entry.error = (
                sanitize_summary(entry.error, deps.sensitive_values)
                if entry.error
                else None
            )
            if entry.effect == "page_may_have_changed":
                entry.effect = (
                    "page_changed"
                    if after.fingerprint != observation.fingerprint
                    else "page_unchanged"
                )
            if event_handler:
                await event_handler(entry)
        progress.extend(batch)
        history.append(
            Transition(
                observation.fingerprint,
                after.fingerprint,
                tuple((entry.action, entry.target) for entry in batch),
            )
        )
        if deps.failure_category == FailureCategory.POLICY_VIOLATION:
            return "failed", "Execution policy prevented further actions"
        if (
            not decision.step_complete
            or any(entry.action == "wait" for entry in batch)
            or executed != len(decision.actions)
            or not all(entry.success for entry in batch)
        ):
            continue
        cursor += 1
        deps.successful_field_updates.clear()
        if cursor == len(spec.steps):
            required = {item.id for item in spec.steps if item.check is not None}
            if verified_steps == required:
                deps.failure_category = None
                return "passed", f"Completed all {len(spec.steps)} test steps"
            return "failed", "Not all planned checks were verified"

    deps.failure_category = deps.failure_category or FailureCategory.ACTION_FAILURE
    return (
        "failed",
        f"Agent exceeded its global limit of {MAX_AGENT_ROUNDS} decision rounds",
    )
