"""Number wording, the cross-modal checker itself, and voice limits (docs/DESIGN.md §6).
Expected strings are written by hand from the Indian grouping rule, not copied from output."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from clucktalk.domain.errors import InsufficientData, UnknownHouse
from clucktalk.server.render import indian_group, num, rupees, weekday_en, weekday_te
from clucktalk.server.tools.farm_status import MAX_SPOKEN_HOUSES, build_status
from clucktalk.server.tools.feed import build_plan
from tests.crossmodal import unbacked_numbers
from tests.unit.helpers import D0, farm_with, layer_house


@pytest.mark.parametrize(
    ("n", "text"),
    [(0, "0"), (999, "999"), (1000, "1,000"), (98175, "98,175"), (123456, "1,23,456"), (12345678, "1,23,45,678")],
)
def test_indian_grouping(n, text):
    assert indian_group(n) == text


def test_num_and_rupees():
    assert num(88.0) == "88"
    assert num(38.5) == "38.5"
    assert num(1.25) == "1.25"
    assert num(4862) == "4,862"
    assert rupees(Decimal("38.50")) == "₹38.50"
    assert rupees(98175) == "₹98,175"
    assert rupees(Decimal("123456")) == "₹1,23,456"
    with pytest.raises(TypeError):
        num(True)


def test_weekdays():
    tuesday = D0 - timedelta(days=D0.weekday()) + timedelta(days=1)
    assert weekday_en(tuesday) == "Tuesday" and weekday_te(tuesday) == "మంగళవారం"


def test_cross_modal_checker_catches_a_mismatch():
    card = {"deaths": 26, "breed": "Ross 308", "stock_kg": 900, "cost": 98175}
    assert unbacked_numbers(card, "26 birds died. Ross 308. 900 kg, about ₹98,175.") == []
    assert unbacked_numbers(card, "27 birds died.") == [27.0]
    assert unbacked_numbers(card, "ఈరోజు 25వ రోజు") == [25.0]
    assert unbacked_numbers(card, "Ross 309") == [309.0]  # only the exact breed name is exempt


class _Source:
    demo_data = False

    def __init__(self, farm, day_offset: int = 9):
        self._farm = farm
        self._as_of = D0 + timedelta(days=day_offset)

    def snapshot(self):
        return self._farm, self._as_of


def _seven_layer_houses():
    return farm_with(
        *(layer_house([0] * 10, [110.0] * 10, eggs=[880] * 10, stock_kg=5000.0, number=n) for n in range(1, 8))
    )


def test_farm_status_speaks_at_most_five_houses_and_no_screen_reference():
    out = build_status(_Source(_seven_layer_houses()), None)
    assert len(out.houses) == 7
    spoken = sum(out.text_en.count(f"House {n} ") for n in range(1, 8))
    assert spoken == MAX_SPOKEN_HOUSES
    assert "ask about one by name" in out.text_en
    assert "card" not in out.text_en.lower() and "screen" not in out.text_en.lower()
    assert unbacked_numbers(out.model_dump(), out.text_en, out.text_te) == []


def test_feed_plan_speaks_at_most_five_houses():
    out = build_plan(_Source(_seven_layer_houses()), None, 7)
    assert len(out.plans) == 7
    assert sum(out.text_en.count(f"House {n}:") for n in range(1, 8)) == MAX_SPOKEN_HOUSES
    assert unbacked_numbers(out.model_dump(), out.text_en, out.text_te) == []


def test_one_failing_house_does_not_hide_the_others():
    ok = layer_house([0] * 10, [110.0] * 10, eggs=[880] * 10, number=1)
    empty = layer_house([], [], number=2)  # no records at all
    out = build_status(_Source(farm_with(ok, empty)), None)
    assert [h.house_id for h in out.houses] == ["house-1"]
    assert [u.house_id for u in out.unavailable] == ["house-2"]
    assert "the status of House 2" in out.text_en and "షెడ్ 2 స్థితి" in out.text_te


def test_domain_errors_carry_telugu():
    err = UnknownHouse("shed 9", ["House 1"], ["షెడ్ 1"])
    assert err.customer_message_te and "షెడ్ 1" in err.next_step_te
    err2 = InsufficientData("the status of House 1", "షెడ్ 1 స్థితి")
    assert "షెడ్ 1 స్థితి" in err2.customer_message_te and err2.next_step_te


def test_fractional_baseline_is_spoken_as_the_card_value():
    """Prior 7 days: 3,4,3,4,3,3,4 deaths = 24/7 = 3.43 a day; the card rounds to 3, so speech must say 3.
    Today (day 8) 20 deaths >= max(3 x 3.43, 3 birds): a spike."""
    deaths = [0, 3, 4, 3, 4, 3, 3, 4, 20]
    house = layer_house(deaths, [110.0] * 9, eggs=[880] * 9, number=1)
    out = build_status(_Source(farm_with(house), day_offset=8), "shed 1")
    spike = next(f for f in out.houses[0].findings if f.code == "mortality_spike")
    assert spike.values == {"deaths": 20, "baseline_per_day": 3}
    assert "20 birds died today, against about 3 a day" in out.text_en
    assert unbacked_numbers(out.model_dump(), out.text_en, out.text_te, spike.text_en, spike.text_te) == []
