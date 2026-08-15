from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

from pydantic_ai import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from qa_agent.agent import AgentDeps, AgentOutcome, browser_agent
from qa_agent.browser import BrowserSession
from qa_agent.policy import ExecutionGuard, ExecutionPolicy


class BrowserAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_executes_typed_tools_without_a_real_model(self) -> None:
        calls = 0

        async def respond(messages: list, info: AgentInfo) -> ModelResponse:
            nonlocal calls
            calls += 1
            if calls == 1:
                return ModelResponse(
                    parts=[ToolCallPart("fill", {"element_id": 1, "value": "Ada"})]
                )
            output_tool = info.output_tools[0].name
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        output_tool,
                        {
                            "status": "passed",
                            "summary": "Name entered",
                            "evidence": ["Name field contains Ada"],
                        },
                    )
                ]
            )

        url = "data:text/html," + quote(
            '<label for="name">Name</label><input id="name">'
        )
        policy = ExecutionPolicy().for_start_url(url)

        with tempfile.TemporaryDirectory() as directory:
            async with BrowserSession(
                trace_path=Path(directory) / "trace.zip"
            ) as browser:
                await browser.navigate(url)
                observation = await browser.observe()
                result = await browser_agent.run(
                    f"Goal: enter a name\nCurrent page: {observation}",
                    deps=AgentDeps(browser, ExecutionGuard(policy)),
                    model=FunctionModel(respond),
                )
                value = await browser.page.locator("#name").input_value()

        self.assertEqual(value, "Ada")
        self.assertEqual(result.output, AgentOutcome(
            status="passed",
            summary="Name entered",
            evidence=["Name field contains Ada"],
        ))


if __name__ == "__main__":
    unittest.main()
