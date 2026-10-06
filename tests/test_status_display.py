import time

from agtop.parser import _compute_status_from_event
from agtop.render import SPINNER_FRAMES, render_card


def _session(status: str) -> dict:
    return {
        "session_id": "s1",
        "project": "demo",
        "task": "build it",
        "last_text": "",
        "status": status,
        "task_runtime": 42.0,
        "tool_summary": "",
    }


def test_hook_prompt_stays_working_for_long_turns() -> None:
    now = time.time()
    state = {"last_event": "prompt", "last_event_ts": now - 600, "status": "working"}
    assert _compute_status_from_event(state, now) == "working"


def test_hook_stop_is_done() -> None:
    now = time.time()
    state = {"last_event": "stop", "stop_ts": now - 5, "status": "done"}
    assert _compute_status_from_event(state, now) == "done"


def test_card_colours() -> None:
    assert render_card(_session("waiting_question")).startswith("🔴")
    assert render_card(_session("waiting_permission")).startswith("🔴")
    assert render_card(_session("done")).startswith("🟢")
    assert render_card(_session("active")).startswith("🟢")


def test_running_card_spins() -> None:
    frames = {render_card(_session("working"), frame).split("[/bold cyan]")[0] for frame in range(len(SPINNER_FRAMES))}
    assert len(frames) == len(SPINNER_FRAMES)
