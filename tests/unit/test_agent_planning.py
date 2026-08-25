from __future__ import annotations

import json

import pytest

from qa_agent.agent.planning import (
    ProgressEntry,
    build_step_prompt,
    sanitize_summary,
)
from qa_agent.agent.planning import (
    TestSpec as AgentTestSpec,
)
from qa_agent.agent.planning import (
    TestStep as AgentTestStep,
)
from qa_agent.browser.observation import InteractiveElement, PageObservation


class TestAgentPlanning:
    def test_limits_generated_title_to_five_words(self) -> None:
        with pytest.raises(ValueError, match="at most 5 words"):
            AgentTestSpec(
                title="This title contains far too many words",
                steps=[AgentTestStep(id=1, kind="assertion", instruction="Verify")],
            )

    def test_sanitizes_known_password_values(self) -> None:
        assert (
            sanitize_summary(
                "Logged in with standard_user/secret_sauce",
                {"secret_sauce"},
            )
            == "Logged in with standard_user/[REDACTED]"
        )

    def test_builds_compact_prompt(self) -> None:
        prompt = build_step_prompt(
            AgentTestStep(id=2, kind="action", instruction="Submit"),
            [AgentTestStep(id=1, kind="action", instruction="Fill the email")],
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
        assert "goal" not in data
        assert data["page"]["elements"][0]["name"] == "Email"
        assert data["completed_steps"][0]["instruction"] == "Fill the email"
        assert len(data["current_step_progress"]) == 10
        assert data["current_step_progress"][0]["action"] == "old-3"
        assert "tag" not in prompt
