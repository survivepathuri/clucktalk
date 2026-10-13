"""The pilot farm file (Step 51 part A): the farmer's real houses, loaded in pilot mode instead of the demo seed.

Only what the tools need to count birds and age: per house a number, the birds placed and the placement date. There
are no names, no coordinates and no synthetic daily records anywhere in this file or in what it builds; every record
the pilot shows is one the farmer logged himself. The file is strict (an unknown field is refused, so a name or a
coordinate cannot slip in) and a bad file is a loud startup error, never a fallback to the demo seed (Rule 6).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from clucktalk.domain.errors import NoReferenceCurve
from clucktalk.domain.models import Farm, House, HouseKind
from clucktalk.domain.reference import curve_for

PILOT_FARM_ID = "farm-pilot"
PILOT_FARM_NAME = "Pilot farm"
# A pilot house has no breed unless the file says so. With no breed there is no growth curve, so no target comparison
# of weight, feed or sale weight is ever made for it (domain/reference.py: never another breed's curve).
PILOT_DEFAULT_BREED = "flock"  # reads naturally in "no verified flock growth standard"
MAX_HOUSES = 20
MAX_LABEL = 200
MAX_PAPER_RATE_DELTA = Decimal("1000")  # a sanity ceiling in rupees per kg, not a sourced figure

_FARM_FIELDS = {
    "feed_price_per_kg_inr",
    "feed_price_label",
    "simulated_live_bird_price_per_kg_inr",
    "sale_price_below_paper_rate_inr",
    "supplier_lead_days",
    "houses",
    "farmer_schedule",
}
_SCHEDULE_FIELDS = {
    "vaccination_farmer_days",
    "weigh_from_farmer_day",
    "weight_ok_above_kg_at_day_40",
    "spray_water_above_c",
    "heat_lights_first_days",
    "vet_visit_every_days",
    "normal_feed_per_bird_kg_45d",
    "normal_weight_kg_45d",
    "note",
    "is_example",
}
_SCHEDULE_DATA = _SCHEDULE_FIELDS - {"note", "is_example"}
MAX_FARMER_DAY = 120
_HOUSE_FIELDS = {
    "number",
    "birds_placed",
    "placed_on",
    "kind",
    "breed",
    "age_at_placement_days",
    "feed_stock_kg",
    "deaths_before_pilot",
}


class PilotFarmError(ValueError):
    """The pilot farm file is missing or invalid. Fail loud at startup (Rule 6)."""


@dataclass(frozen=True)
class PilotHouseSpec:
    number: int
    birds_placed: int
    placed_on: date
    kind: HouseKind
    breed: str
    age_at_placement_days: int
    feed_stock_kg: float
    deaths_before_pilot: int = (
        0  # birds that died before the pilot started (asked of the farmer, entered by the operator)
    )


@dataclass(frozen=True)
class FarmerSchedule:
    """What the farmer himself told us about his routine. Every field is optional; a question whose data is absent is
    never offered. Days are the farmer's own days (his day N is the repository's age N-1). The note is for whoever keeps
    the file and is never shown."""

    vaccination_farmer_days: tuple[int, ...] | None = None
    weigh_from_farmer_day: int | None = None
    weight_ok_above_kg_at_day_40: Decimal | None = None
    spray_water_above_c: Decimal | None = None
    heat_lights_first_days: int | None = None
    vet_visit_every_days: int | None = None
    normal_feed_per_bird_kg_45d: Decimal | None = None
    normal_weight_kg_45d: Decimal | None = None
    is_example: bool = False


@dataclass(frozen=True)
class PilotFarmConfig:
    feed_price_per_kg: Decimal
    feed_price_label: str  # who set the price and how: kept word for word, never presented as a market fact
    simulated_live_bird_price_per_kg: Decimal | None  # used only when the farmer states no rate; labeled Simulated
    supplier_lead_days: int
    houses: tuple[PilotHouseSpec, ...]
    # His own rule: his price is the day's paper rate minus this many rupees per kg. None: no such rule.
    sale_price_below_paper_rate: Decimal | None = None
    schedule: FarmerSchedule | None = None


def is_unmodelled_breed(breed: str) -> bool:
    """True for the placeholder breed: the farmer-facing text stays quiet about the missing growth standard."""
    return breed == PILOT_DEFAULT_BREED


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _decimal(data: dict[str, Any], key: str, *, zero_ok: bool = False, high: Decimal | None = None) -> Decimal:
    raw = data.get(key)
    if not isinstance(raw, str):
        raise PilotFarmError(f'{key} must be a number written as text, for example "40"')
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise PilotFarmError(f'{key} must be a number written as text, for example "40"') from exc
    if not value.is_finite() or value < 0 or (value == 0 and not zero_ok):
        raise PilotFarmError(f"{key} must be greater than 0" if not zero_ok else f"{key} must be 0 or more")
    if high is not None and value > high:
        raise PilotFarmError(f"{key} must be at most {high}")
    return value


def _house(spec: Any, index: int) -> PilotHouseSpec:
    where = f"houses[{index}]"
    if not isinstance(spec, dict):
        raise PilotFarmError(f"{where} must be an object")
    unknown = set(spec) - _HOUSE_FIELDS
    if unknown:
        raise PilotFarmError(f"{where} has unknown field(s) {sorted(unknown)} (no names or coordinates belong here)")
    number, birds = spec.get("number"), spec.get("birds_placed")
    if not _is_int(number) or number < 1:
        raise PilotFarmError(f"{where}.number must be a whole number from 1")
    if not _is_int(birds) or birds < 1:
        raise PilotFarmError(f"{where}.birds_placed must be a whole number from 1")
    raw_day = spec.get("placed_on")
    try:
        placed_on = date.fromisoformat(raw_day) if isinstance(raw_day, str) else None
    except ValueError:
        placed_on = None
    if placed_on is None:
        raise PilotFarmError(f"{where}.placed_on must be a date like 2026-09-01")
    try:
        kind = HouseKind(spec.get("kind", "broiler"))
    except ValueError as exc:
        raise PilotFarmError(f"{where}.kind must be broiler or layer") from exc
    breed = spec.get("breed", PILOT_DEFAULT_BREED)
    if not isinstance(breed, str) or not breed.strip() or len(breed) > 40:
        raise PilotFarmError(f"{where}.breed must be 1 to 40 characters")
    age0 = spec.get("age_at_placement_days", 0)
    if not _is_int(age0) or age0 < 0:
        raise PilotFarmError(f"{where}.age_at_placement_days must be a whole number from 0")
    stock = spec.get("feed_stock_kg", 0)
    if isinstance(stock, bool) or not isinstance(stock, (int, float)) or stock < 0:
        raise PilotFarmError(f"{where}.feed_stock_kg must be a number from 0")
    gone = spec.get("deaths_before_pilot", 0)
    if not _is_int(gone) or not 0 <= gone <= birds:
        raise PilotFarmError(
            f"{where}.deaths_before_pilot must be a whole number from 0 up to the birds placed ({birds})"
        )
    return PilotHouseSpec(number, birds, placed_on, kind, breed.strip(), age0, float(stock), gone)


def _schedule_number(data: dict[str, Any], key: str, high: int) -> Decimal | None:
    if key not in data:
        return None
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= high:
        raise PilotFarmError(f"farmer_schedule.{key} must be a number greater than 0 and at most {high}")
    return Decimal(str(value))


def _schedule_days(data: dict[str, Any], key: str, high: int = MAX_FARMER_DAY) -> int | None:
    if key not in data:
        return None
    value = data[key]
    if not _is_int(value) or not 1 <= value <= high:
        raise PilotFarmError(f"farmer_schedule.{key} must be a whole number from 1 to {high}")
    return value


def _parse_schedule(data: Any) -> FarmerSchedule:
    if not isinstance(data, dict):
        raise PilotFarmError("farmer_schedule must be an object")
    unknown = set(data) - _SCHEDULE_FIELDS
    if unknown:
        raise PilotFarmError(
            f"farmer_schedule has unknown field(s) {sorted(unknown)}; allowed: {sorted(_SCHEDULE_FIELDS)}"
        )
    if not set(data) & _SCHEDULE_DATA:
        raise PilotFarmError("farmer_schedule needs at least one of: " + ", ".join(sorted(_SCHEDULE_DATA)))
    days: tuple[int, ...] | None = None
    if "vaccination_farmer_days" in data:
        raw = data["vaccination_farmer_days"]
        if (
            not isinstance(raw, list)
            or not 1 <= len(raw) <= 20
            or not all(_is_int(d) and 1 <= d <= MAX_FARMER_DAY for d in raw)
            or len(set(raw)) != len(raw)
        ):
            raise PilotFarmError(
                f"farmer_schedule.vaccination_farmer_days must be 1 to 20 different days from 1 to {MAX_FARMER_DAY}"
            )
        days = tuple(sorted(raw))
    note = data.get("note")
    if note is not None and (not isinstance(note, str) or len(note) > MAX_LABEL):
        raise PilotFarmError(f"farmer_schedule.note must be text of at most {MAX_LABEL} characters")
    example = data.get("is_example", False)
    if not isinstance(example, bool):
        raise PilotFarmError("farmer_schedule.is_example must be true or false")
    return FarmerSchedule(
        vaccination_farmer_days=days,
        weigh_from_farmer_day=_schedule_days(data, "weigh_from_farmer_day"),
        weight_ok_above_kg_at_day_40=_schedule_number(data, "weight_ok_above_kg_at_day_40", 20),
        spray_water_above_c=_schedule_number(data, "spray_water_above_c", 60),
        heat_lights_first_days=_schedule_days(data, "heat_lights_first_days", 60),
        vet_visit_every_days=_schedule_days(data, "vet_visit_every_days", 60),
        normal_feed_per_bird_kg_45d=_schedule_number(data, "normal_feed_per_bird_kg_45d", 20),
        normal_weight_kg_45d=_schedule_number(data, "normal_weight_kg_45d", 20),
        is_example=example,
    )


def parse_pilot_farm(data: Any, name: str = "the pilot farm file") -> PilotFarmConfig:
    if not isinstance(data, dict):
        raise PilotFarmError(f"{name} must be a JSON object")
    unknown = set(data) - _FARM_FIELDS
    if unknown:
        raise PilotFarmError(f"{name} has unknown field(s) {sorted(unknown)} (no names or coordinates belong here)")
    label = data.get("feed_price_label")
    if not isinstance(label, str) or not label.strip() or len(label) > MAX_LABEL:
        raise PilotFarmError(
            f"feed_price_label must say, in 1 to {MAX_LABEL} characters, where the feed price comes from"
        )
    lead = data.get("supplier_lead_days", 2)
    if not _is_int(lead) or lead < 0:
        raise PilotFarmError("supplier_lead_days must be a whole number from 0")
    houses = data.get("houses")
    if not isinstance(houses, list) or not 1 <= len(houses) <= MAX_HOUSES:
        raise PilotFarmError(f"houses must be a list of 1 to {MAX_HOUSES} houses")
    specs = tuple(_house(h, i) for i, h in enumerate(houses))
    if len({h.number for h in specs}) != len(specs):
        raise PilotFarmError("house numbers must be unique")
    delta = None
    if "sale_price_below_paper_rate_inr" in data:
        delta = _decimal(data, "sale_price_below_paper_rate_inr", zero_ok=True, high=MAX_PAPER_RATE_DELTA)
    simulated = None
    if "simulated_live_bird_price_per_kg_inr" in data or delta is None:
        simulated = _decimal(data, "simulated_live_bird_price_per_kg_inr")
    elif any(h.kind is HouseKind.BROILER and _has_curve(h.breed) for h in specs):
        # the paper-rate rule replaces the simulated price only where no sale plan can ever use it
        raise PilotFarmError("simulated_live_bird_price_per_kg_inr is needed: a house has a verified growth curve")
    return PilotFarmConfig(
        feed_price_per_kg=_decimal(data, "feed_price_per_kg_inr"),
        feed_price_label=label.strip(),
        simulated_live_bird_price_per_kg=simulated,
        supplier_lead_days=lead,
        houses=specs,
        sale_price_below_paper_rate=delta,
        schedule=_parse_schedule(data["farmer_schedule"]) if "farmer_schedule" in data else None,
    )


def _has_curve(breed: str) -> bool:
    try:
        curve_for(breed)
    except NoReferenceCurve:
        return False
    return True


def load_pilot_farm_file(path: Path) -> PilotFarmConfig:
    if not path.is_file():
        raise PilotFarmError(f"{path.name} not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PilotFarmError(f"{path.name} is not valid JSON text: {exc}") from exc
    return parse_pilot_farm(data, path.name)


def build_pilot_farm(config: PilotFarmConfig, as_of: date) -> Farm:
    """The farm as of ``as_of``: houses with no records. The farmer's own logs are laid over this by the source."""
    houses = []
    for spec in config.houses:
        if spec.placed_on > as_of:
            raise PilotFarmError(f"house {spec.number} is placed on {spec.placed_on}, which is in the future")
        try:
            houses.append(
                House(
                    house_id=f"house-{spec.number}",
                    number=spec.number,
                    kind=spec.kind,
                    breed=spec.breed,
                    placed_on=spec.placed_on,
                    birds_placed=spec.birds_placed,
                    age_at_placement_days=spec.age_at_placement_days,
                    feed_stock_kg=spec.feed_stock_kg,
                    records=(),
                    deaths_before=spec.deaths_before_pilot,
                )
            )
        except ValueError as exc:
            raise PilotFarmError(f"house {spec.number}: {exc}") from exc
    return Farm(
        farm_id=PILOT_FARM_ID,
        name=PILOT_FARM_NAME,
        is_fictional=False,
        houses=tuple(houses),
        feed_price_per_kg=config.feed_price_per_kg,
        supplier_lead_days=config.supplier_lead_days,
        # With no simulated price (the paper-rate rule, no house with a curve) no sale plan runs: 1 is never shown.
        live_bird_price_per_kg=config.simulated_live_bird_price_per_kg or Decimal(1),
    )
