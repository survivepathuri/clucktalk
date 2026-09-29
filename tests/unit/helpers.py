"""Small builders for hand-made test houses. Expected values in tests are computed by hand from the
definitions (docs/DESIGN.md and the cited breed table), never copied from code output."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from clucktalk.domain.models import DailyRecord, Farm, House, HouseKind

D0 = date(2026, 10, 1)


def layer_house(
    deaths: list[int],
    feed_kg: list[float],
    birds: int = 1000,
    eggs: list[int] | None = None,
    stock_kg: float = 1000.0,
    number: int = 1,
) -> House:
    records = tuple(
        DailyRecord(D0 + timedelta(days=i), deaths[i], feed_kg[i], eggs=None if eggs is None else eggs[i])
        for i in range(len(deaths))
    )
    return House(
        house_id=f"house-{number}",
        number=number,
        kind=HouseKind.LAYER,
        breed="BV-300",
        placed_on=D0,
        birds_placed=birds,
        age_at_placement_days=200,
        feed_stock_kg=stock_kg,
        records=records,
    )


def broiler_house(
    feed_kg: list[float],
    weights: dict[int, float] | None = None,
    birds: int = 1000,
    stock_kg: float = 1000.0,
    breed: str = "Ross 308",
    start_age: int = 0,
    number: int = 1,
) -> House:
    """Records start at placement (age ``start_age``); day i has age start_age + i."""
    weights = weights or {}
    records = tuple(
        DailyRecord(D0 + timedelta(days=i), 0, feed_kg[i], avg_weight_g=weights.get(i)) for i in range(len(feed_kg))
    )
    return House(
        house_id=f"house-{number}",
        number=number,
        kind=HouseKind.BROILER,
        breed=breed,
        placed_on=D0,
        birds_placed=birds,
        age_at_placement_days=start_age,
        feed_stock_kg=stock_kg,
        records=records,
    )


def farm_with(*houses: House, price: str = "40.00", lead_days: int = 2, live_price: str = "95.00") -> Farm:
    return Farm(
        farm_id="farm-test",
        name="Test Farm",
        is_fictional=True,
        houses=houses,
        feed_price_per_kg=Decimal(price),
        supplier_lead_days=lead_days,
        live_bird_price_per_kg=Decimal(live_price),
    )
