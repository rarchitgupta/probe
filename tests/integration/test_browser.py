from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from urllib.parse import quote

import pytest

from qa_agent.browser import (
    BrowserSession,
    ClickAction,
    FillAction,
    ScrollAction,
    SelectOptionAction,
    SetCheckedAction,
)

pytestmark = pytest.mark.browser


class TestBrowserSession:
    async def test_reobserves_after_target_disappears_during_model_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            async with BrowserSession(
                trace_path=Path(directory) / "trace.zip"
            ) as session:
                await session.navigate(
                    f"data:text/html,{quote('<label>Username<input></label>')}"
                )
                observation = await session.observe()
                assert session.page is not None
                # Simulate the SPA replacing the form after observation.
                await session.page.evaluate(
                    "document.body.innerHTML = '<button>Catalog</button>'"
                )
                async with asyncio.timeout(2):
                    result = await session.execute(
                        FillAction("fill", observation.elements[0].id, "user")
                    )
                assert not result.success
                assert result.error is not None
                assert "disappeared" in result.error
                fresh = await session.observe()
                assert fresh.elements[0].name == "Catalog"
                assert (
                    await session.execute(ClickAction("click", fresh.elements[0].id))
                ).success

    async def test_observes_control_rendered_on_next_animation_frame(self) -> None:
        html = """
            <button onclick="requestAnimationFrame(() => requestAnimationFrame(() => {
                const button = document.createElement('button');
                button.textContent = 'Increase quantity';
                document.body.append(button);
            }))">Open cart</button>
        """
        with tempfile.TemporaryDirectory() as directory:
            async with BrowserSession(
                trace_path=Path(directory) / "trace.zip"
            ) as session:
                await session.navigate(f"data:text/html,{quote(html)}")
                initial = await session.observe()
                await session.execute(ClickAction("click", initial.elements[0].id))

                observation = await session.observe()

        assert "Increase quantity" in [element.name for element in observation.elements]

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

        assert clicked.success
        assert assertion.success

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

        assert top.can_scroll_down
        assert down.success
        assert bottom.can_scroll_up
        assert "Bottom action" in [element.name for element in bottom.elements]
        assert up.success
        assert not top_again.can_scroll_up
        assert "Top action" in [element.name for element in top_again.elements]

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
                assert not observation.elements[0].checked
                assert observation.elements[1].selected_option == "Canada"

                checked = await session.execute(
                    SetCheckedAction("set_checked", checkbox_id, True)
                )
                observation = await session.observe()
                assert observation.elements[0].checked
                checked_assertion = await session.assert_checked(
                    observation.elements[0].id, True
                )

                selected = await session.execute(
                    SelectOptionAction(
                        "select_option", observation.elements[1].id, "Japan"
                    )
                )
                observation = await session.observe()
                assert observation.elements[1].selected_option == "Japan"
                selected_assertion = await session.assert_selected_option(
                    observation.elements[1].id, "Japan"
                )

        assert checked.success
        assert checked_assertion.success
        assert selected.success
        assert selected_assertion.success

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

                assert result.success
                assert await session.page.title() == "Clicked"

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
                assert not observation.elements[0].filled
                result = await session.execute(
                    FillAction(
                        action="fill", element_id=username_id, value="standard_user"
                    )
                )
                assert result.success

                stale_result = await session.execute(
                    ClickAction(action="click", element_id=username_id)
                )
                assert not stale_result.success

                observation = await session.observe()
                assert observation.elements[0].filled
                password_id = observation.elements[1].id
                result = await session.execute(
                    FillAction(action="fill", element_id=password_id, value="secret")
                )
                assert result.success

                observation = await session.observe()
                login_id = observation.elements[2].id
                result = await session.execute(
                    ClickAction(action="click", element_id=login_id)
                )
                assert result.success

                observation = await session.observe()
                assert observation.title == "Dashboard"
