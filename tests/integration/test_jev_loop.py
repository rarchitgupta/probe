from types import SimpleNamespace
from typing import cast
from urllib.parse import quote

import pytest
from pydantic_ai import ModelResponse, RunUsage, UsageLimits
from pydantic_ai.models.function import FunctionModel
from typesafe_sdk import AsyncTypeSafeClient

from qa_agent.agent.jev import JevSelector
from qa_agent.agent.loop import run_plan
from qa_agent.agent.planning import TestSpec as Plan
from qa_agent.agent.runtime import AgentDeps
from qa_agent.browser.session import BrowserSession
from qa_agent.policy import ExecutionGuard, ExecutionPolicy

pytestmark = pytest.mark.browser


class FakeJevClient:
    async def system_one(self, *, state, questions):
        choices = questions["next_action"].criteria
        target = (
            "using task input"
            if not state["recent_progress"]
            else "Click button"
            if state["recent_progress"][-1]["action"].startswith("fill_form")
            else "Current step is complete"
        )
        selected = next(key for key, label in choices.items() if target in label)
        return SimpleNamespace(
            choices={"next_action": SimpleNamespace(choice=selected)},
            usage=SimpleNamespace(input_tokens=100),
            model="jev-1.13.0",
        )


async def test_jev_decisions_use_existing_executor_and_pinned_check(tmp_path):
    html = (
        "<label>Username<input></label>"
        "<button onclick=\"document.body.innerHTML='Inventory ready'\">Login</button>"
    )
    url = f"data:text/html,{quote(html)}"
    plan = Plan.model_validate(
        {
            "title": "Login",
            "inputs": [{"id": "username", "label": "Username", "value": "qa-user"}],
            "steps": [
                {
                    "id": 1,
                    "kind": "action",
                    "instruction": "Log in",
                    "input_ids": ["username"],
                },
                {
                    "id": 2,
                    "kind": "assertion",
                    "instruction": "Verify inventory",
                    "check": {
                        "assertion": "text_visible",
                        "expected": "Inventory ready",
                    },
                },
            ],
        }
    )
    selector = JevSelector(cast(AsyncTypeSafeClient, FakeJevClient()))
    async with BrowserSession(trace_path=tmp_path / "trace.zip") as browser:
        await browser.navigate(url)
        deps = AgentDeps(
            browser,
            ExecutionGuard(ExecutionPolicy().for_start_url(url)),
            task_inputs={item.id: item for item in plan.inputs},
        )
        status, summary = await run_plan(
            plan,
            deps,
            model=FunctionModel(lambda _messages, _info: ModelResponse(parts=[])),
            model_settings=None,
            usage=RunUsage(),
            usage_limits=UsageLimits(request_limit=1),
            jev_selector=selector,
        )
    assert status == "passed", (summary, selector.requests, deps.diagnostics)
    assert selector.requests == 2
    assert deps.evidence


async def test_passing_next_check_advances_without_jev_completion(tmp_path):
    class ClickOnlyClient:
        async def system_one(self, *, state, questions):
            choices = questions["next_action"].criteria
            selected = next(
                key
                for key, label in choices.items()
                if "Click button 'Submit'" in label
            )
            return SimpleNamespace(
                choices={"next_action": SimpleNamespace(choice=selected)},
                usage=SimpleNamespace(input_tokens=100),
                model="jev-1.13.0",
            )

    html = "<button onclick=\"document.body.innerHTML='Done'\">Submit</button>"
    url = f"data:text/html,{quote(html)}"
    plan = Plan.model_validate(
        {
            "title": "Submit",
            "steps": [
                {"id": 1, "kind": "action", "instruction": "Submit the form"},
                {
                    "id": 2,
                    "kind": "assertion",
                    "instruction": "Verify success",
                    "check": {"assertion": "text_visible", "expected": "Done"},
                },
            ],
        }
    )
    selector = JevSelector(cast(AsyncTypeSafeClient, ClickOnlyClient()))
    async with BrowserSession(trace_path=tmp_path / "trace.zip") as browser:
        await browser.navigate(url)
        deps = AgentDeps(browser, ExecutionGuard(ExecutionPolicy().for_start_url(url)))
        status, summary = await run_plan(
            plan,
            deps,
            model=FunctionModel(lambda _messages, _info: ModelResponse(parts=[])),
            model_settings=None,
            usage=RunUsage(),
            usage_limits=UsageLimits(request_limit=1),
            jev_selector=selector,
        )
    assert status == "passed", summary
    assert selector.requests == 1
    assert len(deps.evidence) == 1


async def test_blocked_decision_reobserves_after_transient_animation(tmp_path):
    class DelayedClient:
        def __init__(self, browser):
            self.browser = browser
            self.calls = 0

        async def system_one(self, *, state, questions):
            self.calls += 1
            choices = questions["next_action"].criteria
            if self.calls == 1:
                await self.browser.page.evaluate(
                    "() => setTimeout(() => document.querySelector('button').style.opacity = '1', 100)"
                )
            target = "Cannot complete" if self.calls == 1 else "Click button 'Submit'"
            selected = next(key for key, label in choices.items() if target in label)
            return SimpleNamespace(
                choices={"next_action": SimpleNamespace(choice=selected)},
                usage=SimpleNamespace(input_tokens=100),
                model="jev-1.13.0",
            )

    html = "<button style='opacity:0' onclick=\"document.body.innerHTML='Done'\">Submit</button>"
    url = f"data:text/html,{quote(html)}"
    plan = Plan.model_validate(
        {
            "title": "Submit",
            "steps": [
                {"id": 1, "kind": "action", "instruction": "Submit"},
                {
                    "id": 2,
                    "kind": "assertion",
                    "instruction": "Verify success",
                    "check": {"assertion": "text_visible", "expected": "Done"},
                },
            ],
        }
    )
    async with BrowserSession(trace_path=tmp_path / "trace.zip") as browser:
        await browser.navigate(url)
        client = DelayedClient(browser)
        selector = JevSelector(cast(AsyncTypeSafeClient, client))
        deps = AgentDeps(browser, ExecutionGuard(ExecutionPolicy().for_start_url(url)))
        status, summary = await run_plan(
            plan,
            deps,
            model=FunctionModel(lambda _messages, _info: ModelResponse(parts=[])),
            model_settings=None,
            usage=RunUsage(),
            usage_limits=UsageLimits(request_limit=1),
            jev_selector=selector,
        )
    assert status == "passed", summary
    assert client.calls == 2
