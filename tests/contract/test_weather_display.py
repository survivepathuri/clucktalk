"""Step 50W-B part C: the weather reminder lines on the daily briefing and the farm status.

The farmer's own outdoor-temperature rules are matched against an hourly forecast; each match is ONE line after all
health and safety text. The farm status gets a SEPARATE structured ``weather_reminders`` list. Nothing weather-related
can change a level, the safety field, a reason code or the vet advice, and with no rules file every output is
byte-identical to what it was before the feature (the baseline in weather_off_baseline.json was recorded from the
code before the feature existed)."""

from __future__ import annotations

import copy
import json
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from clucktalk.agents.model import RulesModel
from clucktalk.domain.weather import WeatherRule
from clucktalk.server.weather import Forecast, MockForecast, WeatherConfig, WeatherReminders
from tests.contract.test_health_tools import _rig
from tests.crossmodal import spoken_numbers

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 10, 4, 2, 0, tzinfo=IST)  # the mock curve: 16.0 at 03:00, 31.9 at 13:00, so both examples match
BASELINE = json.loads((Path(__file__).parent / "weather_off_baseline.json").read_text(encoding="utf-8"))
NOTE = "Example note: replace this with your own words"
COLD = WeatherRule("cold", "min", "below", 20.0, 12, NOTE, True)
HOT = WeatherRule("hot", "max", "above", 30.0, 12, NOTE, True)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    real = socket.socket.connect

    def guarded(self, address, *a, **k):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"a test tried to reach the network: {address!r}")
        return real(self, address, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", guarded)


@pytest.fixture
def rig():
    yield from _rig(RulesModel())


def turn_on(rig, rules=(COLD, HOT), port=None):
    rig.source.weather = WeatherReminders(WeatherConfig(0.0, 0.0, tuple(rules)), port or MockForecast(), lambda: NOW)


def call(rig, name, **args):
    r = rig.call(name, **args)
    assert r.get("isError") in (None, False), r
    return r


class Down:
    def forecast(self, *a):
        return Forecast("unavailable", (), None, "Open-Meteo", False, "timed out")


class Live:
    def __init__(self, temps):
        from clucktalk.domain.weather import HourlyPoint

        self.points = tuple(HourlyPoint(NOW + timedelta(hours=i), t) for i, t in enumerate(temps))

    def forecast(self, *a):
        return Forecast("ok", self.points, NOW, "Open-Meteo", False, None)


def strip(sc):
    """The structured answer without the weather additions."""
    sc = copy.deepcopy(sc)
    sc.pop("weather_reminders", None)
    sc.pop("text_en"), sc.pop("text_te")
    return sc


# -- feature off: byte-identical to before ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("key", "tool", "args"),
    [
        ("get_farm_status", "get_farm_status", {}),
        ("get_farm_status shed 2", "get_farm_status", {"house": "shed 2"}),
        ("get_daily_briefing", "get_daily_briefing", {}),
        ("get_daily_briefing more", "get_daily_briefing", {"more": True}),
    ],
)
def test_with_no_rules_file_every_answer_is_byte_identical_to_the_baseline(rig, key, tool, args):
    got = call(rig, tool, **args)
    assert {"content": got["content"], "structuredContent": got["structuredContent"]} == BASELINE[key]
    assert "weather_reminders" not in got["structuredContent"]


def test_a_weather_service_set_to_none_is_the_same_as_none_at_all(rig):
    rig.source.weather = None
    assert call(rig, "get_farm_status")["structuredContent"] == BASELINE["get_farm_status"]["structuredContent"]


def test_a_config_with_no_rules_shows_nothing_and_fetches_nothing(rig):
    class Counting(MockForecast):
        calls = 0

        def forecast(self, *a):
            Counting.calls += 1
            return super().forecast(*a)

    turn_on(rig, rules=(), port=Counting())
    for tool in ("get_farm_status", "get_daily_briefing"):
        got = call(rig, tool)
        assert got["structuredContent"] == BASELINE[tool]["structuredContent"]
    assert Counting.calls == 0


CHOICE_SENTENCE = (
    " If the first result has `choice`, the house already has deaths for that day: read the question back and answer "
    "with 'yes' plus `deaths_choice` 'add' or 'replace' (never a plain yes)."
)


def test_tools_list_is_unchanged_except_the_optional_additions(rig):
    """Changed deliberately twice, and nothing else: the status gained one optional output property (weather, Step
    50W-B); log_daily_record gained one optional input (`deaths_choice`), one optional output (`choice`) and one
    description sentence (Step 52, the add-or-replace question). Every other tool, field, name and schema is exactly
    the baseline."""
    now = {t["name"]: t for t in rig.live.call(rig.sid, "tools/list")["result"]["tools"]}
    before = {t["name"]: t for t in BASELINE["tools/list"]}
    assert sorted(now) == sorted(before) and len(now) == 14
    for name, tool in now.items():
        for field in tool:
            if (name, field) in {
                ("get_farm_status", "outputSchema"),
                ("log_daily_record", "description"),
                ("log_daily_record", "inputSchema"),
                ("log_daily_record", "outputSchema"),
            }:
                continue
            assert tool[field] == before[name][field], (name, field)  # names, descriptions, schemas, annotations
    out_now, out_before = now["get_farm_status"]["outputSchema"], before["get_farm_status"]["outputSchema"]
    added = set(out_now["properties"]) - set(out_before["properties"])
    assert added == {"weather_reminders"}
    assert out_now.get("required") == out_before.get("required")  # optional: absent when the feature is off
    assert {k: v for k, v in out_now["properties"].items() if k != "weather_reminders"} == out_before["properties"]

    log_now, log_before = now["log_daily_record"], before["log_daily_record"]
    assert log_now["description"] == log_before["description"] + CHOICE_SENTENCE
    for part, extra in (("inputSchema", "deaths_choice"), ("outputSchema", "choice")):
        a, b = log_now[part], log_before[part]
        assert set(a["properties"]) - set(b["properties"]) == {extra}
        assert {k: v for k, v in a["properties"].items() if k != extra} == b["properties"]
        assert a.get("required") == b.get("required")  # optional: absent unless asked
        assert {k: v for k, v in a.get("$defs", {}).items() if k != "ChoiceOut"} == b.get("$defs", {})


# -- feature on: the line --------------------------------------------------------------------------------------------
COLD_LINE = (
    "Demo data. Forecast (hourly, outdoors at your farm's location, source: Simulated; not real-time; "
    "fetched at 02:00): "
    "the lowest temperature is 16 degrees, below the number you set (20). Your note: " + NOTE + "."
)
HOT_LINE = COLD_LINE.replace(
    "the lowest temperature is 16 degrees, below", "the highest temperature is 31.9 degrees, above"
).replace("(20)", "(30)")


def test_the_status_shows_one_line_per_matched_rule_after_all_other_text(rig):
    base = BASELINE["get_farm_status"]["structuredContent"]
    turn_on(rig)
    sc = call(rig, "get_farm_status")["structuredContent"]
    assert sc["text_en"] == base["text_en"] + " " + COLD_LINE + " " + HOT_LINE
    assert sc["text_en"].index("Please check the birds today") < sc["text_en"].index("Forecast (hourly")
    assert spoken_numbers(sc["text_en"], set()) and sorted(spoken_numbers(sc["text_en"], set())) == sorted(
        spoken_numbers(sc["text_te"], set())
    )


def test_the_status_has_a_separate_structured_list_that_backs_every_spoken_number(rig):
    turn_on(rig)
    sc = call(rig, "get_farm_status")["structuredContent"]
    cold, hot = sc["weather_reminders"]
    assert (cold["rule_id"], cold["stat"], cold["comparator"], cold["threshold_c"], cold["value_c"]) == (
        "cold",
        "min",
        "below",
        20.0,
        16.0,
    )
    assert (hot["rule_id"], hot["value_c"], hot["threshold_c"]) == ("hot", 31.9, 30.0)
    assert (
        cold["note"] == NOTE
        and cold["is_example"] is True
        and cold["simulated"] is True
        and cold["source"] == "simulated"
    )
    assert (cold["fetched_hour"], cold["fetched_minute"]) == (2, 0) and cold["at"].startswith("2026-10-04T03:00")
    assert (
        cold["text_en"] == COLD_LINE
        and "అంచనా" in cold["text_te"]
        and "16" in cold["text_te"]
        and "20" in cold["text_te"]
    )
    assert set(sc) - {"weather_reminders"} == set(
        BASELINE["get_farm_status"]["structuredContent"]
    )  # nothing else added


def test_the_briefing_shows_the_same_lines_after_its_closing_and_adds_no_structured_field(rig):
    base = BASELINE["get_daily_briefing"]["structuredContent"]
    turn_on(rig)
    sc = call(rig, "get_daily_briefing")["structuredContent"]
    assert sc["text_en"] == base["text_en"] + " " + COLD_LINE + " " + HOT_LINE
    assert "weather_reminders" not in sc and strip(sc) == strip(base)
    assert call(rig, "get_daily_briefing")["content"][0]["text"] == sc["text_en"]


def test_levels_safety_reason_codes_and_vet_advice_are_exactly_the_same_with_the_feature_on(rig):
    turn_on(rig)
    for key, tool, args in (
        ("get_farm_status", "get_farm_status", {}),
        ("get_farm_status shed 2", "get_farm_status", {"house": "shed 2"}),
        ("get_daily_briefing", "get_daily_briefing", {}),
        ("get_daily_briefing more", "get_daily_briefing", {"more": True}),
    ):
        sc = call(rig, tool, **args)["structuredContent"]
        before = BASELINE[key]["structuredContent"]
        assert strip(sc) == strip(before), key  # level, houses, items, safety, everything but the weather additions
        assert sc["safety"] == before["safety"] and sc["level"] == before["level"]
        assert sc["text_en"].startswith(before["text_en"]) and sc["text_te"].startswith(before["text_te"])


def test_a_live_forecast_names_open_meteo_and_is_not_labelled_simulated_or_demo(rig):
    turn_on(rig, rules=(WeatherRule("c", "min", "below", 20.0, 6, "curtains", False),), port=Live([18.5, 22, 24]))
    sc = call(rig, "get_farm_status")["structuredContent"]
    [line] = sc["weather_reminders"]
    assert line["source"] == "Open-Meteo" and line["simulated"] is False and line["is_example"] is False
    assert line["text_en"] == (
        "Forecast (hourly, outdoors at your farm's location, source: Open-Meteo; not real-time; fetched at 02:00): "
        "the lowest temperature is 18.5 degrees, below the number you set (20). Your note: curtains."
    )
    assert "Simulated" not in sc["text_en"][len(BASELINE["get_farm_status"]["structuredContent"]["text_en"]) :]


def test_a_rule_with_no_note_has_no_note_sentence(rig):
    turn_on(rig, rules=(WeatherRule("c", "min", "below", 20.0, 12, None, False),))
    line = call(rig, "get_farm_status")["structuredContent"]["weather_reminders"][0]
    assert "Your note" not in line["text_en"] and line["note"] is None and line["text_en"].endswith("(20).")
    turn_on(rig, rules=(WeatherRule("c", "min", "below", 20.0, 12, "   ", False),))
    assert "Your note" not in call(rig, "get_farm_status")["structuredContent"]["weather_reminders"][0]["text_en"]


def test_the_farmers_note_is_shown_exactly_as_he_wrote_it_in_both_languages(rig):
    note = "కర్టెన్లు దించండి, curtains down  <b>&"
    turn_on(rig, rules=(WeatherRule("c", "min", "below", 20.0, 12, note, False),))
    sc = call(rig, "get_farm_status")["structuredContent"]
    line = sc["weather_reminders"][0]
    assert line["note"] == note and f"Your note: {note}." in line["text_en"] and note in line["text_te"]


def test_no_match_gives_an_empty_list_and_no_line(rig):
    turn_on(rig, rules=(WeatherRule("c", "min", "below", -50.0, 12, "n", False),))
    sc = call(rig, "get_farm_status")["structuredContent"]
    assert (
        sc["weather_reminders"] == [] and sc["text_en"] == BASELINE["get_farm_status"]["structuredContent"]["text_en"]
    )
    assert (
        call(rig, "get_daily_briefing")["structuredContent"]["text_en"]
        == BASELINE["get_daily_briefing"]["structuredContent"]["text_en"]
    )


def test_an_unavailable_forecast_says_so_once_and_changes_nothing_else(rig):
    turn_on(rig, port=Down())
    for tool in ("get_farm_status", "get_daily_briefing"):
        sc = call(rig, tool)["structuredContent"]
        base = BASELINE[tool]["structuredContent"]
        assert (
            sc["text_en"]
            == base["text_en"] + " I couldn't get the weather forecast just now, so there is no weather reminder."
        )
        assert strip(sc) == strip(base)
    assert call(rig, "get_farm_status")["structuredContent"]["weather_reminders"] == []


def test_the_shed_status_and_the_farm_status_both_carry_the_lines(rig):
    turn_on(rig)
    one = call(rig, "get_farm_status", house="shed 2")["structuredContent"]
    assert len(one["weather_reminders"]) == 2 and one["text_en"].endswith(HOT_LINE)
    assert strip(one) == strip(BASELINE["get_farm_status shed 2"]["structuredContent"])


def test_the_lines_never_mention_a_shed_interior_or_give_advice(rig):
    turn_on(rig)
    text = call(rig, "get_farm_status")["structuredContent"]["text_en"].lower()
    weather = text[text.index("forecast (hourly") :]
    for word in ("inside", "indoor", "interior", "should", "recommend", "spray", "curtain", "turn on", "advice"):
        assert word not in weather, word
