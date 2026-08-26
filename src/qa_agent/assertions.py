from __future__ import annotations

import re
from typing import Annotated, Literal

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass

ExpectedText = Annotated[str, Field(min_length=1)]
ASSERTION_CONFIG = ConfigDict(extra="forbid")


@dataclass(frozen=True, config=ASSERTION_CONFIG)
class UrlContainsAssertion:
    assertion: Literal["url_contains"]
    expected: ExpectedText


@dataclass(frozen=True, config=ASSERTION_CONFIG)
class TitleEqualsAssertion:
    assertion: Literal["title_equals"]
    expected: ExpectedText


@dataclass(frozen=True, config=ASSERTION_CONFIG)
class TextVisibleAssertion:
    assertion: Literal["text_visible"]
    expected: ExpectedText
    exact: bool = False


@dataclass(frozen=True, config=ASSERTION_CONFIG)
class CheckedAssertion:
    assertion: Literal["checked"]
    element_id: int
    expected: bool


@dataclass(frozen=True, config=ASSERTION_CONFIG)
class SelectedOptionAssertion:
    assertion: Literal["selected_option"]
    element_id: int
    expected: ExpectedText


@dataclass(frozen=True, config=ASSERTION_CONFIG)
class DialogMessageAssertion:
    assertion: Literal["dialog_message"]
    expected: ExpectedText


PageAssertion = UrlContainsAssertion | TitleEqualsAssertion | TextVisibleAssertion
ElementAssertion = CheckedAssertion | SelectedOptionAssertion
BrowserAssertion = PageAssertion | ElementAssertion | DialogMessageAssertion


@dataclass(frozen=True)
class AssertionResult:
    assertion: Literal[
        "url_contains",
        "title_equals",
        "text_visible",
        "checked",
        "selected_option",
        "dialog_message",
    ]
    success: bool
    expected: str | bool
    actual: str | bool | None
    error: str | None = None


async def evaluate_assertion(
    page: Page,
    assertion: PageAssertion,
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


async def _current_value(page: Page, assertion: PageAssertion) -> str | None:
    if isinstance(assertion, UrlContainsAssertion):
        return page.url
    if isinstance(assertion, TitleEqualsAssertion):
        return await page.title()
    return None
