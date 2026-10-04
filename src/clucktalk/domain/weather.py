"""The farmer's own weather rules, matched against an hourly OUTDOOR forecast (Step 50W-B, docs/DESIGN.md).

A rule is an outside-temperature trigger written by the farmer: "when the lowest (or highest) forecast temperature
over the next N hours is below (or above) the number I set, remind me with my note". The numbers, the window and the
note are his; this module sets no threshold, gives no advice, and never rewrites a note. It knows only Celsius and
only a forecast for one outdoor point: there is no shed-interior value anywhere in it, and nothing here can change a
shed's health level, its safety field or a vet recommendation (it imports nothing from them).

``evaluate`` is pure and total: it never raises, whatever the input, and returns the same answer for the same input.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class WeatherRule:
    id: str
    stat: str  # "min" or "max" of the hourly forecast over the window
    comparator: str  # "below" or "above" the number
    threshold_c: float  # degrees Celsius, the farmer's number
    window_hours: int  # how many hours ahead of now are looked at
    note: str | None  # the farmer's own words: stored and shown exactly as given
    is_example: bool  # an example setting (demo), never a default


@dataclass(frozen=True)
class HourlyPoint:
    at: datetime  # the hour the value is for
    temperature_c: float | None  # outdoor air temperature, None when the source had no value


@dataclass(frozen=True)
class Match:
    rule_id: str
    value: float  # the minimum or maximum temperature found in the window
    at: datetime  # the first hour in the window at which that value occurs


def _comparable(point: HourlyPoint, now: datetime) -> bool:
    """Timezone-aware and naive datetimes cannot be compared: such a point is skipped, never raised on."""
    return (point.at.tzinfo is None) == (now.tzinfo is None)


def _match(rule: WeatherRule, points: Sequence[HourlyPoint], now: datetime) -> Match | None:
    if rule.stat not in ("min", "max") or rule.comparator not in ("below", "above"):
        return None
    if not isinstance(rule.window_hours, int) or rule.window_hours <= 0:
        return None
    if not (isinstance(rule.threshold_c, (int, float)) and math.isfinite(rule.threshold_c)):
        return None
    end = now + timedelta(hours=rule.window_hours)
    best: HourlyPoint | None = None
    for p in points:
        try:
            t = p.temperature_c
            if t is None or not isinstance(t, (int, float)) or not math.isfinite(t) or not _comparable(p, now):
                continue
            if not (now <= p.at < end):
                continue
            if best is None or (t < best.temperature_c if rule.stat == "min" else t > best.temperature_c):  # type: ignore[operator]
                best = p  # strict comparison: the first hour wins when the extreme repeats
        except (TypeError, ValueError, AttributeError):  # a malformed point is skipped; the others still count
            continue
    if best is None or best.temperature_c is None:
        return None
    value = float(best.temperature_c)
    crossed = value < rule.threshold_c if rule.comparator == "below" else value > rule.threshold_c  # equal: no match
    return Match(rule.id, value, best.at) if crossed else None


def evaluate(rules: Sequence[WeatherRule], points: Sequence[HourlyPoint], now: datetime) -> list[Match]:
    """The rules that match the forecast, in rule order. Each rule is judged alone. Never raises."""
    matches: list[Match] = []
    for rule in rules:
        try:
            found = _match(rule, points, now)
        except (
            TypeError,
            ValueError,
            OverflowError,
            AttributeError,
        ):  # a malformed value in a rule or point: no match, no raise
            found = None
        if found is not None:
            matches.append(found)
    return matches
