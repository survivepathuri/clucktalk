"""The demo farm must tell the same story on any day it is run (docs/DESIGN.md §10), and must stay fictional."""

import json
from datetime import date

import pytest

from clucktalk.domain.feed import plan_feed
from clucktalk.domain.houses import resolve_house
from clucktalk.domain.sale import plan_sale
from clucktalk.domain.status import Level, house_status
from clucktalk.seed import DEMO_FARM_PATH, build_demo_farm

# Three arbitrary days, weeks apart: the story must not depend on the run date.
DAYS = [date(2026, 9, 29), date(2026, 10, 23), date(2026, 11, 15)]


def test_seed_file_is_labeled_fictional():
    raw = json.loads(DEMO_FARM_PATH.read_text(encoding="utf-8"))
    assert raw["fictional_notice"].startswith("FICTIONAL DEMO DATA")
    assert "simulated" in raw


def test_build_is_deterministic():
    assert build_demo_farm(DAYS[0]) == build_demo_farm(DAYS[0])


@pytest.mark.parametrize("as_of", DAYS)
def test_story_shed_two_needs_attention(as_of):
    farm = build_demo_farm(as_of)
    assert farm.is_fictional
    house = resolve_house(farm, "shed two")
    status = house_status(house, as_of)
    codes = {f.code for f in status.findings}
    assert status.level is Level.ALERT
    assert {"mortality_spike", "feed_intake_drop"} <= codes
    assert plan_feed(farm, house, as_of).reorder_needed


@pytest.mark.parametrize("as_of", DAYS)
def test_story_house_one_is_calm(as_of):
    farm = build_demo_farm(as_of)
    house = resolve_house(farm, "house 1")
    assert house_status(house, as_of).level is Level.OK
    assert not plan_feed(farm, house, as_of).reorder_needed


@pytest.mark.parametrize("as_of", DAYS)
def test_story_house_three_is_near_market_age_with_rising_mortality(as_of):
    """House 3 (added 2026-09-29, broiler-first): on target for weight, but 3 days of rising deaths make
    plan_sale's own math say sell now (docs/DESIGN.md §12.4) -- the get_farm_status alert and the sale
    plan agree because both read the same records."""
    farm = build_demo_farm(as_of)
    house = resolve_house(farm, "house 3")
    status = house_status(house, as_of)
    assert status.level is Level.ALERT
    assert "mortality_spike" in {f.code for f in status.findings}
    assert not plan_feed(farm, house, as_of).reorder_needed
    plan = plan_sale(farm, house, as_of)
    assert plan.mortality_rising
    assert plan.best_day_index == 0
    assert plan.break_even_day_index == 1


def test_every_house_is_current():
    as_of = DAYS[0]
    for house in build_demo_farm(as_of).houses:
        assert house.records[-1].day == as_of
