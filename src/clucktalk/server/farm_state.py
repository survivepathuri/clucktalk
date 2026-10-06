"""Where tools get the farm from. Precomputed per day, so tools only read (docs/DESIGN.md §3; Rule 4).

Demo mode only: the fictional seeded farm, labeled ``demo_data=True`` in every tool result (Rule 6).
There is no live farm source: live AI mode (docs/DESIGN.md §18) also runs on this synthetic demo farm.
What the farmer changes (farm profile, proposals awaiting "yes") lives in the state store (clucktalk.store).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from clucktalk.domain.models import Farm
from clucktalk.domain.profile import FarmProfile, demo_default_profile
from clucktalk.domain.records import overlay_house_records
from clucktalk.pilot import PilotFarmConfig, build_pilot_farm
from clucktalk.seed import build_demo_farm
from clucktalk.store import Store
from clucktalk.store.sqlite import SqliteStore

# India Standard Time has no daylight saving, so a fixed offset is exact (and needs no tz database on Windows).
IST = timezone(timedelta(hours=5, minutes=30), "IST")


def now_ist() -> datetime:
    return datetime.now(IST)


def today_ist() -> date:
    return now_ist().date()


DEMO_CLOCK_MAX_DAYS = 30


def _check_days_later(days: object) -> int:
    if isinstance(days, bool) or not isinstance(days, int) or not 0 <= days <= DEMO_CLOCK_MAX_DAYS:
        raise ValueError(
            f"The demo clock must be a whole number of days from 0 to {DEMO_CLOCK_MAX_DAYS}, not {days!r}."
        )
    return days


class DemoClock:
    """The demo clock (docs/DESIGN.md section 18): shifts the farmer's "today" and "now" by whole days, so a video can
    say "three days later" without waiting. It only moves the two injected clocks; nothing stored is rewritten.
    It is a Simulator/CLI/env setting (``CLUCKTALK_DEMO_DAYS_LATER``), refused in live mode by the config, and no tool
    can set it. ``set_days_later`` exists for the eval runner and tests (in-process only). Real time is read only
    in ``now_ist`` above."""

    def __init__(self, days_later: int = 0, real_now: Callable[[], datetime] = now_ist) -> None:
        self._days = _check_days_later(days_later)
        self._real_now = real_now

    @property
    def days_later(self) -> int:
        return self._days

    def set_days_later(self, days_later: int) -> None:
        self._days = _check_days_later(days_later)

    def now(self) -> datetime:
        return self._real_now() + timedelta(days=self._days)

    def today(self) -> date:
        return self.now().date()


def overlay_records(farm: Farm, store: Store, *, add_missing: bool = False) -> Farm:
    """The voice record book (``log_daily_record``) is now the farm's primary data source: whatever the
    farmer has logged for a house replaces the seed's synthetic guess for that same day. Applied fresh on
    every snapshot (cheap: a couple of indexed reads), never cached, so a record logged a moment ago shows up
    in the very next tool call (docs/DESIGN.md §13.2)."""
    houses = tuple(
        overlay_house_records(
            house, {r.day: r for r in store.records(farm.farm_id, house.house_id)}, add_missing=add_missing
        )
        for house in farm.houses
    )
    return replace(farm, houses=houses)


class DemoFarmSource:
    demo_data = True
    overlay_adds_days = False  # the seed has a record for every day; a pilot farm has none, so its logs are added
    weights_allowed = True  # the demo farm's breed has a curve; a pilot's birds do not (PilotFarmSource)

    def __init__(
        self,
        clock: Callable[[], date] = today_ist,
        store: Store | None = None,
        now: Callable[[], datetime] = now_ist,
        demo_clock: DemoClock | None = None,
    ) -> None:
        """``store`` defaults to an in-memory store (tests); the server passes the file store (config).
        ``demo_clock`` (demo mode only) replaces ``clock`` and ``now`` with the shifted ones."""
        if demo_clock is not None:
            clock, now = demo_clock.today, demo_clock.now
        self.demo_clock = demo_clock
        self._clock = clock
        self.store: Store = store if store is not None else SqliteStore()
        self.now = now  # wall clock for proposal expiry (docs/DESIGN.md §5.1)
        self._cached: tuple[date, Farm] | None = None
        self.snapshot()  # build at startup, not on the first tool call

    def snapshot(self) -> tuple[Farm, date]:
        """The farm as of the farmer's today. The seed rebuilds once when the date changes (cached); the
        record book overlay (``overlay_records``) is re-applied every call, so a record logged a moment ago
        is never served stale."""
        as_of = self._clock()
        if self._cached is None or self._cached[0] != as_of:
            self._cached = (as_of, self._build_farm(as_of))
        return overlay_records(self._cached[1], self.store, add_missing=self.overlay_adds_days), as_of

    def _build_farm(self, as_of: date) -> Farm:
        return build_demo_farm(as_of)

    @property
    def demo_clock_days(self) -> int:
        """0 unless the demo clock is on: the marker "Demo clock: +N days" shows only when this is above 0."""
        return self.demo_clock.days_later if self.demo_clock is not None else 0

    @property
    def farm_id(self) -> str:
        return self.snapshot()[0].farm_id

    def profile(self) -> FarmProfile:
        """The farmer's saved profile, or the demo farm's starting profile (independent) if never changed."""
        return self.store.get_profile(self.farm_id) or demo_default_profile(self.farm_id)


class PilotFarmSource(DemoFarmSource):
    """Pilot mode (Step 51): the farmer's real houses from his farm file, with NO synthetic history. Everything a tool
    says about a record is one he logged himself. Not demo data (``demo_data`` is False, so no answer or card says
    "Demo data"); simulated items (market rate, supplier) are still labeled Simulated by the tools that show them.
    Bird weights are not logged in the pilot: the weight target is a breed curve that does not describe his birds."""

    demo_data = False
    overlay_adds_days = True
    weights_allowed = False

    def __init__(self, config: PilotFarmConfig, **kwargs) -> None:
        self.config = config  # set before super().__init__, which builds the first snapshot
        super().__init__(**kwargs)

    def _build_farm(self, as_of: date) -> Farm:
        return build_pilot_farm(self.config, as_of)
