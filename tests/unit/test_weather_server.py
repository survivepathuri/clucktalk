"""Step 50W-B part B: the forecast port. MockForecast (deterministic, SIMULATED), an OPT-IN Open-Meteo adapter
(no API key, hourly temperature_2m only, timeout of at most 3 seconds, a 30 minute in-process cache that records
when it was fetched, graceful failure that never raises), the weather_rules.json loader and the environment wiring.

THESE TESTS NEVER USE THE NETWORK: an autouse fixture makes any socket connection to a non-loopback address fail the
test, and the live adapter is only ever given a fake transport."""

from __future__ import annotations

import json
import socket
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import httpx2
import pytest

from clucktalk.domain.weather import HourlyPoint
from clucktalk.server import weather
from clucktalk.server.weather import (
    Forecast,
    MockForecast,
    OpenMeteoForecast,
    WeatherConfigError,
    WeatherReminders,
    load_weather_config,
    weather_from_env,
)

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 10, 4, 6, 30, tzinfo=IST)
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any connection to a host that is not this machine fails the test."""
    real = socket.socket.connect

    def guarded(self, address, *a, **k):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"a test tried to reach the network: {address!r}")
        return real(self, address, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", guarded)


def good_rules(**over):
    rule = {"id": "cold", "stat": "min", "comparator": "below", "threshold_c": 20, "window_hours": 12, "note": "n"}
    rule.update(over)
    return rule


def write(tmp_path, data, name="weather_rules.json"):
    path = tmp_path / name
    path.write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def config_file(tmp_path, **over):
    data = {"latitude": 17.4, "longitude": 78.5, "rules": [good_rules()]}
    data.update(over)
    return write(tmp_path, data)


# -- the config file -------------------------------------------------------------------------
def test_no_file_means_the_feature_is_off(tmp_path):
    assert load_weather_config(tmp_path / "weather_rules.json") is None


def test_a_valid_file_is_read_exactly_including_a_telugu_note(tmp_path):
    note = "కర్టెన్లు దించండి, వర్షం ముందు  "  # trailing spaces kept: the note is never rewritten
    path = config_file(
        tmp_path,
        rules=[
            good_rules(note=note, is_example=True),
            good_rules(id="hot", stat="max", comparator="above", threshold_c=30.5),
        ],
    )
    cfg = load_weather_config(path)
    assert (cfg.latitude, cfg.longitude) == (17.4, 78.5) and len(cfg.rules) == 2
    first, second = cfg.rules
    assert first.note == note and first.is_example is True
    assert second.note == "n"
    assert (
        second.threshold_c == 30.5
        and second.stat == "max"
        and second.comparator == "above"
        and second.is_example is False
    )


def test_a_rule_without_a_note_is_allowed_and_has_none():
    rule = good_rules()
    del rule["note"]
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        cfg = load_weather_config(write(Path(d), {"latitude": 1, "longitude": 2, "rules": [rule]}))
    assert cfg.rules[0].note is None


def test_an_empty_rule_list_is_a_valid_file():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        assert load_weather_config(write(Path(d), {"latitude": 1, "longitude": 2, "rules": []})).rules == ()


BAD = [
    ("not json", "{", "not valid JSON"),
    ("a list", "[]", "must be a JSON object"),
    ("no latitude", {"longitude": 2, "rules": []}, "latitude"),
    ("latitude out of range", {"latitude": 91, "longitude": 2, "rules": []}, "latitude"),
    ("longitude out of range", {"latitude": 1, "longitude": 181, "rules": []}, "longitude"),
    ("latitude a string", {"latitude": "17", "longitude": 2, "rules": []}, "latitude"),
    ("latitude a bool", {"latitude": True, "longitude": 2, "rules": []}, "latitude"),
    ("latitude NaN", '{"latitude": NaN, "longitude": 2, "rules": []}', "latitude"),
    ("rules missing", {"latitude": 1, "longitude": 2}, "rules"),
    ("rules not a list", {"latitude": 1, "longitude": 2, "rules": {}}, "rules"),
    ("unknown top key", {"latitude": 1, "longitude": 2, "rules": [], "advice": "x"}, "advice"),
    (
        "too many rules",
        {"latitude": 1, "longitude": 2, "rules": [good_rules(id=f"r{i}") for i in range(21)]},
        "at most 20",
    ),
    ("rule not an object", {"latitude": 1, "longitude": 2, "rules": ["x"]}, r"rules\[0\]"),
    ("no id", {"latitude": 1, "longitude": 2, "rules": [{k: v for k, v in good_rules().items() if k != "id"}]}, "id"),
    ("empty id", {"latitude": 1, "longitude": 2, "rules": [good_rules(id="")]}, "id"),
    ("long id", {"latitude": 1, "longitude": 2, "rules": [good_rules(id="x" * 41)]}, "id"),
    ("duplicate id", {"latitude": 1, "longitude": 2, "rules": [good_rules(), good_rules()]}, "duplicate"),
    ("bad stat", {"latitude": 1, "longitude": 2, "rules": [good_rules(stat="mean")]}, "stat"),
    ("bad comparator", {"latitude": 1, "longitude": 2, "rules": [good_rules(comparator="equal")]}, "comparator"),
    ("threshold a string", {"latitude": 1, "longitude": 2, "rules": [good_rules(threshold_c="20")]}, "threshold_c"),
    ("threshold a bool", {"latitude": 1, "longitude": 2, "rules": [good_rules(threshold_c=True)]}, "threshold_c"),
    (
        "threshold infinite",
        '{"latitude":1,"longitude":2,"rules":[{"id":"a","stat":"min","comparator":"below","threshold_c":Infinity,"window_hours":3}]}',
        "threshold_c",
    ),
    ("window zero", {"latitude": 1, "longitude": 2, "rules": [good_rules(window_hours=0)]}, "window_hours"),
    ("window too long", {"latitude": 1, "longitude": 2, "rules": [good_rules(window_hours=169)]}, "window_hours"),
    ("window a float", {"latitude": 1, "longitude": 2, "rules": [good_rules(window_hours=6.5)]}, "window_hours"),
    ("note not text", {"latitude": 1, "longitude": 2, "rules": [good_rules(note=5)]}, "note"),
    ("note too long", {"latitude": 1, "longitude": 2, "rules": [good_rules(note="x" * 501)]}, "note"),
    ("is_example not a bool", {"latitude": 1, "longitude": 2, "rules": [good_rules(is_example="yes")]}, "is_example"),
    ("unknown rule key", {"latitude": 1, "longitude": 2, "rules": [good_rules(advice="spray")]}, "advice"),
]


@pytest.mark.parametrize(("what", "data", "fragment"), BAD, ids=[b[0] for b in BAD])
def test_an_invalid_file_fails_loudly_and_names_the_problem(tmp_path, what, data, fragment):
    with pytest.raises(WeatherConfigError, match=fragment):
        load_weather_config(write(tmp_path, data))


def test_the_edges_that_are_allowed(tmp_path):
    ok = {"latitude": -90, "longitude": 180, "rules": [good_rules(window_hours=168, note="x" * 500, id="x" * 40)]}
    assert load_weather_config(write(tmp_path, ok)).rules[0].window_hours == 168


def test_the_committed_example_file_loads_and_both_rules_are_marked_as_examples():
    cfg = load_weather_config(ROOT / "docs" / "weather_rules.example.json")
    assert cfg is not None and len(cfg.rules) == 2 and all(r.is_example for r in cfg.rules)
    assert {(r.stat, r.comparator, r.threshold_c) for r in cfg.rules} == {
        ("min", "below", 20.0),
        ("max", "above", 30.0),
    }


# -- the mock forecast -----------------------------------------------------------------------
def test_the_mock_is_deterministic_simulated_and_covers_three_days():
    a, b = MockForecast().forecast(17.4, 78.5, NOW), MockForecast().forecast(17.4, 78.5, NOW)
    assert a == b and a.status == "ok" and a.simulated is True and a.source == "simulated"
    assert len(a.points) == 72 and a.fetched_at == NOW
    assert a.points[0].at == NOW.replace(minute=0, second=0, microsecond=0)
    assert all(p.at - q.at == timedelta(hours=1) for q, p in zip(a.points, a.points[1:], strict=False))
    temps = [p.temperature_c for p in a.points]
    assert min(temps) == 16.0 and max(temps) == 33.0  # a daily curve: cold night, hot afternoon


def test_the_mock_depends_only_on_the_hour_not_the_minute_or_the_place():
    f = MockForecast()
    assert f.forecast(1, 2, NOW).points == f.forecast(50, 60, NOW.replace(minute=59)).points


# -- the Open-Meteo adapter, with a fake transport only --------------------------------------
def payload(n=48, start="2026-10-04T00:00", temps=None):
    t0 = datetime.fromisoformat(start)
    return {
        "utc_offset_seconds": 0,
        "hourly": {
            "time": [(t0 + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(n)],
            "temperature_2m": temps if temps is not None else [20.0 + (i % 5) for i in range(n)],
        },
    }


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Fake:
    def __init__(self, result=...):
        self.calls = []
        self.result = payload() if result is ... else result

    def __call__(self, url, params, timeout):
        self.calls.append((url, dict(params), timeout))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def adapter(fake, clock=None, **kw):
    return OpenMeteoForecast(transport=fake, clock=clock or Clock(), **kw)


def test_a_good_answer_becomes_hourly_points_in_utc_and_is_not_simulated():
    fake = Fake(payload(n=3, start="2026-10-04T00:00", temps=[17.5, None, 19]))
    f = adapter(fake).forecast(17.4, 78.5, NOW)
    assert f.status == "ok" and f.simulated is False and f.source == "Open-Meteo" and f.fetched_at == NOW
    assert [p.temperature_c for p in f.points] == [17.5, None, 19.0]
    assert f.points[0].at == datetime(2026, 10, 4, 0, 0, tzinfo=UTC) and f.points[2].at.hour == 2


def test_the_request_asks_for_hourly_temperature_only_without_a_key_and_with_a_short_timeout():
    fake = Fake()
    adapter(fake).forecast(17.4, 78.5, NOW)
    [(url, params, timeout)] = fake.calls
    assert url.startswith("https://") and url.endswith("/v1/forecast")
    assert params == {
        "latitude": 17.4,
        "longitude": 78.5,
        "hourly": "temperature_2m",
        "forecast_days": 3,
        "timezone": "GMT",
    }
    assert timeout <= 3.0
    assert not any("key" in k.lower() for k in params)


def test_a_longer_timeout_is_clamped_to_three_seconds():
    fake = Fake()
    adapter(fake, timeout=30).forecast(1, 2, NOW)
    assert fake.calls[0][2] == 3.0
    fake = Fake()
    adapter(fake, timeout=1.5).forecast(1, 2, NOW)
    assert fake.calls[0][2] == 1.5


def test_the_cache_serves_for_about_thirty_minutes_then_fetches_again():
    fake, clock = Fake(), Clock()
    a = adapter(fake, clock)
    first = a.forecast(17.4, 78.5, NOW)
    clock.t += 29 * 60
    again = a.forecast(17.4, 78.5, NOW + timedelta(minutes=29))
    assert len(fake.calls) == 1 and again == first and again.fetched_at == NOW  # the time it was FETCHED, not asked
    clock.t += 2 * 60
    later = a.forecast(17.4, 78.5, NOW + timedelta(minutes=31))
    assert len(fake.calls) == 2 and later.fetched_at == NOW + timedelta(minutes=31)


def test_the_cache_is_per_place():
    fake = Fake()
    a = adapter(fake)
    a.forecast(17.4, 78.5, NOW)
    a.forecast(28.6, 77.2, NOW)
    assert len(fake.calls) == 2


def test_a_stale_cache_is_never_served_when_the_refetch_fails():
    fake, clock = Fake(), Clock()
    a = adapter(fake, clock)
    assert a.forecast(17.4, 78.5, NOW).status == "ok"
    clock.t += 31 * 60
    fake.result = httpx2.ConnectError("down")
    after = a.forecast(17.4, 78.5, NOW + timedelta(minutes=31))
    assert after.status == "unavailable" and after.points == () and after.fetched_at is None


FAILURES = [
    httpx2.ConnectError("down"),
    httpx2.ReadTimeout("slow"),
    TimeoutError("slow"),
    OSError("no route"),
    ValueError("bad json"),
    {},
    {"hourly": []},
    {"hourly": {"time": ["2026-10-04T00:00"]}},
    {"hourly": {"time": ["2026-10-04T00:00"], "temperature_2m": [1, 2]}},
    {"hourly": {"time": ["not a time"], "temperature_2m": [1]}},
    {"hourly": {"time": [5], "temperature_2m": [1]}},
    {"hourly": {"time": "2026-10-04T00:00", "temperature_2m": 1}},
    {"hourly": {"time": [], "temperature_2m": []}},
    [],
    None,
    "text",
]


@pytest.mark.parametrize("failure", FAILURES, ids=[repr(f)[:40] for f in FAILURES])
def test_any_failure_or_bad_shape_is_unavailable_and_never_raises(failure):
    f = adapter(Fake(failure)).forecast(17.4, 78.5, NOW)
    assert f.status == "unavailable" and f.points == () and f.reason


def test_a_temperature_that_is_not_a_number_becomes_a_missing_hour_not_a_zero():
    f = adapter(Fake(payload(n=3, temps=["hot", 18, None]))).forecast(1, 2, NOW)
    assert [p.temperature_c for p in f.points] == [None, 18.0, None]


def test_a_failure_is_not_cached_so_the_next_call_tries_again():
    fake = Fake(httpx2.ConnectError("down"))
    a = adapter(fake)
    assert a.forecast(1, 2, NOW).status == "unavailable"
    fake.result = payload()
    assert a.forecast(1, 2, NOW).status == "ok" and len(fake.calls) == 2


def test_the_default_transport_uses_httpx2_with_the_clamped_timeout_and_no_other_option(monkeypatch):
    seen = {}

    class Resp:
        status_code = 200

        def json(self):
            return payload(n=2)

        def raise_for_status(self):
            pass

    def fake_get(url, params=None, timeout=None, **kw):
        seen.update(url=url, params=params, timeout=timeout, extra=kw)
        return Resp()

    monkeypatch.setattr(weather.httpx2, "get", fake_get)
    f = OpenMeteoForecast(clock=Clock(), timeout=99).forecast(1, 2, NOW)
    assert (
        f.status == "ok"
        and seen["timeout"] == 3.0
        and seen["extra"] == {}
        and seen["params"]["hourly"] == "temperature_2m"
    )


def test_the_default_transport_reports_a_bad_status_as_unavailable(monkeypatch):
    class Resp:
        status_code = 500

        def json(self):
            return {}

        def raise_for_status(self):
            raise httpx2.HTTPStatusError("500", request=None, response=None)

    monkeypatch.setattr(weather.httpx2, "get", lambda *a, **k: Resp())
    assert OpenMeteoForecast(clock=Clock()).forecast(1, 2, NOW).status == "unavailable"


# -- the environment wiring: off unless the file exists, live only by opt-in -----------------
def test_without_the_file_nothing_is_built_and_the_live_adapter_cannot_even_be_constructed(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the live adapter was built")

    monkeypatch.setattr(weather, "OpenMeteoForecast", boom)
    env = {"CLUCKTALK_WEATHER_RULES_PATH": str(tmp_path / "missing.json"), "CLUCKTALK_WEATHER_LIVE": "true"}
    assert weather_from_env(env, lambda: NOW) is None


def test_with_the_file_and_no_flag_the_forecast_is_the_simulated_one(tmp_path):
    svc = weather_from_env({"CLUCKTALK_WEATHER_RULES_PATH": str(config_file(tmp_path))}, lambda: NOW)
    assert isinstance(svc.port, MockForecast)


@pytest.mark.parametrize("value", ["", "false", "FALSE", "0"])
def test_only_an_explicit_true_turns_the_live_adapter_on(tmp_path, value):
    env = {"CLUCKTALK_WEATHER_RULES_PATH": str(config_file(tmp_path)), "CLUCKTALK_WEATHER_LIVE": value}
    assert isinstance(weather_from_env(env, lambda: NOW).port, MockForecast)


def test_live_true_with_the_file_builds_the_adapter_with_the_injected_transport(tmp_path):
    fake = Fake()
    env = {"CLUCKTALK_WEATHER_RULES_PATH": str(config_file(tmp_path)), "CLUCKTALK_WEATHER_LIVE": "true"}
    svc = weather_from_env(env, lambda: NOW, transport=fake)
    assert isinstance(svc.port, OpenMeteoForecast) and fake.calls == []  # nothing is fetched until a tool asks


def test_a_bad_live_flag_or_a_bad_file_fails_at_startup(tmp_path):
    with pytest.raises(WeatherConfigError, match="CLUCKTALK_WEATHER_LIVE"):
        weather_from_env(
            {"CLUCKTALK_WEATHER_RULES_PATH": str(config_file(tmp_path)), "CLUCKTALK_WEATHER_LIVE": "maybe"}, lambda: NOW
        )
    with pytest.raises(WeatherConfigError):
        weather_from_env({"CLUCKTALK_WEATHER_RULES_PATH": str(write(tmp_path, "{"))}, lambda: NOW)


def test_a_relative_rules_path_is_taken_from_the_repo_root_and_must_be_json(tmp_path):
    with pytest.raises(WeatherConfigError, match=r"\.json"):
        weather_from_env({"CLUCKTALK_WEATHER_RULES_PATH": str(tmp_path / "rules.txt")}, lambda: NOW)
    assert weather.resolve_rules_path("docs/weather_rules.example.json") == ROOT / "docs" / "weather_rules.example.json"
    with pytest.raises(WeatherConfigError, match=r"\.json"):
        weather.resolve_rules_path("")  # there is no default location any more


def test_without_a_path_nothing_is_read_at_all_least_of_all_a_local_file(monkeypatch):
    seen = []
    real = Path.exists
    monkeypatch.setattr(Path, "exists", lambda self: (seen.append(self), real(self))[1])
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: seen.append(self) or "{}")
    assert weather_from_env({}, lambda: NOW) is None
    assert weather_from_env({"CLUCKTALK_WEATHER_RULES_PATH": "  "}, lambda: NOW) is None
    assert seen == []


# -- the service: rules + forecast + the clock -----------------------------------------------
class Counting:
    def __init__(self, result):
        self.result, self.calls = result, 0

    def forecast(self, lat, lon, now):
        self.calls += 1
        return self.result


def cfg(tmp_path, rules):
    return load_weather_config(config_file(tmp_path, rules=rules))


def hours(temps, start=None):
    start = start or NOW.replace(minute=0)
    return tuple(HourlyPoint(start + timedelta(hours=i), t) for i, t in enumerate(temps))


def ok(points, source="simulated", simulated=True):
    return Forecast("ok", points, NOW, source, simulated, None)


def test_a_matching_rule_gives_a_reminder_with_the_value_and_the_hour(tmp_path):
    svc = WeatherReminders(cfg(tmp_path, [good_rules(note="curtains")]), Counting(ok(hours([22, 18, 21]))), lambda: NOW)
    view = svc.check()
    assert view.status == "ok" and view.simulated is True and view.source == "simulated" and view.fetched_at == NOW
    [r] = view.reminders
    assert r.rule.id == "cold" and r.match.value == 18 and r.match.at == NOW.replace(minute=0) + timedelta(hours=1)


def test_no_match_gives_an_ok_view_with_no_reminders(tmp_path):
    view = WeatherReminders(cfg(tmp_path, [good_rules()]), Counting(ok(hours([25, 26]))), lambda: NOW).check()
    assert view.status == "ok" and view.reminders == ()


def test_an_unavailable_forecast_gives_an_unavailable_view(tmp_path):
    bad = Forecast("unavailable", (), None, "Open-Meteo", False, "timed out")
    view = WeatherReminders(cfg(tmp_path, [good_rules()]), Counting(bad), lambda: NOW).check()
    assert view.status == "unavailable" and view.reminders == ()


def test_with_no_rules_nothing_is_fetched_and_nothing_is_shown(tmp_path):
    port = Counting(ok(hours([1])))
    view = WeatherReminders(cfg(tmp_path, []), port, lambda: NOW).check()
    assert port.calls == 0 and view.status == "off" and view.reminders == ()


def test_a_port_that_raises_is_unavailable_not_an_error(tmp_path):
    class Raises:
        def forecast(self, *a):
            raise RuntimeError("boom")

    view = WeatherReminders(cfg(tmp_path, [good_rules()]), Raises(), lambda: NOW).check()
    assert view.status == "unavailable"


def test_the_sources_page_records_open_meteo_with_what_is_not_verified():
    text = (ROOT / "docs" / "SOURCES.md").read_text(encoding="utf-8")
    block = text.split("## Weather forecast: Open-Meteo")[1].split("\n## ")[0]
    for needle in ("/v1/forecast", "temperature_2m", "non-commercial", "CC-BY 4.0", "10'000", "not verified"):
        assert needle in block, needle
    assert "api.open-meteo.com" in block and "**not verified**" in block  # the host is said not to be verified
