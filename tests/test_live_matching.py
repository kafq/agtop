import agtop.providers as providers


def test_etime_parsing() -> None:
    assert providers._etime_seconds("06-20:15:21") == 591321
    assert providers._etime_seconds("22:00:57") == 79257
    assert providers._etime_seconds("01:22") == 82
    assert providers._etime_seconds("bad") is None


def _session(session_id: str, cwd: str, mtime: float, pid=None, last_event_ts=0.0) -> dict:
    session = {"session_id": session_id, "cwd": cwd, "mtime": mtime}
    if pid:
        session["_event_state"] = {"pid": pid, "last_event_ts": last_event_ts}
    return session


def _fake_processes(monkeypatch, pids_to_cwd: dict[str, str]) -> None:
    cache = {pid: {"ppid": "1", "tty": "ttys001", "cmd": "claude"} for pid in pids_to_cwd}
    monkeypatch.setattr(providers, "_build_ps_cache", lambda: cache)
    lsof = "".join(f"p{pid}\nn{cwd}\n" for pid, cwd in pids_to_cwd.items())
    monkeypatch.setattr(providers.subprocess, "check_output", lambda *a, **k: lsof)


def test_hook_pid_beats_folder_guess(monkeypatch) -> None:
    _fake_processes(monkeypatch, {"100": "/p"})
    sessions = [
        _session("old", "/p", mtime=50),
        _session("new", "/p", mtime=10, pid=100, last_event_ts=10),
    ]
    assert providers.get_live_session_ids(sessions) == {"new": "100"}


def test_latest_hook_event_wins_after_session_switch(monkeypatch) -> None:
    _fake_processes(monkeypatch, {"100": "/p"})
    sessions = [
        _session("before-clear", "/p", mtime=10, pid=100, last_event_ts=10),
        _session("after-clear", "/p", mtime=20, pid=100, last_event_ts=20),
    ]
    assert providers.get_live_session_ids(sessions) == {"after-clear": "100"}


def test_without_hooks_newest_log_in_folder_wins(monkeypatch) -> None:
    _fake_processes(monkeypatch, {"100": "/p"})
    sessions = [_session("stale", "/p", mtime=10), _session("current", "/p", mtime=99)]
    assert providers.get_live_session_ids(sessions) == {"current": "100"}


def test_two_processes_in_one_folder_get_different_sessions(monkeypatch) -> None:
    _fake_processes(monkeypatch, {"100": "/p", "200": "/p"})
    sessions = [_session("a", "/p", mtime=10), _session("b", "/p", mtime=20)]
    live = providers.get_live_session_ids(sessions)
    assert set(live) == {"a", "b"} and set(live.values()) == {"100", "200"}
