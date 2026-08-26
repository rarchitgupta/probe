from __future__ import annotations

import asyncio
from contextlib import suppress

from qa_agent.agent import AgentTask
from qa_agent.runs.execution import RunExecutor, execute_stored_run
from qa_agent.runs.service import RunService
from qa_agent.runs.store import RunStore, TaskRun


class RunQueueService(RunService):
    # ponytail: one in-process worker; use an external broker for multi-process workers.
    def __init__(
        self,
        store: RunStore,
        executor: RunExecutor | None = None,
    ) -> None:
        super().__init__(store)
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
        await execute_stored_run(
            self.store,
            run_id,
            executor=self.executor,
            update_handler=self._publish,
        )

    async def _publish(self) -> None:
        async with self._updates:
            self._version += 1
            self._updates.notify_all()
