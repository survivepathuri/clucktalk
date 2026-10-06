"""The farmer's own daily deaths rule, pure (Step 51 part B). It fires when deaths_today / live birds at the start
of the day * 1000 is STRICTLY greater than his number ("more than 8 on 4000" at 2 per 1000). It is total: it
never raises."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from clucktalk.domain.daily_deaths import DailyDeathsRule, evaluate

RULE = DailyDeathsRule(per_1000_live=Decimal("2"), note="my note", is_example=False)


def test_exactly_the_threshold_does_not_fire_and_one_more_does():
    assert evaluate(RULE, 8, 4000) is None  # 2.0 per 1000: equal, not greater
    m = evaluate(RULE, 9, 4000)
    assert m is not None and m.deaths == 9 and m.live_at_start == 4000
    assert m.per_1000 == 2.25 and m.limit_per_1000 == 2.0


def test_the_farmers_example_more_than_eight_on_four_thousand():
    assert evaluate(RULE, 8, 4000) is None and evaluate(RULE, 9, 4000) is not None


def test_zero_or_negative_live_birds_never_fires_and_never_divides():
    for live in (0, -1, -4000):
        assert evaluate(RULE, 5, live) is None


def test_no_deaths_never_fires_even_with_a_zero_threshold():
    zero = DailyDeathsRule(Decimal("0"), None, False)
    assert evaluate(zero, 0, 100) is None
    assert evaluate(zero, 1, 100) is not None


def test_a_fractional_threshold_is_exact_decimal_arithmetic():
    half = DailyDeathsRule(Decimal("0.5"), None, False)
    assert evaluate(half, 2, 4000) is None  # 0.5 per 1000 exactly
    assert evaluate(half, 3, 4000) is not None
    tenth = DailyDeathsRule(Decimal("0.1"), None, False)
    assert evaluate(tenth, 1, 10000) is None  # 0.1 per 1000 exactly: a float comparison could get this wrong
    assert evaluate(tenth, 2, 10000) is not None


@pytest.mark.parametrize("deaths", [None, "3", 2.5, True, [1]])
def test_garbage_deaths_never_raises_and_never_fires(deaths):
    assert evaluate(RULE, deaths, 4000) is None  # type: ignore[arg-type]


@pytest.mark.parametrize("live", [None, "4000", 4000.5, True])
def test_garbage_live_never_raises_and_never_fires(live):
    assert evaluate(RULE, 50, live) is None  # type: ignore[arg-type]


def test_a_broken_rule_never_raises():
    for bad in (None, object(), DailyDeathsRule(Decimal("NaN"), None, False), DailyDeathsRule("x", None, False)):  # type: ignore[arg-type]
        assert evaluate(bad, 50, 100) is None  # type: ignore[arg-type]


@given(st.integers(0, 5000), st.integers(-10, 20000), st.decimals(0, 1000, allow_nan=False, places=3))
def test_it_fires_exactly_when_the_strict_inequality_holds(deaths, live, limit):
    rule = DailyDeathsRule(limit, None, False)
    expected = live > 0 and Decimal(deaths) * 1000 > limit * live
    assert (evaluate(rule, deaths, live) is not None) == expected


@given(st.integers(0, 5000), st.integers(1, 20000), st.decimals(0, 1000, allow_nan=False, places=3))
def test_a_higher_threshold_never_fires_where_a_lower_one_did_not(deaths, live, limit):
    low = evaluate(DailyDeathsRule(limit, None, False), deaths, live)
    high = evaluate(DailyDeathsRule(limit + 1, None, False), deaths, live)
    assert high is None or low is not None
