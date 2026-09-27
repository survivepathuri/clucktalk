from datetime import timedelta

import pytest

from clucktalk.domain.errors import InsufficientData
from clucktalk.domain.status import Level, house_status
from tests.unit.helpers import D0, broiler_house, layer_house


def codes(status):
    return {f.code: f for f in status.findings}


# --- cumulative mortality (sourced thresholds: 5% / 10%) ---------------------------------------


def test_healthy_flock_is_ok():
    h = layer_house(deaths=[1] * 10, feed_kg=[110.0] * 10)
    s = house_status(h, D0 + timedelta(days=9))
    assert s.level is Level.OK and s.findings == ()
    assert s.live_birds == 990
    assert s.cum_mortality_pct == 1.0
    assert s.deaths_7d == 7


def test_cum_mortality_6pct_is_watch():
    h = layer_house(deaths=[6] * 10, feed_kg=[110.0] * 10)  # 60 / 1000 = 6%
    s = house_status(h, D0 + timedelta(days=9))
    assert codes(s)["cum_mortality_high"].level is Level.WATCH
    assert s.cum_mortality_pct == 6.0


def test_cum_mortality_11pct_is_alert():
    h = layer_house(deaths=[11] * 10, feed_kg=[110.0] * 10)  # 110 / 1000 = 11%
    s = house_status(h, D0 + timedelta(days=9))
    assert codes(s)["cum_mortality_high"].level is Level.ALERT
    assert s.level is Level.ALERT


# --- mortality spike (heuristic: >= 3x baseline, >= 0.1% of flock, >= 3 birds) ------------------


def test_spike_detected():
    # baseline 2/day; threshold max(3*2, ceil(0.001*~4986)=5, 3) = 6; today 10
    h = layer_house(deaths=[2] * 7 + [10], feed_kg=[550.0] * 8, birds=5000)
    f = codes(house_status(h, D0 + timedelta(days=7)))["mortality_spike"]
    assert f.level is Level.ALERT
    assert f.values["deaths"] == 10 and f.values["baseline_daily_avg"] == 2.0


def test_below_spike_threshold_is_not_flagged():
    h = layer_house(deaths=[2] * 7 + [5], feed_kg=[550.0] * 8, birds=5000)  # 5 < 6
    assert "mortality_spike" not in codes(house_status(h, D0 + timedelta(days=7)))


@pytest.mark.parametrize(("today", "spike"), [(2, False), (3, True)])
def test_small_farm_needs_at_least_three_birds(today, spike):
    h = layer_house(deaths=[0] * 7 + [today], feed_kg=[55.0] * 8, birds=500)
    assert ("mortality_spike" in codes(house_status(h, D0 + timedelta(days=7)))) is spike


def test_spike_needs_baseline_days():
    h = layer_house(deaths=[0, 0, 20], feed_kg=[110.0] * 3)  # only 2 prior days
    assert "mortality_spike" not in codes(house_status(h, D0 + timedelta(days=2)))


# --- feed intake drop (heuristic: < 85% of trailing 3-day baseline) -----------------------------


def test_layer_feed_drop_flagged():
    h = layer_house(deaths=[0] * 4, feed_kg=[110.0, 110.0, 110.0, 90.0])  # 90/110 = 0.818
    f = codes(house_status(h, D0 + timedelta(days=3)))["feed_intake_drop"]
    assert f.level is Level.WATCH
    assert f.values["drop_pct"] == pytest.approx(18.2, abs=0.05)


def test_layer_small_feed_dip_not_flagged():
    h = layer_house(deaths=[0] * 4, feed_kg=[110.0, 110.0, 110.0, 95.0])  # 0.864
    assert "feed_intake_drop" not in codes(house_status(h, D0 + timedelta(days=3)))


def test_broiler_feed_drop_accounts_for_daily_growth():
    # Broilers eating exactly on the Ross curve for ages 0..20, then 80% of target at age 21.
    from clucktalk.domain.reference import curve_for

    ross = curve_for("Ross 308")
    feed = [ross.daily_intake_g(a) for a in range(21)] + [0.8 * ross.daily_intake_g(21)]  # 1000 birds: g == kg
    s = house_status(broiler_house(feed_kg=feed), D0 + timedelta(days=21))
    assert codes(s)["feed_intake_drop"].values["drop_pct"] == pytest.approx(20.0, abs=0.05)


def test_broiler_on_curve_growth_is_not_a_drop():
    from clucktalk.domain.reference import curve_for

    ross = curve_for("Ross 308")
    feed = [ross.daily_intake_g(a) for a in range(22)]
    assert "feed_intake_drop" not in codes(house_status(broiler_house(feed_kg=feed), D0 + timedelta(days=21)))


# --- broiler weight & FCR vs Ross 308 target at day 14 (533 g, FCR 535/533) ---------------------


@pytest.mark.parametrize(("weight", "level"), [(500, None), (450, Level.WATCH), (420, Level.ALERT)])
def test_weight_vs_target(weight, level):
    # 500/533 = 93.8% ok; 450/533 = 84.4% watch; 420/533 = 78.8% alert
    h = broiler_house(feed_kg=[30.0] * 15, weights={14: weight})
    s = house_status(h, D0 + timedelta(days=14))
    assert s.target_weight_g == 533
    found = codes(s).get("weight_below_target")
    assert (found.level if found else None) == level


def test_fcr_ok_when_near_target():
    h = broiler_house(feed_kg=[30.0] * 15, weights={14: 500})  # 450 kg feed / 500 kg live = 0.90
    s = house_status(h, D0 + timedelta(days=14))
    assert s.farm_fcr == pytest.approx(0.90)
    assert s.target_fcr == pytest.approx(535 / 533, abs=1e-3)
    assert "fcr_above_target" not in codes(s)


def test_fcr_above_target_is_watch():
    h = broiler_house(feed_kg=[40.0] * 15, weights={14: 500})  # 600 / 500 = 1.20 > 1.004 + 0.10
    f = codes(house_status(h, D0 + timedelta(days=14)))["fcr_above_target"]
    assert f.values == {"farm_fcr": 1.2, "target_fcr": 1.0}


# --- layers, stale data, missing data ------------------------------------------------------------


def test_laying_drop():
    # hen-day: 900/1000 = 90% for 7 days, then 790/1000 = 79% -> 11-point drop -> alert
    h = layer_house(deaths=[0] * 8, feed_kg=[110.0] * 8, eggs=[900] * 7 + [790])
    s = house_status(h, D0 + timedelta(days=7))
    assert s.hen_day_pct == 79.0 and s.hen_day_pct_7d_avg == 90.0
    assert codes(s)["laying_drop"].level is Level.ALERT


def test_stale_records_are_flagged_not_hidden():
    h = layer_house(deaths=[0] * 5, feed_kg=[110.0] * 5)
    s = house_status(h, D0 + timedelta(days=7))  # last record 3 days before as_of
    assert codes(s)["records_stale"].values["days_since_record"] == 3


def test_no_records_raises_insufficient_data():
    with pytest.raises(InsufficientData):
        house_status(layer_house(deaths=[], feed_kg=[]), D0)


def test_findings_are_ranked_most_severe_first():
    h = layer_house(deaths=[6] * 7 + [40], feed_kg=[110.0] * 7 + [80.0])  # spike + drop + cum mortality
    levels = [f.level for f in house_status(h, D0 + timedelta(days=7)).findings]
    assert levels == sorted(levels, reverse=True)
    assert levels[0] is Level.ALERT
