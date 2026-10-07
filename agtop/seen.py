"""Remembers when you last looked at each session, and classifies finished ones.

A finished open session is:
- "done_unseen" (blue) from the moment it finishes until you look at it,
- "done" (green) after you looked, for IDLE_AFTER seconds since your last look,
- "idle" (grey) once you have not looked for longer than that.

Looking means its Terminal tab was the front tab while Terminal was the
active app and you were using the keyboard or mouse, or you jumped to it
from agtop.
"""

import json
from pathlib import Path
from typing import Any, Optional

SEEN_PATH = Path.home() / ".config" / "agtop" / "seen.json"
IDLE_AFTER = 5 * 60
# Forget sessions nobody has looked at for this long, so the file stays small.
FORGET_AFTER = 14 * 24 * 60 * 60
FINISHED_STATUSES = ("done", "active")


def finished_at(session: dict[str, Any]) -> float:
    """When the last turn ended: the stop hook if present, else the log time."""
    event_state = session.get("_event_state")
    if isinstance(event_state, dict):
        stop_ts = event_state.get("stop_ts")
        if isinstance(stop_ts, (int, float)):
            return float(stop_ts)
    return float(session.get("mtime", 0))


def finished_status(
    session: dict[str, Any],
    last_seen: Optional[float],
    now: float,
    idle_after: float = IDLE_AFTER,
) -> str:
    """Status for a finished, open session: done_unseen, done or idle."""
    if last_seen is None or last_seen < finished_at(session):
        return "done_unseen"
    if now - last_seen <= idle_after:
        return "done"
    return "idle"


def classify(
    session: dict[str, Any],
    last_seen: Optional[float],
    now: float,
    idle_after: float = IDLE_AFTER,
) -> str:
    """The session's display status. Only finished, open sessions change."""
    status = str(session.get("status", ""))
    if status not in FINISHED_STATUSES or not session.get("alive"):
        return status
    return finished_status(session, last_seen, now, idle_after)


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
