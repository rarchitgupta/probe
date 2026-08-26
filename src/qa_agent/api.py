from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy.exc import IntegrityError

from qa_agent.agent import AgentTask
from qa_agent.artifacts import artifact_storage
from qa_agent.environments import EnvironmentDefinition, EnvironmentProfile
from qa_agent.failures import FailureCategory
from qa_agent.runs import (
    InvalidRunTransitionError,
    RunEventKind,
    RunQueueService,
    RunStatus,
    RunStore,
    TaskRun,
)


class CreateRunRequest(BaseModel):
    start_url: HttpUrl
    goal: str = Field(min_length=1)
    environment_id: str | None = None


class CreateEnvironmentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    definition: EnvironmentDefinition = Field(default_factory=EnvironmentDefinition)
    viewport_width: int = Field(default=1280, ge=320, le=3840)
    viewport_height: int = Field(default=720, ge=240, le=2160)


class EnvironmentResponse(BaseModel):
    id: str
    name: str
    definition: EnvironmentDefinition
    viewport_width: int
    viewport_height: int
    created_at: datetime


class UpdateRunRequest(BaseModel):
    status: Literal[RunStatus.CANCELLED]


class RunListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None
    start_url: str
    goal: str
    status: RunStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RunUsageResponse(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    requests: int | None = None
    cost: str | None = None


class AgentConfigurationResponse(BaseModel):
    model: str
    prompt_version: str
    model_config_version: str


class RunResultResponse(BaseModel):
    summary: str | None
    final_url: str | None
    http_status: int | None
    evidence: tuple[str, ...]
    usage: RunUsageResponse
    configuration: AgentConfigurationResponse | None


class RunStatsResponse(BaseModel):
    duration_ms: int | None
    action_count: int
    assertion_count: int
    failed_action_count: int


class RunArtifactResponse(BaseModel):
    id: str
    kind: str
    content_type: str
    size_bytes: int
    created_at: datetime
    url: str


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None
    start_url: str
    goal: str
    status: RunStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    stats: RunStatsResponse
    artifacts: tuple[RunArtifactResponse, ...]
    result: RunResultResponse | None
    error: str | None
    failure_category: FailureCategory | None
    environment_id: str | None


class RunEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: RunEventKind
    created_at: datetime
    status: RunStatus | None
    action: str | None
    element: str | None
    success: bool | None
    message: str | None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    queue = RunQueueService(RunStore())
    await queue.start()
    app.state.run_queue = queue
    app.state.artifact_storage = artifact_storage()
    try:
        yield
    finally:
        await queue.close()


app = FastAPI(title="Probe", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "Range"],
    expose_headers=["Accept-Ranges", "Content-Length", "Content-Range"],
)

STREAM_TERMINAL_STATUSES = {
    RunStatus.PASSED,
    RunStatus.FAILED,
    RunStatus.BLOCKED,
    RunStatus.ERROR,
    RunStatus.CANCELLED,
}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/environments",
    response_model=EnvironmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_environment(
    payload: CreateEnvironmentRequest, request: Request
) -> EnvironmentResponse:
    queue: RunQueueService = request.app.state.run_queue
    try:
        environment = await queue.create_environment(**payload.model_dump())
    except IntegrityError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Environment name already exists"
        ) from None
    return _environment_response(environment)


@app.get("/environments", response_model=list[EnvironmentResponse])
async def list_environments(request: Request) -> list[EnvironmentResponse]:
    queue: RunQueueService = request.app.state.run_queue
    return [
        _environment_response(environment)
        for environment in await queue.list_environments()
    ]


@app.post("/runs", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_run(
    payload: CreateRunRequest, request: Request, response: Response
) -> RunResponse:
    queue: RunQueueService = request.app.state.run_queue
    if payload.environment_id and not await queue.get_environment(
        payload.environment_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Environment not found")
    run = await queue.submit(
        AgentTask(
            start_url=payload.start_url,
            goal=payload.goal,
            environment_id=payload.environment_id,
        )
    )
    response.headers["Location"] = f"/runs/{run.id}"
    return _run_response(run)


@app.get("/runs", response_model=list[RunListItem])
async def list_runs(
    request: Request,
    status_filter: RunStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[RunListItem]:
    queue: RunQueueService = request.app.state.run_queue
    runs = await queue.list_runs(status=status_filter, limit=limit, offset=offset)
    return [RunListItem.model_validate(run) for run in runs]


@app.get("/runs/stream")
async def stream_runs(request: Request) -> StreamingResponse:
    queue: RunQueueService = request.app.state.run_queue

    async def events() -> AsyncGenerator[str, None]:
        version = -1
        while not await request.is_disconnected():
            if version != queue.version:
                observed_version = queue.version
                runs = await queue.list_runs(limit=100)
                payload = (
                    "["
                    + ",".join(
                        RunListItem.model_validate(run).model_dump_json()
                        for run in runs
                    )
                    + "]"
                )
                yield _sse("runs", payload)
                version = observed_version
            if await queue.wait_for_update(version) is None:
                yield ": keep-alive\n\n"

    return _streaming_response(events())


@app.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, request: Request) -> StreamingResponse:
    queue: RunQueueService = request.app.state.run_queue
    if not await queue.get(run_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    last_event_id = request.headers.get("last-event-id", "0")
    after = int(last_event_id) if last_event_id.isdigit() else 0

    async def events() -> AsyncGenerator[str, None]:
        nonlocal after
        version = -1
        while not await request.is_disconnected():
            observed_version = queue.version
            run = await queue.get_details(run_id)
            if not run:
                return
            for event in await queue.list_events(run_id, after=after):
                payload = RunEventResponse.model_validate(event).model_dump_json()
                yield _sse("progress", payload, event.id)
                after = event.id
            yield _sse("run", _run_response(run).model_dump_json())
            if run.status in STREAM_TERMINAL_STATUSES:
                return
            version = observed_version
            if await queue.wait_for_update(version) is None:
                yield ": keep-alive\n\n"

    return _streaming_response(events())


@app.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, request: Request) -> RunResponse:
    queue: RunQueueService = request.app.state.run_queue
    run = await queue.get_details(run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return _run_response(run)


@app.get("/runs/{run_id}/artifacts/{artifact_id}/content")
async def get_artifact_content(
    run_id: str, artifact_id: str, request: Request
) -> Response:
    queue: RunQueueService = request.app.state.run_queue
    run = await queue.get(run_id)
    artifact = await queue.get_artifact(run_id, artifact_id)
    if not run or not run.result or not artifact:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")
    storage = artifact_storage(artifact.storage)
    if url := storage.signed_url(artifact.path):
        return RedirectResponse(url)
    run_directory = Path(run.result.artifact_directory).resolve()
    path = Path(artifact.path).resolve()
    if not path.is_relative_to(run_directory) or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")
    return FileResponse(
        path,
        media_type=artifact.content_type,
        content_disposition_type="inline",
    )


@app.patch("/runs/{run_id}", response_model=RunResponse)
async def update_run(
    run_id: str, payload: UpdateRunRequest, request: Request
) -> RunResponse:
    queue: RunQueueService = request.app.state.run_queue
    try:
        run = await queue.cancel(run_id)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found") from None
    except InvalidRunTransitionError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Only queued or running runs can be cancelled"
        ) from None
    return _run_response(run)


@app.post(
    "/runs/{run_id}/reruns",
    response_model=RunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def rerun(run_id: str, request: Request, response: Response) -> RunResponse:
    queue: RunQueueService = request.app.state.run_queue
    source = await queue.get(run_id)
    if not source:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    if source.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Run has not finished")
    run = await queue.submit(
        AgentTask(
            start_url=source.start_url,
            goal=source.goal,
            environment_id=source.environment_id,
        )
    )
    response.headers["Location"] = f"/runs/{run.id}"
    return _run_response(run)


@app.get("/runs/{run_id}/events", response_model=list[RunEventResponse])
async def list_run_events(
    run_id: str,
    request: Request,
    after: int = Query(default=0, ge=0),
) -> list[RunEventResponse]:
    queue: RunQueueService = request.app.state.run_queue
    try:
        events = await queue.list_events(run_id, after=after)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found") from None
    return [RunEventResponse.model_validate(event) for event in events]


def _run_response(run: TaskRun) -> RunResponse:
    duration_ms = (
        round((run.finished_at - run.started_at).total_seconds() * 1000)
        if run.started_at and run.finished_at
        else None
    )
    result = run.result
    return RunResponse(
        id=run.id,
        title=run.title,
        start_url=run.start_url,
        goal=run.goal,
        status=run.status,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        stats=RunStatsResponse(
            duration_ms=duration_ms,
            action_count=sum(event.kind == RunEventKind.ACTION for event in run.events),
            assertion_count=sum(
                event.kind == RunEventKind.ASSERTION for event in run.events
            ),
            failed_action_count=sum(
                event.kind == RunEventKind.ACTION and event.success is False
                for event in run.events
            ),
        ),
        artifacts=tuple(
            RunArtifactResponse(
                id=artifact.id,
                kind=artifact.kind,
                content_type=artifact.content_type,
                size_bytes=artifact.size_bytes,
                created_at=artifact.created_at,
                url=f"/runs/{run.id}/artifacts/{artifact.id}/content",
            )
            for artifact in run.artifacts
        ),
        result=(
            RunResultResponse(
                summary=result.summary,
                final_url=result.final_url,
                http_status=result.http_status,
                evidence=result.evidence,
                usage=RunUsageResponse.model_validate(result.usage),
                configuration=(
                    AgentConfigurationResponse.model_validate(
                        result.configuration, from_attributes=True
                    )
                    if result.configuration
                    else None
                ),
            )
            if result
            else None
        ),
        error=run.error,
        failure_category=run.failure_category,
        environment_id=run.environment_id,
    )


def _environment_response(environment: EnvironmentProfile) -> EnvironmentResponse:
    return EnvironmentResponse(
        id=environment.id,
        name=environment.name,
        definition=environment.definition,
        viewport_width=environment.viewport_width,
        viewport_height=environment.viewport_height,
        created_at=environment.created_at,
    )


def _sse(event: str, data: str, event_id: int | None = None) -> str:
    prefix = f"id: {event_id}\n" if event_id is not None else ""
    return f"{prefix}event: {event}\ndata: {data}\n\n"


def _streaming_response(
    events: AsyncGenerator[str, None],
) -> StreamingResponse:
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
