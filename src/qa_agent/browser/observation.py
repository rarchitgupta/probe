"""Compact, semantic DOM observation for browser agents."""

from __future__ import annotations

from dataclasses import dataclass

MAX_INTERACTIVE_ELEMENTS = 100
ELEMENT_REFERENCE_ATTRIBUTE = "data-qa-agent-ref"
INTERACTIVE_SELECTOR = ",".join(
    (
        "a",
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
(elements, options) => {
    const { limit, referencePrefix, referenceAttribute } = options;
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

    document.querySelectorAll(`[${referenceAttribute}]`).forEach((element) => {
        element.removeAttribute(referenceAttribute);
    });

    const observations = [];
    for (const element of elements) {
        if (observations.length === limit) break;
        if (!isAvailable(element)) continue;

        const id = observations.length + 1;
        const reference = `${referencePrefix}:${id}`;
        const role = inferredRole(element);
        element.setAttribute(referenceAttribute, reference);
        observations.push({
            reference,
            id,
            role,
            name: accessibleName(element),
            tag: element.tagName.toLowerCase(),
            input_type: element.tagName === 'INPUT' ? element.type : null,
            disabled: Boolean(
                element.disabled || element.getAttribute('aria-disabled') === 'true',
            ),
            checked: ['checkbox', 'radio'].includes(role)
                ? Boolean(element.checked ?? element.getAttribute('aria-checked') === 'true')
                : null,
            selected_option: element.tagName === 'SELECT'
                ? normalize(element.selectedOptions?.[0]?.textContent)
                : null,
            filled: role === 'textbox' || role === 'spinbutton'
                ? Boolean(normalize(element.value ?? element.textContent))
                : null,
        });
    }
    const scrollingElement = document.scrollingElement;
    const scrollTop = scrollingElement?.scrollTop ?? scrollY;
    const scrollHeight = scrollingElement?.scrollHeight ?? document.documentElement.scrollHeight;
    return {
        elements: observations,
        can_scroll_up: scrollTop > 1,
        can_scroll_down: scrollTop + innerHeight < scrollHeight - 1,
    };
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
    checked: bool | None = None
    selected_option: str | None = None
    filled: bool | None = None


@dataclass(frozen=True)
class PageObservation:
    url: str
    title: str
    elements: tuple[InteractiveElement, ...]
    can_scroll_up: bool = False
    can_scroll_down: bool = False
