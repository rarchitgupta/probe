from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Literal

from playwright.async_api import (
    Browser,
    BrowserContext,
    ConsoleMessage,
    Locator,
    Page,
    Playwright,
    Request,
    async_playwright,
)

from qa_agent.assertions import AssertionResult, BrowserAssertion, evaluate_assertion

MAX_INTERACTIVE_ELEMENTS = 100
MAX_RECORDED_ERRORS = 100
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
OBSERVE_INTERACTIVE_ELEMENTS = r"""
(elements, limit) => {
    const normalize = (value) => (value ?? '').replace(/\s+/g, ' ').trim();

    const isAvailable = (element) => {
        for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) {
            const style = getComputedStyle(ancestor);
            if (
                ancestor.getAttribute('aria-hidden') === 'true' ||
                ancestor.inert ||
                style.display === 'none' ||
                ['hidden', 'collapse'].includes(style.visibility) ||
                Number(style.opacity) === 0
            ) {
                return false;
            }
        }

        const rect = element.getBoundingClientRect();
        const visibleBounds = {
            left: Math.max(0, rect.left),
            right: Math.min(innerWidth, rect.right),
            top: Math.max(0, rect.top),
            bottom: Math.min(innerHeight, rect.bottom),
        };
        if (
            visibleBounds.right <= visibleBounds.left ||
            visibleBounds.bottom <= visibleBounds.top
        ) {
            return false;
        }

        const hit = document.elementFromPoint(
            (visibleBounds.left + visibleBounds.right) / 2,
            (visibleBounds.top + visibleBounds.bottom) / 2,
        );
        return Boolean(
            hit && (hit === element || element.contains(hit) || hit.control === element),
        );
    };

    const inferredRole = (element) => {
        const explicitRole = element.getAttribute('role');
        if (explicitRole) return explicitRole;
        if (element.tagName === 'A') return 'link';
        if (element.tagName === 'BUTTON') return 'button';
        if (element.tagName === 'SELECT') return 'combobox';
        if (element.tagName === 'TEXTAREA' || element.isContentEditable) return 'textbox';
        if (element.tagName !== 'INPUT') return 'unknown';

        const type = (element.type || 'text').toLowerCase();
        if (['button', 'submit', 'reset', 'image'].includes(type)) return 'button';
        if (type === 'checkbox') return 'checkbox';
        if (type === 'radio') return 'radio';
        if (type === 'range') return 'slider';
        if (type === 'number') return 'spinbutton';
        return 'textbox';
    };

    const accessibleName = (element) => {
        const labelledBy = element.getAttribute('aria-labelledby');
        const referenced = labelledBy
            ? labelledBy
                .split(/\s+/)
                .map((id) => document.getElementById(id)?.textContent)
                .join(' ')
            : '';
        const labels = Array.from(element.labels ?? [], (label) => label.textContent).join(' ');
        const buttonValue =
            element.tagName === 'INPUT' && ['button', 'submit', 'reset'].includes(element.type)
                ? element.value
                : '';
        const ownImageAlt =
            element.tagName === 'INPUT' && element.type === 'image'
                ? element.getAttribute('alt')
                : '';
        const visibleText =
            ['A', 'BUTTON'].includes(element.tagName) ||
            ['button', 'link'].includes(element.getAttribute('role'))
                ? element.innerText
                : '';
        const imageAlt = Array.from(
            element.querySelectorAll('img[alt]'),
            (image) => image.alt,
        ).join(' ');
        const candidates = [
            element.getAttribute('aria-label'),
            referenced,
            labels,
            buttonValue,
            ownImageAlt,
            visibleText,
            imageAlt,
            element.getAttribute('placeholder'),
            element.getAttribute('title'),
            element.getAttribute('name'),
        ];
        return normalize(candidates.find((value) => normalize(value))).slice(0, 200);
    };

    const observations = [];
    for (const [candidateIndex, element] of elements.entries()) {
        if (observations.length === limit) break;
        if (!isAvailable(element)) continue;

        observations.push({
            candidate_index: candidateIndex,
            id: observations.length + 1,
            role: inferredRole(element),
            name: accessibleName(element),
            tag: element.tagName.toLowerCase(),
            input_type: element.tagName === 'INPUT' ? element.type : null,
            disabled: Boolean(
                element.disabled || element.getAttribute('aria-disabled') === 'true',
            ),
        });
    }
    return observations;
}
"""


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
        self._element_refs: dict[int, Locator] = {}

    async def __aenter__(self) -> BrowserSession:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch()
        self._context = await self._browser.new_context()
        await self._context.tracing.start(
            screenshots=True, snapshots=True
        )
        self.page = await self._context.new_page()
        self.page.on("console", self._record_console_error)
        self.page.on("requestfailed", self._record_failed_request)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._element_refs.clear()
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
        self._element_refs.clear()
        candidates = self.page.locator(INTERACTIVE_SELECTOR)
        raw_elements = await candidates.evaluate_all(
            OBSERVE_INTERACTIVE_ELEMENTS,
            MAX_INTERACTIVE_ELEMENTS,
        )
        elements: list[InteractiveElement] = []
        for raw_element in raw_elements:
            candidate_index = raw_element.pop("candidate_index")
            element = InteractiveElement(**raw_element)
            self._element_refs[element.id] = candidates.nth(candidate_index)
            elements.append(element)
        return PageObservation(
            url=self.page.url,
            title=await self.page.title(),
            elements=tuple(elements),
        )

    async def execute(self, action: BrowserAction) -> ActionResult:
        locator = self._element_refs.get(action.element_id)
        if not locator:
            return ActionResult(
                action=action.action,
                element_id=action.element_id,
                success=False,
                error="Unknown or stale element ID; observe the page again",
            )

        try:
            if not await locator.is_enabled():
                return ActionResult(
                    action=action.action,
                    element_id=action.element_id,
                    success=False,
                    error="Element is disabled",
                )
            if isinstance(action, ClickAction):
                await locator.click()
            else:
                await locator.fill(action.value)
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
            self._element_refs.clear()

    async def assert_that(
        self,
        assertion: BrowserAssertion,
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
