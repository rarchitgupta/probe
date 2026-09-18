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
class RegionContainsAssertion:
    assertion: Literal["region_contains"]
    anchor: ExpectedText
    expected: tuple[ExpectedText, ...]


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


PageAssertion = (
    UrlContainsAssertion
    | TitleEqualsAssertion
    | TextVisibleAssertion
    | RegionContainsAssertion
)
ElementAssertion = CheckedAssertion | SelectedOptionAssertion
BrowserAssertion = PageAssertion | ElementAssertion | DialogMessageAssertion


@dataclass(frozen=True)
class AssertionResult:
    assertion: Literal[
        "url_contains",
        "title_equals",
        "text_visible",
        "region_contains",
        "checked",
        "selected_option",
        "dialog_message",
    ]
    success: bool
    expected: str | bool | tuple[str, ...]
    actual: str | bool | None
    error: str | None = None


async def evaluate_assertion(
    page: Page,
    assertion: PageAssertion,
    *,
    timeout_ms: float = 5_000,
) -> AssertionResult:
    expected: str | tuple[str, ...] = (
        (assertion.anchor, *assertion.expected)
        if isinstance(assertion, RegionContainsAssertion)
        else assertion.expected
    )
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
        elif isinstance(assertion, TextVisibleAssertion):
            locator = page.get_by_text(assertion.expected, exact=assertion.exact).first
            await locator.wait_for(state="visible", timeout=timeout_ms)
            actual = await locator.inner_text()
            success = True
        else:
            actual = await page.locator("body *").evaluate_all(
                r"""
                (elements, requirement) => {
                    const normalize = value => (value || '').replace(/\s+/g, ' ').trim();
                    const expected = [requirement.anchor, ...requirement.expected];
                    const candidates = elements
                        .map(element => ({element, text: normalize(element.innerText)}))
                        .filter(({element, text}) => {
                            const style = getComputedStyle(element);
                            return element.getClientRects().length > 0
                                && style.visibility !== 'hidden'
                                && style.display !== 'none'
                                && expected.every(value => text.includes(value));
                        })
                        .sort((left, right) => left.text.length - right.text.length);
                    const match = candidates[0];
                    if (!match) return null;
                    match.element.scrollIntoView({block: 'center', inline: 'nearest'});
                    return match.text;
                }
                """,
                {"anchor": assertion.anchor, "expected": assertion.expected},
            )
            success = actual is not None
            if not success:
                raise PlaywrightTimeoutError("No matching visible region")
        return AssertionResult(
            assertion=assertion.assertion,
            success=success,
            expected=expected,
            actual=actual,
            error=None if success else "Observed value did not match",
        )
    except PlaywrightTimeoutError:
        actual = await _current_value(page, assertion)
        return AssertionResult(
            assertion=assertion.assertion,
            success=False,
            expected=expected,
            actual=actual,
            error=f"Condition was not met within {timeout_ms:g} ms",
        )


async def _current_value(page: Page, assertion: PageAssertion) -> str | None:
    if isinstance(assertion, UrlContainsAssertion):
        return page.url
    if isinstance(assertion, TitleEqualsAssertion):
        return await page.title()
    return None
