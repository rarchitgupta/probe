from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from qa_agent.agent import AgentTask
from qa_agent.api import app, lifespan
from qa_agent.configuration import AgentConfiguration
from qa_agent.runner import AgentTaskResult
from qa_agent.runs import RunEvent, RunEventKind, RunQueueService, RunStatus, TaskRun


class TestApiLifespan:
    async def test_starts_and_closes_run_queue(self) -> None:
        queue = Mock(spec=RunQueueService)
        queue.start = AsyncMock()
        queue.close = AsyncMock()

        with patch("qa_agent.api.RunQueueService", return_value=queue):
            async with lifespan(app):
                assert app.state.run_queue is queue
                queue.start.assert_awaited_once()
                queue.close.assert_not_awaited()

        queue.close.assert_awaited_once()


class TestCreateRun:
    def test_allows_cors_from_local_frontend(self) -> None:
        queue = Mock(spec=RunQueueService)
        queue.start = AsyncMock()
        queue.close = AsyncMock()

        with (
            patch("qa_agent.api.RunQueueService", return_value=queue),
            TestClient(app) as client,
        ):
            allowed = client.options(
                "/runs",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            denied = client.options(
                "/runs",
                headers={
                    "Origin": "http://localhost:3001",
                    "Access-Control-Request-Method": "POST",
                },
            )

        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert "access-control-allow-origin" not in denied.headers

    def test_accepts_and_queues_a_run(self) -> None:
        submitted: list[AgentTask] = []
        run = TaskRun(
            id="run-1",
            title=None,
            start_url="https://example.com/",
            goal="Verify the page",
            status=RunStatus.QUEUED,
            created_at=datetime.now(UTC),
        )
        completed = TaskRun(
            id="run-2",
            title="Verify Example Page",
            start_url=run.start_url,
            goal=run.goal,
            status=RunStatus.PASSED,
            created_at=run.created_at,
            started_at=run.created_at,
            finished_at=run.created_at + timedelta(seconds=2),
            result=AgentTaskResult(
                task_id="run-2",
                status="passed",
                start_url=run.start_url,
                final_url=run.start_url,
                http_status=200,
                summary="Passed",
                evidence=(),
                diagnostics=(),
                usage={
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cache_read_tokens": 80,
                    "requests": 2,
                    "cost": "0.0001",
                },
                error=None,
                artifact_directory=".runs/run-2",
                title="Verify Example Page",
                configuration=AgentConfiguration(model="test-model"),
            ),
            events=(
                RunEvent(
                    id=2,
                    kind=RunEventKind.ACTION,
                    created_at=run.created_at,
                    status=None,
                    action="click",
                    element="Submit",
                    success=True,
                    message="page_changed",
                ),
                RunEvent(
                    id=3,
                    kind=RunEventKind.ASSERTION,
                    created_at=run.created_at,
                    status=None,
                    action=None,
                    element=None,
                    success=True,
                    message="Page visible",
                ),
            ),
        )

        async def submit(task: AgentTask) -> TaskRun:
            submitted.append(task)
            return run

        queue = Mock(spec=RunQueueService)
        queue.start = AsyncMock()
        queue.close = AsyncMock()
        queue.submit = AsyncMock(side_effect=submit)
        queue.list_runs = AsyncMock(return_value=[run])
        queue.list_events = AsyncMock(
            side_effect=lambda run_id, after=0: (
                [
                    RunEvent(
                        id=1,
                        kind=RunEventKind.STATUS,
                        created_at=run.created_at,
                        status=RunStatus.QUEUED,
                        action=None,
                        element=None,
                        success=None,
                        message="Run queued",
                    )
                ]
                if run_id == run.id
                else (_ for _ in ()).throw(KeyError(run_id))
            )
        )
        queue.get_details = AsyncMock(
            side_effect=lambda run_id: {run.id: run, completed.id: completed}.get(
                run_id
            )
        )

        with (
            patch("qa_agent.api.RunQueueService", return_value=queue),
            TestClient(app) as client,
        ):
            response = client.post(
                "/runs",
                json={
                    "start_url": "https://example.com/",
                    "goal": "Verify the page",
                },
            )
            invalid = client.post("/runs", json={"start_url": "not-a-url", "goal": ""})
            listed = client.get("/runs?status=queued&limit=10&offset=0")
            invalid_filter = client.get("/runs?status=unknown")
            fetched = client.get("/runs/run-1")
            events = client.get("/runs/run-1/events")
            missing_events = client.get("/runs/missing/events")
            completed_response = client.get("/runs/run-2")
            missing = client.get("/runs/missing")

        assert response.status_code == 202
        assert response.json()["id"] == "run-1"
        assert response.json()["title"] is None
        assert response.json()["start_url"] == "https://example.com/"
        assert response.json()["goal"] == "Verify the page"
        assert response.json()["status"] == "queued"
        assert response.json()["started_at"] is None
        assert response.json()["finished_at"] is None
        assert response.json()["result"] is None
        assert response.json()["stats"] == {
            "duration_ms": None,
            "action_count": 0,
            "assertion_count": 0,
            "failed_action_count": 0,
        }
        assert response.json()["error"] is None
        assert response.json()["failure_category"] is None
        assert response.headers["location"] == "/runs/run-1"
        assert invalid.status_code == 422
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == "run-1"
        assert listed.json()[0]["title"] is None
        assert "result" not in listed.json()[0]
        assert invalid_filter.status_code == 422
        queue.list_runs.assert_awaited_once_with(
            status=RunStatus.QUEUED, limit=10, offset=0
        )
        assert fetched.status_code == 200
        assert fetched.json()["id"] == "run-1"
        assert fetched.json()["status"] == "queued"
        assert fetched.json()["result"] is None
        assert events.json()[0]["status"] == "queued"
        assert missing_events.status_code == 404
        assert completed_response.json()["title"] == "Verify Example Page"
        completed_json = completed_response.json()
        assert completed_json["stats"] == {
            "duration_ms": 2000,
            "action_count": 1,
            "assertion_count": 1,
            "failed_action_count": 0,
        }
        assert set(completed_json["result"]) == {
            "summary",
            "final_url",
            "http_status",
            "evidence",
            "usage",
            "configuration",
        }
        assert completed_json["result"]["usage"]["requests"] == 2
        assert completed_json["result"]["configuration"] == {
            "model": "test-model",
            "prompt_version": "1",
            "model_config_version": "1",
        }
        assert missing.status_code == 404
        assert missing.json() == {"detail": "Run not found"}
        task = submitted[0]
        assert str(task.start_url) == "https://example.com/"
        assert task.goal == "Verify the page"
