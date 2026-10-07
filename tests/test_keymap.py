import asyncio

from agtop.app import AgtopApp
from agtop.keymap import latin_key


def test_layout_letters_map_to_their_key() -> None:
    assert latin_key("о") == "j"  # Russian J key
    assert latin_key("й") == "q"
    assert latin_key("і") == "s"  # Ukrainian / Belarusian S key
    assert latin_key("ў") == "o"  # Belarusian O key
    assert latin_key("О") == "J"
    assert latin_key("j") is None
    assert latin_key("ctrl+c") is None


def test_russian_q_quits(monkeypatch) -> None:
    monkeypatch.setattr(AgtopApp, "_scan", lambda self: [])
    monkeypatch.setattr("agtop.app.scan_history", lambda days=7: [])

    async def run() -> None:
        app = AgtopApp()
        async with app.run_test() as pilot:
            await pilot.press("й")
            await pilot.pause()
            assert not app.is_running

    asyncio.run(run())


def test_russian_h_toggles_history(monkeypatch) -> None:
    monkeypatch.setattr(AgtopApp, "_scan", lambda self: [])
    monkeypatch.setattr("agtop.app.scan_history", lambda days=7: [])

    async def run() -> None:
        app = AgtopApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("р")
            await pilot.pause()
            assert app._history_mode

    asyncio.run(run())
