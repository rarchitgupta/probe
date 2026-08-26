from __future__ import annotations

import io
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from qa_agent.cli import main
from qa_agent.evaluation import BenchmarkMetrics, BenchmarkResult
from qa_agent.runner import AgentTaskResult


class TestCli:
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
            usage={"requests": 4, "cost": "0.00026"},
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
            pytest.raises(SystemExit) as exit_code,
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
        assert str(task.start_url) == "https://example.com/"
        assert task.goal == "Verify checkout"
        assert execute.call_args.kwargs["artifact_root"] == Path("artifacts")
        assert exit_code.value.code == 0
        assert "PASSED  task-1" in output.getvalue()
        assert "4 requests · $0.000260" in output.getvalue()

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
            pytest.raises(SystemExit) as exit_code,
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

        assert execute.call_args.args[1:] == (Path("artifacts"),)
        assert exit_code.value.code == 0

    def test_runs_evaluation_suite_and_writes_report(self) -> None:
        suite = object()
        metrics = BenchmarkMetrics(
            total_trials=1,
            verdict_counts={"true_pass": 1},
            success_rate=1,
            false_pass_rate=0,
            median_duration_ms=100,
            p95_duration_ms=100,
            average_requests=3,
            average_input_tokens=100,
            average_output_tokens=20,
            average_cache_read_tokens=0,
            total_cost=Decimal("0.001"),
            average_cost=Decimal("0.001"),
        )
        result = BenchmarkResult(
            suite_name="smoke",
            suite_version=1,
            trials_per_case=1,
            trials=(),
            metrics=metrics,
        )

        with (
            patch("qa_agent.cli.load_evaluation_suite", return_value=suite),
            patch(
                "qa_agent.cli.run_suite", new=AsyncMock(return_value=result)
            ) as execute,
            patch("qa_agent.cli.write_report") as write,
            redirect_stdout(io.StringIO()) as output,
            pytest.raises(SystemExit) as exit_code,
        ):
            main(
                [
                    "eval",
                    "suite.json",
                    "--trials",
                    "2",
                    "--output",
                    "report.json",
                    "--artifacts",
                    "artifacts",
                ]
            )

        assert execute.call_args.kwargs == {
            "trials_per_case": 2,
            "artifact_root": Path("artifacts"),
        }
        assert write.call_args.args == (result, suite, Path("report.json"))
        assert exit_code.value.code == 0
        assert "Success: 100.0%" in output.getvalue()
        assert "Report: report.json" in output.getvalue()
