from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import quote

import pytest

from qa_agent.agent.planning import (
    ClickInstruction,
    FormField,
    TaskInput,
    WaitInstruction,
    page_state,
)
from qa_agent.agent.runtime import AgentDeps, execute_instructions, perform_fill_form
from qa_agent.browser import BrowserSession
from qa_agent.policy import ExecutionGuard, ExecutionPolicy

pytestmark = pytest.mark.browser


class TestAgentRuntime:
    async def test_wait_ends_batch_and_allows_delayed_form_to_render(
        self, tmp_path
    ) -> None:
        url = f"data:text/html,{quote('<title>Loading</title>')}"
        async with BrowserSession(trace_path=tmp_path / "trace.zip") as browser:
            await browser.navigate(url)
            deps = AgentDeps(
                browser,
                ExecutionGuard(ExecutionPolicy(max_actions=1).for_start_url(url)),
            )
            assert browser.page is not None
            await browser.page.evaluate(
                "setTimeout(() => document.body.innerHTML = '<label>Name<input></label>', 50)"
            )
            batch, executed = await execute_instructions(
                deps,
                [
                    WaitInstruction(action="wait"),
                    ClickInstruction(action="click", element_id=999),
                ],
            )
            assert executed == 1
            assert batch[0].success and batch[0].effect == "waited"
            assert not deps.evidence
            assert deps.guard.actions == 1
            assert (await browser.observe()).elements[0].name == "Name"
            blocked, _ = await execute_instructions(
                deps, [WaitInstruction(action="wait")]
            )
            assert not blocked[0].success
            assert blocked[0].error and "Action limit" in blocked[0].error

    async def test_rejects_link_before_filling_any_fields(self, tmp_path) -> None:
        html = '<label>Name <input></label><a href="#">Home</a>'
        url = f"data:text/html,{quote(html)}"
        async with BrowserSession(trace_path=tmp_path / "trace.zip") as browser:
            await browser.navigate(url)
            state = page_state(await browser.observe())
            deps = AgentDeps(
                browser,
                ExecutionGuard(ExecutionPolicy().for_start_url(url)),
                elements={element.id: element for element in state.elements},
                task_inputs={"name": TaskInput(id="name", label="Name", value="Ada")},
            )
            result = await perform_fill_form(
                deps,
                [
                    FormField(element_id=1, input_id="name"),
                    FormField(element_id=2, input_id="name"),
                ],
            )
            assert not result.success
            assert result.error and "not a text or select field" in result.error
            assert not deps.diagnostics
            assert not deps.successful_field_updates
            assert browser.page is not None
            assert await browser.page.locator("input").input_value() == ""

    async def test_fills_mixed_form_in_one_instruction(self) -> None:
        html = """
            <label>Name <input></label>
            <label><input type="checkbox"> Accept terms</label>
            <label>Country <select><option>Canada</option><option>Japan</option></select></label>
        """
        url = f"data:text/html,{quote(html)}"
        policy = ExecutionPolicy().for_start_url(url)

        with tempfile.TemporaryDirectory() as directory:
            async with BrowserSession(
                trace_path=Path(directory) / "trace.zip"
            ) as browser:
                await browser.navigate(url)
                state = page_state(await browser.observe())
                deps = AgentDeps(
                    browser,
                    ExecutionGuard(policy),
                    elements={element.id: element for element in state.elements},
                    task_inputs={
                        "name": TaskInput(id="name", label="name", value="Ada"),
                        "country": TaskInput(
                            id="country", label="country", value="Japan"
                        ),
                    },
                )
                result = await perform_fill_form(
                    deps,
                    [
                        FormField(element_id=1, input_id="name"),
                        FormField(element_id=2, value=True),
                        FormField(element_id=3, input_id="country"),
                    ],
                )

                assert result.success
                assert deps.successful_field_updates == {
                    (url, "textbox", "Name"),
                    (url, "checkbox", "Accept terms"),
                    (url, "combobox", state.elements[2].name),
                }
                assert browser.page is not None
                assert await browser.page.locator("input").first.input_value() == "Ada"
                assert await browser.page.locator("input[type=checkbox]").is_checked()
                assert [item.action for item in deps.diagnostics] == [
                    "fill",
                    "set_checked",
                    "select_option",
                ]
                assert await browser.page.locator("select").input_value() == "Japan"

                repeated, _ = await execute_instructions(
                    deps, [ClickInstruction(action="click", element_id=2)]
                )
                assert await browser.page.locator("input[type=checkbox]").is_checked()
                assert repeated[0].success
