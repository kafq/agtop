import agtop.providers as providers


def test_user_idle_seconds_parses_ioreg(monkeypatch) -> None:
    sample = '    | |     "HIDIdleTime" = 65000000000\n'
    monkeypatch.setattr(providers.subprocess, "check_output", lambda *a, **k: sample)
    assert providers.user_idle_seconds() == 65.0


def test_user_idle_seconds_unknown_without_ioreg(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise OSError("no ioreg")

    monkeypatch.setattr(providers.subprocess, "check_output", fail)
    assert providers.user_idle_seconds() is None
