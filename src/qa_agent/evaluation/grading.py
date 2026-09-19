from __future__ import annotations

from dataclasses import dataclass

from playwright.async_api import Page

from qa_agent.agent.assertions import AssertionResult, PageAssertion, evaluate_assertion


@dataclass(frozen=True)
class OutcomeGrade:
    results: tuple[AssertionResult, ...]

    @property
    def passed(self) -> bool:
        return bool(self.results) and all(result.success for result in self.results)


async def grade_page(
    page: Page,
    checks: tuple[PageAssertion, ...],
    *,
    timeout_ms: float = 5_000,
) -> OutcomeGrade:
    results = []
    for check in checks:
        results.append(await evaluate_assertion(page, check, timeout_ms=timeout_ms))
    return OutcomeGrade(tuple(results))
