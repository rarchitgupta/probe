from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

from qa_agent.browser import BrowserSession


class BrowserObservationTest(unittest.IsolatedAsyncioTestCase):
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
        """
        with tempfile.TemporaryDirectory() as directory:
            async with BrowserSession(trace_path=Path(directory) / "trace.zip") as session:
                await session.navigate(f"data:text/html,{quote(html)}")
                observation = await session.observe()

        self.assertEqual(
            [(element.role, element.name) for element in observation.elements],
            [("button", "Visible"), ("link", "Shopping cart")],
        )


if __name__ == "__main__":
    unittest.main()
