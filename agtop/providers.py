import json
import os
import shutil
import subprocess
import threading
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .hooks import EVENTS_DIR


def _escape_applescript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _run_osascript(script: str, timeout: int = 5) -> bool:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0
    except Exception:
        return False


def _app_running(executable_suffix: str) -> bool:
    """True when a process whose executable path ends with the suffix is running."""
    try:
        output = subprocess.check_output(["ps", "-axo", "comm="], text=True, timeout=2)
    except Exception:
        return False
    return any(line.strip().endswith(executable_suffix) for line in output.splitlines())


def _pgrep_running(*args: str) -> bool:
    try:
        result = subprocess.run(
            ["pgrep", *args],
            capture_output=True,
            timeout=2,
        )
        return result.returncode == 0
    except Exception:
        return False


def _load_terminal_info(session_id: str) -> Optional[dict[str, Any]]:
    if not session_id:
        return None

    path = EVENTS_DIR / f"{session_id}.json"
    try:
        with open(path, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
    except (OSError, json.JSONDecodeError):
        return None

    terminal = data.get("terminal")
    if not isinstance(terminal, dict) or not terminal:
        return None
    return terminal


def _normalize_term_program(term_program: Any) -> str:
    value = str(term_program or "").strip().lower()
    if not value:
        return ""
    if "kaku" in value:
        return "kaku"
    if "wezterm" in value:
        return "wezterm"
    if "iterm" in value:
        return "iterm2"
    if value in {"terminal", "apple_terminal"}:
        return "terminal"
    if "warp" in value:
        return "warp"
    return value


class TerminalProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable terminal name."""

    @abstractmethod
    def available(self) -> bool:
        """Return True if this terminal is running and reachable."""

    @abstractmethod
    def activate(self, terminal_info: dict[str, Any]) -> bool:
        """Switch to the session identified by hook-provided terminal info."""


class KakuProvider(TerminalProvider):
    def __init__(self) -> None:
        self._bin = "kaku"

    @property
    def name(self) -> str:
        return "Kaku"

    def available(self) -> bool:
        return shutil.which(self._bin) is not None

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        sock = env.get("KAKU_UNIX_SOCKET", "")
        if sock:
            env["WEZTERM_UNIX_SOCKET"] = sock
        return env

    def _list_panes(self) -> list[dict[str, Any]]:
        try:
            output = subprocess.check_output(
                [self._bin, "cli", "list", "--format", "json"],
                env=self._env(),
                text=True,
                timeout=2,
            )
            panes = json.loads(output)
        except Exception:
            return []
        return panes if isinstance(panes, list) else []

    def _resolve_target(self, terminal_info: dict[str, Any]) -> tuple[str, str] | None:
        pane_id = str(terminal_info.get("wezterm_pane", "")).strip()
        if pane_id:
            return "pane", pane_id

        tty = str(terminal_info.get("tty", "")).strip()
        if not tty:
            return None

        for pane in self._list_panes():
            if str(pane.get("tty_name", "")).strip() != tty:
                continue
            direct_pane_id = pane.get("pane_id")
            if direct_pane_id not in (None, ""):
                return "pane", str(direct_pane_id)
            tab_id = pane.get("tab_id")
            if tab_id not in (None, ""):
                return "tab", str(tab_id)
        return None

    def activate(self, terminal_info: dict[str, Any]) -> bool:
        target = self._resolve_target(terminal_info)
        if target is None:
            return False

        kind, target_id = target
        cmd = [self._bin, "cli", "activate-pane", "--pane-id", target_id]
        if kind == "tab":
            cmd = [self._bin, "cli", "activate-tab", "--tab-id", target_id]

        try:
            subprocess.run(
                cmd,
                env=self._env(),
                timeout=2,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False


class ITermProvider(TerminalProvider):
    _LIST_SCRIPT = r'''
tell application "iTerm2"
    set output to ""
    repeat with w in every window
        repeat with t in every tab of w
            repeat with s in every session of t
                set output to output & (tty of s) & linefeed
            end repeat
        end repeat
    end repeat
    return output
end tell
'''

    @property
    def name(self) -> str:
        return "iTerm2"

    def available(self) -> bool:
        return _pgrep_running("-x", "iTerm2")

    def activate(self, terminal_info: dict[str, Any]) -> bool:
        session_id = str(terminal_info.get("iterm_session", "")).strip()
        tty = str(terminal_info.get("tty", "")).strip()
        if not session_id and not tty:
            return False

        match = (
            f'id of s is "{_escape_applescript_string(session_id)}"'
            if session_id
            else f'tty of s is "{_escape_applescript_string(tty)}"'
        )
        script = f'''
tell application "iTerm2"
    activate
    repeat with w in every window
        repeat with t in every tab of w
            repeat with s in every session of t
                if {match} then
                    select w
                    tell w to select t
                    tell t to select s
                    return "ok"
                end if
            end repeat
        end repeat
    end repeat
end tell
'''
        return _run_osascript(script)


class TmuxProvider(TerminalProvider):
    @property
    def name(self) -> str:
        return "tmux"

    def available(self) -> bool:
        return shutil.which("tmux") is not None

    def _resolve_target(self, terminal_info: dict[str, Any]) -> str:
        pane = str(terminal_info.get("tmux_pane", "")).strip()
        if pane:
            return pane

        tty = str(terminal_info.get("tty", "")).strip()
        if not tty:
            return ""

        try:
            output = subprocess.check_output(
                [
                    "tmux", "list-panes", "-a",
                    "-F", "#{pane_tty}\t#{pane_id}",
                ],
                text=True,
                timeout=2,
            )
        except Exception:
            return ""

        for line in output.splitlines():
            pane_tty, _, pane_id = line.partition("\t")
            if pane_tty == tty:
                return pane_id.strip()
        return ""

    def activate(self, terminal_info: dict[str, Any]) -> bool:
        target = self._resolve_target(terminal_info)
        if not target:
            return False

        try:
            window_target = subprocess.check_output(
                [
                    "tmux", "display-message", "-p", "-t", target,
                    "#{session_name}:#{window_index}",
                ],
                text=True,
                timeout=2,
            ).strip()
        except Exception:
            window_target = ""

        if window_target:
            try:
                subprocess.run(
                    ["tmux", "switch-client", "-t", window_target.split(":", 1)[0]],
                    timeout=2,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

            try:
                subprocess.run(
                    ["tmux", "select-window", "-t", window_target],
                    timeout=2,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                return False

        try:
            subprocess.run(
                ["tmux", "select-pane", "-t", target],
                timeout=2,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False


class WezTermProvider(TerminalProvider):
    @property
    def name(self) -> str:
        return "WezTerm"

    def available(self) -> bool:
        return shutil.which("wezterm") is not None

    def _list_panes(self) -> list[dict[str, Any]]:
        try:
            output = subprocess.check_output(
                ["wezterm", "cli", "list", "--format", "json"],
                text=True,
                timeout=2,
            )
            panes = json.loads(output)
        except Exception:
            return []
        return panes if isinstance(panes, list) else []

    def _resolve_target(self, terminal_info: dict[str, Any]) -> tuple[str, str] | None:
        pane_id = str(terminal_info.get("wezterm_pane", "")).strip()
        if pane_id:
            return "pane", pane_id

        tty = str(terminal_info.get("tty", "")).strip()
        if not tty:
            return None

        for pane in self._list_panes():
            if str(pane.get("tty_name", "")).strip() != tty:
                continue
            direct_pane_id = pane.get("pane_id")
            if direct_pane_id not in (None, ""):
                return "pane", str(direct_pane_id)
            tab_id = pane.get("tab_id")
            if tab_id not in (None, ""):
                return "tab", str(tab_id)
        return None

    def activate(self, terminal_info: dict[str, Any]) -> bool:
        target = self._resolve_target(terminal_info)
        if target is None:
            return False

        kind, target_id = target
        cmd = ["wezterm", "cli", "activate-pane", "--pane-id", target_id]
        if kind == "tab":
            cmd = ["wezterm", "cli", "activate-tab", "--tab-id", target_id]

        try:
            subprocess.run(
                cmd,
                timeout=2,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False


class TerminalAppProvider(TerminalProvider):
    _LIST_SCRIPT = r'''
tell application "Terminal"
    set output to ""
    repeat with w in every window
        -- Some windows (e.g. Settings) have no tabs; skip them instead of failing.
        try
            set windowTabs to every tab of w
        on error
            set windowTabs to {}
        end try
        repeat with t in windowTabs
            set output to output & (tty of t) & linefeed
        end repeat
    end repeat
    return output
end tell
'''

    @property
    def name(self) -> str:
        return "Terminal"

    def available(self) -> bool:
        # pgrep -x Terminal misses Terminal.app on recent macOS, while ps lists
        # it by executable path, so match that path instead.
        return _app_running("/Terminal.app/Contents/MacOS/Terminal")

    def activate(self, terminal_info: dict[str, Any]) -> bool:
        tty = str(terminal_info.get("tty", "")).strip()
        if not tty:
            return False

        # Read every tab's tty in one Apple Event; asking each tab separately
        # costs a round trip per tab. Raise the right window before activating
        # Terminal, so the wrong window never shows first.
        script = f'''
tell application "Terminal"
    set target to "{_escape_applescript_string(tty)}"
    try
        set windowTtys to tty of every tab of every window
    on error
        -- Some windows (e.g. Settings) have no tabs; search them one by one.
        set windowTtys to {{}}
        repeat with w in every window
            try
                set end of windowTtys to tty of every tab of w
            on error
                set end of windowTtys to {{}}
            end try
        end repeat
    end try
    repeat with i from 1 to count of windowTtys
        set tabTtys to item i of windowTtys
        repeat with j from 1 to count of tabTtys
            if item j of tabTtys is target then
                set w to window i
                set selected tab of w to tab j of w
                set index of w to 1
                activate
                return "ok"
            end if
        end repeat
    end repeat
end tell
error "tab not found"
'''
        return _run_osascript(script)

    def window_bounds(self, tty: str) -> Optional[tuple[int, int, int, int]]:
        """Bounds (left, top, right, bottom) of the window that holds the tab."""
        tty = tty.strip()
        if not tty:
            return None
        script = f'''
tell application "Terminal"
    repeat with w in every window
        try
            set windowTabs to every tab of w
        on error
            set windowTabs to {{}}
        end try
        repeat with t in windowTabs
            if tty of t is "{_escape_applescript_string(tty)}" then
                set b to bounds of w
                return ((item 1 of b) as text) & "," & ((item 2 of b) as text) & "," & ((item 3 of b) as text) & "," & ((item 4 of b) as text)
            end if
        end repeat
    end repeat
    return ""
end tell
'''
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            values = [int(part) for part in result.stdout.strip().split(",")]
        except Exception:
            return None
        if len(values) != 4 or values[2] <= values[0] or values[3] <= values[1]:
            return None
        return values[0], values[1], values[2], values[3]

    def shake(self, tty: str) -> None:
        """Shake the window sideways, then put it back where it was.

        Blocks until the shake ends, so call it off the UI thread. The
        original position is restored even when a step fails.
        """
        tty = tty.strip()
        if not tty:
            return
        script = f'''
tell application "Terminal"
    repeat with w in every window
        try
            set windowTabs to every tab of w
        on error
            set windowTabs to {{}}
        end try
        repeat with t in windowTabs
            if tty of t is "{_escape_applescript_string(tty)}" then
                -- Use position, not bounds: on multi-display setups Terminal
                -- does not set bounds back exactly, and the window drifts.
                set original to position of w
                set {{x, y}} to original
                try
                    repeat with dx in {{14, -14, 11, -11, 7, -7, 3, -3}}
                        set position of w to {{x + dx, y}}
                        delay 0.025
                    end repeat
                end try
                set position of w to original
                return
            end if
        end repeat
    end repeat
end tell
'''
        _run_osascript(script)

    def flash(self, tty: str) -> None:
        """Blink the tab's background twice, then restore it.

        Runs as a detached osascript so the delays never block the TUI.
        """
        tty = tty.strip()
        if not tty:
            return
        script = f'''
tell application "Terminal"
    repeat with w in every window
        -- Some windows (e.g. Settings) have no tabs; skip them instead of failing.
        try
            set windowTabs to every tab of w
        on error
            set windowTabs to {{}}
        end try
        repeat with t in windowTabs
            if tty of t is "{_escape_applescript_string(tty)}" then
                set original to background color of t
                repeat 2 times
                    set background color of t to {{65535, 11565, 37008}}
                    delay 0.12
                    set background color of t to original
                    delay 0.12
                end repeat
                return
            end if
        end repeat
    end repeat
end tell
'''
        try:
            subprocess.Popen(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


class WarpProvider(TerminalProvider):
    @property
    def name(self) -> str:
        return "Warp"

    def available(self) -> bool:
        return _pgrep_running("-f", "Warp.app")

    def activate(self, terminal_info: dict[str, Any]) -> bool:
        return _run_osascript('tell application "Warp" to activate', timeout=3)


_PROVIDER_BY_KEY: dict[str, TerminalProvider] = {
    "kaku": KakuProvider(),
    "tmux": TmuxProvider(),
    "wezterm": WezTermProvider(),
    "iterm2": ITermProvider(),
    "terminal": TerminalAppProvider(),
    "warp": WarpProvider(),
}
TERMINAL_PROVIDERS: list[TerminalProvider] = list(_PROVIDER_BY_KEY.values())


def _append_provider(
    providers: list[TerminalProvider],
    key: str,
) -> None:
    provider = _PROVIDER_BY_KEY.get(key)
    if provider is not None and provider not in providers:
        providers.append(provider)


def _candidate_providers(terminal_info: dict[str, Any]) -> list[TerminalProvider]:
    providers: list[TerminalProvider] = []
    normalized = _normalize_term_program(terminal_info.get("term_program"))

    if terminal_info.get("tmux_pane"):
        _append_provider(providers, "tmux")

    if normalized:
        _append_provider(providers, normalized)

    if terminal_info.get("iterm_session"):
        _append_provider(providers, "iterm2")

    if terminal_info.get("wezterm_pane"):
        if normalized == "wezterm":
            _append_provider(providers, "wezterm")
            _append_provider(providers, "kaku")
        else:
            _append_provider(providers, "kaku")
            _append_provider(providers, "wezterm")

    if terminal_info.get("term_session_id"):
        _append_provider(providers, "terminal")

    if terminal_info.get("tty"):
        for key in ("kaku", "wezterm", "iterm2", "terminal"):
            _append_provider(providers, key)

    if normalized == "warp":
        _append_provider(providers, "warp")

    return providers


def _provider_known_ttys(provider: TerminalProvider) -> set[str]:
    if isinstance(provider, KakuProvider):
        return {
            str(pane.get("tty_name", "")).strip()
            for pane in provider._list_panes()
            if str(pane.get("tty_name", "")).strip()
        }

    if isinstance(provider, WezTermProvider):
        return {
            str(pane.get("tty_name", "")).strip()
            for pane in provider._list_panes()
            if str(pane.get("tty_name", "")).strip()
        }

    if isinstance(provider, TmuxProvider):
        try:
            output = subprocess.check_output(
                ["tmux", "list-panes", "-a", "-F", "#{pane_tty}"],
                text=True,
                timeout=2,
            )
        except Exception:
            return set()
        return {line.strip() for line in output.splitlines() if line.strip()}

    if isinstance(provider, ITermProvider):
        try:
            output = subprocess.check_output(
                ["osascript", "-e", provider._LIST_SCRIPT],
                text=True,
                timeout=5,
            )
        except Exception:
            return set()
        return {line.strip() for line in output.splitlines() if line.strip()}

    if isinstance(provider, TerminalAppProvider):
        try:
            output = subprocess.check_output(
                ["osascript", "-e", provider._LIST_SCRIPT],
                text=True,
                timeout=5,
            )
        except Exception:
            return set()
        return {line.strip() for line in output.splitlines() if line.strip()}

    return set()


def _is_warp_process(pid: str, ps_cache: dict[str, dict[str, str]]) -> bool:
    cur = pid
    visited: set[str] = set()
    for _ in range(6):
        info = ps_cache.get(cur)
        if not info or cur in visited:
            break
        visited.add(cur)
        if "Warp.app" in info.get("cmd", ""):
            return True
        cur = info.get("ppid", "1")
    return False


def _pid_cwd(pid: str) -> str:
    try:
        output = subprocess.check_output(
            ["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"],
            text=True,
            timeout=2,
        )
        for line in output.splitlines():
            if line.startswith("n/"):
                return line[1:]
    except Exception:
        pass
    return ""


def _resolve_tty(
    pid: str,
    known_ttys: set[str],
    ps_cache: dict[str, dict[str, str]],
) -> Optional[str]:
    tty = ps_cache.get(pid, {}).get("tty")
    if tty and f"/dev/{tty}" in known_ttys:
        return f"/dev/{tty}"

    cur = pid
    visited: set[str] = set()
    for _ in range(5):
        info = ps_cache.get(cur)
        if not info or cur in visited:
            break
        visited.add(cur)
        ppid = info.get("ppid", "1")
        if ppid in ("1", "0"):
            server_cmd = info.get("cmd", "")
            for pinfo in ps_cache.values():
                cmd = pinfo.get("cmd", "")
                tty_name = pinfo.get("tty", "")
                if not tty_name or tty_name == "??":
                    continue
                tty_path = f"/dev/{tty_name}"
                if tty_path not in known_ttys:
                    continue
                if ("zellij" in cmd and "zellij" in server_cmd) or (
                    "tmux" in cmd and "tmux" in server_cmd
                ):
                    return tty_path
            break
        cur = ppid
        tty_name = ps_cache.get(cur, {}).get("tty")
        if tty_name and f"/dev/{tty_name}" in known_ttys:
            return f"/dev/{tty_name}"
    return None


def _match_session_to_pid(
    cwd: str,
    session_id: str,
    birthtime: float,
    ps_cache: dict[str, dict[str, str]],
) -> Optional[str]:
    if session_id:
        for pid, cmd, _ in _iter_cli_pids(ps_cache):
            if f"--resume {session_id}" in cmd:
                return pid

    target = cwd.rstrip("/")
    if not target:
        return None

    candidates: list[str] = []
    for pid, _, _ in _iter_cli_pids(ps_cache):
        if _pid_cwd(pid).rstrip("/") == target:
            candidates.append(pid)

    if len(candidates) == 1:
        return candidates[0]

    if len(candidates) > 1 and birthtime > 0:
        best_pid = None
        best_diff = float("inf")
        for pid in candidates:
            process_start = _pid_start_time(pid)
            if process_start > 0 and process_start <= birthtime:
                diff = birthtime - process_start
                if diff < best_diff:
                    best_diff = diff
                    best_pid = pid
        if best_pid:
            return best_pid

    return None


def _fallback_jump(
    cwd: str,
    session_id: str,
    birthtime: float,
) -> tuple[bool, str]:
    if not cwd:
        return False, "No cwd"

    ps_cache = _build_ps_cache()
    exact_pid = _match_session_to_pid(cwd, session_id, birthtime, ps_cache)

    fallback_providers = [
        _PROVIDER_BY_KEY["kaku"],
        _PROVIDER_BY_KEY["tmux"],
        _PROVIDER_BY_KEY["wezterm"],
        _PROVIDER_BY_KEY["iterm2"],
        _PROVIDER_BY_KEY["terminal"],
    ]
    for provider in fallback_providers:
        if not provider.available():
            continue
        known_ttys = _provider_known_ttys(provider)
        if not known_ttys:
            continue

        resolved = None
        if exact_pid:
            resolved = _resolve_tty(exact_pid, known_ttys, ps_cache)
        else:
            target = cwd.rstrip("/")
            for pid, _, _ in _iter_cli_pids(ps_cache):
                if _pid_cwd(pid).rstrip("/") == target:
                    resolved = _resolve_tty(pid, known_ttys, ps_cache)
                    if resolved:
                        break

        if resolved and provider.activate({"tty": resolved}):
            _flash_terminal_tab(provider, resolved)
            return True, f"{provider.name} fallback"

    warp = _PROVIDER_BY_KEY["warp"]
    if warp.available():
        target = cwd.rstrip("/")
        for pid, _, _ in _iter_cli_pids(ps_cache):
            if _pid_cwd(pid).rstrip("/") == target and _is_warp_process(pid, ps_cache):
                if warp.activate({}):
                    return True, "Warp fallback"

    return False, "not found"


def terminal_front_tty() -> str:
    """TTY of Terminal's front tab, or "" when Terminal is not the active app.

    Checks first that Terminal runs, because "tell application" would
    launch it otherwise.
    """
    if not _app_running("/Terminal.app/Contents/MacOS/Terminal"):
        return ""
    script = '''
tell application "Terminal"
    if not frontmost then return ""
    try
        return tty of selected tab of front window
    on error
        return ""
    end try
end tell
'''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return ""
    return result.stdout.strip()


def user_idle_seconds() -> Optional[float]:
    """Seconds since the last keyboard, mouse or trackpad input, or None."""
    try:
        output = subprocess.check_output(
            ["ioreg", "-c", "IOHIDSystem", "-d", "4"],
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    for line in output.splitlines():
        if '"HIDIdleTime"' in line:
            try:
                return int(line.rsplit("=", 1)[1].strip()) / 1_000_000_000
            except ValueError:
                return None
    return None


def pid_ttys(pids: list[str]) -> dict[str, str]:
    """Map each pid to its controlling TTY as "/dev/ttysNNN"."""
    if not pids:
        return {}
    try:
        output = subprocess.check_output(
            ["ps", "-o", "pid=,tty=", "-p", ",".join(pids)],
            text=True,
            timeout=2,
        )
    except Exception:
        return {}
    ttys: dict[str, str] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] not in ("??", "-"):
            ttys[parts[0]] = f"/dev/{parts[1]}"
    return ttys


JUMP_EFFECTS = ("pulse", "flash", "none")
PULSE_HELPER = Path(__file__).resolve().parent.parent / "bin" / "agtop-pulse"

_jump_effect = "pulse"
_jump_shake = True


def set_jump_effect(effect: str, shake: bool = True) -> None:
    global _jump_effect, _jump_shake
    _jump_effect = effect if effect in JUMP_EFFECTS else "pulse"
    _jump_shake = shake


def _pulse_helper() -> Optional[str]:
    if PULSE_HELPER.is_file() and os.access(PULSE_HELPER, os.X_OK):
        return str(PULSE_HELPER)
    return shutil.which("agtop-pulse")


def _pulse_or_flash(provider: "TerminalAppProvider", tty: str) -> None:
    helper = _pulse_helper()
    bounds = provider.window_bounds(tty) if helper else None
    if helper and bounds:
        try:
            subprocess.Popen(
                [helper, *(str(value) for value in bounds)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            pass
    provider.flash(tty)


def _highlight_window(provider: "TerminalAppProvider", tty: str) -> None:
    # Shake first and wait for it: the pulse reads the window bounds once,
    # so it must start after the window is back in place.
    if _jump_shake:
        provider.shake(tty)
    if _jump_effect == "pulse":
        _pulse_or_flash(provider, tty)
    elif _jump_effect == "flash":
        provider.flash(tty)


def _flash_terminal_tab(provider: TerminalProvider, tty: str) -> None:
    if not isinstance(provider, TerminalAppProvider):
        return
    if not _jump_shake and _jump_effect == "none":
        return
    # Every step is a blocking osascript call; keep them off the UI thread.
    threading.Thread(target=_highlight_window, args=(provider, tty), daemon=True).start()


def jump_to_session(
    session_id: str,
    cwd: str = "",
    birthtime: float = 0,
) -> tuple[bool, str]:
    terminal_info = _load_terminal_info(session_id)
    no_hook_msg = "run agtop --install-hooks, then start a new Claude session"
    if terminal_info is not None:
        providers = _candidate_providers(terminal_info)
        activated: list[str] = []
        for provider in providers:
            if not provider.available():
                continue
            if not provider.activate(terminal_info):
                continue
            _flash_terminal_tab(provider, str(terminal_info.get("tty", "")))
            activated.append(provider.name)
            if provider.name != "tmux":
                return True, " + ".join(activated)
        if activated:
            return True, " + ".join(activated)

    # Without hook data (hooks not installed, or a session started before
    # they were), find the tab through the agent process's TTY instead.
    ok, via = _fallback_jump(cwd, session_id, birthtime)
    if ok:
        return ok, via
    return False, no_hook_msg if terminal_info is None else via


def has_active_children(pid: str) -> bool:
    """Check if a process has actively running child processes.

    When waiting for permission: claude is blocked on stdin, no children.
    When tool is executing: there's a child process (shell, node, etc).
    """
    try:
        out = subprocess.check_output(
            ["pgrep", "-P", pid],
            text=True,
            timeout=2,
        )
        return bool(out.strip())
    except Exception:
        return False


def _etime_seconds(etime: str) -> Optional[float]:
    """Parse ps etime ("[[dd-]hh:]mm:ss") into seconds."""
    days, _, clock = etime.strip().rpartition("-")
    try:
        parts = [int(part) for part in clock.split(":")]
        seconds = int(days) * 86400 if days else 0
    except ValueError:
        return None
    clock_seconds = 0
    for part in parts:
        clock_seconds = clock_seconds * 60 + part
    return seconds + clock_seconds


def has_children_younger_than(pid: str, seconds: float) -> bool:
    """True when the process has a child started within the last `seconds`.

    Claude keeps long-lived children (MCP servers) for its whole life, so
    only children younger than the current turn point to a running tool.
    """
    try:
        children = subprocess.check_output(["pgrep", "-P", pid], text=True, timeout=2).split()
        if not children:
            return False
        output = subprocess.check_output(
            ["ps", "-o", "etime=", "-p", ",".join(children)],
            text=True,
            timeout=2,
        )
    except Exception:
        return False
    for line in output.splitlines():
        age = _etime_seconds(line)
        if age is not None and age < seconds:
            return True
    return False


def _build_ps_cache() -> dict[str, dict[str, str]]:
    cache: dict[str, dict[str, str]] = {}
    try:
        output = subprocess.check_output(
            ["ps", "-eo", "pid,ppid,tty,args"],
            text=True,
            timeout=2,
        )
    except Exception:
        return cache

    for line in output.strip().splitlines()[1:]:
        parts = line.split()
        if len(parts) < 4:
            continue
        cache[parts[0]] = {
            "ppid": parts[1],
            "tty": parts[2],
            "cmd": " ".join(parts[3:]),
        }
    return cache


def _iter_cli_pids(ps_cache: dict[str, dict[str, str]]):
    """Yield (pid, cmd, source) for all Claude and Codex CLI processes."""
    for pid, info in ps_cache.items():
        cmd = info["cmd"]
        first_arg = cmd.split()[0] if cmd else ""
        basename = first_arg.rsplit("/", 1)[-1] if first_arg else ""
        if basename == "claude":
            yield pid, cmd, "claude"
            continue
        if basename == "codex":
            yield pid, cmd, "codex"


def _pid_start_time(pid: str) -> float:
    try:
        output = subprocess.check_output(
            ["ps", "-o", "lstart=", "-p", pid],
            text=True,
            timeout=2,
        ).strip()
        return datetime.strptime(output, "%a %b %d %H:%M:%S %Y").timestamp()
    except Exception:
        return 0


def get_live_session_ids(sessions: list[dict]) -> dict[str, str]:
    """Return {session_id: pid} for sessions with a running claude process.

    Direction: for each process, find the best matching session (not vice versa).
    One process → at most one session_id marked alive.
    """
    ps_cache = _build_ps_cache()
    cli_pids = list(_iter_cli_pids(ps_cache))
    if not cli_pids:
        return {}

    all_pids = [pid for pid, _, _ in cli_pids]
    pid_cwd: dict[str, str] = {}
    try:
        out = subprocess.check_output(
            ["lsof", "-a", "-p", ",".join(all_pids), "-d", "cwd", "-Fn"],
            text=True,
            timeout=3,
        )
        cur = None
        for line in out.splitlines():
            if line.startswith("p"):
                cur = line[1:]
            elif line.startswith("n") and cur:
                pid_cwd[cur] = line[1:].rstrip("/")
    except Exception:
        return {}

    from collections import defaultdict

    sessions_by_cwd: dict[str, list[dict]] = defaultdict(list)
    sessions_by_id: dict[str, dict] = {}
    for session in sessions:
        sessions_by_cwd[session["cwd"].rstrip("/")].append(session)
        sessions_by_id[session["session_id"]] = session

    live_map: dict[str, str] = {}
    running = {pid for pid, _, _ in cli_pids}

    # 1. Hook data names the exact process. One process can move to a new
    #    session (/clear, /resume); its latest hook event wins.
    latest_by_pid: dict[str, tuple[float, str]] = {}
    for session in sessions:
        event_state = session.get("_event_state")
        if not isinstance(event_state, dict):
            continue
        pid = str(event_state.get("pid") or "")
        if pid not in running:
            continue
        stamp = float(event_state.get("last_event_ts") or 0)
        if stamp >= latest_by_pid.get(pid, (-1.0, ""))[0]:
            latest_by_pid[pid] = (stamp, session["session_id"])
    for pid, (_, session_id) in latest_by_pid.items():
        live_map[session_id] = pid

    claimed = set(live_map)
    for pid, cmd, _ in cli_pids:
        if pid in latest_by_pid:
            continue
        cwd = pid_cwd.get(pid, "").rstrip("/")
        if not cwd:
            continue

        # 2. A resumed session carries its id on the command line.
        matched = False
        for session_id in sessions_by_id:
            if session_id not in claimed and f"--resume {session_id}" in cmd:
                live_map[session_id] = pid
                claimed.add(session_id)
                matched = True
                break
        if matched:
            continue

        # 3. Otherwise the most recently written session in the same folder:
        #    a running process writes to its current session, and start
        #    times stop matching once the process switches sessions.
        cwd_sessions = [
            session
            for session in sessions_by_cwd.get(cwd, [])
            if session["session_id"] not in claimed
        ]
        if not cwd_sessions:
            continue
        newest = max(cwd_sessions, key=lambda session: session.get("mtime", 0))
        live_map[newest["session_id"]] = pid
        claimed.add(newest["session_id"])

    return live_map
