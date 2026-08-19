from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from qa_agent.agent import AgentTask
from qa_agent.database import Base
from qa_agent.runner import AgentTaskResult
from qa_agent.runs import RunQueueService, RunStatus, RunStore, TaskRun


def passed_result(task: AgentTask) -> AgentTaskResult:
    return AgentTaskResult(
        task_id=task.task_id,
        status="passed",
        start_url=str(task.start_url),
        final_url=str(task.start_url),
        http_status=200,
        summary="Passed",
        evidence=(),
        diagnostics=(),
        usage={},
        error=None,
        artifact_directory=f".runs/{task.task_id}",
        title="Verify Example Page",
    )


class RunQueueServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name) / "probe.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.store = RunStore(async_sessionmaker(self.engine, expire_on_commit=False))

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self.directory.cleanup()

    async def test_accepts_a_second_run_while_processing_the_first(self) -> None:
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        order: list[str] = []

        async def execute(task: AgentTask) -> AgentTaskResult:
            order.append(f"start:{task.task_id}")
            if task.task_id == "run-1":
                first_started.set()
                await release_first.wait()
            order.append(f"finish:{task.task_id}")
            return passed_result(task)

        service = RunQueueService(self.store, execute)
        await service.start()
        try:
            await service.submit(_task("run-1"))
            await first_started.wait()
            second = await service.submit(_task("run-2"))

            self.assertEqual((await _run(service, "run-1")).status, RunStatus.RUNNING)
            self.assertEqual(second.status, RunStatus.QUEUED)

            release_first.set()
            await service.join()

            self.assertEqual((await _run(service, "run-1")).status, RunStatus.PASSED)
            self.assertEqual((await _run(service, "run-2")).status, RunStatus.PASSED)
            self.assertEqual(
                order,
                ["start:run-1", "finish:run-1", "start:run-2", "finish:run-2"],
            )
        finally:
            release_first.set()
            await service.close()

    async def test_records_executor_errors_and_continues(self) -> None:
        async def execute(task: AgentTask) -> AgentTaskResult:
            if task.task_id == "run-1":
                raise RuntimeError("browser crashed")
            return passed_result(task)

        service = RunQueueService(self.store, execute)
        await service.start()
        try:
            await service.submit(_task("run-1"))
            await service.submit(_task("run-2"))
            await service.join()

            failed = await _run(service, "run-1")
            self.assertEqual(failed.status, RunStatus.ERROR)
            self.assertEqual(failed.error, "RuntimeError: browser crashed")
            self.assertEqual((await _run(service, "run-2")).status, RunStatus.PASSED)
        finally:
            await service.close()


def _task(task_id: str) -> AgentTask:
    return AgentTask(
        task_id=task_id,
        start_url="https://example.com",
        goal="Verify the page",
    )


async def _run(service: RunQueueService, run_id: str) -> TaskRun:
    run = await service.get(run_id)
    assert run is not None
    return run


if __name__ == "__main__":
    unittest.main()
