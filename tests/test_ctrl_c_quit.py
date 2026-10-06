import asyncio

from agtop.app import AgtopApp


def _app(monkeypatch) -> AgtopApp:
    monkeypatch.setattr(AgtopApp, "_scan", lambda self: [])
    monkeypatch.setattr("agtop.app.scan_history", lambda days=7: [])
    return AgtopApp()


def test_single_ctrl_c_keeps_running(monkeypatch) -> None:
    async def run() -> None:
        app = _app(monkeypatch)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+c")
            await pilot.pause()
            assert app.is_running

    asyncio.run(run())


def test_double_ctrl_c_quits(monkeypatch) -> None:
    async def run() -> None:
        app = _app(monkeypatch)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+c")
            await pilot.press("ctrl+c")
            await pilot.pause()
            assert not app.is_running

    asyncio.run(run())


def test_slow_second_ctrl_c_does_not_quit(monkeypatch) -> None:
    async def run() -> None:
        app = _app(monkeypatch)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+c")
            app._last_ctrl_c -= AgtopApp.CTRL_C_QUIT_WINDOW + 1
            await pilot.press("ctrl+c")
            await pilot.pause()
            assert app.is_running

    asyncio.run(run())
