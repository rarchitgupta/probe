from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from qa_agent.agent import AgentTask
from qa_agent.runner import AgentTaskResult
from qa_agent.runs import RunEventKind, RunQueueService, RunStatus, RunStore


class CreateRunRequest(BaseModel):
    start_url: HttpUrl
    goal: str = Field(min_length=1)


class RunAccepted(BaseModel):
    id: str
    status: RunStatus


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
    result: AgentTaskResult | None
    error: str | None


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
    try:
        yield
    finally:
        await queue.close()


app = FastAPI(title="Probe", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.post("/runs", response_model=RunAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_run(
    payload: CreateRunRequest, request: Request, response: Response
) -> RunAccepted:
    queue: RunQueueService = request.app.state.run_queue
    run = await queue.submit(AgentTask(start_url=payload.start_url, goal=payload.goal))
    response.headers["Location"] = f"/runs/{run.id}"
    return RunAccepted(id=run.id, status=run.status)


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


@app.get(
    "/runs/{run_id}",
    response_model=RunResponse,
    response_model_exclude={"result": {"title"}},
)
async def get_run(run_id: str, request: Request) -> RunResponse:
    queue: RunQueueService = request.app.state.run_queue
    run = await queue.get_details(run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return RunResponse.model_validate(run)


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
