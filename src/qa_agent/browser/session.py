from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from secrets import token_hex
from types import TracebackType
from typing import Any, Literal, cast

from playwright.async_api import (
    Browser,
    BrowserContext,
    ConsoleMessage,
    Dialog,
    Locator,
    Page,
    Playwright,
    Request,
    ViewportSize,
    async_playwright,
)

from qa_agent.agent.assertions import AssertionResult, PageAssertion, evaluate_assertion
from qa_agent.browser.observation import (
    ELEMENT_REFERENCE_ATTRIBUTE,
    INTERACTIVE_SELECTOR,
    MAX_INTERACTIVE_ELEMENTS,
    OBSERVE_INTERACTIVE_ELEMENTS,
    InteractiveElement,
    PageObservation,
)
from qa_agent.failures import FailureCategory

MAX_RECORDED_ERRORS = 100
ACTION_TIMEOUT_MS = 3_000


@dataclass(frozen=True)
class ClickAction:
    action: Literal["click"]
    element_id: int


@dataclass(frozen=True)
class FillAction:
    action: Literal["fill"]
    element_id: int
    value: str


@dataclass(frozen=True)
class SetCheckedAction:
    action: Literal["set_checked"]
    element_id: int
    checked: bool


@dataclass(frozen=True)
class SelectOptionAction:
    action: Literal["select_option"]
    element_id: int
    label: str


@dataclass(frozen=True)
class ScrollAction:
    action: Literal["scroll"]
    direction: Literal["up", "down"]
    element_id: None = None


BrowserAction = (
    ClickAction | FillAction | SetCheckedAction | SelectOptionAction | ScrollAction
)


@dataclass(frozen=True)
class ActionResult:
    action: Literal["click", "fill", "set_checked", "select_option", "scroll"]
    element_id: int | None
    success: bool
    error: str | None = None
    failure_category: FailureCategory | None = None


class BrowserSession:
    """One isolated browser context, reusable for a complete QA task."""

    def __init__(
        self,
        *,
        trace_path: Path,
        video_path: Path | None = None,
        headers: dict[str, str] | None = None,
        cookies: list[dict[str, Any]] | None = None,
        viewport: dict[str, int] | None = None,
    ) -> None:
        self.trace_path = trace_path
        self.video_path = video_path
        self.headers = headers or {}
        self.cookies = cookies or []
        self.viewport = viewport
        self.console_errors: list[str] = []
        self.failed_requests: list[str] = []
        self.dialog_messages: list[str] = []
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None
        self._element_refs: dict[int, Locator] = {}

    async def __aenter__(self) -> BrowserSession:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch()
        self._context = await self._browser.new_context(
            record_video_dir=self.video_path.parent if self.video_path else None,
            record_video_size={"width": 800, "height": 450}
            if self.video_path
            else None,
            extra_http_headers=self.headers or None,
            viewport=cast(ViewportSize | None, self.viewport),
        )
        if self.cookies:
            await self._context.add_cookies(cast(Any, self.cookies))
        await self._context.tracing.start(screenshots=True, snapshots=True)
        self.page = await self._context.new_page()
        self.page.on("console", self._record_console_error)
        self.page.on("requestfailed", self._record_failed_request)
        self.page.on("dialog", self._handle_dialog)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._element_refs.clear()
        video = self.page.video if self.page else None
        if self._context:
            await self._context.tracing.stop(path=self.trace_path)
            await self._context.close()
        if video and self.video_path:
            recorded_path = Path(await video.path())
            recorded_path.replace(self.video_path)
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def navigate(self, url: str) -> int | None:
        if not self.page:
            raise RuntimeError("BrowserSession must be entered before use")
        response = await self.page.goto(url, wait_until="domcontentloaded")
        return response.status if response else None

    async def observe(self) -> PageObservation:
        if not self.page:
            raise RuntimeError("BrowserSession must be entered before use")
        await self.page.evaluate(
            "() => new Promise(resolve => "
            "requestAnimationFrame(() => requestAnimationFrame(resolve)))"
        )
        self._element_refs.clear()
        candidates = self.page.locator(INTERACTIVE_SELECTOR)
        raw_observation = await candidates.evaluate_all(
            OBSERVE_INTERACTIVE_ELEMENTS,
            {
                "limit": MAX_INTERACTIVE_ELEMENTS,
                "referencePrefix": token_hex(8),
                "referenceAttribute": ELEMENT_REFERENCE_ATTRIBUTE,
            },
        )
        elements: list[InteractiveElement] = []
        for raw_element in raw_observation["elements"]:
            reference = raw_element.pop("reference")
            element = InteractiveElement(**raw_element)
            self._element_refs[element.id] = self.page.locator(
                f'[{ELEMENT_REFERENCE_ATTRIBUTE}="{reference}"]'
            )
            elements.append(element)
        title = await self.page.title()
        return PageObservation(
            url=self.page.url,
            title=title,
            elements=tuple(elements),
            can_scroll_up=raw_observation["can_scroll_up"],
            can_scroll_down=raw_observation["can_scroll_down"],
            fingerprint=sha256(
                json.dumps(
                    {
                        "url": self.page.url,
                        "title": title,
                        "text": raw_observation["text"],
                        "scroll": raw_observation["scroll_position"],
                        "elements": [
                            {key: value for key, value in item.items() if key != "id"}
                            for item in raw_observation["elements"]
                        ],
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
            text=raw_observation["text"][:3000],
        )

    async def execute(self, action: BrowserAction) -> ActionResult:
        if isinstance(action, ScrollAction):
            if not self.page:
                raise RuntimeError("BrowserSession must be entered before use")
            try:
                await self.page.evaluate(
                    "direction => scrollBy(0, innerHeight * 0.5 * "
                    "(direction === 'down' ? 1 : -1))",
                    action.direction,
                )
                return ActionResult("scroll", None, True)
            except Exception as exc:
                return ActionResult(
                    "scroll",
                    None,
                    False,
                    f"{type(exc).__name__}: {exc}",
                    FailureCategory.BROWSER_ERROR,
                )
            finally:
                self._element_refs.clear()

        locator = self._element_refs.get(action.element_id)
        if not locator:
            return ActionResult(
                action=action.action,
                element_id=action.element_id,
                success=False,
                error="Unknown or stale element ID; observe the page again",
                failure_category=FailureCategory.ACTION_FAILURE,
            )

        try:
            if await locator.count() != 1:
                return ActionResult(
                    action.action,
                    action.element_id,
                    False,
                    "Observed element disappeared; observe the page again",
                    FailureCategory.ACTION_FAILURE,
                )
            if not await locator.is_enabled(timeout=ACTION_TIMEOUT_MS):
                return ActionResult(
                    action=action.action,
                    element_id=action.element_id,
                    success=False,
                    error="Element is disabled",
                    failure_category=FailureCategory.ACTION_FAILURE,
                )
            if isinstance(action, ClickAction):
                await locator.click(timeout=ACTION_TIMEOUT_MS)
            elif isinstance(action, FillAction):
                await locator.fill(action.value, timeout=ACTION_TIMEOUT_MS)
            elif isinstance(action, SetCheckedAction):
                await locator.set_checked(action.checked, timeout=ACTION_TIMEOUT_MS)
            else:
                await locator.select_option(
                    label=action.label, timeout=ACTION_TIMEOUT_MS
                )
            return ActionResult(
                action=action.action,
                element_id=action.element_id,
                success=True,
            )
        except Exception as exc:
            return ActionResult(
                action=action.action,
                element_id=action.element_id,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                failure_category=FailureCategory.BROWSER_ERROR,
            )
        finally:
            self._element_refs.clear()

    async def assert_that(
        self,
        assertion: PageAssertion,
        *,
        timeout_ms: float = 5_000,
    ) -> AssertionResult:
        if not self.page:
            raise RuntimeError("BrowserSession must be entered before use")
        return await evaluate_assertion(
            self.page,
            assertion,
            timeout_ms=timeout_ms,
        )

    async def assert_checked(self, element_id: int, expected: bool) -> AssertionResult:
        locator = self._element_refs.get(element_id)
        if not locator:
            return AssertionResult(
                assertion="checked",
                success=False,
                expected=expected,
                actual=None,
                error="Unknown or stale element ID",
            )
        try:
            actual = await locator.is_checked()
            return AssertionResult(
                assertion="checked",
                success=actual == expected,
                expected=expected,
                actual=actual,
                error=None if actual == expected else "Observed value did not match",
            )
        except Exception as exc:
            return AssertionResult(
                assertion="checked",
                success=False,
                expected=expected,
                actual=None,
                error=f"{type(exc).__name__}: {exc}",
            )

    async def assert_selected_option(
        self, element_id: int, expected: str
    ) -> AssertionResult:
        locator = self._element_refs.get(element_id)
        if not locator:
            return AssertionResult(
                assertion="selected_option",
                success=False,
                expected=expected,
                actual=None,
                error="Unknown or stale element ID",
            )
        try:
            actual = await locator.locator("option:checked").first.text_content()
            success = actual == expected
            return AssertionResult(
                assertion="selected_option",
                success=success,
                expected=expected,
                actual=actual,
                error=None if success else "Observed value did not match",
            )
        except Exception as exc:
            return AssertionResult(
                assertion="selected_option",
                success=False,
                expected=expected,
                actual=None,
                error=f"{type(exc).__name__}: {exc}",
            )

    def assert_dialog_message(self, expected: str) -> AssertionResult:
        actual = self.dialog_messages[-1] if self.dialog_messages else None
        return AssertionResult(
            "dialog_message",
            actual == expected,
            expected,
            actual,
            None if actual == expected else "Observed value did not match",
        )

    async def _handle_dialog(self, dialog: Dialog) -> None:
        self.dialog_messages.append(dialog.message)
        await dialog.dismiss()

    def _record_console_error(self, message: ConsoleMessage) -> None:
        if message.type == "error" and len(self.console_errors) < MAX_RECORDED_ERRORS:
            self.console_errors.append(message.text)

    def _record_failed_request(self, request: Request) -> None:
        if len(self.failed_requests) < MAX_RECORDED_ERRORS:
            self.failed_requests.append(
                f"{request.method} {request.url}: {request.failure or 'unknown failure'}"
            )

    async def screenshot(self, path: Path) -> None:
        if not self.page:
            raise RuntimeError("BrowserSession must be entered before use")
        await self.page.screenshot(path=path)
