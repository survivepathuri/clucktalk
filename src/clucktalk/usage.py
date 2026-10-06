"""Anonymous usage counters for the pilot (Step 51 part D): numbers only, so they can be published.

What is kept: the days the page was used (as dates, so a day is counted once), how many records the farmer confirmed,
how many watch and alert answers he was shown, and how many read-backs he confirmed or cancelled. What is never kept:
a word he said, a shed, a number he logged, a token, a session, an address or a time of day. The file is one small JSON
file next to the pilot's own state file; ``python tasks.py pilot-stats`` prints only the totals (not even the dates).
A damaged file stops the start; it is never silently reset (Rule 6).
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

# Standard library only, so `python tasks.py pilot-stats` runs without the virtual environment. The clock is handed in
# (the Simulator gives it the one place that reads real time, clucktalk.server.farm_state), never read here.
KEYS = {"days_used", "records_confirmed", "alerts_shown", "confirmations", "cancellations"}
STATUS_TOOLS = ("get_farm_status", "get_daily_briefing")


def _empty() -> dict[str, Any]:
    return {
        "days_used": [],
        "records_confirmed": 0,
        "alerts_shown": {"watch": 0, "alert": 0},
        "confirmations": 0,
        "cancellations": 0,
    }


def _valid(data: Any) -> bool:
    if not isinstance(data, dict) or set(data) != KEYS:
        return False
    days = data["days_used"]
    if not isinstance(days, list) or not all(isinstance(d, str) for d in days):
        return False
    alerts = data["alerts_shown"]
    if not isinstance(alerts, dict) or set(alerts) != {"watch", "alert"}:
        return False
    counts = [data["records_confirmed"], data["confirmations"], data["cancellations"], *alerts.values()]
    return all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in counts)


def load_usage(path: Path) -> dict[str, Any]:
    """The counters in ``path``. ValueError (naming the usage file, never repairing it) when it is damaged."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"the usage file {path.name} is damaged or unreadable: {exc}") from exc
    if not _valid(data):
        raise ValueError(f"the usage file {path.name} does not have the expected counters")
    return data


class UsageCounters:
    def __init__(self, path: Path, today: Callable[[], date]) -> None:
        self.path = path
        self._today = today
        self._lock = threading.Lock()
        self._data = load_usage(path) if path.exists() else _empty()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self._data, indent=1) + "\n", encoding="utf-8", newline="\n")
        os.replace(tmp, self.path)

    def record_turn(self) -> None:
        with self._lock:
            day = self._today().isoformat()
            if day not in self._data["days_used"]:
                self._data["days_used"] = sorted([*self._data["days_used"], day])
                self._save()

    def record_answer(self, answer: str, applied_record: bool) -> None:
        """A read-back answered: ``yes`` is a confirmation (and a record when one was saved), ``no`` a cancellation."""
        with self._lock:
            if answer == "yes":
                self._data["confirmations"] += 1
                self._data["records_confirmed"] += 1 if applied_record else 0
            elif answer == "no":
                self._data["cancellations"] += 1
            else:
                return
            self._save()

    def record_result(self, tool: str, structured: dict[str, Any]) -> None:
        """A status or briefing answer shown: counted as an alert when its level is watch or alert."""
        level = structured.get("level") if isinstance(structured, dict) else None
        if tool in STATUS_TOOLS and level in ("watch", "alert"):
            with self._lock:
                self._data["alerts_shown"][level] += 1
                self._save()


LATE_AFTER_HOURS = 26  # a daily backup that is more than two hours late is a warning


def backup_report(stamp_text: str | None, now: datetime) -> list[str]:
    """The age of the last good backup, from the stamp the backup script writes (its first line is a UTC time), as the
    lines pilot-stats prints. A missing, damaged or future stamp is a warning and never a good age. ``now`` is given
    (this module never reads the clock)."""
    if stamp_text is None or not stamp_text.strip():
        return ["WARNING: no backup stamp found (has the backup ever run?)"]
    try:
        made = datetime.fromisoformat(stamp_text.strip().splitlines()[0])
    except ValueError:
        return ["WARNING: the backup stamp is unreadable"]
    if made.tzinfo is None:
        return ["WARNING: the backup stamp has no time zone, so its age cannot be told"]
    hours = (now - made).total_seconds() / 3600
    if hours < 0:
        return ["WARNING: the last good backup is dated in the future (check the server clock)"]
    line = f"Last good backup: {hours:.1f} hours ago"
    if hours > LATE_AFTER_HOURS:
        return [
            line,
            f"WARNING: the last good backup is more than {LATE_AFTER_HOURS} hours old. Check clucktalk-backup.",
        ]
    return [line]


def format_stats(data: dict[str, Any]) -> str:
    alerts = data["alerts_shown"]
    return "\n".join(
        [
            "Pilot usage (anonymous totals only)",
            f"Days used: {len(data['days_used'])}",
            f"Records confirmed: {data['records_confirmed']}",
            f"Alerts shown: {alerts['watch'] + alerts['alert']} (watch {alerts['watch']}, alert {alerts['alert']})",
            f"Confirmations: {data['confirmations']}",
            f"Cancellations: {data['cancellations']}",
            f"Confirmations versus cancellations: {data['confirmations']} to {data['cancellations']}",
        ]
    )
