"""The farmer's own daily deaths rule, pure (Step 51 part B, docs/DESIGN.md).

"When more than N birds die in one day for every 1000 live birds at the start of that day, flag the shed." The number
and the note are his; this module sets no number and gives no advice. It fires when

    deaths_today / live_birds_at_start_of_the_day * 1000   is STRICTLY GREATER than   his number

(he said "more than 8 on 4000", which is 2 per 1000). The arithmetic is exact (``Decimal``, no floats), so a number
sitting exactly on the line never fires by rounding. The rule can only RAISE a shed to WATCH; it never lowers a level
and never touches vet advice (it imports nothing from them). ``evaluate`` is total: it never raises.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class DailyDeathsRule:
    per_1000_live: Decimal  # his number: deaths in a day for every 1000 live birds at the start of that day
    note: str | None  # his own words, shown exactly as he wrote them
    is_example: bool  # an example setting (demo), never a default


@dataclass(frozen=True)
class DeathsMatch:
    deaths: int
    live_at_start: int
    per_1000: float  # the day's rate, rounded to 2 places for speech
    limit_per_1000: float  # his number


def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def evaluate(rule: DailyDeathsRule, deaths: int, live_at_start: int) -> DeathsMatch | None:
    """A match when the day's rate is strictly above his number; None otherwise, and None for anything it cannot judge
    (no live birds, a value that is not a whole number, a broken rule). Never raises."""
    try:
        if not _whole(deaths) or not _whole(live_at_start) or live_at_start <= 0 or deaths < 0:
            return None
        limit = rule.per_1000_live
        if not isinstance(limit, Decimal) or not limit.is_finite() or limit < 0:
            return None
        if Decimal(deaths) * 1000 <= limit * live_at_start:  # equal is not "more than"
            return None
        rate = Decimal(deaths) * 1000 / live_at_start
        return DeathsMatch(deaths, live_at_start, float(round(rate, 2)), float(limit))
    except (TypeError, ValueError, ArithmeticError, AttributeError):  # a broken rule or number: no match, no raise
        return None
