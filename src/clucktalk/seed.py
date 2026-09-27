"""Build the fictional demo farm from data/seed/demo_farm.json, anchored to any "today".

Records are generated deterministically from the JSON parameters: same input and as_of, same farm.
Dates are relative (``days_ago``), so the demo never goes stale. Broiler feed and weight follow the
cited breed curve, scaled by each house's profile factors.
"""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from clucktalk.config import DATA_DIR
from clucktalk.domain.models import DailyRecord, Farm, House, HouseKind
from clucktalk.domain.reference import curve_for

DEMO_FARM_PATH = DATA_DIR / "seed" / "demo_farm.json"


def _broiler_records(spec: dict, placed_on: date, as_of: date) -> tuple[DailyRecord, ...]:
    curve = curve_for(spec["breed"])
    prof = spec["profile"]
    events = {e["days_ago"]: e for e in spec["events"]}
    live, carry, records = spec["birds_placed"], 0.0, []
    day = placed_on
    while day <= as_of:
        age = spec["age_at_placement_days"] + (day - placed_on).days
        event = events.get((as_of - day).days, {})
        carry += live * prof["daily_mortality_pct"] / 100
        deaths = event.get("deaths", math.floor(carry))
        carry = carry - math.floor(carry) if "deaths" not in event else carry
        intake = event.get("intake_factor", prof["intake_factor"])
        feed_kg = round(live * curve.daily_intake_g(age) * intake / 1000, 1)
        weighed = age > 0 and age % prof["weigh_every_days"] == 0
        weight = round(curve.weight_g(age) * prof["weight_factor"]) if weighed else None
        records.append(DailyRecord(day, deaths, feed_kg, avg_weight_g=weight))
        live -= deaths
        day += timedelta(days=1)
    return tuple(records)


def _layer_records(spec: dict, placed_on: date, as_of: date) -> tuple[DailyRecord, ...]:
    prof = spec["profile"]
    events = {e["days_ago"]: e for e in spec["events"]}
    live, carry, records = spec["birds_placed"], 0.0, []
    day = placed_on
    while day <= as_of:
        age = spec["age_at_placement_days"] + (day - placed_on).days
        event = events.get((as_of - day).days, {})
        carry += live * prof["daily_mortality_pct"] / 100
        deaths = event.get("deaths", math.floor(carry))
        carry = carry - math.floor(carry) if "deaths" not in event else carry
        pct = event.get("hen_day_pct", prof["hen_day_pct"]) if age >= prof["lay_start_age_days"] else 0.0
        eggs = round(live * pct / 100)
        feed_kg = round(live * prof["feed_g_per_bird"] / 1000, 1)
        records.append(DailyRecord(day, deaths, feed_kg, eggs=eggs))
        live -= deaths
        day += timedelta(days=1)
    return tuple(records)


def build_demo_farm(as_of: date, path: Path = DEMO_FARM_PATH) -> Farm:
    raw = json.loads(path.read_text(encoding="utf-8"))
    try:
        houses = []
        for spec in raw["houses"]:
            kind = HouseKind(spec["kind"])
            placed_on = as_of - timedelta(days=spec["placed_days_ago"])
            build = _broiler_records if kind is HouseKind.BROILER else _layer_records
            houses.append(
                House(
                    house_id=spec["house_id"],
                    number=spec["number"],
                    kind=kind,
                    breed=spec["breed"],
                    placed_on=placed_on,
                    birds_placed=spec["birds_placed"],
                    age_at_placement_days=spec["age_at_placement_days"],
                    feed_stock_kg=float(spec["feed_stock_kg"]),
                    records=build(spec, placed_on, as_of),
                )
            )
        return Farm(
            farm_id=raw["farm_id"],
            name=raw["name"],
            is_fictional=True,
            houses=tuple(houses),
            feed_price_per_kg=Decimal(raw["simulated"]["feed_price_per_kg_inr"]),
            supplier_lead_days=raw["simulated"]["supplier_lead_days"],
        )
    except KeyError as exc:
        raise ValueError(f"{path.name}: missing required field {exc}") from exc
