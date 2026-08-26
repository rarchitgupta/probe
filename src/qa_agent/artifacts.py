from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ArtifactPaths:
    run: Path
    result: Path
    screenshot: Path
    trace: Path
    video: Path

    @classmethod
    def create(cls, root: Path, task_id: str) -> ArtifactPaths:
        run = root / task_id
        run.mkdir(parents=True, exist_ok=False)
        return cls(
            run=run,
            result=run / "result.json",
            screenshot=run / "screenshot.png",
            trace=run / "trace.zip",
            video=run / "replay.webm",
        )

    def write_result(self, data: dict[str, Any]) -> None:
        self.result.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
