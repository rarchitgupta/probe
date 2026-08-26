from __future__ import annotations

from pathlib import Path

import pytest

from qa_agent.agent import AgentTask, ProgressEntry
from qa_agent.configuration import AgentConfiguration
from qa_agent.environments import EnvironmentDefinition
from qa_agent.runner import AgentTaskResult
from qa_agent.runs import InvalidRunTransitionError, RunStatus, RunStore


class TestRunStore:
    async def test_persists_reusable_environment(self, run_store: RunStore) -> None:
        environment = await run_store.create_environment(
            name="Staging",
            definition=EnvironmentDefinition(secrets={"password": "TEST_PASSWORD"}),
            viewport_width=1024,
            viewport_height=768,
        )
        await run_store.create(
            AgentTask(
                task_id="environment-run",
                start_url="https://example.com",
                goal="Verify the page",
                environment_id=environment.id,
            )
        )

        loaded = await run_store.get_environment(environment.id)
        runs = await run_store.list_runs()

        assert loaded == environment
        assert [item.name for item in await run_store.list_environments()] == [
            "Staging"
        ]
        assert runs[0].environment_id == environment.id

    async def test_persists_and_transitions_a_run(
        self, run_store: RunStore, tmp_path: Path
    ) -> None:
        run_directory = tmp_path / "run-1"
        run_directory.mkdir()
        (run_directory / "replay.webm").write_bytes(b"video")
        created = await run_store.create(_task())
        loaded = await run_store.get("run-1")
        running = await run_store.mark_running("run-1")
        await run_store.finish(
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
                artifact_directory=str(run_directory),
                title="Verify Example Page",
                configuration=AgentConfiguration(model="test-model"),
            ),
        )
        fetched = await run_store.get_details("run-1")

        assert created.status == RunStatus.QUEUED
        assert loaded == created
        assert running.status == RunStatus.RUNNING
        assert (fetched.status if fetched else None) == RunStatus.PASSED
        assert (fetched.title if fetched else None) == "Verify Example Page"
        assert (fetched.result.evidence if fetched and fetched.result else None) == (
            "Page visible",
        )
        assert (
            fetched.result.configuration.model
            if fetched and fetched.result and fetched.result.configuration
            else None
        ) == "test-model"
        assert fetched is not None
        assert len(fetched.artifacts) == 1
        assert fetched.artifacts[0].content_type == "video/webm"
        assert fetched.artifacts[0].size_bytes == 5
        assert (
            await run_store.get_artifact("run-1", fetched.artifacts[0].id)
            == fetched.artifacts[0]
        )
        with pytest.raises(InvalidRunTransitionError):
            await run_store.mark_running("run-1")

    async def test_rejects_cancelling_terminal_run(self, run_store: RunStore) -> None:
        await run_store.create(_task())
        cancelled = await run_store.cancel("run-1")

        assert cancelled.status == RunStatus.CANCELLED
        with pytest.raises(InvalidRunTransitionError):
            await run_store.cancel("run-1")

    async def test_cancels_running_run(self, run_store: RunStore) -> None:
        await run_store.create(_task())
        await run_store.mark_running("run-1")

        cancelled = await run_store.cancel("run-1")

        assert cancelled.status == RunStatus.CANCELLED
        assert cancelled.finished_at is not None

    async def test_lists_newest_runs_with_status_filter(
        self, run_store: RunStore
    ) -> None:
        await run_store.create(_task("run-1"))
        await run_store.create(_task("run-2"))
        await run_store.mark_running("run-2")

        all_runs = await run_store.list_runs()
        running = await run_store.list_runs(status=RunStatus.RUNNING)

        assert [run.id for run in all_runs] == ["run-2", "run-1"]
        assert [run.id for run in running] == ["run-2"]

    async def test_records_progress_events_in_order(self, run_store: RunStore) -> None:
        await run_store.create(_task())
        await run_store.add_progress(
            "run-1",
            ProgressEntry(action="click", target="Login", success=True),
        )

        events = await run_store.list_events("run-1")
        later_events = await run_store.list_events("run-1", after=events[0].id)

        assert [event.action for event in events] == [None, "click"]
        assert [event.action for event in later_events] == ["click"]


def _task(task_id: str = "run-1") -> AgentTask:
    return AgentTask(
        task_id=task_id,
        start_url="https://example.com",
        goal="Verify the page",
    )
