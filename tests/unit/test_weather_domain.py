"""Step 50W-B part A: the pure weather domain. A rule is the farmer's own: an outside-temperature trigger (the lowest or
the highest hourly forecast value over the next N hours, below or above a number he set, with his own note). The
evaluation takes (rules, hourly series, now) and returns matches. It is Celsius only, it never reads a shed-interior
temperature (there is none in this module), and it never raises."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from clucktalk.domain.weather import HourlyPoint, Match, WeatherRule, evaluate

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 10, 4, 6, 0, tzinfo=IST)


def series(temps, start=NOW, step_h=1):
    return [HourlyPoint(start + timedelta(hours=i * step_h), t) for i, t in enumerate(temps)]


def rule(stat="min", comparator="below", threshold=20.0, window=12, note="my words", rid="r1", example=False):
    return WeatherRule(rid, stat, comparator, threshold, window, note, example)


# -- the documented example rules -------------------------------------------------------------------
def test_a_minimum_below_the_number_matches_and_names_the_hour_it_occurs():
    hours = series([22, 21, 19.5, 20.5, 23])
    [m] = evaluate([rule("min", "below", 20)], hours, NOW)
    assert m == Match("r1", 19.5, NOW + timedelta(hours=2))


def test_a_maximum_above_the_number_matches():
    [m] = evaluate([rule("max", "above", 30, rid="hot")], series([28, 31.2, 29, 30.5]), NOW)
    assert m.rule_id == "hot" and m.value == 31.2 and m.at == NOW + timedelta(hours=1)


# -- edges ------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("comparator", "temps"),
    [("below", [20.0, 25.0]), ("above", [30.0, 25.0])],
)
def test_equal_to_the_threshold_is_not_a_match(comparator, temps):
    stat, threshold = ("min", 20) if comparator == "below" else ("max", 30)
    assert evaluate([rule(stat, comparator, threshold)], series(temps), NOW) == []


def test_the_smallest_step_past_the_threshold_is_a_match():
    assert len(evaluate([rule("min", "below", 20)], series([19.999]), NOW)) == 1
    assert len(evaluate([rule("max", "above", 30)], series([30.001]), NOW)) == 1


def test_min_and_max_look_at_different_values_of_the_same_hours():
    hours = series([15, 25, 35])
    got = {
        m.rule_id: m.value
        for m in evaluate([rule("min", "below", 20, rid="a"), rule("max", "above", 30, rid="b")], hours, NOW)
    }
    assert got == {"a": 15, "b": 35}
    assert evaluate([rule("min", "above", 20, rid="c")], hours, NOW) == []  # the minimum is 15, and 15 is not above 20
    assert evaluate([rule("min", "above", 10, rid="c")], hours, NOW)[0].value == 15


def test_an_empty_series_or_an_empty_window_matches_nothing():
    assert evaluate([rule()], [], NOW) == []
    assert evaluate([rule(window=0)], series([1, 2]), NOW) == []
    assert evaluate([rule(window=-3)], series([1, 2]), NOW) == []
    assert evaluate([rule(window=2)], series([1, 2], start=NOW + timedelta(hours=5)), NOW) == []  # all hours outside


def test_only_hours_inside_the_window_count():
    hours = series([25, 25, 10, 25])  # the cold hour is the third, 2 hours ahead
    assert evaluate([rule("min", "below", 20, window=2)], hours, NOW) == []  # hours 0 and 1 only
    assert len(evaluate([rule("min", "below", 20, window=3)], hours, NOW)) == 1


def test_hours_before_now_are_ignored_and_the_current_hour_counts():
    past = series([5, 25, 25], start=NOW - timedelta(hours=1))  # the first point is one hour ago
    assert evaluate([rule("min", "below", 20, window=6)], past, NOW) == []
    assert len(evaluate([rule("min", "below", 20, window=6)], series([5, 25]), NOW)) == 1  # at now exactly


def test_a_window_larger_than_the_series_uses_what_there_is():
    assert len(evaluate([rule(window=500)], series([10, 30]), NOW)) == 1


def test_missing_hours_are_skipped_not_counted_as_zero():
    hours = series([None, 25, None, 24])
    assert evaluate([rule("min", "below", 20)], hours, NOW) == []  # a missing value is not a 0 degree hour
    assert evaluate([rule("min", "below", 24.5)], hours, NOW)[0].value == 24
    assert evaluate([rule()], series([None, None]), NOW) == []


def test_non_finite_values_are_treated_as_missing():
    assert evaluate([rule()], series([math.nan, math.inf, -math.inf]), NOW) == []
    assert evaluate([rule(threshold=math.nan)], series([1.0]), NOW) == []


def test_the_first_hour_wins_when_the_extreme_repeats():
    [m] = evaluate([rule("min", "below", 20)], series([18, 18, 18]), NOW)
    assert m.at == NOW


def test_a_rule_with_no_note_still_matches_and_keeps_none_or_blank_as_given():
    [m] = evaluate([rule(note=None)], series([10]), NOW)
    assert m.rule_id == "r1"
    assert WeatherRule("r", "min", "below", 20, 6, None, False).note is None
    assert WeatherRule("r", "min", "below", 20, 6, "   ", False).note == "   "  # never rewritten
    assert WeatherRule("r", "min", "below", 20, 6, "తెలుగు note", False).note == "తెలుగు note"


def test_many_rules_come_back_in_rule_order_and_each_is_judged_alone():
    rules = [rule("min", "below", t, rid=f"r{t}") for t in (5, 15, 25, 35)]
    got = [m.rule_id for m in evaluate(rules, series([20, 22]), NOW)]
    assert got == ["r25", "r35"]
    big = [rule("min", "below", 100, rid=f"x{i}") for i in range(500)]
    assert len(evaluate(big, series([1]), NOW)) == 500


def test_the_input_is_not_changed_and_the_result_is_a_fresh_list():
    rules, hours = [rule()], series([10, 11])
    before = (list(rules), list(hours))
    out = evaluate(rules, hours, NOW)
    assert (rules, hours) == before and out is not evaluate(rules, hours, NOW)


def test_a_naive_clock_or_naive_points_do_not_raise():
    naive = datetime(2026, 10, 4, 6, 0)
    assert evaluate([rule()], series([10]), naive) == []  # mixed naive and aware: nothing matches, nothing raises
    assert len(evaluate([rule()], series([10], start=naive), naive)) == 1


def test_the_model_holds_only_an_outside_celsius_value_and_the_farmers_own_fields():
    import dataclasses

    assert [f.name for f in dataclasses.fields(HourlyPoint)] == ["at", "temperature_c"]
    assert [f.name for f in dataclasses.fields(WeatherRule)] == [
        "id", "stat", "comparator", "threshold_c", "window_hours", "note", "is_example"
    ]  # fmt: skip
    assert [f.name for f in dataclasses.fields(Match)] == ["rule_id", "value", "at"]


def test_an_infinite_threshold_matches_nothing():
    assert evaluate([rule("min", "below", math.inf)], series([10]), NOW) == []
    assert evaluate([rule("max", "above", -math.inf)], series([10]), NOW) == []


def test_malformed_values_in_a_rule_or_a_point_match_nothing_and_never_raise():
    bad_points = [HourlyPoint(None, 10.0), HourlyPoint("noon", 10.0), HourlyPoint(NOW, "hot"), HourlyPoint(NOW, [1])]
    assert evaluate([rule()], bad_points, NOW) == []
    good = series([10])
    assert evaluate([rule(threshold="warm")], good, NOW) == []
    assert evaluate([rule(window="six")], good, NOW) == []
    assert evaluate([rule(window=10**12)], good, NOW) == []  # a window too large for a timedelta
    assert len(evaluate([rule(rid="ok")], [*bad_points, *good], NOW)) == 1  # the bad ones do not hide a good one
    assert [m.rule_id for m in evaluate([rule(window="x", rid="bad"), rule(rid="good")], good, NOW)] == ["good"]


# -- the rule model's own limits --------------------------------------------------------------------
def test_a_rule_is_frozen_and_hashable():
    r = rule()
    with pytest.raises(AttributeError):
        r.threshold_c = 1  # type: ignore[misc]
    assert hash(r) == hash(rule())


# -- the property: deterministic, never raises ------------------------------------------------------
temps = st.one_of(st.none(), st.floats(allow_nan=True, allow_infinity=True, width=32))
points = st.lists(
    st.builds(
        HourlyPoint,
        st.datetimes(
            min_value=datetime(2026, 1, 1),
            max_value=datetime(2027, 1, 1),
            timezones=st.sampled_from([IST, UTC, None]),
        ),
        temps,
    ),
    max_size=60,
)
rules = st.lists(
    st.builds(
        WeatherRule,
        st.text(max_size=8),
        st.sampled_from(["min", "max", "weird"]),
        st.sampled_from(["below", "above", "equal"]),
        st.floats(allow_nan=True, allow_infinity=True, width=32),
        st.integers(min_value=-10, max_value=10_000),
        st.one_of(st.none(), st.text(max_size=20)),
        st.booleans(),
    ),
    max_size=30,
)
nows = st.datetimes(
    min_value=datetime(2026, 1, 1), max_value=datetime(2027, 1, 1), timezones=st.sampled_from([IST, UTC, None])
)


@settings(max_examples=300, derandomize=True, deadline=None)
@given(rules, points, nows)
def test_evaluation_is_deterministic_and_never_raises_on_any_input(rs, pts, now):
    first = evaluate(rs, pts, now)
    assert first == evaluate(rs, pts, now)
    assert len(first) <= len(rs) and all(isinstance(m, Match) for m in first)
    assert first == [m for r in rs for m in evaluate([r], pts, now)]  # each rule is judged alone, in rule order
    for m in first:
        assert math.isfinite(m.value)
