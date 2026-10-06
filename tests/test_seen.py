from agtop.seen import IDLE_AFTER, SeenStore, classify

NOW = 1_000_000.0


def _finished(finished: float, status: str = "done", alive: bool = True) -> dict:
    return {
        "status": status,
        "alive": alive,
        "mtime": finished,
        "_event_state": {"stop_ts": finished},
    }


def test_just_finished_and_not_looked_is_yellow() -> None:
    assert classify(_finished(NOW - 5), None, NOW) == "done_unseen"


def test_looked_before_it_finished_is_still_yellow() -> None:
    assert classify(_finished(NOW - 60), NOW - 120, NOW) == "done_unseen"


def test_looked_after_it_finished_is_green() -> None:
    assert classify(_finished(NOW - 60), NOW - 30, NOW) == "done"


def test_looked_long_ago_turns_grey() -> None:
    finished = NOW - IDLE_AFTER - 120
    assert classify(_finished(finished), NOW - IDLE_AFTER - 1, NOW) == "idle"


def test_other_states_are_unchanged() -> None:
    assert classify(_finished(NOW - 5, status="working"), None, NOW) == "working"
    assert classify(_finished(NOW - 5, status="waiting_question"), None, NOW) == "waiting_question"
    assert classify(_finished(NOW - 5, alive=False), None, NOW) == "done"


def test_without_hooks_the_log_time_is_the_finish_time() -> None:
    session = {"status": "done", "alive": True, "mtime": NOW - 10}
    assert classify(session, NOW - 5, NOW) == "done"
    assert classify(session, NOW - 20, NOW) == "done_unseen"


def test_store_round_trip(tmp_path) -> None:
    path = tmp_path / "seen.json"
    store = SeenStore(path)
    store.mark("s1", NOW)
    store.save(NOW)
    assert SeenStore(path).get("s1") == NOW
