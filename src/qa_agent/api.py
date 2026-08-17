from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from qa_agent.agent import AgentTask
from qa_agent.runner import AgentTaskResult
from qa_agent.runs import RunQueueService, RunStatus, RunStore


class CreateRunRequest(BaseModel):
    start_url: HttpUrl
    goal: str = Field(min_length=1)


class RunAccepted(BaseModel):
    id: str
    status: RunStatus


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    start_url: str
    goal: str
    status: RunStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result: AgentTaskResult | None
    error: str | None


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


@app.post("/runs", response_model=RunAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_run(
    payload: CreateRunRequest, request: Request, response: Response
) -> RunAccepted:
    queue: RunQueueService = request.app.state.run_queue
    run = await queue.submit(AgentTask(start_url=payload.start_url, goal=payload.goal))
    response.headers["Location"] = f"/runs/{run.id}"
    return RunAccepted(id=run.id, status=run.status)


@app.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, request: Request) -> RunResponse:
    queue: RunQueueService = request.app.state.run_queue
    run = await queue.get_details(run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return RunResponse.model_validate(run)
