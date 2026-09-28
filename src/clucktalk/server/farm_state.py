"""Where tools get the farm from. Precomputed per day, so tools only read (docs/DESIGN.md §3; Rule 4).

Demo mode only: the fictional seeded farm, labeled ``demo_data=True`` in every tool result (Rule 6).
Live mode has no source yet; ``clucktalk.server.app.main`` refuses to start without MOCK_BEDROCK=true.
What the farmer changes (farm profile, proposals awaiting "yes") lives in the state store (clucktalk.store).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

from clucktalk.domain.models import Farm
from clucktalk.domain.profile import FarmProfile, demo_default_profile
from clucktalk.seed import build_demo_farm
from clucktalk.store import Store
from clucktalk.store.sqlite import SqliteStore

# India Standard Time has no daylight saving, so a fixed offset is exact (and needs no tz database on Windows).
IST = timezone(timedelta(hours=5, minutes=30), "IST")


def now_ist() -> datetime:
    return datetime.now(IST)


def today_ist() -> date:
    return now_ist().date()


class DemoFarmSource:
    demo_data = True

    def __init__(
        self,
        clock: Callable[[], date] = today_ist,
        store: Store | None = None,
        now: Callable[[], datetime] = now_ist,
    ) -> None:
        """``store`` defaults to an in-memory store (tests); the server passes the file store (config)."""
        self._clock = clock
        self.store: Store = store if store is not None else SqliteStore()
        self.now = now  # wall clock for proposal expiry (docs/DESIGN.md §5.1)
        self._cached: tuple[date, Farm] | None = None
        self.snapshot()  # build at startup, not on the first tool call

    def snapshot(self) -> tuple[Farm, date]:
        """The farm as of the farmer's today. Rebuilt once when the date changes."""
        as_of = self._clock()
        if self._cached is None or self._cached[0] != as_of:
            self._cached = (as_of, build_demo_farm(as_of))
        return self._cached[1], as_of

    @property
    def farm_id(self) -> str:
        return self.snapshot()[0].farm_id

    def profile(self) -> FarmProfile:
        """The farmer's saved profile, or the demo farm's starting profile (independent) if never changed."""
        return self.store.get_profile(self.farm_id) or demo_default_profile(self.farm_id)
