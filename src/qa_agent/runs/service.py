from __future__ import annotations

from qa_agent.environments import EnvironmentDefinition, EnvironmentProfile
from qa_agent.runs.store import RunArtifact, RunEvent, RunStatus, RunStore, TaskRun


class RunService:
    def __init__(self, store: RunStore) -> None:
        self.store = store

    async def get(self, run_id: str) -> TaskRun | None:
        return await self.store.get(run_id)

    async def get_details(self, run_id: str) -> TaskRun | None:
        return await self.store.get_details(run_id)

    async def list_runs(
        self,
        *,
        status: RunStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[TaskRun]:
        return await self.store.list_runs(status=status, limit=limit, offset=offset)

    async def list_events(self, run_id: str, *, after: int = 0) -> list[RunEvent]:
        return await self.store.list_events(run_id, after=after)

    async def create_environment(
        self,
        *,
        name: str,
        definition: EnvironmentDefinition,
        viewport_width: int,
        viewport_height: int,
    ) -> EnvironmentProfile:
        return await self.store.create_environment(
            name=name,
            definition=definition,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )

    async def get_environment(self, environment_id: str) -> EnvironmentProfile | None:
        return await self.store.get_environment(environment_id)

    async def list_environments(self) -> list[EnvironmentProfile]:
        return await self.store.list_environments()

    async def get_artifact(self, run_id: str, artifact_id: str) -> RunArtifact | None:
        return await self.store.get_artifact(run_id, artifact_id)
