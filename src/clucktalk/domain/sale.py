"""Sale-day profit: for each day from today (d=0) to +HORIZON_DAYS, what selling the flock that day is worth.

Broilers only (docs/DESIGN.md §12.4): a live sale needs a weight-vs-price comparison, which layers (sold for eggs,
then culled) do not have. Pure function of (house, prices, as_of); no I/O, deterministic, fast path.

Weight basis: the house's own latest weight sample scaled forward along the breed curve's shape (never another
breed's curve, Rule 6); the curve alone only when no sample exists yet (``basis="breed_target"``, stated openly).
Feed basis reuses ``domain.feed.per_bird_projection`` (broiler branch), so the feed cost here matches plan_feed's
own number for the same house.
Mortality: the trailing 7-day daily rate, or the trailing 3-day rate if it is higher ("rising"), applied compounding
forward like plan_feed's projection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from clucktalk.domain.errors import BeyondGrowthTable, NotSoldByWeight
from clucktalk.domain.feed import per_bird_projection
from clucktalk.domain.models import Farm, House, HouseKind
from clucktalk.domain.reference import curve_for

HORIZON_DAYS = 10
MORTALITY_BASELINE_DAYS = 7
MORTALITY_RECENT_DAYS = 3

WeightBasis = Literal["house_actual", "breed_target"]


def _money(x: Decimal) -> Decimal:
    return x.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class DayOutcome:
    day: date
    age_days: int
    live_birds: int
    weight_g: float
    weight_gain_g: float  # vs the previous day; 0 for d=0 (today, the reference point)
    feed_kg: float  # whole flock, that day only
    fcr: float | None  # the curve's target FCR at this age, scaled the same way as the weight (evidence for §12.4)
    gain_value_inr: Decimal
    feed_cost_inr: Decimal
    mortality_loss_inr: Decimal
    marginal_profit_inr: Decimal  # gain - feed - mortality; 0 for d=0
    net_vs_today_inr: Decimal  # cumulative marginal_profit from d=1..this day


@dataclass(frozen=True)
class SalePlan:
    house_id: str
    label_en: str
    label_te: str
    as_of: date
    weight_basis: WeightBasis
    live_price_per_kg: Decimal
    feed_price_per_kg: Decimal
    mortality_rate_pct: float  # the daily rate used (whichever baseline), as a percentage
    mortality_rising: bool
    days: tuple[DayOutcome, ...]  # index 0 = today; index i = today + i days
    best_day_index: int  # argmax(net_vs_today_inr); earliest on ties
    break_even_day_index: int | None  # first index >= 1 where marginal_profit_inr < 0; None if never in horizon


def _mortality_rate(house: House, as_of: date) -> tuple[float, bool]:
    live_now = house.live_birds(as_of)

    def rate_over(days: int) -> float:
        recent = [r for r in house.records_until(as_of) if r.day > as_of - timedelta(days=days)]
        if not recent or live_now == 0:
            return 0.0
        return sum(r.deaths for r in recent) / len(recent) / live_now

    baseline = rate_over(MORTALITY_BASELINE_DAYS)
    recent = rate_over(MORTALITY_RECENT_DAYS)
    rising = recent > baseline
    return (recent if rising else baseline), rising


def plan_sale(
    farm: Farm, house: House, as_of: date, live_price_per_kg: Decimal | None = None, horizon_days: int = HORIZON_DAYS
) -> SalePlan:
    if house.kind is not HouseKind.BROILER:
        raise NotSoldByWeight(house.label_en, house.label_te)
    curve = curve_for(house.breed)  # NoReferenceCurve propagates: never substitute another breed's curve

    age0 = house.age_days(as_of)
    days_left = curve.max_day - age0
    if days_left <= 0:
        raise BeyondGrowthTable(house.label_en, house.label_te, house.breed, curve.max_day, 0)
    horizon = min(horizon_days, days_left)

    weighed = [r for r in house.records_until(as_of) if r.avg_weight_g is not None]
    if weighed:
        latest = weighed[-1]
        weight_ratio = latest.avg_weight_g / curve.weight_g(house.age_days(latest.day))
        weight_basis: WeightBasis = "house_actual"
    else:
        weight_ratio = 1.0
        weight_basis = "breed_target"

    def weight_at(age: int) -> float:
        return curve.weight_g(age) * weight_ratio

    per_bird, _feed_basis, intake_scale = per_bird_projection(house, as_of)
    fcr_scale = intake_scale if intake_scale is not None else 1.0
    rate, rising = _mortality_rate(house, as_of)

    price = live_price_per_kg if live_price_per_kg is not None else farm.live_bird_price_per_kg
    feed_price = farm.feed_price_per_kg

    live0 = house.live_birds(as_of)
    w0 = weight_at(age0)
    days = [
        DayOutcome(
            day=as_of,
            age_days=age0,
            live_birds=live0,
            weight_g=round(w0, 1),
            weight_gain_g=0.0,
            feed_kg=round(live0 * per_bird(age0) / 1000, 1),
            fcr=round(curve.target_fcr(age0) * fcr_scale, 3),
            gain_value_inr=Decimal(0),
            feed_cost_inr=Decimal(0),
            mortality_loss_inr=Decimal(0),
            marginal_profit_inr=Decimal(0),
            net_vs_today_inr=Decimal(0),
        )
    ]
    live_prev, w_prev, net = live0, w0, Decimal(0)
    for d in range(1, horizon + 1):
        day = as_of + timedelta(days=d)
        age = age0 + d
        live = round(live_prev * (1 - rate))
        w = weight_at(age)
        feed_kg = live * per_bird(age) / 1000
        gain_value = _money(Decimal(str(live)) * Decimal(str((w - w_prev) / 1000)) * price)
        feed_cost = _money(Decimal(str(feed_kg)) * feed_price)
        died = live_prev - live
        mortality_loss = _money(Decimal(str(died)) * Decimal(str(w / 1000)) * price)
        marginal = gain_value - feed_cost - mortality_loss
        net += marginal
        days.append(
            DayOutcome(
                day=day,
                age_days=age,
                live_birds=live,
                weight_g=round(w, 1),
                weight_gain_g=round(w - w_prev, 1),
                feed_kg=round(feed_kg, 1),
                fcr=round(curve.target_fcr(age) * fcr_scale, 3),
                gain_value_inr=gain_value,
                feed_cost_inr=feed_cost,
                mortality_loss_inr=mortality_loss,
                marginal_profit_inr=marginal,
                net_vs_today_inr=net,
            )
        )
        live_prev, w_prev = live, w

    best_idx = max(range(len(days)), key=lambda i: (days[i].net_vs_today_inr, -i))
    break_even = next((i for i in range(1, len(days)) if days[i].marginal_profit_inr < 0), None)

    return SalePlan(
        house_id=house.house_id,
        label_en=house.label_en,
        label_te=house.label_te,
        as_of=as_of,
        weight_basis=weight_basis,
        live_price_per_kg=price,
        feed_price_per_kg=feed_price,
        mortality_rate_pct=round(rate * 100, 3),
        mortality_rising=rising,
        days=tuple(days),
        best_day_index=best_idx,
        break_even_day_index=break_even,
    )
