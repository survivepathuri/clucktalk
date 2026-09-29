"""domain/sale.py: expected values computed by hand from the cited Ross 308 curve and the stated rounding rule
(nearest rupee, ROUND_HALF_UP), never copied from the module's own output (docs/DESIGN.md, CLAUDE.md Rule 3)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from clucktalk.domain.errors import BeyondGrowthTable, NotSoldByWeight
from clucktalk.domain.reference import curve_for
from clucktalk.domain.sale import plan_sale
from tests.unit.helpers import D0, broiler_house, farm_with, layer_house
from tests.unit.test_feed import on_curve_broiler

ROSS = curve_for("Ross 308")


def test_no_weight_sample_uses_the_breed_curve_directly():
    h = on_curve_broiler(age_today=20)  # on_curve_broiler sets no avg_weight_g anywhere
    as_of = D0 + timedelta(days=20)
    p = plan_sale(farm_with(h), h, as_of)
    assert p.weight_basis == "breed_target"
    assert p.days[0].weight_g == round(ROSS.weight_g(20), 1)  # ratio 1.0: today's weight is exactly the curve's


def test_a_weight_sample_scales_the_curve_by_the_houses_own_ratio():
    # A record at age 20 weighing 10% over the curve's value there; nothing else changes.
    age0 = 25
    house = on_curve_broiler(age_today=age0)
    records = tuple(
        replace(r, avg_weight_g=ROSS.weight_g(20) * 1.1) if r.day == D0 + timedelta(days=20) else r
        for r in house.records
    )
    house = replace(house, records=records)
    p = plan_sale(farm_with(house), house, D0 + timedelta(days=age0))
    assert p.weight_basis == "house_actual"
    assert p.days[0].weight_g == round(ROSS.weight_g(age0) * 1.1, 1)


def test_break_even_and_best_day_match_hand_computed_daily_profit():
    """age0=42, zero mortality, on-curve intake (scale 1.0), ₹90/kg live, ₹40/kg feed, 1000 birds.
    Marginal profit (see module docstring for the money-rounding rule) turns negative at day 5 (age 47);
    cumulative net peaks at day 4 (₹975), so day 4 is best."""
    h = on_curve_broiler(age_today=42)
    as_of = D0 + timedelta(days=42)
    p = plan_sale(farm_with(h, price="40.00", live_price="90.00"), h, as_of)
    assert [d.marginal_profit_inr for d in p.days[1:8]] == [398, 295, 192, 90, -13, -116, -219]
    assert p.days[4].net_vs_today_inr == 975
    assert p.best_day_index == 4
    assert p.break_even_day_index == 5
    assert p.days[0].fcr == round(ROSS.target_fcr(42), 3)


def test_no_negative_day_means_no_break_even_in_the_horizon():
    h = on_curve_broiler(age_today=20)  # far from the curve's end; growth still outpaces feed cost
    p = plan_sale(farm_with(h, price="30.00", live_price="150.00"), h, D0 + timedelta(days=20))
    assert p.break_even_day_index is None
    assert p.best_day_index == len(p.days) - 1  # still improving on the last projected day


def test_mortality_rising_when_the_last_three_days_are_worse_than_the_week():
    # 7 days at 1 death/day, then the last 3 days at 5/day: recent (3-day) rate > 7-day baseline.
    h = on_curve_broiler(age_today=9, days_of_records=10)
    h = replace(h, records=tuple(replace(r, deaths=5 if i >= 7 else 1) for i, r in enumerate(h.records)))
    p = plan_sale(farm_with(h), h, D0 + timedelta(days=9))
    assert p.mortality_rising
    live = h.live_birds(D0 + timedelta(days=9))
    assert p.mortality_rate_pct == pytest.approx(round(100 * 5 / live, 3))


def test_mortality_not_rising_when_recent_matches_the_baseline():
    h = on_curve_broiler(age_today=9, days_of_records=10)  # zero deaths throughout: recent == baseline == 0
    p = plan_sale(farm_with(h), h, D0 + timedelta(days=9))
    assert not p.mortality_rising and p.mortality_rate_pct == 0.0


def test_layer_house_is_not_sold_by_weight():
    h = layer_house(deaths=[0] * 3, feed_kg=[110.0] * 3)
    with pytest.raises(NotSoldByWeight):
        plan_sale(farm_with(h), h, D0 + timedelta(days=2))


def test_past_the_end_of_the_growth_table_is_refused():
    h = on_curve_broiler(age_today=56)  # Ross 308's last cited day
    with pytest.raises(BeyondGrowthTable) as exc:
        plan_sale(farm_with(h), h, D0 + timedelta(days=56))
    assert exc.value.days_left == 0


def test_horizon_is_clipped_at_the_end_of_the_growth_table():
    h = on_curve_broiler(age_today=54)  # 2 days left before day 56
    p = plan_sale(farm_with(h), h, D0 + timedelta(days=54))
    assert len(p.days) == 3  # today + 2 more
    assert p.days[-1].age_days == 56


def test_farmer_given_price_overrides_the_farms_simulated_default():
    h = on_curve_broiler(age_today=20)
    farm = farm_with(h, live_price="95.00")
    p = plan_sale(farm, h, D0 + timedelta(days=20), live_price_per_kg=Decimal("120"))
    assert p.live_price_per_kg == Decimal("120")


def test_unsourced_breed_is_refused():
    h = broiler_house(feed_kg=[10.0] * 5, breed="Cobb 430")
    from clucktalk.domain.errors import NoReferenceCurve

    with pytest.raises(NoReferenceCurve):
        plan_sale(farm_with(h), h, D0 + timedelta(days=4))
