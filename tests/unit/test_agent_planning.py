from __future__ import annotations

import json

import pytest

from qa_agent.agent.planning import (
    ProgressEntry,
    TaskInput,
    build_step_prompt,
    sanitize_summary,
    validate_task_inputs,
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
                steps=[
                    AgentTestStep(
                        id=1,
                        kind="assertion",
                        instruction="Verify",
                        check={"assertion": "text_visible", "expected": "Ready"},
                    )
                ],
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
            AgentTestStep(
                id=2,
                kind="action",
                instruction="Submit",
                input_ids=["username"],
            ),
            [AgentTestStep(id=1, kind="action", instruction="Fill the email")],
            [ProgressEntry(action=f"old-{index}", success=True) for index in range(13)],
            PageObservation(
                url="https://example.com/login",
                title="Login",
                elements=(
                    InteractiveElement(1, "textbox", "Email", "input", "email", False),
                ),
                text="Invalid password secret-value",
            ),
            {
                "username": TaskInput(
                    id="username", label="username", value="standard_user"
                )
            },
            sensitive_values={"secret-value"},
            successful_field_updates=[
                ("https://example.com/login", "textbox", "Password")
            ],
        )

        data = json.loads(prompt)
        assert "goal" not in data
        assert "secret-value" not in prompt
        assert "standard_user" not in prompt
        assert data["page"]["elements"][0]["name"] == "Email"
        assert data["completed_steps"][0]["instruction"] == "Fill the email"
        assert data["step_inputs"] == [
            {
                "id": "username",
                "label": "username",
            }
        ]
        assert len(data["recent_progress"]) == 8
        assert data["successful_field_updates"] == [
            {"url": "https://example.com/login", "role": "textbox", "name": "Password"}
        ]
        assert data["recent_progress"][0]["action"] == "old-5"
        assert "tag" not in prompt

    def test_rejects_task_input_not_copied_from_goal(self) -> None:
        spec = AgentTestSpec(
            title="Login check",
            inputs=[
                TaskInput(
                    id="username",
                    label="username",
                    value="invented@example.com",
                )
            ],
            steps=[
                AgentTestStep(
                    id=1,
                    kind="assertion",
                    instruction="Verify login",
                    input_ids=["username"],
                    check={"assertion": "text_visible", "expected": "Logged in"},
                )
            ],
        )

        with pytest.raises(ValueError, match="was not copied from the task"):
            validate_task_inputs(spec, "Log in as standard_user")

    def test_allows_available_secret_placeholder(self) -> None:
        secret = TaskInput(
            id="password",
            label="password",
            value="{{secret:password}}",
            sensitive=True,
        )
        spec = AgentTestSpec(
            title="Login check",
            inputs=[secret],
            steps=[
                AgentTestStep(
                    id=1,
                    kind="assertion",
                    instruction="Verify login",
                    input_ids=["password"],
                    check={"assertion": "text_visible", "expected": "Logged in"},
                )
            ],
        )

        assert validate_task_inputs(spec, "Log in", {"password"}) == {
            "password": secret
        }
