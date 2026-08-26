from __future__ import annotations

from qa_agent.browser import ActionResult, BrowserAction, BrowserSession
from qa_agent.failures import FailureCategory
from qa_agent.policy import ExecutionGuard, PolicyViolation


async def execute_guarded_action(
    session: BrowserSession,
    guard: ExecutionGuard,
    action: BrowserAction,
) -> ActionResult:
    try:
        guard.check_url(session.page.url if session.page else "")
        guard.record_action()
    except PolicyViolation as exc:
        return ActionResult(
            action.action,
            action.element_id,
            False,
            str(exc),
            FailureCategory.POLICY_VIOLATION,
        )

    result = await session.execute(action)
    if not result.success:
        return result

    try:
        guard.check_url(session.page.url if session.page else "")
    except PolicyViolation as exc:
        return ActionResult(
            action.action,
            action.element_id,
            False,
            str(exc),
            FailureCategory.POLICY_VIOLATION,
        )
    return result
