from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from qa_agent.agent import AgentTask
from qa_agent.runs import InvalidRunTransitionError, RunStatus, SQLiteRunStore


class SQLiteRunStoreTest(unittest.TestCase):
    def test_initializes_and_persists_a_queued_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "data" / "probe.db"
            store = SQLiteRunStore(database)
            store.initialize()
            store.initialize()

            created = store.create(
                AgentTask(
                    task_id="run-1",
                    start_url="https://example.com",
                    goal="Verify the page",
                )
            )
            loaded = SQLiteRunStore(database).get("run-1")

            self.assertEqual(created.status, RunStatus.QUEUED)
            self.assertEqual(loaded, created)
            self.assertIsNone(created.started_at)
            self.assertIsNone(created.finished_at)
            self.assertIsNone(created.result)

            with sqlite3.connect(database) as connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
            self.assertEqual(version, 1)

    def test_transitions_a_run_atomically_to_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteRunStore(Path(directory) / "probe.db")
            store.initialize()
            store.create(
                AgentTask(
                    task_id="run-1",
                    start_url="https://example.com",
                    goal="Verify the page",
                )
            )

            running = store.mark_running("run-1")
            finished = store.finish(
                "run-1",
                RunStatus.PASSED,
                result={"summary": "Verified"},
            )

            self.assertEqual(running.status, RunStatus.RUNNING)
            self.assertIsNotNone(running.started_at)
            self.assertEqual(finished.status, RunStatus.PASSED)
            self.assertIsNotNone(finished.finished_at)
            self.assertEqual(finished.result, {"summary": "Verified"})
            with self.assertRaises(InvalidRunTransitionError):
                store.mark_running("run-1")

    def test_cancels_only_queued_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteRunStore(Path(directory) / "probe.db")
            store.initialize()
            store.create(
                AgentTask(
                    task_id="run-1",
                    start_url="https://example.com",
                    goal="Verify the page",
                )
            )

            cancelled = store.cancel("run-1")

            self.assertEqual(cancelled.status, RunStatus.CANCELLED)
            self.assertIsNotNone(cancelled.finished_at)
            with self.assertRaises(InvalidRunTransitionError):
                store.cancel("run-1")


if __name__ == "__main__":
    unittest.main()
