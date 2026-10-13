"""The forecast port and the farmer's weather rules file (Step 50W-B, docs/DESIGN.md).

* ``weather_rules.json`` (path from CLUCKTALK_WEATHER_RULES_PATH; read only when that is set, never a ``.local``
  default) holds the farm's latitude and longitude and the farmer's own rules. No file means the
  feature is OFF: nothing is built, no forecast is ever asked for and no network call is possible.
* ``MockForecast`` is the default forecast: deterministic and labelled SIMULATED.
* ``OpenMeteoForecast`` is the one live adapter. It is built only when the file exists AND
  CLUCKTALK_WEATHER_LIVE=true. It asks for hourly ``temperature_2m`` only, with no API key, a timeout of at most 3
  seconds and a 30 minute in-process cache that records when the data was fetched. Any failure becomes an
  "unavailable" forecast; nothing raises into a tool and a stale cache is never served as fresh.

The forecast is an OUTDOOR value for one point. Nothing here knows or claims a temperature inside a shed.
"""

from __future__ import annotations

import json
import logging
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import httpx2

from clucktalk.config import REPO_ROOT
from clucktalk.domain.weather import HourlyPoint, Match, WeatherRule, evaluate

logger = logging.getLogger("clucktalk.server")

SOURCE_LIVE = "Open-Meteo"
SOURCE_MOCK = "simulated"
OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"  # the path is documented; the host is not verified (docs/SOURCES.md)
)
MAX_TIMEOUT_S = 3.0
CACHE_TTL_S = 30 * 60
FORECAST_DAYS = 3
MAX_RULES, MAX_NOTE, MAX_ID, MAX_WINDOW_H = 20, 500, 40, 168
_RULE_KEYS = {"id", "stat", "comparator", "threshold_c", "window_hours", "note", "is_example"}


class WeatherConfigError(ValueError):
    """The weather rules file or its environment setting is invalid. Fail loud at startup (Rule 6)."""


# -- the rules file --------------------------------------------------------------------------
@dataclass(frozen=True)
class WeatherConfig:
    latitude: float
    longitude: float
    rules: tuple[WeatherRule, ...]


def _number(value: object, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise WeatherConfigError(f"{where} must be a finite number")
    return float(value)


def _rule(raw: object, index: int) -> WeatherRule:
    at = f"rules[{index}]"
    if not isinstance(raw, dict):
        raise WeatherConfigError(f"{at} must be an object")
    unknown = set(raw) - _RULE_KEYS
    if unknown:
        raise WeatherConfigError(f"{at} has unknown field(s) {sorted(unknown)}; allowed: {sorted(_RULE_KEYS)}")
    rid = raw.get("id")
    if not isinstance(rid, str) or not rid or len(rid) > MAX_ID:
        raise WeatherConfigError(f"{at}.id must be text of 1 to {MAX_ID} characters")
    if raw.get("stat") not in ("min", "max"):
        raise WeatherConfigError(f'{at}.stat must be "min" or "max"')
    if raw.get("comparator") not in ("below", "above"):
        raise WeatherConfigError(f'{at}.comparator must be "below" or "above"')
    threshold = _number(raw.get("threshold_c"), f"{at}.threshold_c")
    window = raw.get("window_hours")
    if isinstance(window, bool) or not isinstance(window, int) or not 1 <= window <= MAX_WINDOW_H:
        raise WeatherConfigError(f"{at}.window_hours must be a whole number from 1 to {MAX_WINDOW_H}")
    note = raw.get("note")
    if note is not None and (not isinstance(note, str) or len(note) > MAX_NOTE):
        raise WeatherConfigError(f"{at}.note must be text of at most {MAX_NOTE} characters (the farmer's own words)")
    example = raw.get("is_example", False)
    if not isinstance(example, bool):
        raise WeatherConfigError(f"{at}.is_example must be true or false")
    return WeatherRule(rid, raw["stat"], raw["comparator"], threshold, window, note, example)


def load_weather_config(path: Path) -> WeatherConfig | None:
    """None when the file does not exist (the feature is off). Raises WeatherConfigError for any invalid content."""
    if not path.exists():
        return None
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WeatherConfigError(f"{path.name} is not valid JSON text: {exc}") from exc
    if not isinstance(data, dict):
        raise WeatherConfigError(f"{path.name} must be a JSON object")
    unknown = set(data) - {"latitude", "longitude", "rules"}
    if unknown:
        raise WeatherConfigError(f"{path.name} has unknown field(s) {sorted(unknown)}")
    lat = _number(data.get("latitude"), "latitude")
    lon = _number(data.get("longitude"), "longitude")
    if not -90 <= lat <= 90:
        raise WeatherConfigError("latitude must be between -90 and 90")
    if not -180 <= lon <= 180:
        raise WeatherConfigError("longitude must be between -180 and 180")
    rules = data.get("rules")
    if not isinstance(rules, list):
        raise WeatherConfigError("rules must be a list")
    if len(rules) > MAX_RULES:
        raise WeatherConfigError(f"rules has {len(rules)} entries; at most {MAX_RULES} are allowed")
    parsed = tuple(_rule(r, i) for i, r in enumerate(rules))
    ids = [r.id for r in parsed]
    if len(ids) != len(set(ids)):
        raise WeatherConfigError(f"duplicate rule id in {sorted({i for i in ids if ids.count(i) > 1})}")
    return WeatherConfig(lat, lon, parsed)


# -- forecasts -------------------------------------------------------------------------------
@dataclass(frozen=True)
class Forecast:
    status: str  # "ok" or "unavailable"
    points: tuple[HourlyPoint, ...]
    fetched_at: datetime | None  # when the data was fetched (the cache keeps the original time)
    source: str  # SOURCE_LIVE or SOURCE_MOCK
    simulated: bool
    reason: str | None  # why it is unavailable (developer text, never spoken)


def _unavailable(source: str, reason: str) -> Forecast:
    return Forecast("unavailable", (), None, source, source == SOURCE_MOCK, reason)


class ForecastPort(Protocol):
    def forecast(self, latitude: float, longitude: float, now: datetime) -> Forecast: ...


class MockForecast:
    """A deterministic daily curve from 16.0 (the 03:00 hour) to 33.0 (the 15:00 hour), for 72 hours from the current
    hour. SIMULATED: it depends on nothing but the hour, so a demo and a test see the same numbers."""

    def forecast(self, latitude: float, longitude: float, now: datetime) -> Forecast:
        start = now.replace(minute=0, second=0, microsecond=0)
        points = tuple(
            HourlyPoint(
                start + timedelta(hours=i),
                round(24.5 + 8.5 * math.sin(2 * math.pi * (((start + timedelta(hours=i)).hour - 9) % 24) / 24), 1),
            )
            for i in range(FORECAST_DAYS * 24)
        )
        return Forecast("ok", points, now, SOURCE_MOCK, True, None)


Transport = Callable[[str, Mapping[str, Any], float], Any]


def _httpx_transport(url: str, params: Mapping[str, Any], timeout: float) -> Any:
    response = httpx2.get(url, params=dict(params), timeout=timeout)
    response.raise_for_status()
    return response.json()


def _parse(payload: Any) -> tuple[HourlyPoint, ...]:
    """The hourly points of an Open-Meteo answer (times are UTC because the request says timezone=GMT).
    Raises ValueError/KeyError/TypeError for any other shape."""
    hourly = payload["hourly"]
    times, temps = hourly["time"], hourly["temperature_2m"]
    if not isinstance(times, list) or not isinstance(temps, list) or len(times) != len(temps) or not times:
        raise ValueError("hourly.time and hourly.temperature_2m must be lists of the same, non-zero length")
    points = []
    for t, v in zip(times, temps, strict=True):
        if not isinstance(t, str):
            raise ValueError("an hourly time is not text")
        at = datetime.fromisoformat(t).replace(tzinfo=UTC)
        ok = isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
        points.append(HourlyPoint(at, float(v) if ok else None))
    return tuple(points)


class OpenMeteoForecast:
    """The live adapter. Built only on explicit opt-in. ``transport(url, params, timeout)`` returns the decoded JSON or
    raises; tests pass a fake, so they never touch the network."""

    def __init__(
        self,
        transport: Transport | None = None,
        timeout: float = MAX_TIMEOUT_S,
        ttl_s: float = CACHE_TTL_S,
        clock: Callable[[], float] = time.monotonic,
        base_url: str = OPEN_METEO_URL,
    ) -> None:
        self._transport = transport or _httpx_transport
        self._timeout = min(float(timeout), MAX_TIMEOUT_S)
        self._ttl = ttl_s
        self._clock = clock
        self._url = base_url
        self._cache: dict[tuple[float, float], tuple[float, Forecast]] = {}

    def forecast(self, latitude: float, longitude: float, now: datetime) -> Forecast:
        key = (round(latitude, 3), round(longitude, 3))
        cached = self._cache.get(key)
        if cached is not None and self._clock() - cached[0] < self._ttl:
            return cached[1]
        self._cache.pop(key, None)  # expired: never served as fresh
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "temperature_2m",
            "forecast_days": FORECAST_DAYS,
            "timezone": "GMT",
        }
        try:
            points = _parse(self._transport(self._url, params, self._timeout))
        except (httpx2.HTTPError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            logger.warning("weather forecast unavailable (%s)", type(exc).__name__)  # no coordinates in the log
            return _unavailable(SOURCE_LIVE, f"{type(exc).__name__}")
        result = Forecast("ok", points, now, SOURCE_LIVE, False, None)
        self._cache[key] = (self._clock(), result)
        return result


# -- the service the tools use ---------------------------------------------------------------
@dataclass(frozen=True)
class Reminder:
    rule: WeatherRule
    match: Match


@dataclass(frozen=True)
class WeatherView:
    status: str  # "ok", "unavailable" or "off" (no rules, nothing to show)
    simulated: bool
    source: str
    fetched_at: datetime | None
    reminders: tuple[Reminder, ...]


class WeatherReminders:
    """The farmer's rules plus a forecast port. ``check`` is what the briefing and the farm status call."""

    def __init__(self, config: WeatherConfig, port: ForecastPort, now: Callable[[], datetime]) -> None:
        self.config, self.port, self._now = config, port, now

    def check(self) -> WeatherView:
        simulated = isinstance(self.port, MockForecast)
        source = SOURCE_MOCK if simulated else SOURCE_LIVE
        if not self.config.rules:  # until he has entered a rule nothing weather-related is shown, or even asked for
            return WeatherView("off", simulated, source, None, ())
        now = self._now()
        try:
            forecast = self.port.forecast(self.config.latitude, self.config.longitude, now)
        except Exception:  # a port must not raise; if one does, say "unavailable", never break a tool
            logger.exception("weather forecast port raised")
            return WeatherView("unavailable", simulated, source, None, ())
        if forecast.status != "ok":
            return WeatherView("unavailable", forecast.simulated, forecast.source, None, ())
        by_id = {r.id: r for r in self.config.rules}
        matches = evaluate(self.config.rules, forecast.points, now)
        reminders = tuple(Reminder(by_id[m.rule_id], m) for m in matches)
        return WeatherView("ok", forecast.simulated, forecast.source, forecast.fetched_at, reminders)


# -- the environment -------------------------------------------------------------------------
def resolve_rules_path(raw: str) -> Path:
    """A relative path is taken from the repo root; it must be a .json file."""
    path = Path(raw.strip())
    if path.suffix.lower() != ".json":
        raise WeatherConfigError(f"CLUCKTALK_WEATHER_RULES_PATH={raw!r} must name a .json file")
    return path if path.is_absolute() else REPO_ROOT / path


def weather_from_env(
    env: Mapping[str, str], now: Callable[[], datetime], transport: Transport | None = None
) -> WeatherReminders | None:
    """None (feature off) when the rules file does not exist: then nothing is built and no network call is possible.
    The live adapter only when CLUCKTALK_WEATHER_LIVE is exactly "true"; otherwise the simulated forecast."""
    live_raw = env.get("CLUCKTALK_WEATHER_LIVE", "").strip().lower()
    if live_raw not in ("", "true", "false", "0"):
        raise WeatherConfigError(f"CLUCKTALK_WEATHER_LIVE={live_raw!r} must be true or false")
    raw = env.get("CLUCKTALK_WEATHER_RULES_PATH", "").strip()
    if not raw:  # no default location: the demo never looks in .local
        return None
    config = load_weather_config(resolve_rules_path(raw))
    if config is None:
        return None
    port: ForecastPort = OpenMeteoForecast(transport=transport) if live_raw == "true" else MockForecast()
    return WeatherReminders(config, port, now)
