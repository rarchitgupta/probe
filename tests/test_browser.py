from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

from qa_agent.browser import BrowserSession, ClickAction, FillAction


class BrowserSessionTest(unittest.IsolatedAsyncioTestCase):
    async def test_observe_fill_click_and_reobserve(self) -> None:
        html = """
            <title>Login</title>
            <label for="username">Username</label>
            <input id="username">
            <label for="password">Password</label>
            <input id="password" type="password">
            <button onclick="document.title = 'Dashboard'">Login</button>
        """
        with tempfile.TemporaryDirectory() as directory:
            async with BrowserSession(
                trace_path=Path(directory) / "trace.zip"
            ) as session:
                await session.navigate(f"data:text/html,{quote(html)}")

                observation = await session.observe()
                username_id = observation.elements[0].id
                result = await session.execute(
                    FillAction(
                        action="fill", element_id=username_id, value="standard_user"
                    )
                )
                self.assertTrue(result.success)

                stale_result = await session.execute(
                    ClickAction(action="click", element_id=username_id)
                )
                self.assertFalse(stale_result.success)

                observation = await session.observe()
                password_id = observation.elements[1].id
                result = await session.execute(
                    FillAction(action="fill", element_id=password_id, value="secret")
                )
                self.assertTrue(result.success)

                observation = await session.observe()
                login_id = observation.elements[2].id
                result = await session.execute(
                    ClickAction(action="click", element_id=login_id)
                )
                self.assertTrue(result.success)

                observation = await session.observe()
                self.assertEqual(observation.title, "Dashboard")


if __name__ == "__main__":
    unittest.main()
