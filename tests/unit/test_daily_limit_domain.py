"""The farmer's own age-banded per-day death limit, pure (the 7th safety rule; docs/SAFETY_MATRIX.md).

His table, in the repository's age (0 on the arrival day; he calls the arrival day day 1, so his day N is age N-1):
ages 0 to 29: more than 6 deaths in a day; age 30 onward: more than 3. Strictly MORE than the limit raises the shed to
ALERT, with no history needed. It never lowers, hides or rewords any other finding, and it is off without bands."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from clucktalk.domain.daily_deaths import AgeBand, DailyDeathsRule, evaluate_limit
from clucktalk.domain.models import DailyRecord, House, HouseKind
from clucktalk.domain.status import Level, house_status

PLACED = date(2026, 9, 21)
BANDS = (AgeBand(0, 29, 6), AgeBand(30, None, 3))
LIMIT = DailyDeathsRule(None, "his note", False, BANDS)
PER_1000 = DailyDeathsRule(Decimal("2"), None, False)


def shed(deaths_by_age: dict[int, int], birds: int = 4000) -> House:
    """A 4000-bird shed placed 2026-09-21 (age 0 that day), with a record on each given age."""
    records = tuple(DailyRecord(PLACED + timedelta(days=a), d, 100.0) for a, d in sorted(deaths_by_age.items()))
    return House("house-1", 1, HouseKind.BROILER, "flock", PLACED, birds, 0, 100000.0, records)


def steady(age: int, today: int, base: int = 5) -> House:
    """``base`` deaths a day on every earlier age, ``today`` on ``age``."""
    return shed({**{a: base for a in range(age)}, age: today})


def status(house: House, rule=None):
    return house_status(house, house.records[-1].day, rule)


def real(findings):
    """The findings that need attention (the "no reference curve" note is always there for a flock with no curve)."""
    return [f for f in findings if f.code != "no_reference_curve"]


@pytest.mark.parametrize(
    ("age", "deaths", "fires"),
    [
        (29, 6, False),  # exactly his limit is normal
        (29, 7, True),  # more than 6: vet
        (30, 3, False),  # his day 31: exactly 3 is normal
        (30, 4, True),  # more than 3: vet
        (20, 7, True),
        (20, 6, False),
        (35, 4, True),
        (35, 3, False),
        (0, 7, True),  # the arrival day itself is inside the first band
        (0, 0, False),
    ],
)
def test_the_limit_fires_only_for_strictly_more_than_the_limit_of_that_age(age, deaths, fires):
    match = evaluate_limit(LIMIT, deaths, age)
    assert (match is not None) is fires
    if fires:
        assert match.deaths == deaths and match.age_days == age
        assert match.limit == (6 if age <= 29 else 3)


def test_the_band_edges_are_age_29_and_30_in_repo_age():
    assert evaluate_limit(LIMIT, 4, 29) is None and evaluate_limit(LIMIT, 4, 30) is not None
    assert evaluate_limit(LIMIT, 7, 29) is not None and evaluate_limit(LIMIT, 7, 30) is not None


def test_this_farm_switches_from_6_to_3_on_2026_10_21():
    day = lambda n: PLACED + timedelta(days=n)  # noqa: E731
    assert day(29) == date(2026, 10, 20) and day(30) == date(2026, 10, 21)


def test_no_bands_means_no_limit():
    assert evaluate_limit(PER_1000, 400, 10) is None
    assert evaluate_limit(DailyDeathsRule(None, None, False, ()), 400, 10) is None


def test_an_age_in_no_band_is_not_judged():
    gap = DailyDeathsRule(None, None, False, (AgeBand(0, 9, 6), AgeBand(20, None, 3)))
    assert evaluate_limit(gap, 99, 15) is None
    assert evaluate_limit(gap, 99, 9) is not None and evaluate_limit(gap, 99, 20) is not None


@pytest.mark.parametrize(
    ("deaths", "age"),
    [(True, 5), (7, True), (7.0, 5), (7, 5.0), (-1, 5), (7, -1), ("7", 5), (7, None), (None, 5)],
)
def test_anything_it_cannot_judge_is_no_match_and_never_raises(deaths, age):
    assert evaluate_limit(LIMIT, deaths, age) is None


def test_a_broken_rule_is_no_match_and_never_raises():
    assert evaluate_limit(None, 9, 5) is None
    assert evaluate_limit(DailyDeathsRule(None, None, False, ("x",)), 9, 5) is None  # type: ignore[arg-type]


# -- on the shed's status ------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("age", "today", "fires"),
    [(29, 6, False), (29, 7, True), (30, 3, False), (30, 4, True), (20, 7, True), (35, 4, True), (35, 3, False)],
)
def test_the_status_edges(age, today, fires):
    st = status(steady(age, today, base=2), LIMIT)
    found = [f for f in st.findings if f.code == "daily_limit_exceeded"]
    assert bool(found) is fires
    if fires:
        assert found[0].level is Level.ALERT and st.level is Level.ALERT
        assert found[0].values == {"deaths": today, "limit": 6 if age <= 29 else 3, "age_days": age}


def test_forty_deaths_with_no_history_is_an_alert():
    house = shed({5: 40})  # one record ever: the spike rule needs 3 prior days and cannot fire
    assert "mortality_spike" not in [f.code for f in status(house, None).findings]
    assert status(house, None).level is Level.OK  # today's behaviour without bands
    st = status(house, LIMIT)
    assert [f.code for f in st.findings if f.level is Level.ALERT] == ["daily_limit_exceeded"]


def test_spike_and_limit_on_the_same_day_both_stay_and_the_spike_is_unchanged():
    house = steady(15, 40, base=5)
    without = real(status(house, None).findings)
    with_limit = real(status(house, LIMIT).findings)
    assert [f.code for f in without] == ["mortality_spike"]
    spike = [f for f in with_limit if f.code == "mortality_spike"]
    assert spike == [f for f in without if f.code == "mortality_spike"]
    assert [f.code for f in with_limit] == ["mortality_spike", "daily_limit_exceeded"]  # the spike keeps its place


def test_every_existing_finding_is_unchanged_when_the_limit_is_added():
    for age, today in ((5, 3), (15, 7), (29, 7), (30, 4), (40, 40)):
        house = steady(age, today)
        base = status(house, None)
        with_limit = status(house, LIMIT)
        kept = tuple(f for f in with_limit.findings if f.code != "daily_limit_exceeded")
        assert kept == base.findings, (age, today)
        assert with_limit.level >= base.level


def test_a_cumulative_alert_stays_alongside_the_limit():
    house = shed({**{a: 130 for a in range(30)}, 30: 4})  # 130 x 30 + 4 = 3,904 of 4,000 birds gone
    codes_ = [f.code for f in status(house, LIMIT).findings]
    assert "cum_mortality_high" in codes_ and "daily_limit_exceeded" in codes_


def test_without_age_bands_the_status_is_identical():
    for age, today in ((5, 40), (15, 9), (30, 4)):
        house = steady(age, today)
        assert status(house, DailyDeathsRule(None, None, False, ())).findings == status(house, None).findings
        assert status(house, PER_1000) == status(house, DailyDeathsRule(Decimal("2"), None, False, ()))


def test_the_per_1000_rule_is_not_repeated_when_the_limit_fires():
    house = steady(15, 12)  # 12 is more than 2 per 1000 of 4000, and more than 6
    both = DailyDeathsRule(Decimal("2"), None, False, BANDS)
    got = [f.code for f in status(house, both).findings]
    assert "daily_limit_exceeded" in got and "daily_deaths_rule" not in got
    only_rate = DailyDeathsRule(Decimal("2"), None, False, (AgeBand(0, None, 50),))  # limit not exceeded
    got = [f.code for f in status(house, only_rate).findings]
    assert "daily_deaths_rule" in got and "daily_limit_exceeded" not in got


def test_the_limit_reads_the_age_of_the_record_day_not_the_day_it_is_asked():
    house = steady(29, 7, base=2)
    later = house_status(house, house.records[-1].day + timedelta(days=3), LIMIT)  # asked 3 days later
    got = [f for f in later.findings if f.code == "daily_limit_exceeded"]
    assert got and got[0].values["age_days"] == 29 and got[0].values["limit"] == 6


def test_a_flock_that_arrived_older_uses_its_real_age():
    house = House(
        "house-1", 1, HouseKind.BROILER, "flock", PLACED, 4000, 28,
        100000.0, (DailyRecord(PLACED + timedelta(days=2), 4, 100.0),),
    )  # fmt: skip
    # age 28 + 2 = 30: the second band applies, 4 is more than 3
    got = [f for f in status(house, LIMIT).findings if f.code == "daily_limit_exceeded"]
    assert got and got[0].values["age_days"] == 30 and got[0].values["limit"] == 3


def test_a_true_or_false_is_not_a_death_count():
    """``True`` is a whole number to Python (1) but not a count of birds: with a limit of 0 it would fire."""
    zero = DailyDeathsRule(None, None, False, (AgeBand(0, None, 0),))
    assert evaluate_limit(zero, 1, 5) is not None  # a real 1 is more than 0
    assert evaluate_limit(zero, True, 5) is None and evaluate_limit(zero, False, 5) is None
