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

from clucktalk.domain.models import Farm, House, HouseKind

PILOT_FARM_ID = "farm-pilot"
PILOT_FARM_NAME = "Pilot farm"
# A pilot house has no breed unless the file says so. With no breed there is no growth curve, so no target comparison
# of weight, feed or sale weight is ever made for it (domain/reference.py: never another breed's curve).
PILOT_DEFAULT_BREED = "your birds"
MAX_HOUSES = 20
MAX_LABEL = 200

_FARM_FIELDS = {
    "feed_price_per_kg_inr",
    "feed_price_label",
    "simulated_live_bird_price_per_kg_inr",
    "supplier_lead_days",
    "houses",
}
_HOUSE_FIELDS = {"number", "birds_placed", "placed_on", "kind", "breed", "age_at_placement_days", "feed_stock_kg"}


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


@dataclass(frozen=True)
class PilotFarmConfig:
    feed_price_per_kg: Decimal
    feed_price_label: str  # who set the price and how: kept word for word, never presented as a market fact
    simulated_live_bird_price_per_kg: Decimal  # used only when the farmer states no rate; labeled Simulated
    supplier_lead_days: int
    houses: tuple[PilotHouseSpec, ...]


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _decimal(data: dict[str, Any], key: str) -> Decimal:
    raw = data.get(key)
    if not isinstance(raw, str):
        raise PilotFarmError(f'{key} must be a number written as text, for example "40"')
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise PilotFarmError(f'{key} must be a number written as text, for example "40"') from exc
    if not value.is_finite() or value <= 0:
        raise PilotFarmError(f"{key} must be greater than 0")
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
    return PilotHouseSpec(number, birds, placed_on, kind, breed.strip(), age0, float(stock))


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
    return PilotFarmConfig(
        feed_price_per_kg=_decimal(data, "feed_price_per_kg_inr"),
        feed_price_label=label.strip(),
        simulated_live_bird_price_per_kg=_decimal(data, "simulated_live_bird_price_per_kg_inr"),
        supplier_lead_days=lead,
        houses=specs,
    )


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
        live_bird_price_per_kg=config.simulated_live_bird_price_per_kg,
    )
