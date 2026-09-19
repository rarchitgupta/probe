from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from qa_agent.agent.planning import AgentTask
from qa_agent.agent.runner import AgentTaskResult, execute_agent_task
from qa_agent.evaluation.models import (
    BenchmarkComparison,
    BenchmarkResult,
    load_evaluation_suite,
)
from qa_agent.evaluation.reporting import compare_reports, load_report, write_report
from qa_agent.evaluation.runner import run_suite
from qa_agent.llm import OPENAI_MODEL_NAME


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="probe")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run an AI browser QA task")
    run.add_argument("url")
    run.add_argument("goal")
    run.add_argument("--artifacts", type=Path, default=Path(".runs"))
    run.add_argument("--json", action="store_true", dest="json_output")

    evaluate = commands.add_parser("eval", help="Run a browser QA evaluation suite")
    evaluate.add_argument("suite", type=Path)
    evaluate.add_argument("--trials", type=_positive_int, default=1)
    evaluate.add_argument("--output", type=Path)
    evaluate.add_argument("--baseline", type=Path)
    evaluate.add_argument("--artifacts", type=Path, default=Path(".eval-runs"))
    return parser


def format_agent_result(result: AgentTaskResult) -> str:
    lines = [f"{result.status.upper()}  {result.task_id}"]
    if result.summary:
        lines.extend(("", result.summary))
    if result.error:
        lines.extend(("", f"Error: {result.error}"))
    if result.evidence:
        lines.extend(("", "Evidence:"))
        lines.extend(f"  - {item}" for item in result.evidence)

    requests = result.usage.get("requests")
    cost = result.usage.get("cost")
    metrics = []
    if requests is not None:
        metrics.append(f"{requests} requests")
    if cost is not None:
        metrics.append(f"${float(str(cost)):.6f}")
    if metrics:
        lines.extend(("", " · ".join(metrics)))
    lines.append(f"Artifacts: {result.artifact_directory}")
    return "\n".join(lines)


def format_benchmark_result(
    result: BenchmarkResult,
    report_path: Path,
    comparison: BenchmarkComparison | None = None,
) -> str:
    metrics = result.metrics
    lines = [
        f"EVALUATED  {metrics.total_trials} trials",
        f"Success: {metrics.success_rate:.1%}",
        f"False passes: {metrics.false_pass_rate:.1%}",
        f"Median / p95: {metrics.median_duration_ms} / {metrics.p95_duration_ms} ms",
        f"Average requests: {metrics.average_requests:.2f}",
        f"Total cost: ${metrics.total_cost}",
        f"Report: {report_path}",
    ]
    if comparison:
        status = "REGRESSION" if comparison.quality_regressed else "NO REGRESSION"
        lines.extend(
            (
                "",
                f"Baseline: {status}",
                f"Success delta: {comparison.deltas.success_rate:+.1%}",
                f"False-pass delta: {comparison.deltas.false_pass_rate:+.1%}",
                f"Average cost delta: ${comparison.deltas.average_cost:+}",
            )
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "eval":
        output = args.output or _default_report_path(args.suite)
        if args.baseline and output.resolve() == args.baseline.resolve():
            raise SystemExit("Output path cannot overwrite the baseline report")
        suite = load_evaluation_suite(args.suite)
        result = asyncio.run(
            run_suite(
                suite,
                trials_per_case=args.trials,
                artifact_root=args.artifacts,
            )
        )
        write_report(result, suite, output, model_name=OPENAI_MODEL_NAME)
        comparison = (
            compare_reports(load_report(args.baseline), load_report(output))
            if args.baseline
            else None
        )
        print(format_benchmark_result(result, output, comparison))
        raise SystemExit(1 if comparison and comparison.quality_regressed else 0)

    task = AgentTask(start_url=args.url, goal=args.goal)
    result = asyncio.run(execute_agent_task(task, artifact_root=args.artifacts))
    print(
        json.dumps(asdict(result), indent=2)
        if args.json_output
        else format_agent_result(result)
    )
    raise SystemExit(0 if result.status == "passed" else 1)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _default_report_path(suite_path: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path(".eval-reports") / f"{suite_path.stem}-{timestamp}.json"
