from datetime import timedelta
from decimal import Decimal

import pytest

from clucktalk.domain.errors import InsufficientData, InvalidInput, NoReferenceCurve
from clucktalk.domain.feed import PhaseChange, broiler_phase, plan_feed
from clucktalk.domain.reference import curve_for
from tests.unit.helpers import D0, broiler_house, farm_with, layer_house

AS_OF = D0 + timedelta(days=6)


def layer(stock_kg):
    return layer_house(deaths=[0] * 7, feed_kg=[110.0] * 7, stock_kg=stock_kg)  # 110 g/bird/day, 1000 birds


def test_layer_plan_uses_house_actual_intake():
    h = layer(500.0)
    p = plan_feed(farm_with(h), h, AS_OF)
    assert p.basis == "house_actual"
    assert p.per_bird_today_g == 110.0
    assert p.need_kg == 770.0  # 7 days * 110 kg
    # 4 days = 440 kg fit in 500 kg; the 5th day doesn't -> runs out on day 5
    assert p.days_covered == 4 and not p.days_covered_capped
    assert p.runs_out_on == AS_OF + timedelta(days=5)


def test_no_reorder_when_stock_outlasts_lead_time_plus_safety():
    h = layer(500.0)  # covers 4 days; lead 2 + safety 2 = 4 -> not < 4
    p = plan_feed(farm_with(h), h, AS_OF)
    assert not p.reorder_needed
    assert p.suggested_order_bags == 0 and p.suggested_order_cost_inr == 0


def test_reorder_rounds_up_to_whole_50kg_bags():
    h = layer(400.0)  # covers 3 days < 4 -> reorder; need 770 over 7 days - 400 = 370 kg -> 8 bags
    p = plan_feed(farm_with(h, price="40.00"), h, AS_OF)
    assert p.reorder_needed
    assert p.suggested_order_bags == 8 and p.suggested_order_kg == 400
    assert p.suggested_order_cost_inr == Decimal("16000")


def test_large_stock_reports_at_least_lookahead():
    h = layer(100_000.0)
    p = plan_feed(farm_with(h), h, AS_OF)
    assert p.days_covered == 30 and p.days_covered_capped and p.runs_out_on is None


@pytest.mark.parametrize("horizon", [0, 15])
def test_horizon_out_of_range_is_refused(horizon):
    h = layer(500.0)
    with pytest.raises(InvalidInput):
        plan_feed(farm_with(h), h, AS_OF, horizon_days=horizon)


def test_layer_needs_three_days_of_records():
    h = layer_house(deaths=[0, 0], feed_kg=[110.0, 110.0])
    with pytest.raises(InsufficientData):
        plan_feed(farm_with(h), h, D0 + timedelta(days=1))


def test_projection_applies_recent_mortality():
    # 10 deaths/day over 7 days on 1000 birds; 930 alive; rate = 10/930 per day
    h = layer_house(deaths=[10] * 7, feed_kg=[100.0] * 7, stock_kg=5000.0)
    p = plan_feed(farm_with(h), h, AS_OF, horizon_days=1)
    assert p.daily[0].birds == round(930 * (1 - 10 / 930))  # 920


# --- broilers: Ross 308 curve -----------------------------------------------------------------------


def on_curve_broiler(age_today, scale=1.0, stock_kg=5000.0, days_of_records=None):
    ross = curve_for("Ross 308")
    n = age_today + 1 if days_of_records is None else days_of_records
    start = age_today + 1 - n
    feed = [scale * ross.daily_intake_g(start + i) for i in range(n)]  # 1000 birds: g/bird == kg
    return broiler_house(feed_kg=feed, stock_kg=stock_kg, start_age=start)


def test_broiler_on_curve_projects_curve_intake():
    h = on_curve_broiler(age_today=20)
    p = plan_feed(farm_with(h), h, D0 + timedelta(days=20))
    assert p.basis == "breed_target_scaled" and p.intake_scale == 1.0
    # ages 21..27, linear between 105 (d21) and 145 (d28): 7*105 + (40/7)*(0+1+...+6) = 855 g/bird
    assert p.need_kg == pytest.approx(855.0, abs=0.3)


def test_broiler_scale_follows_how_the_house_actually_eats():
    h = on_curve_broiler(age_today=20, scale=1.1)
    p = plan_feed(farm_with(h), h, D0 + timedelta(days=20))
    assert p.intake_scale == pytest.approx(1.1)
    assert p.need_kg == pytest.approx(855.0 * 1.1, abs=0.5)


def test_broiler_with_few_records_says_it_uses_breed_target():
    h = on_curve_broiler(age_today=20, days_of_records=2)
    p = plan_feed(farm_with(h), h, D0 + timedelta(days=1))
    assert p.basis == "breed_target" and p.intake_scale is None


def test_phase_change_announced_within_horizon():
    # TNAU phases: starter to day 28, finisher from day 29. Age 26 today -> switch at age 29 (in 3 days).
    h = on_curve_broiler(age_today=26)
    as_of = D0 + timedelta(days=26)
    p = plan_feed(farm_with(h), h, as_of)
    assert p.current_phase == "starter"
    assert p.phase_change == PhaseChange(as_of + timedelta(days=3), "starter", "finisher")


@pytest.mark.parametrize(
    ("age", "phase"), [(0, "pre-starter"), (14, "pre-starter"), (15, "starter"), (28, "starter"), (29, "finisher")]
)
def test_broiler_phase_boundaries(age, phase):
    assert broiler_phase(age) == phase


def test_plan_past_end_of_curve_is_refused():
    h = on_curve_broiler(age_today=52)
    with pytest.raises(InsufficientData):
        plan_feed(farm_with(h), h, D0 + timedelta(days=52))


def test_unsourced_breed_is_refused():
    h = broiler_house(feed_kg=[10.0] * 5, breed="Cobb 430")
    with pytest.raises(NoReferenceCurve):
        plan_feed(farm_with(h), h, D0 + timedelta(days=4))
