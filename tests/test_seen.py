from agtop.seen import UNSEEN_AFTER, SeenStore, is_unseen

NOW = 1_000_000.0


def _done(finished: float, status: str = "done", alive: bool = True) -> dict:
    return {
        "status": status,
        "alive": alive,
        "mtime": finished,
        "_event_state": {"stop_ts": finished},
    }


def test_fresh_finish_stays_green() -> None:
    assert not is_unseen(_done(NOW - 60), None, NOW)


def test_old_unchecked_finish_turns_yellow() -> None:
    assert is_unseen(_done(NOW - UNSEEN_AFTER - 1), None, NOW)


def test_checked_after_finish_stays_green() -> None:
    finished = NOW - UNSEEN_AFTER - 60
    assert not is_unseen(_done(finished), finished + 10, NOW)


def test_checked_before_finish_does_not_count() -> None:
    finished = NOW - UNSEEN_AFTER - 60
    assert is_unseen(_done(finished), finished - 10, NOW)


def test_running_waiting_or_closed_sessions_are_never_yellow() -> None:
    old = NOW - UNSEEN_AFTER - 60
    assert not is_unseen(_done(old, status="working"), None, NOW)
    assert not is_unseen(_done(old, status="waiting_question"), None, NOW)
    assert not is_unseen(_done(old, alive=False), None, NOW)


def test_without_hooks_the_log_time_is_the_finish_time() -> None:
    session = {"status": "done", "alive": True, "mtime": NOW - UNSEEN_AFTER - 1}
    assert is_unseen(session, None, NOW)


def test_store_round_trip(tmp_path) -> None:
    path = tmp_path / "seen.json"
    store = SeenStore(path)
    store.mark("s1", NOW)
    store.save(NOW)
    assert SeenStore(path).get("s1") == NOW
