from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import quote

import pytest

from qa_agent.browser.session import BrowserSession

pytestmark = pytest.mark.browser


class TestBrowserObservation:
    async def test_distinguishes_navigation_button_from_form_submit(
        self, tmp_path
    ) -> None:
        html = """
            <header><nav><a href="/login"><button type="button">Sign in</button></a></nav></header>
            <main><form><input aria-label="Username"><button>Sign in</button></form></main>
        """
        async with BrowserSession(trace_path=tmp_path / "trace.zip") as browser:
            await browser.navigate(f"data:text/html,{quote(html)}")
            observation = await browser.observe()

        buttons = [
            element for element in observation.elements if element.role == "button"
        ]
        assert [(item.name, item.context, item.is_submit) for item in buttons] == [
            ("Sign in", "navigation", False),
            ("Sign in", "form", True),
        ]

    async def test_fingerprint_tracks_content_and_scroll_not_reference_ids(
        self, tmp_path
    ) -> None:
        html = '<button>Increase</button><output>1</output><div style="height:2000px"></div>'
        async with BrowserSession(trace_path=tmp_path / "trace.zip") as browser:
            await browser.navigate(f"data:text/html,{quote(html)}")
            first = await browser.observe()
            second = await browser.observe()
            assert first.fingerprint == second.fingerprint
            assert browser.page is not None
            await browser.page.locator("output").evaluate("el => el.textContent = '2'")
            updated = await browser.observe()
            assert first.elements == updated.elements
            assert first.fingerprint != updated.fingerprint
            await browser.page.evaluate("scrollTo(0, 100)")
            scrolled = await browser.observe()
            assert scrolled.fingerprint != updated.fingerprint

    async def test_keeps_only_available_controls_and_names_image_links(self) -> None:
        html = """
            <style>
                #offscreen { position: absolute; left: -500px; }
                #covered { position: absolute; top: 100px; left: 10px; }
                #cover { position: absolute; top: 100px; left: 10px; width: 100px;
                         height: 30px; background: black; }
            </style>
            <button>Visible</button>
            <div aria-hidden="true"><button>ARIA hidden</button></div>
            <div inert><button>Inert</button></div>
            <button id="offscreen">Offscreen</button>
            <button id="covered">Covered</button><div id="cover"></div>
            <a href="/cart"><img alt="Shopping cart"></a>
            <a onclick="void 0">JavaScript link</a>
        """
        with tempfile.TemporaryDirectory() as directory:
            async with BrowserSession(
                trace_path=Path(directory) / "trace.zip"
            ) as session:
                await session.navigate(f"data:text/html,{quote(html)}")
                observation = await session.observe()

        assert [(element.role, element.name) for element in observation.elements] == [
            ("button", "Visible"),
            ("link", "Shopping cart"),
            ("link", "JavaScript link"),
        ]
