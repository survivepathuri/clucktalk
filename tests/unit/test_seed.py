"""The demo farm must tell the same story on any day it is run (PRD 12.7), and must stay fictional."""

import json
from datetime import date

import pytest

from clucktalk.domain.feed import plan_feed
from clucktalk.domain.houses import resolve_house
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
def test_story_other_houses_are_calm(as_of):
    farm = build_demo_farm(as_of)
    for number in (1, 3):
        house = resolve_house(farm, f"house {number}")
        assert house_status(house, as_of).level is Level.OK
        assert not plan_feed(farm, house, as_of).reorder_needed


def test_every_house_is_current():
    as_of = DAYS[0]
    for house in build_demo_farm(as_of).houses:
        assert house.records[-1].day == as_of
