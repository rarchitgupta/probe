from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from qa_agent.agent import AgentTask

DEFAULT_DATABASE_PATH = Path(".qa-agent/qa-agent.db")


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    ERROR = "error"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = {
    RunStatus.PASSED,
    RunStatus.FAILED,
    RunStatus.BLOCKED,
    RunStatus.ERROR,
}


class InvalidRunTransitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class TaskRun:
    id: str
    start_url: str
    goal: str
    status: RunStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, object] | None = None
    error: str | None = None


class SQLiteRunStore:
    def __init__(self, path: Path = DEFAULT_DATABASE_PATH) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS task_runs (
                    id TEXT PRIMARY KEY,
                    start_url TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN (
                        'queued', 'running', 'passed', 'failed',
                        'blocked', 'error', 'cancelled'
                    )),
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    result_json TEXT,
                    error TEXT
                );
                PRAGMA user_version = 1;
                """
            )

    def create(self, task: AgentTask) -> TaskRun:
        created_at = datetime.now(UTC)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO task_runs (id, start_url, goal, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    task.task_id,
                    str(task.start_url),
                    task.goal,
                    RunStatus.QUEUED,
                    created_at.isoformat(),
                ),
            )
        run = self.get(task.task_id)
        assert run is not None
        return run

    def get(self, run_id: str) -> TaskRun | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM task_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return _task_run(row) if row else None

    def mark_running(self, run_id: str) -> TaskRun:
        started_at = datetime.now(UTC).isoformat()
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                UPDATE task_runs
                SET status = ?, started_at = ?
                WHERE id = ? AND status = ?
                """,
                (RunStatus.RUNNING, started_at, run_id, RunStatus.QUEUED),
            )
            return self._updated_run(connection, cursor, run_id, RunStatus.RUNNING)

    def finish(
        self,
        run_id: str,
        status: RunStatus,
        *,
        result: dict[str, object] | None = None,
        error: str | None = None,
    ) -> TaskRun:
        if status not in TERMINAL_STATUSES:
            raise ValueError(f"{status} is not a completion status")
        finished_at = datetime.now(UTC).isoformat()
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                UPDATE task_runs
                SET status = ?, finished_at = ?, result_json = ?, error = ?
                WHERE id = ? AND status = ?
                """,
                (
                    status,
                    finished_at,
                    (
                        json.dumps(result, separators=(",", ":"))
                        if result is not None
                        else None
                    ),
                    error,
                    run_id,
                    RunStatus.RUNNING,
                ),
            )
            return self._updated_run(connection, cursor, run_id, status)

    def cancel(self, run_id: str) -> TaskRun:
        finished_at = datetime.now(UTC).isoformat()
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                UPDATE task_runs
                SET status = ?, finished_at = ?
                WHERE id = ? AND status = ?
                """,
                (RunStatus.CANCELLED, finished_at, run_id, RunStatus.QUEUED),
            )
            return self._updated_run(connection, cursor, run_id, RunStatus.CANCELLED)

    def recover_pending(self) -> list[TaskRun]:
        finished_at = datetime.now(UTC).isoformat()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE task_runs
                SET status = ?, finished_at = ?, error = ?
                WHERE status = ?
                """,
                (
                    RunStatus.ERROR,
                    finished_at,
                    "Worker stopped before the run completed",
                    RunStatus.RUNNING,
                ),
            )
            rows = connection.execute(
                "SELECT * FROM task_runs WHERE status = ? ORDER BY created_at, id",
                (RunStatus.QUEUED,),
            ).fetchall()
        return [_task_run(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @staticmethod
    def _updated_run(
        connection: sqlite3.Connection,
        cursor: sqlite3.Cursor,
        run_id: str,
        target: RunStatus,
    ) -> TaskRun:
        row = connection.execute(
            "SELECT * FROM task_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if not row:
            raise KeyError(f"Unknown run {run_id!r}")
        if cursor.rowcount != 1:
            raise InvalidRunTransitionError(
                f"Cannot move run {run_id!r} from {row['status']!r} to {target!r}"
            )
        return _task_run(row)


def _task_run(row: sqlite3.Row) -> TaskRun:
    return TaskRun(
        id=row["id"],
        start_url=row["start_url"],
        goal=row["goal"],
        status=RunStatus(row["status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        started_at=(
            datetime.fromisoformat(row["started_at"]) if row["started_at"] else None
        ),
        finished_at=(
            datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None
        ),
        result=json.loads(row["result_json"]) if row["result_json"] else None,
        error=row["error"],
    )
