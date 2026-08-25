from __future__ import annotations

import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import httpx2
import pytest
from openai import APITimeoutError
from pydantic_ai import ModelAPIError, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from qa_agent.agent import AgentTask
from qa_agent.evaluation import EvaluationCase, run_trial
from qa_agent.failures import FailureCategory
from qa_agent.runner import execute_agent_task

pytestmark = pytest.mark.browser


class PageHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = (
            b'<title>Form</title><label for="name">Name</label><input id="name">'
            b'<label for="city">City</label><input id="city">'
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


class TestAgentRunner:
    async def test_preserves_diagnostics_when_model_times_out(self) -> None:
        calls = 0

        async def respond(messages: list, info: AgentInfo) -> ModelResponse:
            nonlocal calls
            calls += 1
            if calls == 1:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            info.output_tools[0].name,
                            {
                                "title": "Fill Example Form",
                                "steps": [
                                    {
                                        "id": 1,
                                        "kind": "action",
                                        "instruction": "Fill the name",
                                    },
                                    {
                                        "id": 2,
                                        "kind": "assertion",
                                        "instruction": "Verify the title",
                                    },
                                ],
                            },
                        )
                    ]
                )
            if calls == 2:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            info.output_tools[0].name,
                            {
                                "actions": [
                                    {
                                        "action": "fill_form",
                                        "fields": [{"element_id": 1, "value": "Ada"}],
                                    }
                                ],
                                "step_complete": True,
                            },
                        )
                    ]
                )
            timeout = APITimeoutError(request=httpx2.Request("POST", "https://model"))
            raise ModelAPIError("deepseek-v4-flash", timeout.message) from timeout

        server = ThreadingHTTPServer(("127.0.0.1", 0), PageHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                result = await execute_agent_task(
                    AgentTask(
                        task_id="timed-out-run",
                        goal="Fill the form",
                        start_url=f"http://127.0.0.1:{server.server_port}",
                    ),
                    model=FunctionModel(respond),
                    artifact_root=Path(directory),
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

        assert result.error == "Model request timed out after 60 seconds"
        assert result.failure_category == FailureCategory.MODEL_TIMEOUT
        assert result.configuration is not None
        assert result.configuration.prompt_version == "1"
        assert result.configuration.model_config_version == "1"
        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].action == "fill"

    async def test_runs_agent_and_writes_artifacts(self) -> None:
        calls = 0

        async def respond(messages: list, info: AgentInfo) -> ModelResponse:
            nonlocal calls
            calls += 1
            if calls == 1:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            info.output_tools[0].name,
                            {
                                "title": "Fill Example Form",
                                "steps": [
                                    {
                                        "id": 1,
                                        "kind": "action",
                                        "instruction": "Fill the form",
                                    },
                                    {
                                        "id": 2,
                                        "kind": "assertion",
                                        "instruction": "Verify the title",
                                    },
                                ],
                            },
                        )
                    ]
                )
            if calls == 2:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            info.output_tools[0].name,
                            {
                                "actions": [
                                    {
                                        "action": "fill_form",
                                        "fields": [
                                            {"element_id": 1, "value": "Ada"},
                                            {"element_id": 2, "value": "London"},
                                        ],
                                    },
                                ],
                                "step_complete": True,
                            },
                        )
                    ]
                )
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        info.output_tools[0].name,
                        {
                            "actions": [
                                {
                                    "action": "assert_title_equals",
                                    "expected": "Form",
                                }
                            ],
                            "step_complete": False,
                        },
                    )
                ]
            )

        server = ThreadingHTTPServer(("127.0.0.1", 0), PageHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                case = EvaluationCase.model_validate(
                    {
                        "id": "fill-example-form",
                        "name": "Fill example form",
                        "start_url": f"http://127.0.0.1:{server.server_port}",
                        "goal": "Fill the name and verify the form",
                        "checks": [
                            {
                                "assertion": "text_visible",
                                "expected": "This outcome is intentionally absent",
                            }
                        ],
                    }
                )
                with patch.dict("os.environ", {"PROBE_DIAGNOSTICS": "false"}):
                    trial = await run_trial(
                        case,
                        model=FunctionModel(respond),
                        artifact_root=root,
                        grader_timeout_ms=50,
                    )
                run_directory = Path(trial.artifact_directory)
                saved = json.loads((run_directory / "result.json").read_text())

                assert trial.error is None
                assert (run_directory / "screenshot.png").exists()
                assert (run_directory / "trace.zip").exists()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

        assert trial.agent_status == "passed"
        assert trial.oracle_passed is False
        assert trial.verdict == "false_pass"
        assert trial.failure_category is None
        assert trial.configuration is not None
        assert trial.duration_ms is not None
        assert trial.duration_ms > 0
        assert saved["summary"] == "Completed all 2 test steps"
        assert saved["title"] == "Fill Example Form"
        assert trial.usage["requests"] == 3
        assert saved["diagnostics"] == []
        assert "Ada" not in json.dumps(saved)
        assert "London" not in json.dumps(saved)
        assert saved["evidence"] == ["title_equals: expected='Form', actual='Form'"]
        assert case.goal not in json.dumps(saved)
