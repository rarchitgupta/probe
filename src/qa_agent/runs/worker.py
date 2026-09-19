from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from datetime import timedelta

from temporalio import activity
from temporalio.client import Client
from temporalio.worker import Worker

from qa_agent.runs.execution import execute_stored_run
from qa_agent.runs.models import RunStatus
from qa_agent.runs.store import InvalidRunTransitionError, RunStore
from qa_agent.runs.workflow import QARunWorkflow


@activity.defn(name="execute_qa_run")
async def execute_qa_run(run_id: str) -> str:
    store = RunStore()
    heartbeat = asyncio.create_task(_heartbeat(run_id))
    try:
        run = await execute_stored_run(store, run_id)
        if not run:
            raise KeyError(f"Unknown run {run_id!r}")
        return run.status.value
    except asyncio.CancelledError:
        current = await store.get(run_id)
        if current and current.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
            with suppress(InvalidRunTransitionError):
                await asyncio.shield(store.cancel(run_id))
        raise
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat


async def _heartbeat(run_id: str) -> None:
    while True:
        activity.heartbeat(run_id)
        await asyncio.sleep(10)


async def run_worker() -> None:
    client = await Client.connect(
        os.getenv("PROBE_TEMPORAL_ADDRESS", "localhost:7233"),
        namespace=os.getenv("PROBE_TEMPORAL_NAMESPACE", "probe"),
    )
    worker = Worker(
        client,
        task_queue=os.getenv("PROBE_TEMPORAL_TASK_QUEUE", "probe-runs"),
        workflows=[QARunWorkflow],
        activities=[execute_qa_run],
        max_concurrent_activities=1,
        graceful_shutdown_timeout=timedelta(seconds=30),
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
