from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from qa_agent.artifacts import ArtifactPaths
from qa_agent.browser import InteractiveElement, inspect_page


@dataclass(frozen=True)
class InspectionTask:
    task_id: str
    url: str


@dataclass(frozen=True)
class InspectionResult:
    task_id: str
    status: Literal["completed", "error"]
    started_at: str
    finished_at: str
    requested_url: str
    final_url: str | None
    title: str | None
    http_status: int | None
    elements: tuple[InteractiveElement, ...]
    console_errors: tuple[str, ...]
    failed_requests: tuple[str, ...]
    error: str | None
    artifact_directory: str


async def execute_inspection(
    task: InspectionTask,
    *,
    artifact_root: Path = Path(".runs"),
) -> InspectionResult:
    started_at = datetime.now(UTC).isoformat()
    artifacts = ArtifactPaths.create(artifact_root, task.task_id)
    observation = await inspect_page(
        task.url,
        screenshot_path=artifacts.screenshot,
        trace_path=artifacts.trace,
    )
    result = InspectionResult(
        task_id=task.task_id,
        status="error" if observation.error else "completed",
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        requested_url=observation.requested_url,
        final_url=observation.final_url,
        title=observation.title,
        http_status=observation.http_status,
        elements=observation.elements,
        console_errors=observation.console_errors,
        failed_requests=observation.failed_requests,
        error=observation.error,
        artifact_directory=str(artifacts.run),
    )
    artifacts.write_result(asdict(result))
    return result
