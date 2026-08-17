from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import AsyncMock, patch

from qa_agent.cli import main
from qa_agent.runner import AgentTaskResult


class CliTest(unittest.TestCase):
    def test_runs_agent_with_readable_output(self) -> None:
        result = AgentTaskResult(
            task_id="task-1",
            status="passed",
            start_url="https://example.com/",
            final_url="https://example.com/done",
            http_status=200,
            summary="Checkout works",
            evidence=("text_visible: Order confirmed",),
            diagnostics=(),
            usage={"requests": 4, "tool_calls": 5, "cost": "0.00026"},
            error=None,
            artifact_directory=".runs/task-1",
        )

        output = io.StringIO()
        with (
            patch(
                "qa_agent.cli.execute_agent_task",
                new=AsyncMock(return_value=result),
            ) as execute,
            redirect_stdout(output),
            self.assertRaises(SystemExit) as exit_code,
        ):
            main(
                [
                    "run",
                    "https://example.com/",
                    "Verify checkout",
                    "--artifacts",
                    "artifacts",
                ]
            )

        task = execute.call_args.args[0]
        self.assertEqual(str(task.start_url), "https://example.com/")
        self.assertEqual(task.goal, "Verify checkout")
        self.assertEqual(execute.call_args.kwargs["artifact_root"], Path("artifacts"))
        self.assertEqual(exit_code.exception.code, 0)
        self.assertIn("PASSED  task-1", output.getvalue())
        self.assertIn("4 requests · 5 tools · $0.000260", output.getvalue())

    def test_runs_agent_through_queue(self) -> None:
        result = AgentTaskResult(
            task_id="task-2",
            status="passed",
            start_url="https://example.com/",
            final_url="https://example.com/done",
            http_status=200,
            summary="Queued run passed",
            evidence=(),
            diagnostics=(),
            usage={},
            error=None,
            artifact_directory="artifacts/task-2",
        )

        with (
            patch(
                "qa_agent.cli.execute_queued_task",
                new=AsyncMock(return_value=result),
            ) as execute,
            redirect_stdout(io.StringIO()),
            self.assertRaises(SystemExit) as exit_code,
        ):
            main(
                [
                    "run",
                    "https://example.com/",
                    "Verify checkout",
                    "--queued",
                    "--artifacts",
                    "artifacts",
                ]
            )

        self.assertEqual(execute.call_args.args[1:], (Path("artifacts"),))
        self.assertEqual(exit_code.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
