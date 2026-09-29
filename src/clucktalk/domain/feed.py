"""Feed plan per house: projected need, how long stock lasts, and whether to reorder. Pure function.

Projection basis is always reported (``basis``) so the answer can say what it rests on:
  - "house_actual": layers use the house's own trailing per-bird intake.
  - "breed_target_scaled": broilers use the breed curve, scaled by how this house actually eats vs target.
  - "breed_target": broilers with too few records to scale. Stated openly, never hidden.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from clucktalk.domain.errors import BeyondGrowthTable, InsufficientData, InvalidInput
from clucktalk.domain.models import Farm, House, HouseKind
from clucktalk.domain.reference import curve_for

MIN_HORIZON_DAYS = 1
MAX_HORIZON_DAYS = 14
DEFAULT_HORIZON_DAYS = 7
COVERAGE_LOOKAHEAD_DAYS = 30  # how far ahead "stock lasts N days" is computed
BAG_KG = 50  # standard feed bag in India
SAFETY_DAYS = 2  # reorder when stock lasts fewer than supplier lead time + this
INTAKE_BASELINE_DAYS = 3
LAYER_BASELINE_DAYS = 7
MORTALITY_BASELINE_DAYS = 7

# Broiler feed phases by age (TNAU Agritech Portal, Broiler Management: pre-starter 0-2 weeks,
# starter 3-4 weeks, finisher 5-6 weeks).
BROILER_PHASES = ((14, "pre-starter"), (28, "starter"), (10_000, "finisher"))

Basis = Literal["house_actual", "breed_target_scaled", "breed_target"]


@dataclass(frozen=True)
class DayNeed:
    day: date
    age_days: int
    birds: int
    feed_kg: float


@dataclass(frozen=True)
class PhaseChange:
    day: date
    from_phase: str
    to_phase: str


@dataclass(frozen=True)
class FeedPlan:
    house_id: str
    label_en: str
    label_te: str
    as_of: date
    horizon_days: int
    basis: Basis
    intake_scale: float | None  # broilers: actual / target intake ratio used for scaling
    per_bird_today_g: float
    stock_kg: float
    need_kg: float  # over the horizon
    days_covered: int  # full days (from tomorrow) the stock lasts, capped at the lookahead
    days_covered_capped: bool  # True means "at least days_covered"
    runs_out_on: date | None
    reorder_needed: bool
    suggested_order_kg: int  # whole bags, 0 if no order needed
    suggested_order_bags: int
    feed_price_per_kg: Decimal  # simulated
    suggested_order_cost_inr: Decimal  # before GST/delivery; the order flow adds those
    current_phase: str | None
    phase_change: PhaseChange | None
    daily: tuple[DayNeed, ...]


def broiler_phase(age_days: int) -> str:
    for last_day, name in BROILER_PHASES:
        if age_days <= last_day:
            return name
    raise AssertionError("unreachable: last phase is open-ended")


def _live_start(house: House, day: date) -> int:
    return house.live_birds(day - timedelta(days=1))


def _daily_mortality_rate(house: House, as_of: date) -> float:
    recent = [r for r in house.records_until(as_of) if r.day > as_of - timedelta(days=MORTALITY_BASELINE_DAYS)]
    live = house.live_birds(as_of)
    if not recent or live == 0:
        return 0.0
    return sum(r.deaths for r in recent) / len(recent) / live


def per_bird_projection(house: House, as_of: date):
    """Return (fn(age)->grams per bird per day, basis, intake_scale). Public: reused by domain/sale.py, which
    needs the same actual-vs-target scaling for broilers so its feed cost matches plan_feed's own projection."""
    records = house.records_until(as_of)
    if house.kind is HouseKind.LAYER:
        recent = records[-LAYER_BASELINE_DAYS:]
        if len(recent) < INTAKE_BASELINE_DAYS:
            raise InsufficientData(f"a feed plan for {house.label_en}", f"{house.label_te} ఫీడ్ ప్లాన్")
        avg = sum(1000 * r.feed_kg / _live_start(house, r.day) for r in recent) / len(recent)
        return (lambda _age: avg), "house_actual", None

    curve = curve_for(house.breed)
    recent = records[-INTAKE_BASELINE_DAYS:]
    if len(recent) < INTAKE_BASELINE_DAYS:
        return curve.daily_intake_g, "breed_target", None
    actual = sum(1000 * r.feed_kg / _live_start(house, r.day) for r in recent)
    target = sum(curve.daily_intake_g(house.age_days(r.day)) for r in recent)
    scale = actual / target
    return (lambda age: curve.daily_intake_g(age) * scale), "breed_target_scaled", round(scale, 3)


def _project(house: House, as_of: date, days: int, per_bird, max_age: int | None) -> list[DayNeed]:
    live = house.live_birds(as_of)
    rate = _daily_mortality_rate(house, as_of)
    needs = []
    for d in range(1, days + 1):
        day = as_of + timedelta(days=d)
        age = house.age_days(day)
        if max_age is not None and age > max_age:
            break
        birds = round(live * (1 - rate) ** d)
        needs.append(DayNeed(day, age, birds, round(birds * per_bird(age) / 1000, 1)))
    return needs


def plan_feed(farm: Farm, house: House, as_of: date, horizon_days: int = DEFAULT_HORIZON_DAYS) -> FeedPlan:
    if not MIN_HORIZON_DAYS <= horizon_days <= MAX_HORIZON_DAYS:
        raise InvalidInput(
            f"I can plan feed for {MIN_HORIZON_DAYS} to {MAX_HORIZON_DAYS} days ahead.",
            "How many days should I plan for?",
            f"నేను {MIN_HORIZON_DAYS} నుండి {MAX_HORIZON_DAYS} రోజుల వరకు ఫీడ్ ప్లాన్ చేయగలను.",
            "ఎన్ని రోజులకు ప్రణాళిక చేయాలి?",
        )
    if house.live_birds(as_of) == 0:
        raise InsufficientData(
            f"a feed plan for {house.label_en}, because no live birds are recorded there",
            f"{house.label_te} ఫీడ్ ప్లాన్ (అక్కడ బతికి ఉన్న కోళ్లు నమోదు కాలేదు)",
        )

    max_age = None
    if house.kind is HouseKind.BROILER:
        # Checked before any projection: past the table's last day there is no target to scale.
        max_age = curve_for(house.breed).max_day
        days_left = max_age - house.age_days(as_of)
        if days_left < horizon_days:
            raise BeyondGrowthTable(house.label_en, house.label_te, house.breed, max_age, max(days_left, 0))
    per_bird, basis, scale = per_bird_projection(house, as_of)
    horizon = _project(house, as_of, horizon_days, per_bird, max_age)

    lookahead = _project(house, as_of, COVERAGE_LOOKAHEAD_DAYS, per_bird, max_age)
    covered, running = 0, 0.0
    for need in lookahead:
        running += need.feed_kg
        if running > house.feed_stock_kg:
            break
        covered += 1
    capped = covered == len(lookahead)
    runs_out_on = None if capped else as_of + timedelta(days=covered + 1)

    reorder = covered < farm.supplier_lead_days + SAFETY_DAYS
    order_kg = order_bags = 0
    if reorder:
        cover_days = max(horizon_days, farm.supplier_lead_days + SAFETY_DAYS)
        shortfall = sum(n.feed_kg for n in lookahead[:cover_days]) - house.feed_stock_kg
        # Never suggest buying feed the numbers don't show is needed. This also covers stock that outlasts
        # every projectable day (lookahead cut short by the growth table's end): its shortfall is <= 0.
        if shortfall > 0:
            order_bags = math.ceil(shortfall / BAG_KG)
            order_kg = order_bags * BAG_KG
        else:
            reorder = False
    cost = (farm.feed_price_per_kg * order_kg).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    phase = change = None
    if house.kind is HouseKind.BROILER:
        phase = broiler_phase(house.age_days(as_of))
        for need in horizon:
            nxt = broiler_phase(need.age_days)
            if nxt != phase:
                change = PhaseChange(need.day, phase, nxt)
                break

    return FeedPlan(
        house_id=house.house_id,
        label_en=house.label_en,
        label_te=house.label_te,
        as_of=as_of,
        horizon_days=horizon_days,
        basis=basis,
        intake_scale=scale,
        per_bird_today_g=round(per_bird(house.age_days(as_of)), 1),
        stock_kg=house.feed_stock_kg,
        need_kg=round(sum(n.feed_kg for n in horizon), 1),
        days_covered=covered,
        days_covered_capped=capped,
        runs_out_on=runs_out_on,
        reorder_needed=reorder,
        suggested_order_kg=order_kg,
        suggested_order_bags=order_bags,
        feed_price_per_kg=farm.feed_price_per_kg,
        suggested_order_cost_inr=cost,
        current_phase=phase,
        phase_change=change,
        daily=tuple(horizon),
    )
