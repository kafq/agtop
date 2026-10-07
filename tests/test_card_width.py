import asyncio

from textual.widgets import ListView, Static

from agtop.app import AgtopApp
from tests.test_select_on_focus import _sessions


def test_card_text_fills_the_card_after_a_resize(monkeypatch) -> None:
    long = [dict(s, task="x" * 300, last_text="y" * 300) for s in _sessions(2)]
    monkeypatch.setattr(AgtopApp, "_scan", lambda self: long)
    monkeypatch.setattr("agtop.app.scan_history", lambda days=7: [])

    async def run() -> None:
        app = AgtopApp()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            for width in (70, 90):
                await pilot.resize_terminal(width, 30)
                await pilot.pause()
                await pilot.pause()
                item = app.query_one("#slist", ListView).children[0]
                task_line = str(item.query_one(Static).render()).splitlines()[1]
                assert len(task_line) == item.content_size.width

    asyncio.run(run())
