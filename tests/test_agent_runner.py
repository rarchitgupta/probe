from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pydantic_ai import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from qa_agent.agent import AgentTask
from qa_agent.runner import execute_agent_task


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


class AgentRunnerTest(unittest.IsolatedAsyncioTestCase):
    async def test_runs_agent_and_writes_artifacts(self) -> None:
        calls = 0

        async def respond(messages: list, info: AgentInfo) -> ModelResponse:
            nonlocal calls
            calls += 1
            if calls == 1:
                return ModelResponse(
                    parts=[
                        ToolCallPart("fill", {"element_id": 1, "value": "Ada"}),
                        ToolCallPart("fill", {"element_id": 2, "value": "London"}),
                    ]
                )
            if calls == 2:
                return ModelResponse(
                    parts=[ToolCallPart("assert_title_equals", {"title": "Form"})]
                )
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        info.output_tools[0].name,
                        {"status": "passed", "summary": "Form verified"},
                    )
                ]
            )

        server = ThreadingHTTPServer(("127.0.0.1", 0), PageHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                task = AgentTask(
                    task_id="agent-run",
                    goal="Fill the name and verify the form",
                    start_url=f"http://127.0.0.1:{server.server_port}",
                )
                result = await execute_agent_task(
                    task,
                    model=FunctionModel(respond),
                    artifact_root=root,
                )
                saved = json.loads((root / task.task_id / "result.json").read_text())

                self.assertIsNone(result.error)
                self.assertTrue((root / task.task_id / "screenshot.png").exists())
                self.assertTrue((root / task.task_id / "trace.zip").exists())
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

        self.assertEqual(result.status, "passed")
        self.assertEqual(result.summary, "Form verified")
        self.assertEqual(result.usage["requests"], 3)
        self.assertEqual(result.diagnostics, ())
        self.assertEqual(saved["diagnostics"], [])
        self.assertNotIn("Ada", json.dumps(saved))
        self.assertNotIn("London", json.dumps(saved))
        self.assertEqual(
            saved["evidence"], ["title_equals: expected='Form', actual='Form'"]
        )
        self.assertNotIn(task.goal, json.dumps(saved))


if __name__ == "__main__":
    unittest.main()
