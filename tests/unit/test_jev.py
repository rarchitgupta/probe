from types import SimpleNamespace
from typing import cast

import pytest
from typesafe_sdk import AsyncTypeSafeClient

from qa_agent.agent.jev import JevSelector
from qa_agent.agent.planning import ClickInstruction, TaskInput
from qa_agent.agent.planning import TestStep as Step
from qa_agent.browser.observation import InteractiveElement, PageObservation


class FakeClient:
    def __init__(self, selected_description: str):
        self.selected_description = selected_description
        self.state = None
        self.options: dict[str, str] = {}

    async def system_one(self, *, state, questions):
        self.state = state
        options = questions["next_action"].criteria
        self.options = options
        selected = next(
            key
            for key, description in options.items()
            if self.selected_description in description
        )
        return SimpleNamespace(
            choices={"next_action": SimpleNamespace(choice=selected)},
            usage=SimpleNamespace(input_tokens=100),
            model="jev-1.13.0",
        )


@pytest.mark.parametrize(
    ("selection", "expected"),
    [
        ("using task input 'Username'", "fill_form"),
        ("Click button 'Login'", "click"),
        ("Current step is complete", None),
    ],
)
async def test_jev_maps_only_observed_actions(selection, expected):
    client = FakeClient(selection)
    selector = JevSelector(cast(AsyncTypeSafeClient, client))
    step = Step(id=1, kind="action", instruction="Log in", input_ids=["username"])
    observation = PageObservation(
        url="https://example.test/login",
        title="Login",
        elements=(
            InteractiveElement(1, "textbox", "Username", "input", "text", False),
            InteractiveElement(2, "button", "Login", "button", None, False),
        ),
    )
    decision = await selector.decide(
        step,
        observation,
        {
            "username": TaskInput(
                id="username", label="Username", value="secret", sensitive=True
            )
        },
        [],
        None,
        set(),
        {"secret"},
    )
    assert (decision.actions[0].action if decision.actions else None) == expected
    assert "secret" not in str(client.state)
    assert selector.usage()["requests"] == 1
    assert selector.usage()["input_tokens"] == 100


async def test_blocked_choice_tries_unattempted_form_submit_once():
    client = FakeClient("Cannot complete this step")
    selector = JevSelector(cast(AsyncTypeSafeClient, client))
    step = Step(id=1, kind="action", instruction="Sign in", input_ids=["username"])
    observation = PageObservation(
        url="https://example.test/login",
        title="Login",
        elements=(
            InteractiveElement(
                1, "button", "Sign in", "button", None, False, context="navigation"
            ),
            InteractiveElement(
                2,
                "textbox",
                "Username",
                "input",
                "text",
                False,
                context="form",
                filled=True,
            ),
            InteractiveElement(
                3,
                "button",
                "Sign in",
                "button",
                None,
                False,
                context="form",
                is_submit=True,
            ),
        ),
    )
    args = (
        step,
        observation,
        {"username": TaskInput(id="username", label="Username", value="qa")},
        [],
        None,
        {(observation.url, "textbox", "Username")},
        set(),
    )
    first = await selector.decide(*args)
    assert isinstance(first.actions[0], ClickInstruction)
    assert first.actions[0].element_id == 3
    assert any(
        "navigation button 'Sign in'" in value for value in client.options.values()
    )
    assert any(
        "form submit button 'Sign in'" in value for value in client.options.values()
    )
    second = await selector.decide(*args)
    assert second.blocked


async def test_blocked_choice_explores_scrollable_content():
    client = FakeClient("Cannot complete this step")
    selector = JevSelector(cast(AsyncTypeSafeClient, client))
    step = Step(id=1, kind="action", instruction="Find a product")
    observation = PageObservation(
        url="https://example.test/catalog",
        title="Catalog",
        elements=(),
        can_scroll_down=True,
    )
    decision = await selector.decide(step, observation, {}, [], None, set(), set())
    assert decision.actions[0].action == "scroll"
    assert decision.actions[0].direction == "down"

    bottom = PageObservation(
        url=observation.url,
        title=observation.title,
        elements=(),
    )
    decision = await selector.decide(step, bottom, {}, [], None, set(), set())
    assert decision.blocked


async def test_jev_matches_visible_form_fields_in_one_request():
    class BatchClient:
        def __init__(self):
            self.calls = 0

        async def system_one(self, *, state, questions):
            self.calls += 1
            assert set(questions) == {"username", "password"}
            assert "secret" not in str(state)
            return SimpleNamespace(
                choices={
                    "username": SimpleNamespace(choice="e1"),
                    "password": SimpleNamespace(choice="e2"),
                },
                usage=SimpleNamespace(input_tokens=120),
                model="jev-1.13.0",
            )

    client = BatchClient()
    selector = JevSelector(cast(AsyncTypeSafeClient, client))
    step = Step(
        id=1,
        kind="action",
        instruction="Log in",
        input_ids=["username", "password"],
    )
    observation = PageObservation(
        url="https://example.test/login",
        title="Login",
        elements=(
            InteractiveElement(1, "textbox", "Username", "input", "text", False),
            InteractiveElement(2, "textbox", "Password", "input", "password", False),
        ),
    )
    decision = await selector.decide(
        step,
        observation,
        {
            "username": TaskInput(id="username", label="Username", value="qa"),
            "password": TaskInput(
                id="password", label="Password", value="secret", sensitive=True
            ),
        },
        [],
        None,
        set(),
        {"secret"},
    )
    assert len(decision.actions) == 1
    assert decision.actions[0].action == "fill_form"
    assert [
        (item.element_id, item.input_id) for item in decision.actions[0].fields
    ] == [
        (1, "username"),
        (2, "password"),
    ]
    assert client.calls == 1
