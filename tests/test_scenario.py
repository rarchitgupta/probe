from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

from qa_agent.assertions import TextVisibleAssertion, TitleEqualsAssertion
from qa_agent.scenario import (
    ClickStep,
    ElementTarget,
    FillStep,
    ScenarioTask,
    execute_scenario,
)
from qa_agent.policy import ExecutionPolicy


class ScenarioRunnerTest(unittest.IsolatedAsyncioTestCase):
    async def test_runs_actions_and_assertions(self) -> None:
        html = """
            <title>Login</title>
            <label for="username">Username</label><input id="username">
            <label for="password">Password</label><input id="password" type="password">
            <button onclick="document.title = 'Dashboard';
                document.body.insertAdjacentHTML('beforeend', '<p>Account ready</p>')">
                Login
            </button>
        """
        task = ScenarioTask(
            task_id="passing-scenario",
            start_url=f"data:text/html,{quote(html)}",
            steps=(
                FillStep("fill", ElementTarget("textbox", "Username"), "demo-user"),
                FillStep("fill", ElementTarget("textbox", "Password"), "demo-password"),
                ClickStep("click", ElementTarget("button", "Login")),
                TitleEqualsAssertion("title_equals", "Dashboard"),
                TextVisibleAssertion("text_visible", "Account ready", exact=True),
            ),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = await execute_scenario(task, artifact_root=root)
            saved = json.loads(
                (root / task.task_id / "result.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result.status, "passed")
        self.assertEqual(len(result.steps), 5)
        self.assertTrue(all(step.success for step in result.steps))
        self.assertNotIn("demo-password", json.dumps(saved))

    async def test_stops_on_ambiguous_target(self) -> None:
        html = "<button>Add</button><button>Add</button>"
        task = ScenarioTask(
            task_id="ambiguous-scenario",
            start_url=f"data:text/html,{quote(html)}",
            steps=(ClickStep("click", ElementTarget("button", "Add")),),
        )

        with tempfile.TemporaryDirectory() as directory:
            result = await execute_scenario(task, artifact_root=Path(directory))

        self.assertEqual(result.status, "failed")
        self.assertEqual(len(result.steps), 1)
        self.assertIn("Found 2", result.steps[0].error or "")

    async def test_stops_at_action_limit(self) -> None:
        html = "<button>First</button><button>Second</button>"
        task = ScenarioTask(
            task_id="limited-scenario",
            start_url=f"data:text/html,{quote(html)}",
            steps=(
                ClickStep("click", ElementTarget("button", "First")),
                ClickStep("click", ElementTarget("button", "Second")),
            ),
        )

        with tempfile.TemporaryDirectory() as directory:
            result = await execute_scenario(
                task,
                artifact_root=Path(directory),
                policy=ExecutionPolicy(max_actions=1),
            )

        self.assertEqual(result.status, "failed")
        self.assertEqual(len(result.steps), 2)
        self.assertIn("Action limit", result.steps[-1].error or "")


if __name__ == "__main__":
    unittest.main()
