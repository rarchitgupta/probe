from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import quote

import pytest

from qa_agent.agent.assertions import (
    RegionContainsAssertion,
    TextVisibleAssertion,
    TitleEqualsAssertion,
    UrlContainsAssertion,
)
from qa_agent.browser.session import BrowserSession

pytestmark = pytest.mark.browser


class TestBrowserAssertion:
    async def test_evaluates_generic_browser_conditions(self) -> None:
        html = """
            <title>Loading</title>
            <script>
                setTimeout(() => {
                    document.title = 'Dashboard';
                    document.body.insertAdjacentHTML('beforeend', '<p>Account ready</p>');
                }, 25);
            </script>
        """
        with tempfile.TemporaryDirectory() as directory:
            async with BrowserSession(
                trace_path=Path(directory) / "trace.zip"
            ) as session:
                await session.navigate(f"data:text/html,{quote(html)}")

                url_result = await session.assert_that(
                    UrlContainsAssertion("url_contains", "data:text/html")
                )
                title_result = await session.assert_that(
                    TitleEqualsAssertion("title_equals", "Dashboard")
                )
                text_result = await session.assert_that(
                    TextVisibleAssertion("text_visible", "Account ready", exact=True)
                )
                failure = await session.assert_that(
                    TextVisibleAssertion("text_visible", "Missing text"),
                    timeout_ms=50,
                )

                assert session.page is not None
                await session.page.set_content(
                    "<section><h2>Mechanical Keyboard</h2><span>Quantity</span>"
                    "<strong>2</strong></section><section><h2>Mouse</h2>"
                    "<strong>1</strong></section>"
                )
                region = await session.assert_that(
                    RegionContainsAssertion(
                        "region_contains", "Mechanical Keyboard", ("Quantity", "2")
                    )
                )

        assert url_result.success
        assert title_result.success
        assert text_result.success
        assert not failure.success
        assert failure.actual is None
        assert "50 ms" in (failure.error or "")
        assert region.success
        assert isinstance(region.actual, str)
        assert "Mechanical Keyboard" in region.actual
