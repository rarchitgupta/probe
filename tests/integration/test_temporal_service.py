from unittest.mock import AsyncMock, Mock

import pytest
from temporalio.client import Client

from qa_agent.agent.planning import AgentTask
from qa_agent.failures import FailureCategory
from qa_agent.runs.models import RunStatus
from qa_agent.runs.store import RunStore
from qa_agent.runs.temporal import TemporalRunService
from qa_agent.runs.workflow import QARunWorkflow


async def test_submits_and_cancels_temporal_workflow(run_store: RunStore) -> None:
    handle = Mock()
    handle.cancel = AsyncMock()
    client = Mock(spec=Client)
    client.start_workflow = AsyncMock()
    client.get_workflow_handle.return_value = handle
    service = TemporalRunService(run_store, client, "probe-runs")

    run = await service.submit(_task("run-1"))
    cancelled = await service.cancel(run.id)

    client.start_workflow.assert_awaited_once()
    call = client.start_workflow.await_args
    assert call is not None
    assert call.args == (QARunWorkflow.run, "run-1")
    assert call.kwargs["id"] == "run-1"
    assert call.kwargs["task_queue"] == "probe-runs"
    handle.cancel.assert_awaited_once()
    assert cancelled.status == RunStatus.CANCELLED


async def test_records_temporal_submission_failure(run_store: RunStore) -> None:
    client = Mock(spec=Client)
    client.start_workflow = AsyncMock(side_effect=ConnectionError("unavailable"))
    service = TemporalRunService(run_store, client, "probe-runs")

    with pytest.raises(ConnectionError, match="unavailable"):
        await service.submit(_task("run-1"))

    run = await run_store.get("run-1")
    assert run is not None
    assert run.status == RunStatus.ERROR
    assert run.failure_category == FailureCategory.INFRASTRUCTURE_ERROR


def _task(run_id: str) -> AgentTask:
    return AgentTask(
        task_id=run_id,
        start_url="https://example.com",
        goal="Verify the page",
    )
