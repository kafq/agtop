import asyncio

import pytest

from agtop.app import AgtopApp


@pytest.mark.parametrize(
    ("width", "detail_visible"),
    [(AgtopApp.NARROW_WIDTH - 1, False), (AgtopApp.NARROW_WIDTH, True)],
)
def test_detail_panel_hides_in_narrow_windows(monkeypatch, width, detail_visible) -> None:
    monkeypatch.setattr(AgtopApp, "_scan", lambda self: [])
    monkeypatch.setattr("agtop.app.scan_history", lambda days=7: [])

    async def run() -> None:
        app = AgtopApp()
        async with app.run_test(size=(width, 30)) as pilot:
            await pilot.pause()
            assert app.query_one("#right").display is detail_visible
            left = app.query_one("#left")
            assert (left.size.width == width) is not detail_visible

    asyncio.run(run())
