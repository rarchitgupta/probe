from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import asdict

from qa_agent.agent import AgentTask
from qa_agent.runner import AgentTaskResult, execute_agent_task
from qa_agent.runs.store import RunStatus, SQLiteRunStore, TaskRun

RunExecutor = Callable[[AgentTask], Awaitable[AgentTaskResult]]


class RunQueueService:
    # ponytail: one in-process worker; use an external broker for multi-process workers.
    def __init__(
        self,
        store: SQLiteRunStore,
        executor: RunExecutor = execute_agent_task,
    ) -> None:
        self.store = store
        self.executor = executor
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._worker:
            return
        self.store.initialize()
        for run in self.store.recover_pending():
            self._queue.put_nowait(run.id)
        self._worker = asyncio.create_task(self._work(), name="probe-worker")

    async def submit(self, task: AgentTask) -> TaskRun:
        if not self._worker:
            raise RuntimeError("RunQueueService must be started before submission")
        run = self.store.create(task)
        await self._queue.put(run.id)
        return run

    def get(self, run_id: str) -> TaskRun | None:
        return self.store.get(run_id)

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
            try:
                await self._execute(run_id)
            finally:
                self._queue.task_done()

    async def _execute(self, run_id: str) -> None:
        run = self.store.get(run_id)
        if not run or run.status != RunStatus.QUEUED:
            return
        self.store.mark_running(run_id)
        task = AgentTask(task_id=run.id, start_url=run.start_url, goal=run.goal)
        try:
            result = await self.executor(task)
        except Exception as exc:
            self.store.finish(
                run_id,
                RunStatus.ERROR,
                error=f"{type(exc).__name__}: {exc}",
            )
            return
        self.store.finish(
            run_id,
            RunStatus(result.status),
            result=asdict(result),
            error=result.error,
        )
