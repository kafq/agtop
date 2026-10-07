import asyncio

from textual import events
from textual.widgets import ListView

from agtop.app import AgtopApp


def _sessions(count: int) -> list[dict]:
    return [
        {
            "session_id": f"s{index}",
            "project": f"p{index}",
            "cwd": "/p",
            "task": "",
            "last_text": "",
            "status": "done",
            "task_runtime": None,
            "tool_summary": "",
            "alive": True,
            "mtime": 0,
            "age": 0,
            "turns": [],
        }
        for index in range(count)
    ]


def test_focusing_the_window_selects_the_hovered_card(monkeypatch) -> None:
    monkeypatch.setattr(AgtopApp, "_scan", lambda self: _sessions(4))
    monkeypatch.setattr("agtop.app.scan_history", lambda days=7: [])

    async def run() -> None:
        app = AgtopApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            listview = app.query_one("#slist", ListView)
            app.post_message(events.AppBlur())
            await pilot.pause()
            target = list(listview.children)[2]
            await pilot.hover(target)
            app.post_message(events.AppFocus())
            await pilot.pause()
            await pilot.pause()
            assert listview.index == 2
            items = list(listview.children)
            assert "-highlight" in items[2].classes
            assert items[2].styles.border_top[0] == "double"
            assert app.focused is listview

    asyncio.run(run())


def test_focusing_with_the_mouse_elsewhere_keeps_the_selection(monkeypatch) -> None:
    monkeypatch.setattr(AgtopApp, "_scan", lambda self: _sessions(4))
    monkeypatch.setattr("agtop.app.scan_history", lambda days=7: [])

    async def run() -> None:
        app = AgtopApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            listview = app.query_one("#slist", ListView)
            await pilot.hover("Footer")
            app.post_message(events.AppFocus())
            await pilot.pause()
            assert listview.index == 0

    asyncio.run(run())


def test_selected_card_has_a_strong_highlight(monkeypatch) -> None:
    """Guards against Textual renaming its highlight class again."""
    monkeypatch.setattr(AgtopApp, "_scan", lambda self: _sessions(3))
    monkeypatch.setattr("agtop.app.scan_history", lambda days=7: [])

    async def run() -> None:
        app = AgtopApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            listview = app.query_one("#slist", ListView)
            assert app.focused is listview
            listview.index = 1
            await pilot.pause()
            selected, other = list(listview.children)[1], list(listview.children)[0]
            assert selected.styles.border_top[0] == "double"
            assert other.styles.border_top[0] != "double"

    asyncio.run(run())
