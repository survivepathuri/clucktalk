"""Regressions for the independent review of get_farm_status / plan_feed (Rule 11, 2026-09-27).
Each test reproduces a confirmed review scenario; expected values follow from the definitions in the code's
docstrings and docs/DESIGN.md, not from tool output."""

from __future__ import annotations

from datetime import timedelta

import pytest

from clucktalk.domain.errors import BeyondGrowthTable, InsufficientData, NoReferenceCurve
from clucktalk.domain.feed import plan_feed
from clucktalk.domain.profile import demo_default_profile
from clucktalk.server.tools.farm_status import MAX_SPOKEN_HOUSES, build_status
from clucktalk.server.tools.feed import build_plan
from tests.crossmodal import tool_output_problems
from tests.unit.helpers import D0, broiler_house, farm_with, layer_house


class _Source:
    demo_data = False

    def __init__(self, farm, day_offset: int):
        self._farm, self._as_of = farm, D0 + timedelta(days=day_offset)

    def snapshot(self):
        return self._farm, self._as_of

    def profile(self):  # the demo farm's starting profile (independent)
        return demo_default_profile(self._farm.farm_id)


def _steady_layer(number=1, days=10, stock_kg=5000.0):
    return layer_house([0] * days, [110.0] * days, eggs=[880] * days, stock_kg=stock_kg, number=number)


def _ok(out):
    problems = tool_output_problems(out.model_dump(mode="json"))
    assert problems == [], problems
    return out


# Review 1 (High): a broiler past the growth table crashed both tools for the whole farm.
def test_broiler_past_growth_table_does_not_break_the_farm():
    old = broiler_house([100.0] * 10, start_age=51, number=2)  # day 9 -> age 60 > 56 (Ross 308 table end)
    farm = farm_with(_steady_layer(number=1), old)
    status = _ok(build_status(_Source(farm, 9), None))
    assert {h.house_id for h in status.houses} == {"house-1", "house-2"}
    plan = _ok(build_plan(_Source(farm, 9), None, 7))
    assert [p.house_id for p in plan.plans] == ["house-1"]
    assert [u.house_id for u in plan.unavailable] == ["house-2"]
    assert "end of the Ross 308 growth table" in plan.text_en
    with pytest.raises(BeyondGrowthTable) as exc:
        build_plan(_Source(farm, 9), "shed 2", 7)
    assert exc.value.next_step == "Ask me how the shed is doing instead."  # not "add readings": that cannot help


def test_beyond_table_is_still_insufficient_data_and_offers_a_shorter_plan():
    h = broiler_house([100.0] * 10, start_age=45)  # day 9 -> age 54; table ends at 56 -> 2 days left
    with pytest.raises(InsufficientData) as exc:
        plan_feed(farm_with(h), h, D0 + timedelta(days=9), 7)
    assert isinstance(exc.value, BeyondGrowthTable) and exc.value.days_left == 2
    assert exc.value.next_step == "Ask me for 2 days or fewer."


# Review 2 (High): a lookahead cut short by the table end produced a bogus 1-bag order.
def test_no_order_when_stock_outlasts_every_projectable_day():
    h = broiler_house([100.0] * 10, start_age=45, stock_kg=100_000.0)  # age 54, 2 projectable days
    plan = plan_feed(farm_with(h), h, D0 + timedelta(days=9), 1)
    assert plan.days_covered_capped and plan.days_covered == 2
    assert not plan.reorder_needed and plan.suggested_order_bags == 0 and plan.suggested_order_cost_inr == 0
    out = _ok(build_plan(_Source(farm_with(h), 9), "shed 1", 1))
    assert "No reorder needed yet." in out.text_en
    assert "enough until the Ross 308 growth table ends in 2 days" in out.text_en  # says why cover stops


# Review 3 (Medium): layers said "today" for stale data.
def test_stale_layer_is_not_described_as_today():
    farm = farm_with(_steady_layer(days=7))  # records end D0+6
    out = _ok(build_status(_Source(farm, 9), "shed 1"))  # as_of D0+9: 3 days stale
    assert "% today" not in out.text_en and "in the latest count" in out.text_en
    assert "No readings for 3 days." in out.text_en


# Review 4 + 5 (Medium): more than 5 houses read out; farm level "ok" when nothing is known.
def test_unavailable_houses_count_toward_the_spoken_limit_and_level_is_unknown():
    empties = [layer_house([], [], number=n) for n in range(1, 8)]
    out = _ok(build_status(_Source(farm_with(*empties), 9), None))
    assert out.houses == [] and len(out.unavailable) == 7
    assert out.text_en.count("I don't have enough recent records") == MAX_SPOKEN_HOUSES
    assert "ask about one by shed number" in out.text_en
    assert out.level == "unknown"


# Review 6 (Medium): NoReferenceCurve promised deaths and stock, but status failed entirely.
def test_breed_without_curve_still_gets_a_status():
    h = broiler_house([10.0] * 5, breed="Cobb 430", weights={4: 250.0})
    out = _ok(build_status(_Source(farm_with(h), 4), "shed 1"))
    house = out.houses[0]
    assert house.target_weight_g is None and house.avg_weight_g == 250
    assert "no_reference_curve" in [f.code for f in house.findings]
    assert "not compared to a target" in out.text_en
    with pytest.raises(NoReferenceCurve) as exc:
        build_plan(_Source(farm_with(h), 4), "shed 1", 7)
    assert exc.value.next_step == "Ask me how the shed is doing instead."


# Review 7 (Low): "the next 1 days", "at least 1 days".
def test_one_day_grammar():
    out = _ok(build_plan(_Source(farm_with(_steady_layer()), 9), "shed 1", 1))
    assert "tomorrow needs about" in out.text_en and "1 days" not in out.text_en


# Review 8 (Low): wording.
def test_hint_only_for_spoken_findings_and_order_wording():
    low = _steady_layer(number=1, stock_kg=150.0)  # ~110 kg/day: covers 1 day < lead 2 + safety 2 -> reorder
    fine = [_steady_layer(number=n) for n in range(2, 8)]
    out = _ok(build_status(_Source(farm_with(low, *fine), 9), None))
    assert "feed plan" in out.text_en  # House 1's low-stock finding is spoken (worst first)
    assert "to hear how much to order" in out.text_en and "to reorder." not in out.text_en
    plan = _ok(build_plan(_Source(farm_with(low), 9), "shed 1", 7))
    assert "before GST and delivery" in plan.text_en


def test_no_stock_left_wording():
    out = _ok(build_status(_Source(farm_with(_steady_layer(stock_kg=0.0)), 9), "shed 1"))
    assert "There is no feed stock left." in out.text_en and "tomorrow" not in out.text_en


def test_zero_baseline_is_not_spoken_as_about_zero():
    h = layer_house([0] * 9 + [5], [110.0] * 10, eggs=[880] * 10)  # 5 >= max(3 x 0, 3 birds): spike
    out = _ok(build_status(_Source(farm_with(h), 9), "shed 1"))
    assert "5 birds died today, after hardly any deaths this past week" in out.text_en
    assert "about 0" not in out.text_en


# Review 9 (Low): spoken laying arithmetic must add up.
def test_laying_drop_equals_average_minus_today():
    eggs = [900] * 9 + [780]  # sharp drop today
    h = layer_house([0] * 10, [110.0] * 10, eggs=eggs)
    out = _ok(build_status(_Source(farm_with(h), 9), "shed 1"))
    f = next(f for f in out.houses[0].findings if f.code == "laying_drop")
    assert f.values["drop_pts"] == round(f.values["avg_pct"] - f.values["hen_day_pct"], 1)


# Review 10 (Low): unknown cover is unknown, not "not a minimum".
def test_unknown_cover_is_none():
    h = broiler_house([10.0] * 5, breed="Cobb 430")
    house = build_status(_Source(farm_with(h), 4), "shed 1").houses[0]
    assert house.feed_days_covered is None and house.feed_days_covered_is_minimum is None


# Suspicions: stale stock spoken confidently; 'all' or '' sent as a house.
def test_feed_plan_warns_when_readings_are_old():
    out = _ok(build_plan(_Source(farm_with(_steady_layer(days=7)), 9), "shed 1", 7))
    assert out.plans[0].days_since_record == 3
    assert "3 days old" in out.text_en


@pytest.mark.parametrize("ref", ["", "  ", "all", "All Sheds", "whole farm"])
def test_whole_farm_words_mean_every_house(ref):
    farm = farm_with(_steady_layer(number=1), _steady_layer(number=2))
    assert len(build_status(_Source(farm, 9), ref).houses) == 2
    assert len(build_plan(_Source(farm, 9), ref, 7).plans) == 2


# Verification round (review NEW-1, NEW-2, partial #5).
def test_past_table_broiler_gets_a_caveat_and_its_weight_is_spoken():
    h = broiler_house([100.0] * 10, start_age=51, weights={7: 3000.0})  # weighed at age 58; day 9 -> age 60
    out = _ok(build_status(_Source(farm_with(h), 9), "shed 1"))
    codes = [f.code for f in out.houses[0].findings]
    assert "past_growth_table" in codes
    assert "average weight 3,000 g" in out.text_en and "past day 56 of the Ross 308 growth table" in out.text_en


def test_some_houses_unchecked_is_not_ok():
    farm = farm_with(_steady_layer(number=1), layer_house([], [], number=2))
    assert build_status(_Source(farm, 9), None).level == "watch"
