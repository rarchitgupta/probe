from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from qa_agent.agent import AgentTask
from qa_agent.database import Base
from qa_agent.runner import AgentTaskResult
from qa_agent.runs import InvalidRunTransitionError, RunStatus, RunStore


class RunStoreTest(unittest.IsolatedAsyncioTestCase):
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

    async def test_persists_and_transitions_a_run(self) -> None:
        created = await self.store.create(_task())
        loaded = await self.store.get("run-1")
        running = await self.store.mark_running("run-1")
        await self.store.finish(
            "run-1",
            RunStatus.PASSED,
            result=AgentTaskResult(
                task_id="run-1",
                status="passed",
                start_url="https://example.com/",
                final_url="https://example.com/",
                http_status=200,
                summary="Verified",
                evidence=("Page visible",),
                diagnostics=(),
                usage={},
                error=None,
                artifact_directory=".runs/run-1",
            ),
        )
        fetched = await self.store.get_details("run-1")

        self.assertEqual(created.status, RunStatus.QUEUED)
        self.assertEqual(loaded, created)
        self.assertEqual(running.status, RunStatus.RUNNING)
        self.assertEqual(fetched.status if fetched else None, RunStatus.PASSED)
        self.assertEqual(
            fetched.result.evidence if fetched and fetched.result else None,
            ("Page visible",),
        )
        with self.assertRaises(InvalidRunTransitionError):
            await self.store.mark_running("run-1")

    async def test_cancels_only_queued_runs(self) -> None:
        await self.store.create(_task())
        cancelled = await self.store.cancel("run-1")

        self.assertEqual(cancelled.status, RunStatus.CANCELLED)
        with self.assertRaises(InvalidRunTransitionError):
            await self.store.cancel("run-1")

    async def test_lists_newest_runs_with_status_filter(self) -> None:
        await self.store.create(_task("run-1"))
        await self.store.create(_task("run-2"))
        await self.store.mark_running("run-2")

        all_runs = await self.store.list_runs()
        running = await self.store.list_runs(status=RunStatus.RUNNING)

        self.assertEqual([run.id for run in all_runs], ["run-2", "run-1"])
        self.assertEqual([run.id for run in running], ["run-2"])


def _task(task_id: str = "run-1") -> AgentTask:
    return AgentTask(
        task_id=task_id,
        start_url="https://example.com",
        goal="Verify the page",
    )


if __name__ == "__main__":
    unittest.main()
