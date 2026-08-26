from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress

from qa_agent.agent import AgentTask, ProgressEntry
from qa_agent.environments import EnvironmentDefinition, EnvironmentProfile
from qa_agent.runner import AgentTaskResult, execute_agent_task
from qa_agent.runs.store import RunArtifact, RunEvent, RunStatus, RunStore, TaskRun

RunExecutor = Callable[[AgentTask], Awaitable[AgentTaskResult]]


class RunQueueService:
    # ponytail: one in-process worker; use an external broker for multi-process workers.
    def __init__(
        self,
        store: RunStore,
        executor: RunExecutor | None = None,
    ) -> None:
        self.store = store
        self.executor = executor
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._active_run_id: str | None = None
        self._active_task: asyncio.Task[None] | None = None
        self._updates = asyncio.Condition()
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    async def wait_for_update(self, version: int, timeout: float = 15) -> int | None:
        async with self._updates:
            try:
                await asyncio.wait_for(
                    self._updates.wait_for(lambda: self._version > version), timeout
                )
            except TimeoutError:
                return None
            return self._version

    async def start(self) -> None:
        if self._worker:
            return
        for run in await self.store.recover_pending():
            self._queue.put_nowait(run.id)
        self._worker = asyncio.create_task(self._work(), name="probe-worker")

    async def submit(self, task: AgentTask) -> TaskRun:
        if not self._worker:
            raise RuntimeError("RunQueueService must be started before submission")
        run = await self.store.create(task)
        await self._queue.put(run.id)
        await self._publish()
        return run

    async def get(self, run_id: str) -> TaskRun | None:
        return await self.store.get(run_id)

    async def get_details(self, run_id: str) -> TaskRun | None:
        return await self.store.get_details(run_id)

    async def list_runs(
        self,
        *,
        status: RunStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[TaskRun]:
        return await self.store.list_runs(status=status, limit=limit, offset=offset)

    async def list_events(self, run_id: str, *, after: int = 0) -> list[RunEvent]:
        return await self.store.list_events(run_id, after=after)

    async def create_environment(
        self,
        *,
        name: str,
        definition: EnvironmentDefinition,
        viewport_width: int,
        viewport_height: int,
    ) -> EnvironmentProfile:
        return await self.store.create_environment(
            name=name,
            definition=definition,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )

    async def get_environment(self, environment_id: str) -> EnvironmentProfile | None:
        return await self.store.get_environment(environment_id)

    async def list_environments(self) -> list[EnvironmentProfile]:
        return await self.store.list_environments()

    async def get_artifact(self, run_id: str, artifact_id: str) -> RunArtifact | None:
        return await self.store.get_artifact(run_id, artifact_id)

    async def cancel(self, run_id: str) -> TaskRun:
        run = await self.store.get(run_id)
        if not run:
            raise KeyError(run_id)
        if self._active_run_id == run_id and self._active_task:
            self._active_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._active_task
        run = await self.store.cancel(run_id)
        await self._publish()
        return run

    async def join(self) -> None:
        await self._queue.join()

    async def close(self) -> None:
        if not self._worker:
            return
        await self.join()
        self._worker.cancel()
        with suppress(asyncio.CancelledError):
            await self._worker
        self._worker = None

    async def _work(self) -> None:
        while True:
            run_id = await self._queue.get()
            execution = asyncio.create_task(
                self._execute(run_id), name=f"probe-run-{run_id}"
            )
            self._active_run_id = run_id
            self._active_task = execution
            try:
                await execution
            except asyncio.CancelledError:
                pass
            finally:
                self._active_run_id = None
                self._active_task = None
                self._queue.task_done()

    async def _execute(self, run_id: str) -> None:
        run = await self.store.get(run_id)
        if not run or run.status != RunStatus.QUEUED:
            return
        await self.store.mark_running(run_id)
        await self._publish()
        environment = (
            await self.store.get_environment(run.environment_id)
            if run.environment_id
            else None
        )
        task = AgentTask(
            task_id=run.id,
            start_url=run.start_url,
            goal=run.goal,
            environment_id=run.environment_id,
        )
        try:
            result = (
                await self.executor(task)
                if self.executor
                else await execute_agent_task(
                    task,
                    environment=environment,
                    event_handler=lambda event: self._add_progress(run_id, event),
                )
            )
        except Exception as exc:
            await self.store.finish(
                run_id,
                RunStatus.ERROR,
                error=f"{type(exc).__name__}: {exc}",
            )
            await self._publish()
            return
        await self.store.finish(
            run_id,
            RunStatus(result.status),
            result=result,
            error=result.error,
        )
        await self._publish()

    async def _add_progress(self, run_id: str, event: ProgressEntry) -> None:
        await self.store.add_progress(run_id, event)
        await self._publish()

    async def _publish(self) -> None:
        async with self._updates:
            self._version += 1
            self._updates.notify_all()
