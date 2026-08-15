from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl
from pydantic_ai import Agent, RunContext

from qa_agent.browser import (
    BrowserSession,
    ClickAction,
    FillAction,
    PageObservation,
)
from qa_agent.execution import execute_guarded_action
from qa_agent.policy import ExecutionGuard, PolicyViolation


class AgentTask(BaseModel):
    goal: str = Field(min_length=1)
    start_url: HttpUrl


class AgentOutcome(BaseModel):
    status: Literal["passed", "failed", "blocked"]
    summary: str
    evidence: list[str] = Field(default_factory=list)


class ToolResult(BaseModel):
    success: bool
    error: str | None = None
    observation: PageObservation | None = None


@dataclass
class AgentDeps:
    browser: BrowserSession
    guard: ExecutionGuard


async def click(ctx: RunContext[AgentDeps], element_id: int) -> ToolResult:
    """Click a visible element using its ID from the latest observation."""
    return await _execute(ctx, ClickAction("click", element_id))


async def fill(
    ctx: RunContext[AgentDeps],
    element_id: int,
    value: str,
) -> ToolResult:
    """Replace the value of an editable element from the latest observation."""
    return await _execute(ctx, FillAction("fill", element_id, value))


async def _execute(
    ctx: RunContext[AgentDeps],
    action: ClickAction | FillAction,
) -> ToolResult:
    result = await execute_guarded_action(ctx.deps.browser, ctx.deps.guard, action)
    try:
        ctx.deps.guard.check_url(
            ctx.deps.browser.page.url if ctx.deps.browser.page else ""
        )
    except PolicyViolation:
        return ToolResult(success=False, error=result.error)

    observation = await ctx.deps.browser.observe()
    return ToolResult(
        success=result.success,
        error=result.error,
        observation=observation,
    )


browser_agent = Agent(
    deps_type=AgentDeps,
    output_type=AgentOutcome,
    tools=[click, fill],
    max_concurrency=1,
    instructions=(
        "Complete the browser QA goal using one tool at a time. "
        "Element IDs are temporary; use only IDs from the latest observation."
    ),
)
