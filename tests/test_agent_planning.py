from __future__ import annotations

import json
import unittest

from qa_agent.agent.planning import (
    ProgressEntry,
    TestStep,
    build_step_prompt,
    sanitize_summary,
)
from qa_agent.browser.observation import InteractiveElement, PageObservation


class AgentPlanningTest(unittest.TestCase):
    def test_sanitizes_known_password_values(self) -> None:
        self.assertEqual(
            sanitize_summary(
                "Logged in with standard_user/secret_sauce",
                {"secret_sauce"},
            ),
            "Logged in with standard_user/[REDACTED]",
        )

    def test_builds_compact_prompt(self) -> None:
        prompt = build_step_prompt(
            TestStep(id=2, kind="action", instruction="Submit"),
            [TestStep(id=1, kind="action", instruction="Fill the email")],
            [ProgressEntry(action=f"old-{index}", success=True) for index in range(13)],
            PageObservation(
                url="https://example.com/login",
                title="Login",
                elements=(
                    InteractiveElement(1, "textbox", "Email", "input", "email", False),
                ),
            ),
        )

        data = json.loads(prompt)
        self.assertNotIn("goal", data)
        self.assertEqual(data["page"]["elements"][0]["name"], "Email")
        self.assertEqual(data["completed_steps"][0]["instruction"], "Fill the email")
        self.assertEqual(len(data["current_step_progress"]), 10)
        self.assertEqual(data["current_step_progress"][0]["action"], "old-3")
        self.assertNotIn("tag", prompt)


if __name__ == "__main__":
    unittest.main()
