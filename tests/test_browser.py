from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

from qa_agent.browser import (
    BrowserSession,
    ClickAction,
    FillAction,
    ScrollAction,
    SelectOptionAction,
    SetCheckedAction,
)


class BrowserSessionTest(unittest.IsolatedAsyncioTestCase):
    async def test_records_and_dismisses_dialog(self) -> None:
        html = "<button onclick=\"alert('Message received!')\">Submit</button>"
        with tempfile.TemporaryDirectory() as directory:
            async with BrowserSession(
                trace_path=Path(directory) / "trace.zip"
            ) as session:
                await session.navigate(f"data:text/html,{quote(html)}")
                observation = await session.observe()
                clicked = await session.execute(
                    ClickAction("click", observation.elements[0].id)
                )
                assertion = session.assert_dialog_message("Message received!")

        self.assertTrue(clicked.success)
        self.assertTrue(assertion.success)

    async def test_scrolls_down_and_back_up_with_fresh_observations(self) -> None:
        html = """
            <button>Top action</button>
            <div style="height: 800px"></div>
            <button>Bottom action</button>
        """
        with tempfile.TemporaryDirectory() as directory:
            async with BrowserSession(
                trace_path=Path(directory) / "trace.zip"
            ) as session:
                await session.navigate(f"data:text/html,{quote(html)}")
                top = await session.observe()
                down = await session.execute(ScrollAction("scroll", "down"))
                bottom = await session.observe()
                up = await session.execute(ScrollAction("scroll", "up"))
                top_again = await session.observe()

        self.assertTrue(top.can_scroll_down)
        self.assertTrue(down.success)
        self.assertTrue(bottom.can_scroll_up)
        self.assertIn("Bottom action", [element.name for element in bottom.elements])
        self.assertTrue(up.success)
        self.assertFalse(top_again.can_scroll_up)
        self.assertIn("Top action", [element.name for element in top_again.elements])

    async def test_sets_and_verifies_form_controls(self) -> None:
        html = """
            <label><input type="checkbox"> Accept terms</label>
            <label for="country">Country</label>
            <select id="country"><option>Canada</option><option>Japan</option></select>
        """
        with tempfile.TemporaryDirectory() as directory:
            async with BrowserSession(
                trace_path=Path(directory) / "trace.zip"
            ) as session:
                await session.navigate(f"data:text/html,{quote(html)}")
                observation = await session.observe()
                checkbox_id = observation.elements[0].id

                checked = await session.execute(
                    SetCheckedAction("set_checked", checkbox_id, True)
                )
                observation = await session.observe()
                checked_assertion = await session.assert_checked(
                    observation.elements[0].id, True
                )

                selected = await session.execute(
                    SelectOptionAction(
                        "select_option", observation.elements[1].id, "Japan"
                    )
                )
                observation = await session.observe()
                selected_assertion = await session.assert_selected_option(
                    observation.elements[1].id, "Japan"
                )

        self.assertTrue(checked.success)
        self.assertTrue(checked_assertion.success)
        self.assertTrue(selected.success)
        self.assertTrue(selected_assertion.success)

    async def test_element_reference_survives_inserted_interactive_element(
        self,
    ) -> None:
        html = """
            <button id="target" onclick="document.title = 'Clicked'">Target</button>
        """
        with tempfile.TemporaryDirectory() as directory:
            async with BrowserSession(
                trace_path=Path(directory) / "trace.zip"
            ) as session:
                await session.navigate(f"data:text/html,{quote(html)}")
                observation = await session.observe()
                target_id = observation.elements[0].id
                assert session.page is not None
                await session.page.evaluate(
                    "document.body.prepend(document.createElement('button'))"
                )

                result = await session.execute(
                    ClickAction(action="click", element_id=target_id)
                )

                self.assertTrue(result.success)
                self.assertEqual(await session.page.title(), "Clicked")

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
