import asyncio

from textual.widgets import ListView

from agtop.app import AgtopApp
from tests.test_select_on_focus import _sessions


def _run(monkeypatch, clicks: int) -> list[str]:
    monkeypatch.setattr(AgtopApp, "_scan", lambda self: _sessions(4))
    monkeypatch.setattr("agtop.app.scan_history", lambda days=7: [])
    jumped: list[str] = []
    monkeypatch.setattr(
        "agtop.app.jump_to_session",
        lambda session_id, cwd, birthtime: (jumped.append(session_id), (True, "test"))[1],
    )

    async def run() -> None:
        app = AgtopApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            target = list(app.query_one("#slist", ListView).children)[2]
            await pilot.click(target, times=clicks)
            await pilot.pause()

    asyncio.run(run())
    return jumped


def test_double_click_jumps_to_the_clicked_card(monkeypatch) -> None:
    assert _run(monkeypatch, clicks=2) == ["s2"]


def test_single_click_does_not_jump(monkeypatch) -> None:
    assert _run(monkeypatch, clicks=1) == []
