from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

from qa_agent.assertions import (
    TextVisibleAssertion,
    TitleEqualsAssertion,
    UrlContainsAssertion,
)
from qa_agent.browser import BrowserSession


class BrowserAssertionTest(unittest.IsolatedAsyncioTestCase):
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

        self.assertTrue(url_result.success)
        self.assertTrue(title_result.success)
        self.assertTrue(text_result.success)
        self.assertFalse(failure.success)
        self.assertEqual(failure.actual, None)
        self.assertIn("50 ms", failure.error or "")


if __name__ == "__main__":
    unittest.main()
