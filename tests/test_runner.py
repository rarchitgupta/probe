from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from qa_agent.runner import InspectionTask, execute_inspection


class InspectionRunnerTest(unittest.IsolatedAsyncioTestCase):
    async def test_inspects_page_and_writes_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = await execute_inspection(
                InspectionTask(
                    task_id="test-run",
                    url=(
                        "data:text/html,<title>QA Agent</title>"
                        '<label for="email">Email</label><input id="email">'
                        '<input type="submit" value="Sign in">'
                        "<button hidden>Hidden</button>"
                    ),
                ),
                artifact_root=root,
            )

            self.assertEqual(result.status, "completed")
            self.assertEqual(result.title, "QA Agent")
            self.assertEqual(len(result.elements), 2)
            self.assertEqual(result.elements[0].role, "textbox")
            self.assertEqual(result.elements[0].name, "Email")
            self.assertEqual(result.elements[1].role, "button")
            self.assertEqual(result.elements[1].name, "Sign in")
            self.assertTrue((root / "test-run" / "screenshot.png").exists())
            self.assertTrue((root / "test-run" / "trace.zip").exists())
            saved = json.loads((root / "test-run" / "result.json").read_text())
            self.assertEqual(saved["task_id"], "test-run")
            self.assertEqual(saved["elements"][0]["name"], "Email")


if __name__ == "__main__":
    unittest.main()
