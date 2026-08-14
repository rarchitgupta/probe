from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Literal

from playwright.async_api import (
    Browser,
    BrowserContext,
    ElementHandle,
    Page,
    Playwright,
    async_playwright,
)

MAX_INTERACTIVE_ELEMENTS = 100
INTERACTIVE_SELECTOR = ",".join(
    (
        "a[href]",
        "button",
        "input:not([type=hidden])",
        "select",
        "textarea",
        "[contenteditable=true]",
        "[role=button]",
        "[role=link]",
        "[role=checkbox]",
        "[role=radio]",
        "[role=textbox]",
        "[role=combobox]",
        "[role=switch]",
        "[role=menuitem]",
        "[role=tab]",
        "[role=slider]",
        "[role=spinbutton]",
    )
)


@dataclass(frozen=True)
class InteractiveElement:
    id: int
    role: str
    name: str
    tag: str
    input_type: str | None
    disabled: bool


@dataclass(frozen=True)
class PageObservation:
    url: str
    title: str
    elements: tuple[InteractiveElement, ...]


@dataclass(frozen=True)
class BrowserObservation:
    requested_url: str
    final_url: str | None
    title: str | None
    http_status: int | None
    elements: tuple[InteractiveElement, ...]
    console_errors: tuple[str, ...]
    failed_requests: tuple[str, ...]
    error: str | None = None


@dataclass(frozen=True)
class ClickAction:
    action: Literal["click"]
    element_id: int


@dataclass(frozen=True)
class FillAction:
    action: Literal["fill"]
    element_id: int
    value: str


BrowserAction = ClickAction | FillAction


@dataclass(frozen=True)
class ActionResult:
    action: Literal["click", "fill"]
    element_id: int
    success: bool
    error: str | None = None


class BrowserSession:
    """One isolated browser context, reusable for a complete QA task."""

    def __init__(self, *, trace_path: Path) -> None:
        self.trace_path = trace_path
        self.console_errors: list[str] = []
        self.failed_requests: list[str] = []
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None
        self._element_refs: dict[int, ElementHandle] = {}

    async def __aenter__(self) -> BrowserSession:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch()
        self._context = await self._browser.new_context()
        await self._context.tracing.start(
            screenshots=True, snapshots=True, sources=True
        )
        self.page = await self._context.new_page()
        self.page.on(
            "console",
            lambda message: self.console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        self.page.on(
            "requestfailed",
            lambda request: self.failed_requests.append(
                f"{request.method} {request.url}: {request.failure or 'unknown failure'}"
            ),
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._clear_element_refs()
        if self._context:
            await self._context.tracing.stop(path=self.trace_path)
            await self._context.close()
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
        await self._clear_element_refs()
        elements: list[InteractiveElement] = []
        handles = await self.page.locator(INTERACTIVE_SELECTOR).element_handles()
        for handle in handles:
            if len(elements) == MAX_INTERACTIVE_ELEMENTS:
                await handle.dispose()
                continue
            if not await handle.is_visible():
                await handle.dispose()
                continue
            element_id = len(elements) + 1
            raw_element = await handle.evaluate(
                r"""(element, id) => {
                const inferredRole = (element) => {
                    if (element.getAttribute('role')) return element.getAttribute('role');
                    if (element.tagName === 'A') return 'link';
                    if (element.tagName === 'BUTTON') return 'button';
                    if (element.tagName === 'SELECT') return 'combobox';
                    if (element.tagName === 'TEXTAREA') return 'textbox';
                    if (element.isContentEditable) return 'textbox';
                    if (element.tagName === 'INPUT') {
                        const type = (element.type || 'text').toLowerCase();
                        if (['button', 'submit', 'reset', 'image'].includes(type)) return 'button';
                        if (type === 'checkbox') return 'checkbox';
                        if (type === 'radio') return 'radio';
                        if (type === 'range') return 'slider';
                        if (type === 'number') return 'spinbutton';
                        return 'textbox';
                    }
                    return 'unknown';
                };
                const accessibleName = (element) => {
                    const labelledBy = element.getAttribute('aria-labelledby');
                    const referenced = labelledBy
                        ? labelledBy.split(/\s+/).map((id) => document.getElementById(id)?.innerText || '').join(' ')
                        : '';
                    const labels = Array.from(element.labels || []).map((label) => label.innerText).join(' ');
                    const buttonValue = element.tagName === 'INPUT' &&
                        ['button', 'submit', 'reset'].includes(element.type) ? element.value : '';
                    return (element.getAttribute('aria-label') || referenced || labels ||
                        buttonValue || element.innerText || element.getAttribute('placeholder') ||
                        element.getAttribute('title') || element.getAttribute('name') || '').trim().slice(0, 200);
                };
                return {
                    id,
                    role: inferredRole(element),
                    name: accessibleName(element),
                    tag: element.tagName.toLowerCase(),
                    input_type: element.tagName === 'INPUT' ? element.type : null,
                    disabled: Boolean(element.disabled || element.getAttribute('aria-disabled') === 'true'),
                };
            }""",
                element_id,
            )
            self._element_refs[element_id] = handle
            elements.append(InteractiveElement(**raw_element))
        return PageObservation(
            url=self.page.url,
            title=await self.page.title(),
            elements=tuple(elements),
        )

    async def execute(self, action: BrowserAction) -> ActionResult:
        handle = self._element_refs.get(action.element_id)
        if not handle:
            return ActionResult(
                action=action.action,
                element_id=action.element_id,
                success=False,
                error="Unknown or stale element ID; observe the page again",
            )

        try:
            if not await handle.is_enabled():
                return ActionResult(
                    action=action.action,
                    element_id=action.element_id,
                    success=False,
                    error="Element is disabled",
                )
            if isinstance(action, ClickAction):
                await handle.click()
            else:
                await handle.fill(action.value)
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
            )
        finally:
            await self._clear_element_refs()

    async def _clear_element_refs(self) -> None:
        for handle in self._element_refs.values():
            await handle.dispose()
        self._element_refs.clear()

    async def screenshot(self, path: Path) -> None:
        if not self.page:
            raise RuntimeError("BrowserSession must be entered before use")
        await self.page.screenshot(path=path, full_page=True)


async def inspect_page(
    url: str,
    *,
    screenshot_path: Path,
    trace_path: Path,
) -> BrowserObservation:
    final_url: str | None = None
    title: str | None = None
    http_status: int | None = None
    elements: tuple[InteractiveElement, ...] = ()
    error: str | None = None

    async with BrowserSession(trace_path=trace_path) as session:
        try:
            http_status = await session.navigate(url)
            observation = await session.observe()
            final_url = observation.url
            title = observation.title
            elements = observation.elements
            await session.screenshot(screenshot_path)
        except Exception as exc:
            final_url = session.page.url if session.page else None
            error = f"{type(exc).__name__}: {exc}"
            try:
                await session.screenshot(screenshot_path)
            except Exception:
                pass

        return BrowserObservation(
            requested_url=url,
            final_url=final_url,
            title=title,
            http_status=http_status,
            elements=elements,
            console_errors=tuple(session.console_errors),
            failed_requests=tuple(session.failed_requests),
            error=error,
        )
