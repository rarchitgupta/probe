from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from functools import partial
from pathlib import Path
from uuid import uuid4

from pydantic import TypeAdapter

from qa_agent.agent import AgentTask
from qa_agent.runner import (
    AgentTaskResult,
    InspectionTask,
    execute_agent_task,
    execute_inspection,
)
from qa_agent.runs import RunQueueService, SQLiteRunStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qa-agent")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Inspect a page in Chromium")
    inspect.add_argument("url")
    inspect.add_argument("--artifacts", type=Path, default=Path(".runs"))

    run = commands.add_parser("run", help="Run an AI browser QA task")
    run.add_argument("url")
    run.add_argument("goal")
    run.add_argument("--artifacts", type=Path, default=Path(".runs"))
    run.add_argument("--queued", action="store_true")
    run.add_argument("--database", type=Path, default=Path(".qa-agent/qa-agent.db"))
    run.add_argument("--json", action="store_true", dest="json_output")
    return parser


async def execute_queued_task(
    task: AgentTask, database: Path, artifact_root: Path
) -> AgentTaskResult:
    service = RunQueueService(
        SQLiteRunStore(database),
        executor=partial(execute_agent_task, artifact_root=artifact_root),
    )
    await service.start()
    try:
        await service.submit(task)
        await service.join()
        run = service.get(task.task_id)
        if not run or not run.result:
            raise RuntimeError(run.error if run else "Queued run disappeared")
        return TypeAdapter(AgentTaskResult).validate_python(run.result)
    finally:
        await service.close()


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
    tools = result.usage.get("tool_calls")
    cost = result.usage.get("cost")
    metrics = []
    if requests is not None:
        metrics.append(f"{requests} requests")
    if tools is not None:
        metrics.append(f"{tools} tools")
    if cost is not None:
        metrics.append(f"${float(str(cost)):.6f}")
    if metrics:
        lines.extend(("", " · ".join(metrics)))
    lines.append(f"Artifacts: {result.artifact_directory}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "inspect":
        task = InspectionTask(task_id=uuid4().hex, url=args.url)
        result = asyncio.run(execute_inspection(task, artifact_root=args.artifacts))
        print(json.dumps(asdict(result), indent=2))
        raise SystemExit(1 if result.status == "error" else 0)

    task = AgentTask(start_url=args.url, goal=args.goal)
    result = asyncio.run(
        execute_queued_task(task, args.database, args.artifacts)
        if args.queued
        else execute_agent_task(task, artifact_root=args.artifacts)
    )
    print(
        json.dumps(asdict(result), indent=2)
        if args.json_output
        else format_agent_result(result)
    )
    raise SystemExit(0 if result.status == "passed" else 1)
