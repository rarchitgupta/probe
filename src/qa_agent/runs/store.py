from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from qa_agent.agent.planning import AgentTask, ProgressEntry
from qa_agent.agent.runner import AgentTaskResult
from qa_agent.artifacts import ArtifactStorage, artifact_storage
from qa_agent.configuration import AgentConfiguration
from qa_agent.database import async_session_factory
from qa_agent.environments import EnvironmentDefinition, EnvironmentProfile
from qa_agent.failures import FailureCategory
from qa_agent.runs.models import (
    RunArtifactRecord,
    RunEventKind,
    RunEventRecord,
    RunStatus,
    TaskRunRecord,
    TestEnvironmentRecord,
)

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {
    RunStatus.PASSED,
    RunStatus.FAILED,
    RunStatus.BLOCKED,
    RunStatus.ERROR,
}


class InvalidRunTransitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class TaskRun:
    id: str
    title: str | None
    start_url: str
    goal: str
    status: RunStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: AgentTaskResult | None = None
    error: str | None = None
    failure_category: FailureCategory | None = None
    events: tuple[RunEvent, ...] = ()
    artifacts: tuple[RunArtifact, ...] = ()
    environment_id: str | None = None


@dataclass(frozen=True)
class RunArtifact:
    id: str
    run_id: str
    kind: str
    storage: str
    path: str
    content_type: str
    size_bytes: int
    created_at: datetime


@dataclass(frozen=True)
class RunEvent:
    id: int
    kind: RunEventKind
    created_at: datetime
    status: RunStatus | None
    action: str | None
    element: str | None
    success: bool | None
    message: str | None


class RunStore:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession] = async_session_factory,
        artifacts: ArtifactStorage | None = None,
    ) -> None:
        self.sessions = sessions
        self.artifacts = artifacts or artifact_storage()

    async def create(self, task: AgentTask) -> TaskRun:
        record = TaskRunRecord(
            id=task.task_id,
            start_url=str(task.start_url),
            goal=task.goal,
            environment_id=task.environment_id,
            status=RunStatus.QUEUED,
        )
        async with self.sessions.begin() as session:
            session.add(record)
            await session.flush()
            session.add(_status_event(record.id, RunStatus.QUEUED))
        return _task_run(record)

    async def get(self, run_id: str) -> TaskRun | None:
        async with self.sessions() as session:
            record = await session.get(TaskRunRecord, run_id)
            return _task_run(record) if record else None

    async def list_runs(
        self,
        *,
        status: RunStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[TaskRun]:
        query = select(TaskRunRecord)
        if status is not None:
            query = query.where(TaskRunRecord.status == status)
        query = (
            query.order_by(TaskRunRecord.created_at.desc(), TaskRunRecord.id.desc())
            .limit(limit)
            .offset(offset)
        )
        async with self.sessions() as session:
            records = (await session.scalars(query)).all()
        return [_task_run(record) for record in records]

    async def create_environment(
        self,
        *,
        name: str,
        definition: EnvironmentDefinition,
        viewport_width: int,
        viewport_height: int,
    ) -> EnvironmentProfile:
        record = TestEnvironmentRecord(
            id=uuid4().hex,
            name=name,
            definition=definition.model_dump(mode="json"),
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )
        async with self.sessions.begin() as session:
            session.add(record)
        return _test_environment(record)

    async def get_environment(self, environment_id: str) -> EnvironmentProfile | None:
        async with self.sessions() as session:
            record = await session.get(TestEnvironmentRecord, environment_id)
            return _test_environment(record) if record else None

    async def list_environments(self) -> list[EnvironmentProfile]:
        async with self.sessions() as session:
            records = (
                await session.scalars(
                    select(TestEnvironmentRecord).order_by(TestEnvironmentRecord.name)
                )
            ).all()
        return [_test_environment(record) for record in records]

    async def get_details(self, run_id: str) -> TaskRun | None:
        async with self.sessions() as session:
            record = await session.get(TaskRunRecord, run_id)
            if not record:
                return None
            events = (
                await session.scalars(
                    select(RunEventRecord)
                    .where(RunEventRecord.run_id == run_id)
                    .order_by(RunEventRecord.id)
                )
            ).all()
            artifacts = (
                await session.scalars(
                    select(RunArtifactRecord)
                    .where(RunArtifactRecord.run_id == run_id)
                    .order_by(RunArtifactRecord.created_at, RunArtifactRecord.id)
                )
            ).all()
            return _task_run(record, list(events), list(artifacts))

    async def get_artifact(self, run_id: str, artifact_id: str) -> RunArtifact | None:
        async with self.sessions() as session:
            record = await session.get(RunArtifactRecord, artifact_id)
            return _run_artifact(record) if record and record.run_id == run_id else None

    async def add_progress(self, run_id: str, progress: ProgressEntry) -> None:
        async with self.sessions.begin() as session:
            session.add(
                RunEventRecord(
                    run_id=run_id,
                    kind=RunEventKind.ACTION,
                    action=progress.action,
                    element=progress.target,
                    success=progress.success,
                    message=progress.error or progress.effect,
                )
            )

    async def list_events(self, run_id: str, *, after: int = 0) -> list[RunEvent]:
        async with self.sessions() as session:
            if not await session.get(TaskRunRecord, run_id):
                raise KeyError(run_id)
            records = (
                await session.scalars(
                    select(RunEventRecord)
                    .where(
                        RunEventRecord.run_id == run_id,
                        RunEventRecord.id > after,
                    )
                    .order_by(RunEventRecord.id)
                )
            ).all()
        return [_run_event(record) for record in records]

    async def mark_running(self, run_id: str) -> TaskRun:
        return await self._transition(
            run_id,
            RunStatus.QUEUED,
            RunStatus.RUNNING,
            started_at=datetime.now(UTC),
        )

    async def finish(
        self,
        run_id: str,
        status: RunStatus,
        *,
        result: AgentTaskResult | None = None,
        error: str | None = None,
    ) -> TaskRun:
        if status not in TERMINAL_STATUSES:
            raise ValueError(f"{status} is not a completion status")
        usage = result.usage if result else {}
        values = {
            "title": result.title if result else None,
            "finished_at": datetime.now(UTC),
            "final_url": result.final_url if result else None,
            "http_status": result.http_status if result else None,
            "summary": result.summary if result else None,
            "error": error,
            "failure_category": (
                result.failure_category
                if result
                else FailureCategory.INFRASTRUCTURE_ERROR
                if error
                else None
            ),
            "artifact_directory": result.artifact_directory if result else None,
            "model_name": (
                result.configuration.model if result and result.configuration else None
            ),
            "prompt_version": (
                result.configuration.prompt_version
                if result and result.configuration
                else None
            ),
            "model_config_version": (
                result.configuration.model_config_version
                if result and result.configuration
                else None
            ),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "cache_read_tokens": usage.get("cache_read_tokens"),
            "request_count": usage.get("requests"),
            "cost": Decimal(str(usage["cost"])) if usage.get("cost") else None,
        }
        video = await self._video_artifact(run_id, result)
        async with self.sessions.begin() as session:
            record = await self._update(
                session, run_id, RunStatus.RUNNING, status, values
            )
            session.add(
                _status_event(
                    run_id, status, (result.summary if result else None) or error
                )
            )
            session.add_all(
                RunEventRecord(
                    run_id=run_id,
                    kind=RunEventKind.ASSERTION,
                    success=True,
                    message=str(evidence),
                )
                for evidence in (result.evidence if result else ())
            )
            if video:
                session.add(video)
        return _task_run(record, artifacts=[video] if video else None)

    async def _video_artifact(
        self, run_id: str, result: AgentTaskResult | None
    ) -> RunArtifactRecord | None:
        if not result:
            return None
        path = Path(result.artifact_directory) / "replay.webm"
        if not path.is_file():
            return None
        try:
            stored = await self.artifacts.store(
                path, f"runs/{run_id}/replay.webm", "video/webm"
            )
        except Exception:
            logger.exception("Failed to store replay for run %s", run_id)
            return None
        return RunArtifactRecord(
            id=uuid4().hex,
            run_id=run_id,
            kind="video",
            storage=stored.storage,
            path=stored.key,
            content_type="video/webm",
            size_bytes=stored.size_bytes,
        )

    async def cancel(self, run_id: str) -> TaskRun:
        return await self._transition(
            run_id,
            (RunStatus.QUEUED, RunStatus.RUNNING),
            RunStatus.CANCELLED,
            finished_at=datetime.now(UTC),
        )

    async def fail_submission(self, run_id: str, error: str) -> TaskRun:
        return await self._transition(
            run_id,
            RunStatus.QUEUED,
            RunStatus.ERROR,
            finished_at=datetime.now(UTC),
            error=error,
            failure_category=FailureCategory.INFRASTRUCTURE_ERROR,
        )

    async def recover_pending(self) -> list[TaskRun]:
        async with self.sessions.begin() as session:
            await session.execute(
                update(TaskRunRecord)
                .where(TaskRunRecord.status == RunStatus.RUNNING)
                .values(
                    status=RunStatus.ERROR,
                    finished_at=datetime.now(UTC),
                    error="Worker stopped before the run completed",
                    failure_category=FailureCategory.INFRASTRUCTURE_ERROR,
                )
            )
            records = (
                await session.scalars(
                    select(TaskRunRecord)
                    .where(TaskRunRecord.status == RunStatus.QUEUED)
                    .order_by(TaskRunRecord.created_at, TaskRunRecord.id)
                )
            ).all()
            return [_task_run(record) for record in records]

    async def _transition(
        self,
        run_id: str,
        source: RunStatus | tuple[RunStatus, ...],
        target: RunStatus,
        **values: object,
    ) -> TaskRun:
        async with self.sessions.begin() as session:
            record = await self._update(session, run_id, source, target, values)
            session.add(_status_event(run_id, target))
        return _task_run(record)

    @staticmethod
    async def _update(
        session: AsyncSession,
        run_id: str,
        source: RunStatus | tuple[RunStatus, ...],
        target: RunStatus,
        values: dict[str, object],
    ) -> TaskRunRecord:
        source_condition = (
            TaskRunRecord.status.in_(source)
            if isinstance(source, tuple)
            else TaskRunRecord.status == source
        )
        result = await session.execute(
            update(TaskRunRecord)
            .where(TaskRunRecord.id == run_id, source_condition)
            .values(status=target, **values)
            .returning(TaskRunRecord)
        )
        record = result.scalar_one_or_none()
        if record:
            return record
        if not await session.get(TaskRunRecord, run_id):
            raise KeyError(f"Unknown run {run_id!r}")
        raise InvalidRunTransitionError(f"Cannot move run {run_id!r} to {target!r}")


def _status_event(
    run_id: str, status: RunStatus, message: object | None = None
) -> RunEventRecord:
    return RunEventRecord(
        run_id=run_id,
        kind=RunEventKind.STATUS,
        status=status,
        message=str(message or f"Run {status}"),
    )


def _run_event(record: RunEventRecord) -> RunEvent:
    return RunEvent(
        id=record.id,
        kind=record.kind,
        created_at=record.created_at,
        status=record.status,
        action=record.action,
        element=record.element,
        success=record.success,
        message=record.message,
    )


def _task_run(
    record: TaskRunRecord,
    events: list[RunEventRecord] | None = None,
    artifacts: list[RunArtifactRecord] | None = None,
) -> TaskRun:
    run_events = tuple(_run_event(event) for event in events or ())
    result = None
    if record.artifact_directory:
        evidence = [
            event.message
            for event in events or ()
            if event.kind == RunEventKind.ASSERTION and event.message
        ]
        usage = {
            "input_tokens": record.input_tokens,
            "output_tokens": record.output_tokens,
            "cache_read_tokens": record.cache_read_tokens,
            "requests": record.request_count,
            "cost": str(record.cost) if record.cost is not None else None,
        }
        result = AgentTaskResult(
            task_id=record.id,
            status=cast(
                Literal["passed", "failed", "blocked", "error"],
                record.status.value,
            ),
            start_url=record.start_url,
            final_url=record.final_url,
            http_status=record.http_status,
            summary=record.summary,
            evidence=tuple(evidence),
            diagnostics=(),
            usage={key: value for key, value in usage.items() if value is not None},
            error=record.error,
            artifact_directory=record.artifact_directory,
            title=record.title,
            failure_category=record.failure_category,
            configuration=(
                AgentConfiguration(
                    model=record.model_name,
                    prompt_version=record.prompt_version,
                    model_config_version=record.model_config_version,
                )
                if record.model_name
                and record.prompt_version
                and record.model_config_version
                else None
            ),
        )
    return TaskRun(
        id=record.id,
        title=record.title,
        start_url=record.start_url,
        goal=record.goal,
        status=record.status,
        created_at=record.created_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
        result=result,
        error=record.error,
        failure_category=record.failure_category,
        events=run_events,
        artifacts=tuple(_run_artifact(artifact) for artifact in artifacts or ()),
        environment_id=record.environment_id,
    )


def _run_artifact(record: RunArtifactRecord) -> RunArtifact:
    return RunArtifact(
        id=record.id,
        run_id=record.run_id,
        kind=record.kind,
        storage=record.storage,
        path=record.path,
        content_type=record.content_type,
        size_bytes=record.size_bytes,
        created_at=record.created_at,
    )


def _test_environment(record: TestEnvironmentRecord) -> EnvironmentProfile:
    return EnvironmentProfile(
        id=record.id,
        name=record.name,
        definition=EnvironmentDefinition.model_validate(record.definition),
        viewport_width=record.viewport_width,
        viewport_height=record.viewport_height,
        created_at=record.created_at,
    )
