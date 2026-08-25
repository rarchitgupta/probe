from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from qa_agent.runner import InspectionTask, execute_inspection

pytestmark = pytest.mark.browser


class TestInspectionRunner:
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

            assert result.status == "completed"
            assert result.title == "QA Agent"
            assert len(result.elements) == 2
            assert result.elements[0].role == "textbox"
            assert result.elements[0].name == "Email"
            assert result.elements[1].role == "button"
            assert result.elements[1].name == "Sign in"
            assert (root / "test-run" / "screenshot.png").exists()
            assert (root / "test-run" / "trace.zip").exists()
            saved = json.loads((root / "test-run" / "result.json").read_text())
            assert saved["task_id"] == "test-run"
            assert saved["elements"][0]["name"] == "Email"
