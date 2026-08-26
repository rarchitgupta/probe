from __future__ import annotations

import logging
import os

from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from qa_agent.agent import AgentTask
from qa_agent.runs.service import RunService
from qa_agent.runs.store import InvalidRunTransitionError, RunStatus, RunStore, TaskRun
from qa_agent.temporal import QARunWorkflow

logger = logging.getLogger(__name__)


class TemporalRunService(RunService):
    def __init__(self, store: RunStore, client: Client, task_queue: str) -> None:
        super().__init__(store)
        self.client = client
        self.task_queue = task_queue

    @classmethod
    async def connect(cls, store: RunStore) -> TemporalRunService:
        client = await Client.connect(
            os.getenv("PROBE_TEMPORAL_ADDRESS", "localhost:7233"),
            namespace=os.getenv("PROBE_TEMPORAL_NAMESPACE", "probe"),
        )
        return cls(
            store,
            client,
            os.getenv("PROBE_TEMPORAL_TASK_QUEUE", "probe-runs"),
        )

    async def start(self) -> None:
        # Fixed workflow IDs make replaying this bounded recovery scan idempotent.
        for run in await self.store.list_runs(status=RunStatus.QUEUED, limit=100):
            try:
                await self._start_workflow(run.id)
            except WorkflowAlreadyStartedError:
                pass
            except Exception:
                logger.exception("Failed to recover queued run %s", run.id)

    async def close(self) -> None:
        pass

    async def submit(self, task: AgentTask) -> TaskRun:
        run = await self.store.create(task)
        try:
            await self._start_workflow(run.id)
        except Exception as exc:
            await self.store.fail_submission(run.id, f"{type(exc).__name__}: {exc}")
            raise
        return run

    async def cancel(self, run_id: str) -> TaskRun:
        run = await self.store.get(run_id)
        if not run:
            raise KeyError(run_id)
        if run.status not in {RunStatus.QUEUED, RunStatus.RUNNING}:
            raise InvalidRunTransitionError(
                f"Cannot move run {run_id!r} to {RunStatus.CANCELLED!r}"
            )
        await self.client.get_workflow_handle(run_id).cancel()
        try:
            return await self.store.cancel(run_id)
        except InvalidRunTransitionError:
            current = await self.store.get(run_id)
            if current and current.status == RunStatus.CANCELLED:
                return current
            raise

    async def _start_workflow(self, run_id: str) -> None:
        await self.client.start_workflow(
            QARunWorkflow.run,
            run_id,
            id=run_id,
            task_queue=self.task_queue,
            static_summary="Probe browser QA run",
        )
