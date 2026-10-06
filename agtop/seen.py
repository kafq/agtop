"""Remembers when you last looked at each session.

A finished session turns "done_unseen" (yellow) when it finished more than
UNSEEN_AFTER seconds ago and you have not looked at it since. Looking means
its Terminal tab was the front tab while Terminal was the active app, or you
jumped to it from agtop.
"""

import json
from pathlib import Path
from typing import Any, Optional

SEEN_PATH = Path.home() / ".config" / "agtop" / "seen.json"
UNSEEN_AFTER = 5 * 60
# Forget sessions nobody has looked at for this long, so the file stays small.
FORGET_AFTER = 14 * 24 * 60 * 60


def finished_at(session: dict[str, Any]) -> float:
    """When the last turn ended: the stop hook if present, else the log time."""
    event_state = session.get("_event_state")
    if isinstance(event_state, dict):
        stop_ts = event_state.get("stop_ts")
        if isinstance(stop_ts, (int, float)):
            return float(stop_ts)
    return float(session.get("mtime", 0))


def is_unseen(session: dict[str, Any], last_seen: Optional[float], now: float) -> bool:
    if session.get("status") not in ("done", "active") or not session.get("alive"):
        return False
    done_at = finished_at(session)
    if now - done_at <= UNSEEN_AFTER:
        return False
    return last_seen is None or last_seen < done_at


class SeenStore:
    def __init__(self, path: Path = SEEN_PATH) -> None:
        self._path = path
        self._seen: dict[str, float] = {}
        self._dirty = False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._seen = {
                    str(key): float(value)
                    for key, value in data.items()
                    if isinstance(value, (int, float))
                }
        except (OSError, ValueError):
            pass

    def get(self, session_id: str) -> Optional[float]:
        return self._seen.get(session_id)

    def mark(self, session_id: str, at: float) -> None:
        if self._seen.get(session_id, 0) < at:
            self._seen[session_id] = at
            self._dirty = True

    def save(self, now: float) -> None:
        if not self._dirty:
            return
        self._seen = {
            key: value for key, value in self._seen.items() if now - value <= FORGET_AFTER
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._seen), encoding="utf-8")
            tmp.replace(self._path)
            self._dirty = False
        except OSError:
            pass
