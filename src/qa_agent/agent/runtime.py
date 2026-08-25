from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from qa_agent.agent.planning import (
    AgentInstruction,
    AssertionInstruction,
    CheckedInstruction,
    ClickInstruction,
    ElementState,
    FillFormInstruction,
    FormField,
    ProgressEntry,
    ScrollInstruction,
    ToolResult,
    page_state,
)
from qa_agent.assertions import (
    AssertionResult,
    BrowserAssertion,
    CheckedAssertion,
    DialogMessageAssertion,
    SelectedOptionAssertion,
    TextVisibleAssertion,
    TitleEqualsAssertion,
    UrlContainsAssertion,
)
from qa_agent.browser import (
    BrowserSession,
    ClickAction,
    FillAction,
    ScrollAction,
    SelectOptionAction,
    SetCheckedAction,
)
from qa_agent.execution import execute_guarded_action
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
    successful_actions: set[tuple[object, ...]] = field(default_factory=set)
    failure_category: FailureCategory | None = None


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
        if isinstance(form_field.value, bool) and target.role not in {
            "checkbox",
            "radio",
        }:
            deps.failure_category = FailureCategory.ACTION_FAILURE
            return ToolResult(
                success=False,
                error=f"Element {form_field.element_id} is not checkable",
                failure_category=deps.failure_category,
            )
        if target.role == "radio" and form_field.value is False:
            deps.failure_category = FailureCategory.ACTION_FAILURE
            return ToolResult(
                success=False,
                error="Radio buttons cannot be unchecked",
                failure_category=deps.failure_category,
            )
        targets.append((target, form_field.value))

    result = ToolResult(success=True)
    executed = False
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
        action_name = (
            "set_checked"
            if isinstance(value, bool)
            else "select_option"
            if target.role == "combobox"
            else "fill"
        )
        action_key = (
            action_name,
            target.role,
            target.name,
            target.input_type,
            value,
        )
        if action_key in deps.successful_actions:
            continue
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
        executed = True
        deps.successful_actions.add(action_key)
    if executed:
        return result
    deps.failure_category = FailureCategory.ACTION_FAILURE
    return ToolResult(
        success=False,
        error="These fields were already completed; choose another action or finish the step",
        failure_category=deps.failure_category,
    )


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
        deps.evidence.append(
            f"{result.assertion}: expected={result.expected!r}, actual={result.actual!r}"
        )
    else:
        deps.failure_category = FailureCategory.ASSERTION_FAILURE
    return result


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
            action_key = (
                action.action,
                element.role if element else None,
                element.name if element else instruction.element_id,
                element.input_type if element else None,
                True if isinstance(action, SetCheckedAction) else None,
            )
            if action_key in deps.successful_actions:
                deps.failure_category = FailureCategory.ACTION_FAILURE
                result = ToolResult(
                    success=False,
                    error="This action was already completed; choose another action or finish the step",
                    failure_category=deps.failure_category,
                )
            else:
                result = await _execute(deps, action)
                if result.success:
                    deps.successful_actions.add(action_key)
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
        else:
            assertion: BrowserAssertion
            if isinstance(instruction, AssertionInstruction):
                if instruction.action == "assert_text_visible":
                    assertion = TextVisibleAssertion(
                        "text_visible", instruction.expected, instruction.exact
                    )
                elif instruction.action == "assert_url_contains":
                    assertion = UrlContainsAssertion(
                        "url_contains", instruction.expected
                    )
                elif instruction.action == "assert_title_equals":
                    assertion = TitleEqualsAssertion(
                        "title_equals", instruction.expected
                    )
                else:
                    assertion = DialogMessageAssertion(
                        "dialog_message", instruction.expected
                    )
            elif isinstance(instruction, CheckedInstruction):
                assertion = CheckedAssertion(
                    "checked", instruction.element_id, instruction.expected
                )
            else:
                assertion = SelectedOptionAssertion(
                    "selected_option", instruction.element_id, instruction.expected
                )
            target = str(assertion.expected)
            result = await _assert(deps, assertion)

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
                    "page_may_have_changed"
                    if isinstance(instruction, (ClickInstruction, ScrollInstruction))
                    else "asserted"
                    if not isinstance(instruction, FillFormInstruction)
                    else "fields_updated"
                ),
                error=result.error,
            )
        )
        if not result.success or isinstance(
            instruction, (ClickInstruction, ScrollInstruction)
        ):
            break
    return progress, completed
