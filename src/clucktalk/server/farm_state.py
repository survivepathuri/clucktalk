"""Where tools get the farm from. Precomputed per day, so tools only read (docs/DESIGN.md §3; Rule 4).

Demo mode only: the fictional seeded farm, labeled ``demo_data=True`` in every tool result (Rule 6).
Live mode has no source yet; ``clucktalk.server.app.main`` refuses to start without MOCK_BEDROCK=true.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

from clucktalk.domain.models import Farm
from clucktalk.seed import build_demo_farm

# India Standard Time has no daylight saving, so a fixed offset is exact (and needs no tz database on Windows).
IST = timezone(timedelta(hours=5, minutes=30), "IST")


def today_ist() -> date:
    return datetime.now(IST).date()


class DemoFarmSource:
    demo_data = True

    def __init__(self, clock: Callable[[], date] = today_ist) -> None:
        self._clock = clock
        self._cached: tuple[date, Farm] | None = None
        self.snapshot()  # build at startup, not on the first tool call

    def snapshot(self) -> tuple[Farm, date]:
        """The farm as of the farmer's today. Rebuilt once when the date changes."""
        as_of = self._clock()
        if self._cached is None or self._cached[0] != as_of:
            self._cached = (as_of, build_demo_farm(as_of))
        return self._cached[1], as_of
