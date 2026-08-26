from __future__ import annotations

from collections.abc import Awaitable, Callable

from qa_agent.agent import AgentTask, ProgressEntry
from qa_agent.runner import AgentTaskResult, execute_agent_task
from qa_agent.runs.store import RunStatus, RunStore, TaskRun

RunExecutor = Callable[[AgentTask], Awaitable[AgentTaskResult]]
UpdateHandler = Callable[[], Awaitable[None]]


async def execute_stored_run(
    store: RunStore,
    run_id: str,
    *,
    executor: RunExecutor | None = None,
    update_handler: UpdateHandler | None = None,
) -> TaskRun | None:
    run = await store.get(run_id)
    if not run or run.status != RunStatus.QUEUED:
        return run

    await store.mark_running(run_id)
    if update_handler:
        await update_handler()
    environment = (
        await store.get_environment(run.environment_id) if run.environment_id else None
    )
    task = AgentTask(
        task_id=run.id,
        start_url=run.start_url,
        goal=run.goal,
        environment_id=run.environment_id,
    )

    async def record_progress(event: ProgressEntry) -> None:
        await store.add_progress(run_id, event)
        if update_handler:
            await update_handler()

    try:
        result = (
            await executor(task)
            if executor
            else await execute_agent_task(
                task,
                environment=environment,
                event_handler=record_progress,
            )
        )
    except Exception as exc:
        finished = await store.finish(
            run_id,
            RunStatus.ERROR,
            error=f"{type(exc).__name__}: {exc}",
        )
    else:
        finished = await store.finish(
            run_id,
            RunStatus(result.status),
            result=result,
            error=result.error,
        )
    if update_handler:
        await update_handler()
    return finished
