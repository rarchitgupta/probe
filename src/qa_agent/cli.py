from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from qa_agent.runner import InspectionTask, execute_inspection


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qa-agent")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Inspect a page in Chromium")
    inspect.add_argument("url")
    inspect.add_argument("--artifacts", type=Path, default=Path(".runs"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "inspect":
        task = InspectionTask(task_id=uuid4().hex, url=args.url)
        result = asyncio.run(execute_inspection(task, artifact_root=args.artifacts))
        print(json.dumps(asdict(result), indent=2))
        raise SystemExit(1 if result.status == "error" else 0)
