from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import quote

import pytest

from qa_agent.agent.planning import ClickInstruction, FormField, page_state
from qa_agent.agent.runtime import AgentDeps, execute_instructions, perform_fill_form
from qa_agent.browser import BrowserSession
from qa_agent.failures import FailureCategory
from qa_agent.policy import ExecutionGuard, ExecutionPolicy

pytestmark = pytest.mark.browser


class TestAgentRuntime:
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
                )
                result = await perform_fill_form(
                    deps,
                    [
                        FormField(element_id=1, value="Ada"),
                        FormField(element_id=2, value=True),
                        FormField(element_id=3, value="Japan"),
                    ],
                )

                assert result.success
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
                assert not repeated[0].success
                assert "already completed" in (repeated[0].error or "")
                assert deps.failure_category == FailureCategory.ACTION_FAILURE
