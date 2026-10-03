"""Step 48C part A: the briefing and the farm status agree on `safety` (vet_contact_advised, level, reason codes) for
the same farm state. Found in Step 48B: on the fresh demo farm, shed two's death spike made the briefing advise the vet
and the status not."""

from __future__ import annotations

import pytest

from clucktalk.agents.model import RulesModel
from tests.contract.test_follow_up_surfaces import _brief, _status
from tests.contract.test_health_tools import _rig


@pytest.fixture
def rig():
    yield from _rig(RulesModel())


def _briefing_for(rig, house_id: str) -> dict:
    sc = _brief(rig)
    items = [i for i in sc["items"] if i["house_id"] == house_id]
    assert items, house_id
    return sc


def test_fresh_demo_farm_shed_two_the_status_advises_the_vet_like_the_briefing(rig):
    brief = _brief(rig)
    assert brief["safety"]["vet_contact_advised"] is True  # the seeded spike
    one = _status(rig, house="shed 2")
    assert one["safety"]["vet_contact_advised"] is True
    assert one["safety"]["level"] == "ALERT"
    assert "mortality_spike" in one["safety"]["reason_codes"]


def test_fresh_demo_farm_whole_farm_status_and_briefing_agree(rig):
    brief, status = _brief(rig)["safety"], _status(rig)["safety"]
    assert status["vet_contact_advised"] == brief["vet_contact_advised"]
    assert status["level"] == brief["level"]


def _vet_by_shed(rig) -> dict[int, bool]:
    return {n: _status(rig, house=f"shed {n}")["safety"]["vet_contact_advised"] for n in (1, 2, 3)}


def test_fresh_demo_farm_each_shed_advises_the_vet_only_when_it_has_a_death_alert(rig):
    assert _vet_by_shed(rig) == {1: False, 2: True, 3: True}


def test_fresh_demo_farm_codes_level_and_vet_are_the_same_on_the_briefing_and_the_whole_farm_status(rig):
    assert _status(rig)["safety"] == _brief(rig)["safety"]


def test_a_spike_logged_yesterday_is_advised_by_both_even_though_the_status_card_is_ok(rig):
    from datetime import timedelta

    from clucktalk.domain.models import DailyRecord
    from tests.contract.conftest import FIXED_DAY

    rig.source.store.put_record(rig.source.farm_id, "house-1", DailyRecord(FIXED_DAY - timedelta(days=1), 60, 100.0))
    brief, status = _brief(rig)["safety"], _status(rig)["safety"]
    assert status == brief and status["vet_contact_advised"] is True
    assert "recent_logged_spike" in status["reason_codes"]
    assert _status(rig, house="shed 1")["safety"]["vet_contact_advised"] is True
