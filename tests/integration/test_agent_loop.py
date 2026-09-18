import json
from unittest.mock import patch
from urllib.parse import quote

import pytest
from pydantic_ai import ModelResponse, RunUsage, ToolCallPart, UsageLimits
from pydantic_ai.models.function import FunctionModel

from qa_agent.agent.loop import run_plan
from qa_agent.agent.planning import TestSpec as Plan
from qa_agent.agent.runtime import AgentDeps
from qa_agent.browser import BrowserSession
from qa_agent.policy import ExecutionGuard, ExecutionPolicy

pytestmark = pytest.mark.browser


async def test_field_memory_survives_scroll_history_and_clears_after_step(tmp_path):
    url = f"data:text/html,{quote('<title>Form</title><label>Name<input></label><div style="height:2000px"></div>')}"
    plan = Plan.model_validate(
        {
            "title": "Fill and verify",
            "inputs": [{"id": "name", "label": "Name", "value": "Ada"}],
            "steps": [
                {
                    "id": 1,
                    "kind": "action",
                    "instruction": "Fill Name",
                    "input_ids": ["name"],
                },
                {"id": 2, "kind": "action", "instruction": "Finish the flow"},
                {
                    "id": 3,
                    "kind": "assertion",
                    "instruction": "Verify Form title",
                    "check": {"assertion": "title_equals", "expected": "Form"},
                },
            ],
        }
    )
    calls = 0

    async def respond(messages, info):
        nonlocal calls
        calls += 1
        state = json.loads(messages[-1].parts[-1].content)
        if calls == 1:
            actions = [
                {
                    "action": "fill_form",
                    "fields": [{"element_id": 1, "input_id": "name"}],
                }
            ]
        elif calls <= 11:
            actions = [
                {"action": "scroll", "direction": "down" if calls % 2 == 0 else "up"}
            ]
        elif calls == 12:
            assert all(item["action"] == "scroll" for item in state["recent_progress"])
            assert state["successful_field_updates"] == [
                {"url": url, "role": "textbox", "name": "Name"}
            ]
            assert "5 times" in state["feedback"]
            actions = []
        else:
            assert state["successful_field_updates"] == []
            actions = []
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "actions": actions,
                        "step_complete": calls >= 12,
                    },
                )
            ]
        )

    async with BrowserSession(trace_path=tmp_path / "trace.zip") as browser:
        await browser.navigate(url)
        deps = AgentDeps(
            browser,
            ExecutionGuard(ExecutionPolicy().for_start_url(url)),
            task_inputs={item.id: item for item in plan.inputs},
        )
        status, _ = await run_plan(
            plan,
            deps,
            model=FunctionModel(respond),
            model_settings=None,
            usage=RunUsage(),
            usage_limits=UsageLimits(request_limit=15),
        )
    assert status == "passed"
    assert calls == 13


async def test_wait_reobserves_without_completing_step(tmp_path):
    url = f"data:text/html,{quote('<title>Loading</title><script>setTimeout(() => document.title = "Ready", 25)</script>')}"
    plan = Plan.model_validate(
        {
            "title": "Wait and verify",
            "steps": [
                {
                    "id": 1,
                    "kind": "assertion",
                    "instruction": "Verify Ready title",
                    "check": {"assertion": "title_equals", "expected": "Ready"},
                }
            ],
        }
    )
    calls = 0

    async def respond(messages, info):
        nonlocal calls
        calls += 1
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "actions": [{"action": "wait"}],
                        "step_complete": True,
                    },
                )
            ]
        )

    async with BrowserSession(trace_path=tmp_path / "trace.zip") as browser:
        await browser.navigate(url)
        deps = AgentDeps(browser, ExecutionGuard(ExecutionPolicy().for_start_url(url)))
        status, _ = await run_plan(
            plan,
            deps,
            model=FunctionModel(respond),
            model_settings=None,
            usage=RunUsage(),
            usage_limits=UsageLimits(request_limit=3),
        )
    assert status == "passed"
    assert calls == 0
    assert len(deps.evidence) == 1


async def test_failed_pinned_check_cannot_be_weakened_or_retried(tmp_path):
    url = f"data:text/html,{quote('<p>Mechanical Keyboard</p>')}"
    plan = Plan.model_validate(
        {
            "title": "Verify quantity",
            "steps": [
                {
                    "id": 1,
                    "kind": "assertion",
                    "instruction": "Verify two keyboards",
                    "check": {
                        "assertion": "region_contains",
                        "anchor": "Mechanical Keyboard",
                        "expected": ["2"],
                    },
                }
            ],
        }
    )
    calls = 0
    feedback: list[str | None] = []

    async def respond(messages, info):
        nonlocal calls
        calls += 1
        state = json.loads(messages[-1].parts[-1].content)
        feedback.append(state["feedback"])
        output = {"actions": [{"action": "scroll", "direction": "down"}]}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    async with BrowserSession(trace_path=tmp_path / "trace.zip") as browser:
        await browser.navigate(url)
        deps = AgentDeps(browser, ExecutionGuard(ExecutionPolicy().for_start_url(url)))
        with patch("qa_agent.agent.loop.MAX_AGENT_ROUNDS", 2):
            status, _ = await run_plan(
                plan,
                deps,
                model=FunctionModel(respond),
                model_settings=None,
                usage=RunUsage(),
                usage_limits=UsageLimits(request_limit=3),
            )

    assert status == "failed"
    assert calls == 2
    assert "already failed on this unchanged page" in (feedback[1] or "")
    assert deps.evidence == []


async def test_global_loop_recovers_and_requires_fresh_assertions(tmp_path):
    # Same link must work again after returning; repeated clicks also increment state.
    html = """
    <title>Catalog</title><button onclick="document.title =
    document.title === 'Catalog' ? 'Product' : 'Catalog'">Open</button>
    <button onclick="document.querySelector('output').textContent++">Increase</button>
    <output>0</output>
    """
    url = f"data:text/html,{quote(html)}"
    plan = Plan.model_validate(
        {
            "title": "Navigate and verify",
            "steps": [
                {
                    "id": 1,
                    "kind": "action",
                    "instruction": "Recover and increase quantity",
                },
                {
                    "id": 2,
                    "kind": "assertion",
                    "instruction": "Verify Product title",
                    "check": {"assertion": "title_equals", "expected": "Product"},
                },
                {
                    "id": 3,
                    "kind": "assertion",
                    "instruction": "Verify quantity 4",
                    "check": {
                        "assertion": "text_visible",
                        "expected": "4",
                        "exact": True,
                    },
                },
            ],
        }
    )
    calls = 0

    async def respond(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            # A failed action must not poison later completion.
            actions = [{"action": "click", "element_id": 999}]
        elif calls <= 4:
            actions = [{"action": "click", "element_id": 1}]
        elif calls <= 8:
            actions = [{"action": "click", "element_id": 2}]
        else:
            actions = []
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "actions": actions,
                        "step_complete": calls >= 8,
                    },
                )
            ]
        )

    async with BrowserSession(trace_path=tmp_path / "trace.zip") as browser:
        await browser.navigate(url)
        deps = AgentDeps(browser, ExecutionGuard(ExecutionPolicy().for_start_url(url)))
        status, summary = await run_plan(
            plan,
            deps,
            model=FunctionModel(respond),
            model_settings=None,
            usage=RunUsage(),
            usage_limits=UsageLimits(request_limit=45),
        )
        assert browser.page is not None
        assert await browser.page.locator("output").inner_text() == "4"
    assert status == "passed"
    assert len(deps.evidence) == 2
    assert deps.failure_category is None
    assert calls == 8
