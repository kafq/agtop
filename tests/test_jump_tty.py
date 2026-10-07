import json

import agtop.providers as providers


def _event(tmp_path, monkeypatch, terminal: dict, ps_output: str) -> None:
    monkeypatch.setattr(providers, "EVENTS_DIR", tmp_path)
    (tmp_path / "s1.json").write_text(json.dumps({"pid": 123, "terminal": terminal}))
    monkeypatch.setattr(providers.subprocess, "check_output", lambda *a, **k: ps_output)


def test_missing_tty_comes_from_the_agent_process(tmp_path, monkeypatch) -> None:
    _event(tmp_path, monkeypatch, {"term_program": "Apple_Terminal"}, "ttys022 claude\n")
    assert providers._load_terminal_info("s1")["tty"] == "/dev/ttys022"


def test_a_reused_pid_is_not_trusted(tmp_path, monkeypatch) -> None:
    _event(tmp_path, monkeypatch, {"term_program": "Apple_Terminal"}, "ttys022 vim\n")
    assert "tty" not in providers._load_terminal_info("s1")


def test_a_recorded_tty_is_kept(tmp_path, monkeypatch) -> None:
    _event(tmp_path, monkeypatch, {"tty": "/dev/ttys001"}, "ttys022 claude\n")
    assert providers._load_terminal_info("s1")["tty"] == "/dev/ttys001"
