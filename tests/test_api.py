from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from qa_agent.agent import AgentTask
from qa_agent.api import app, lifespan
from qa_agent.runs import RunQueueService, RunStatus, TaskRun


class ApiLifespanTest(unittest.IsolatedAsyncioTestCase):
    async def test_starts_and_closes_run_queue(self) -> None:
        queue = Mock(spec=RunQueueService)
        queue.start = AsyncMock()
        queue.close = AsyncMock()

        with patch("qa_agent.api.RunQueueService", return_value=queue):
            async with lifespan(app):
                self.assertIs(app.state.run_queue, queue)
                queue.start.assert_awaited_once()
                queue.close.assert_not_awaited()

        queue.close.assert_awaited_once()


class CreateRunTest(unittest.TestCase):
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

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(
            allowed.headers["access-control-allow-origin"], "http://localhost:3000"
        )
        self.assertNotIn("access-control-allow-origin", denied.headers)

    def test_accepts_and_queues_a_run(self) -> None:
        submitted: list[AgentTask] = []
        run = TaskRun(
            id="run-1",
            start_url="https://example.com/",
            goal="Verify the page",
            status=RunStatus.QUEUED,
            created_at=datetime.now(UTC),
        )

        async def submit(task: AgentTask) -> TaskRun:
            submitted.append(task)
            return run

        queue = Mock(spec=RunQueueService)
        queue.start = AsyncMock()
        queue.close = AsyncMock()
        queue.submit = AsyncMock(side_effect=submit)
        queue.list_runs = AsyncMock(return_value=[run])
        queue.get_details = AsyncMock(
            side_effect=lambda run_id: run if run_id == run.id else None
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
            missing = client.get("/runs/missing")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"id": "run-1", "status": "queued"})
        self.assertEqual(response.headers["location"], "/runs/run-1")
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]["id"], "run-1")
        self.assertNotIn("result", listed.json()[0])
        self.assertEqual(invalid_filter.status_code, 422)
        queue.list_runs.assert_awaited_once_with(
            status=RunStatus.QUEUED, limit=10, offset=0
        )
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["id"], "run-1")
        self.assertEqual(fetched.json()["status"], "queued")
        self.assertIsNone(fetched.json()["result"])
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json(), {"detail": "Run not found"})
        task = submitted[0]
        self.assertEqual(str(task.start_url), "https://example.com/")
        self.assertEqual(task.goal, "Verify the page")


if __name__ == "__main__":
    unittest.main()
