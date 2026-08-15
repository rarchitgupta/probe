from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError


@dataclass(frozen=True)
class UrlContainsAssertion:
    assertion: Literal["url_contains"]
    expected: str


@dataclass(frozen=True)
class TitleEqualsAssertion:
    assertion: Literal["title_equals"]
    expected: str


@dataclass(frozen=True)
class TextVisibleAssertion:
    assertion: Literal["text_visible"]
    expected: str
    exact: bool = False


BrowserAssertion = UrlContainsAssertion | TitleEqualsAssertion | TextVisibleAssertion


@dataclass(frozen=True)
class AssertionResult:
    assertion: Literal["url_contains", "title_equals", "text_visible"]
    success: bool
    expected: str
    actual: str | None
    error: str | None = None


async def evaluate_assertion(
    page: Page,
    assertion: BrowserAssertion,
    *,
    timeout_ms: float = 5_000,
) -> AssertionResult:
    try:
        if isinstance(assertion, UrlContainsAssertion):
            await page.wait_for_url(
                re.compile(re.escape(assertion.expected)),
                timeout=timeout_ms,
            )
            actual = page.url
            success = assertion.expected in actual
        elif isinstance(assertion, TitleEqualsAssertion):
            await page.wait_for_function(
                "expected => document.title === expected",
                arg=assertion.expected,
                timeout=timeout_ms,
            )
            actual = await page.title()
            success = actual == assertion.expected
        else:
            locator = page.get_by_text(assertion.expected, exact=assertion.exact).first
            await locator.wait_for(state="visible", timeout=timeout_ms)
            actual = await locator.inner_text()
            success = True
        return AssertionResult(
            assertion=assertion.assertion,
            success=success,
            expected=assertion.expected,
            actual=actual,
            error=None if success else "Observed value did not match",
        )
    except PlaywrightTimeoutError:
        actual = await _current_value(page, assertion)
        return AssertionResult(
            assertion=assertion.assertion,
            success=False,
            expected=assertion.expected,
            actual=actual,
            error=f"Condition was not met within {timeout_ms:g} ms",
        )


async def _current_value(page: Page, assertion: BrowserAssertion) -> str | None:
    if isinstance(assertion, UrlContainsAssertion):
        return page.url
    if isinstance(assertion, TitleEqualsAssertion):
        return await page.title()
    return None
