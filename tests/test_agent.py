from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pydantic_ai import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from qa_agent.agent import (
    AgentDeps,
    AgentTask,
    browser_agent,
    build_agent_prompt,
)
from qa_agent.browser import BrowserSession, InteractiveElement, PageObservation
from qa_agent.policy import ExecutionGuard, ExecutionPolicy


class BrowserAgentTest(unittest.IsolatedAsyncioTestCase):
    def test_builds_compact_prompt(self) -> None:
        prompt = build_agent_prompt(
            AgentTask(goal="Sign in", start_url="https://example.com/login"),
            PageObservation(
                url="https://example.com/login",
                title="Login",
                elements=(
                    InteractiveElement(1, "textbox", "Email", "input", "email", False),
                ),
            ),
        )

        data = json.loads(prompt)
        self.assertEqual(data["goal"], "Sign in")
        self.assertEqual(data["page"]["elements"][0]["name"], "Email")
        self.assertNotIn("tag", prompt)

    async def test_rejects_unverified_success(self) -> None:
        calls = 0

        async def respond(messages: list, info: AgentInfo) -> ModelResponse:
            nonlocal calls
            calls += 1
            output_tool = info.output_tools[0].name
            outcome = (
                {
                    "status": "passed",
                    "summary": "Done",
                    "evidence": ["invented"],
                }
                if calls == 1
                else {"status": "failed", "summary": "Not verified", "evidence": []}
            )
            return ModelResponse(parts=[ToolCallPart(output_tool, outcome)])

        url = "data:text/html,<title>Page</title>"
        policy = ExecutionPolicy().for_start_url(url)

        with tempfile.TemporaryDirectory() as directory:
            async with BrowserSession(
                trace_path=Path(directory) / "trace.zip"
            ) as browser:
                await browser.navigate(url)
                result = await browser_agent.run(
                    "Verify the page",
                    deps=AgentDeps(browser, ExecutionGuard(policy)),
                    model=FunctionModel(respond),
                )

        self.assertEqual(calls, 2)
        self.assertEqual(result.output.status, "failed")
        self.assertEqual(result.output.evidence, [])


if __name__ == "__main__":
    unittest.main()
