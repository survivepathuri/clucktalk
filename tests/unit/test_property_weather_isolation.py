"""Step 50W-B part C: weather can never change a health level, the safety field, a reason code or the vet advice.

Hypothesis builds random sequences of health checks, death records and clock moves on the demo farm, plus random
weather rules and forecasts (matching, not matching, missing hours, unavailable). After every event the farm status
(whole farm and each shed) and the daily briefing are built with the feature OFF, then ON, then OFF again. Everything
except the weather additions must be identical: levels, houses, items, safety.level, reason_codes, vet_contact_advised,
the spoken text up to the weather lines. The feature on only ever APPENDS text after the rest."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from clucktalk.agents import demo_ai
from clucktalk.agents.briefing import BriefingRanker
from clucktalk.domain.models import DailyRecord
from clucktalk.domain.triage import Urgency
from clucktalk.domain.weather import HourlyPoint, WeatherRule
from clucktalk.server.tools.briefing import build_briefing
from clucktalk.server.tools.farm_status import build_status
from clucktalk.server.weather import Forecast, WeatherConfig, WeatherReminders
from tests.unit.test_property_follow_up_sequences import World

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 10, 4, 2, 0, tzinfo=IST)

PROPERTY = settings(
    max_examples=25, derandomize=True, deadline=None, suppress_health_check=[HealthCheck.too_slow], database=None
)

events = st.one_of(
    st.tuples(st.just("check"), st.integers(1, 3), st.sampled_from(list(Urgency))),
    st.tuples(st.just("record"), st.integers(1, 3), st.tuples(st.integers(0, 2), st.sampled_from([0, 1, 5, 60, 400]))),
    st.tuples(st.just("clock"), st.just(0), st.integers(0, 4)),
)
rules = st.lists(
    st.builds(
        WeatherRule,
        st.uuids().map(str),
        st.sampled_from(["min", "max"]),
        st.sampled_from(["below", "above"]),
        st.floats(-5, 45, allow_nan=False),
        st.integers(1, 72),
        st.one_of(st.none(), st.text(max_size=30)),
        st.booleans(),
    ),
    max_size=4,
)
forecasts = st.one_of(
    st.none(),  # unavailable
    st.lists(st.one_of(st.none(), st.floats(-10, 50, allow_nan=False)), min_size=0, max_size=80),
)


class Port:
    def __init__(self, temps):
        self.temps = temps

    def forecast(self, *a):
        if self.temps is None:
            return Forecast("unavailable", (), None, "Open-Meteo", False, "down")
        points = tuple(HourlyPoint(NOW + timedelta(hours=i), t) for i, t in enumerate(self.temps))
        return Forecast("ok", points, NOW, "Open-Meteo", False, None)


def snapshot(world, ranker, more=False):
    status = build_status(world.source, None).model_dump(mode="json")
    sheds = [build_status(world.source, f"shed {n}").model_dump(mode="json") for n in (1, 2, 3)]
    brief = build_briefing(world.source, ranker, more).model_dump(mode="json")
    return status, sheds, brief


def without_weather(d):
    d = dict(d)
    d.pop("weather_reminders", None)
    return {k: v for k, v in d.items() if k not in ("text_en", "text_te")}


def apply(world, event):
    kind, house, arg = event
    if kind == "check":
        world.add_check(house, arg)
    elif kind == "record":
        days_ago, deaths = arg
        day = world.clock.today() - timedelta(days=days_ago)
        world.store.put_record(world.source.farm_id, f"house-{house}", DailyRecord(day, deaths, 100.0))
    else:
        world.clock.set_days_later(min(30, world.clock.days_later + arg))


@PROPERTY
@given(st.lists(events, max_size=5), rules, forecasts)
def test_weather_never_changes_a_level_the_safety_field_or_the_vet_advice(sequence, rule_list, temps):
    world = World()
    ranker = BriefingRanker(world.source.store, demo_ai(), world.source.now)
    service = WeatherReminders(WeatherConfig(0.0, 0.0, tuple(rule_list)), Port(temps), lambda: NOW)
    for event in [None, *sequence]:
        if event is not None:
            apply(world, event)
        world.source.weather = None
        off_status, off_sheds, off_brief = snapshot(world, ranker)
        world.source.weather = service
        on_status, on_sheds, on_brief = snapshot(world, ranker)
        world.source.weather = None
        off2_status, off2_sheds, off2_brief = snapshot(world, ranker)
        assert (off_status, off_sheds, off_brief) == (off2_status, off2_sheds, off2_brief)  # the baseline is stable
        for on, off in [(on_status, off_status), (on_brief, off_brief), *zip(on_sheds, off_sheds, strict=True)]:
            assert without_weather(on) == without_weather(off)  # levels, houses, items, safety: nothing else moved
            assert on["text_en"].startswith(off["text_en"]) and on["text_te"].startswith(off["text_te"])
            if "safety" in on:
                for key in ("level", "reason_codes", "vet_contact_advised"):
                    assert on["safety"][key] == off["safety"][key]
            assert on["level"] == off["level"]
        assert (
            off_status["weather_reminders"] is None and "weather_reminders" not in on_brief
        )  # off: None, never a list


def test_a_named_scenario_a_matching_rule_on_an_alert_farm_changes_only_the_text():
    world = World()
    rule = WeatherRule("cold", "min", "below", 100.0, 24, "note", False)  # matches whatever the forecast says
    world.source.weather = WeatherReminders(WeatherConfig(0.0, 0.0, (rule,)), Port([10.0, 12.0]), lambda: NOW)
    on = build_status(world.source, None).model_dump(mode="json")
    world.source.weather = None
    off = build_status(world.source, None).model_dump(mode="json")
    assert on["weather_reminders"] and on["level"] == off["level"] == "alert"
    assert on["safety"] == off["safety"] and on["safety"]["vet_contact_advised"] is True
    assert on["text_en"].startswith(off["text_en"]) and len(on["text_en"]) > len(off["text_en"])
