from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

from qa_agent.agent.planning import FormField, page_state
from qa_agent.agent.runtime import AgentDeps, perform_fill_form
from qa_agent.browser import BrowserSession
from qa_agent.policy import ExecutionGuard, ExecutionPolicy


class AgentRuntimeTest(unittest.IsolatedAsyncioTestCase):
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

                self.assertTrue(result.success)
                assert browser.page is not None
                self.assertEqual(
                    await browser.page.locator("input").first.input_value(), "Ada"
                )
                self.assertTrue(
                    await browser.page.locator("input[type=checkbox]").is_checked()
                )
                self.assertEqual(
                    await browser.page.locator("select").input_value(), "Japan"
                )


if __name__ == "__main__":
    unittest.main()
