"""The farmer's daily deaths rule file (Step 51 part B), the same pattern as the weather rules file.

``daily_deaths_rule.json`` (path from CLUCKTALK_DAILY_DEATHS_RULE_PATH, default ``.local/daily_deaths_rule.json``)::

    {"per_1000_live": 2, "note": "his own words", "is_example": false}

No file means the feature is off and every answer is byte-identical to what it was without the feature. A bad file at
startup stops the start (Rule 6). The file is re-read when it changes while the server runs, so the farmer's number
can be edited without a restart; if an edit makes it unreadable, answers say so and the rule is used for nothing.
The rule can only raise a shed to WATCH (clucktalk.domain.daily_deaths); it never lowers a level or removes vet advice.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from clucktalk.config import REPO_ROOT
from clucktalk.domain.daily_deaths import DailyDeathsRule

DEFAULT_RULE_PATH = REPO_ROOT / ".local" / "daily_deaths_rule.json"
MAX_NOTE = 200
MAX_PER_1000 = 1000
_KEYS = {"per_1000_live", "note", "is_example"}


class DeathsRuleError(ValueError):
    """The daily deaths rule file or its environment setting is invalid. Fail loud at startup (Rule 6)."""


def resolve_rule_path(raw: str) -> Path:
    if not raw.strip():
        return DEFAULT_RULE_PATH
    path = Path(raw.strip())
    if path.suffix.lower() != ".json":
        raise DeathsRuleError(f"CLUCKTALK_DAILY_DEATHS_RULE_PATH={raw!r} must name a .json file")
    return path if path.is_absolute() else REPO_ROOT / path


def parse_rule(data: Any, name: str = "the daily deaths rule file") -> DailyDeathsRule:
    if not isinstance(data, dict):
        raise DeathsRuleError(f"{name} must be a JSON object")
    unknown = set(data) - _KEYS
    if unknown:
        raise DeathsRuleError(f"{name} has unknown field(s) {sorted(unknown)}; allowed: {sorted(_KEYS)}")
    value = data.get("per_1000_live")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise DeathsRuleError("per_1000_live must be a finite number")
    if not 0 <= value <= MAX_PER_1000:
        raise DeathsRuleError(f"per_1000_live must be from 0 to {MAX_PER_1000}")
    note = data.get("note")
    if note is not None and (not isinstance(note, str) or len(note) > MAX_NOTE):
        raise DeathsRuleError(f"note must be text of at most {MAX_NOTE} characters (the farmer's own words)")
    example = data.get("is_example", False)
    if not isinstance(example, bool):
        raise DeathsRuleError("is_example must be true or false")
    return DailyDeathsRule(Decimal(str(value)), note, example)


def load_deaths_rule(path: Path) -> DailyDeathsRule | None:
    """None when the file does not exist (the feature is off). Raises DeathsRuleError for any invalid content."""
    if not path.exists():
        return None
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DeathsRuleError(f"{path.name} is not valid JSON text: {exc}") from exc
    return parse_rule(data, path.name)


@dataclass(frozen=True)
class RuleState:
    rule: DailyDeathsRule | None  # None: off (no file) or unreadable
    unreadable: bool  # the file exists but cannot be used: said in the answer, never silently ignored


class DeathsRuleFile:
    """The rule file as the tools see it: re-read when its size or modified time changes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._stamp: tuple[int, int] | None | str = "unset"
        self._state = RuleState(None, False)

    def current(self) -> RuleState:
        try:
            stat = self.path.stat()
            stamp: tuple[int, int] | None = (stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            stamp = None
        except OSError:
            self._stamp = "unset"  # try again next time; meanwhile it cannot be used
            return RuleState(None, True)
        if stamp != self._stamp:
            self._stamp = stamp
            try:
                self._state = RuleState(load_deaths_rule(self.path), False)
            except DeathsRuleError:
                self._state = RuleState(None, True)
        return self._state


def deaths_rule_from_env(env: Mapping[str, str] | None = None) -> DeathsRuleFile | None:
    """None (feature off) when the file does not exist. A file that exists but is invalid raises, so the start fails."""
    env = os.environ if env is None else env
    path = resolve_rule_path(env.get("CLUCKTALK_DAILY_DEATHS_RULE_PATH", ""))
    if load_deaths_rule(path) is None:
        return None
    return DeathsRuleFile(path)
