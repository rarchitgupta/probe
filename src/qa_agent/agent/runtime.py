from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Literal

from qa_agent.agent.assertions import (
    AssertionResult,
    BrowserAssertion,
    CheckedAssertion,
    DialogMessageAssertion,
    RegionContainsAssertion,
    SelectedOptionAssertion,
    TextVisibleAssertion,
    TitleEqualsAssertion,
    UrlContainsAssertion,
)
from qa_agent.agent.execution import execute_guarded_action
from qa_agent.agent.planning import (
    AgentInstruction,
    ClickInstruction,
    ElementState,
    FillFormInstruction,
    FormField,
    PinnedCheck,
    ProgressEntry,
    RegionContainsCheck,
    ScrollInstruction,
    TaskInput,
    ToolResult,
    WaitInstruction,
    page_state,
)
from qa_agent.browser.session import (
    BrowserSession,
    ClickAction,
    FillAction,
    ScrollAction,
    SelectOptionAction,
    SetCheckedAction,
)
from qa_agent.environments import resolve_secret
from qa_agent.failures import FailureCategory
from qa_agent.policy import ExecutionGuard, PolicyViolation


@dataclass(frozen=True)
class ActionDiagnostic:
    action: Literal["click", "fill", "set_checked", "select_option", "scroll"]
    element_id: int | None
    role: str | None
    input_type: str | None
    success: bool
    url_changed: bool
    value_length: int | None = None
    changed_from_previous: bool | None = None


@dataclass
class AgentDeps:
    browser: BrowserSession
    guard: ExecutionGuard
    evidence: list[str] = field(default_factory=list)
    elements: dict[int, ElementState] = field(default_factory=dict)
    diagnostics: list[ActionDiagnostic] = field(default_factory=list)
    previous_fill_values: dict[tuple[int, str | None], str] = field(
        default_factory=dict
    )
    sensitive_values: set[str] = field(default_factory=set)
    failure_category: FailureCategory | None = None
    secrets: dict[str, str] = field(default_factory=dict)
    task_inputs: dict[str, TaskInput] = field(default_factory=dict)
    successful_field_updates: set[tuple[str, str, str]] = field(default_factory=set)


async def perform_fill_form(deps: AgentDeps, fields: list[FormField]) -> ToolResult:
    targets: list[tuple[ElementState, str | bool]] = []
    for form_field in fields:
        target = deps.elements.get(form_field.element_id)
        if not target:
            deps.failure_category = FailureCategory.ACTION_FAILURE
            return ToolResult(
                success=False,
                error=f"Unknown element ID {form_field.element_id}",
                failure_category=deps.failure_category,
            )
        if form_field.input_id is not None:
            if target.role not in {"textbox", "spinbutton", "combobox"}:
                deps.failure_category = FailureCategory.ACTION_FAILURE
                return ToolResult(
                    success=False,
                    error=f"Element {target.id} ({target.name!r}) is not a text or select field; re-observe before filling",
                    failure_category=deps.failure_category,
                )
            task_input = deps.task_inputs.get(form_field.input_id)
            if not task_input:
                deps.failure_category = FailureCategory.ACTION_FAILURE
                return ToolResult(
                    success=False,
                    error=f"Unknown task input {form_field.input_id!r}",
                    failure_category=deps.failure_category,
                )
            value: str | bool = resolve_secret(task_input.value, deps.secrets)
            if task_input.sensitive:
                deps.sensitive_values.add(value)
        else:
            value = bool(form_field.value)
        if isinstance(value, bool) and target.role not in {
            "checkbox",
            "radio",
        }:
            deps.failure_category = FailureCategory.ACTION_FAILURE
            return ToolResult(
                success=False,
                error=f"Element {form_field.element_id} is not checkable",
                failure_category=deps.failure_category,
            )
        if target.role == "radio" and value is False:
            deps.failure_category = FailureCategory.ACTION_FAILURE
            return ToolResult(
                success=False,
                error="Radio buttons cannot be unchecked",
                failure_category=deps.failure_category,
            )
        targets.append((target, value))

    result = ToolResult(success=True)
    for target, value in targets:
        matches = [
            element
            for element in deps.elements.values()
            if (element.role, element.name, element.input_type)
            == (target.role, target.name, target.input_type)
        ]
        if len(matches) != 1:
            deps.failure_category = FailureCategory.ACTION_FAILURE
            return ToolResult(
                success=False,
                error=f"Field {target.name!r} is no longer uniquely available",
                failure_category=deps.failure_category,
            )
        element_id = matches[0].id
        field_url = deps.browser.page.url if deps.browser.page else ""
        if isinstance(value, bool):
            result = await _execute(
                deps, SetCheckedAction("set_checked", element_id, value)
            )
        elif target.role == "combobox":
            result = await _execute(
                deps, SelectOptionAction("select_option", element_id, value)
            )
        else:
            result = await _execute(deps, FillAction("fill", element_id, value))
        if not result.success:
            return result
        deps.successful_field_updates.add((field_url, target.role, target.name))
    return result


async def _execute(
    deps: AgentDeps,
    action: ClickAction
    | FillAction
    | SetCheckedAction
    | SelectOptionAction
    | ScrollAction,
) -> ToolResult:
    target = deps.elements.get(action.element_id) if action.element_id else None
    before_url = deps.browser.page.url if deps.browser.page else ""
    value_length: int | None = None
    changed_from_previous: bool | None = None
    if isinstance(action, FillAction):
        value_length = len(action.value)
        if target and target.input_type == "password":
            deps.sensitive_values.add(action.value)
        key = (action.element_id, target.input_type if target else None)
        previous = deps.previous_fill_values.get(key)
        changed_from_previous = previous is not None and previous != action.value
        deps.previous_fill_values[key] = action.value

    result = await execute_guarded_action(deps.browser, deps.guard, action)
    if not result.success:
        deps.failure_category = (
            result.failure_category or FailureCategory.ACTION_FAILURE
        )
    after_url = deps.browser.page.url if deps.browser.page else ""
    deps.diagnostics.append(
        ActionDiagnostic(
            action=action.action,
            element_id=action.element_id,
            role=target.role if target else None,
            input_type=target.input_type if target else None,
            success=result.success,
            url_changed=before_url != after_url,
            value_length=value_length,
            changed_from_previous=changed_from_previous,
        )
    )
    try:
        deps.guard.check_url(after_url)
    except PolicyViolation:
        deps.failure_category = FailureCategory.POLICY_VIOLATION
        return ToolResult(
            success=False,
            error=result.error,
            failure_category=deps.failure_category,
        )

    state = page_state(await deps.browser.observe())
    deps.elements = {element.id: element for element in state.elements}
    return ToolResult(
        success=result.success,
        error=result.error,
        observation=state,
        failure_category=result.failure_category,
    )


async def _assert(deps: AgentDeps, assertion: BrowserAssertion) -> AssertionResult:
    try:
        deps.guard.check_url(deps.browser.page.url if deps.browser.page else "")
    except PolicyViolation as exc:
        deps.failure_category = FailureCategory.POLICY_VIOLATION
        return AssertionResult(
            assertion=assertion.assertion,
            success=False,
            expected=assertion.expected,
            actual=None,
            error=str(exc),
        )

    if isinstance(assertion, CheckedAssertion):
        result = await deps.browser.assert_checked(
            assertion.element_id, assertion.expected
        )
    elif isinstance(assertion, SelectedOptionAssertion):
        result = await deps.browser.assert_selected_option(
            assertion.element_id, assertion.expected
        )
    elif isinstance(assertion, DialogMessageAssertion):
        result = deps.browser.assert_dialog_message(assertion.expected)
    else:
        result = await deps.browser.assert_that(assertion)
    if result.success:
        deps.failure_category = None
        deps.evidence.append(
            f"{result.assertion}: expected={result.expected!r}, actual={result.actual!r}"
        )
    else:
        deps.failure_category = FailureCategory.ASSERTION_FAILURE
    return result


async def execute_check(deps: AgentDeps, check: PinnedCheck) -> AssertionResult:
    if isinstance(check, RegionContainsCheck):
        assertion: BrowserAssertion = RegionContainsAssertion(
            "region_contains", check.anchor, tuple(check.expected)
        )
    elif check.assertion == "text_visible":
        assertion = TextVisibleAssertion("text_visible", check.expected, check.exact)
    elif check.assertion == "url_contains":
        assertion = UrlContainsAssertion("url_contains", check.expected)
    elif check.assertion == "title_equals":
        assertion = TitleEqualsAssertion("title_equals", check.expected)
    else:
        assertion = DialogMessageAssertion("dialog_message", check.expected)
    return await _assert(deps, assertion)


async def execute_instructions(
    deps: AgentDeps, instructions: list[AgentInstruction]
) -> tuple[list[ProgressEntry], int]:
    progress: list[ProgressEntry] = []
    completed = 0
    for instruction in instructions:
        target: str | None = None
        if isinstance(instruction, ClickInstruction):
            element = deps.elements.get(instruction.element_id)
            target = element.name if element else f"element {instruction.element_id}"
            action = (
                SetCheckedAction("set_checked", instruction.element_id, True)
                if element and element.role in {"checkbox", "radio"}
                else ClickAction("click", instruction.element_id)
            )
            result = await _execute(deps, action)
        elif isinstance(instruction, FillFormInstruction):
            names = [
                deps.elements[form_field.element_id].name
                for form_field in instruction.fields
                if form_field.element_id in deps.elements
            ]
            target = ", ".join(names)
            result = await perform_fill_form(deps, instruction.fields)
        elif isinstance(instruction, ScrollInstruction):
            target = instruction.direction
            result = await _execute(deps, ScrollAction("scroll", instruction.direction))
        elif isinstance(instruction, WaitInstruction):
            try:
                deps.guard.check_url(deps.browser.page.url if deps.browser.page else "")
                deps.guard.record_action()
                async with asyncio.timeout(deps.guard.remaining_seconds):
                    await asyncio.sleep(1)
                deps.guard.check_url(deps.browser.page.url if deps.browser.page else "")
                result = ToolResult(success=True)
            except PolicyViolation as exc:
                deps.failure_category = FailureCategory.POLICY_VIOLATION
                result = ToolResult(
                    success=False,
                    error=str(exc),
                    failure_category=deps.failure_category,
                )
        else:
            raise AssertionError(f"Unsupported instruction: {instruction!r}")

        completed += 1
        progress.append(
            ProgressEntry(
                action=(
                    f"fill_form:{len(instruction.fields)}"
                    if isinstance(instruction, FillFormInstruction)
                    else instruction.action
                ),
                target=target,
                success=result.success,
                effect=(
                    "waited"
                    if isinstance(instruction, WaitInstruction)
                    else "page_may_have_changed"
                    if isinstance(instruction, (ClickInstruction, ScrollInstruction))
                    else "fields_updated"
                ),
                error=result.error,
            )
        )
        if not result.success or isinstance(
            instruction, (ClickInstruction, ScrollInstruction, WaitInstruction)
        ):
            break
    return progress, completed
