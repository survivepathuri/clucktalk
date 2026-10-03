"""Step 48D part B: after a death spike logged on an EARLIER day this week (and no health check), the briefing says
ALERT and advises the vet. The shed's status card used to say "doing well" while the safety field said ALERT. Now the
card level, the safety level and the briefing agree, with strings that already exist: the ALERT level sentence, the
briefing's own "N birds died <when>, against about B a day the week before" sentence and the vet step."""

from __future__ import annotations

from datetime import timedelta

import pytest

from clucktalk.agents.model import RulesModel
from clucktalk.domain.models import DailyRecord
from clucktalk.server.tools.farm_status import SAFETY_STEP
from tests.contract.conftest import FIXED_DAY
from tests.contract.test_follow_up_surfaces import _brief, _status
from tests.contract.test_health_tools import _rig

LEVEL = {"OK": "ok", "WATCH": "watch", "ALERT": "alert", "UNKNOWN": "unknown"}


@pytest.fixture
def rig():
    yield from _rig(RulesModel())


def _spike(rig, days_ago: int, deaths: int = 60, house: int = 1) -> None:
    day = FIXED_DAY - timedelta(days=days_ago)
    rig.source.store.put_record(rig.source.farm_id, f"house-{house}", DailyRecord(day, deaths, 100.0))


def _item(brief: dict, house: str = "house-1") -> dict | None:
    return next((i for i in brief["items"] if i["category"] == "recent_logged_spike" and i["house_id"] == house), None)


@pytest.mark.parametrize("days_ago", [1, 2, 3])
def test_the_shed_card_says_alert_and_gives_the_reason_and_the_vet_step(rig, days_ago):
    _spike(rig, days_ago)
    brief = _brief(rig)
    item = _item(brief)
    assert item is not None, "the briefing lists the earlier spike"
    one = _status(rig, house="shed 1")
    shed = one["houses"][0]
    assert shed["level"] == "alert", shed["level"]
    assert "is doing well" not in one["text_en"] and "needs attention now" in one["text_en"]
    finding = next(f for f in shed["findings"] if f["code"] == "recent_logged_spike")
    assert finding["level"] == "alert"
    assert item["text_en"].endswith(finding["text_en"]) and item["text_te"].endswith(finding["text_te"])
    assert SAFETY_STEP.en in one["text_en"] and SAFETY_STEP.te in one["text_te"]


def test_card_level_safety_level_and_briefing_agree_for_the_shed_and_the_farm(rig):
    _spike(rig, 2)
    brief = _brief(rig)
    farm = _status(rig)
    one = _status(rig, house="shed 1")
    assert one["level"] == LEVEL[one["safety"]["level"]] == "alert"
    assert one["houses"][0]["level"] == next(h for h in farm["houses"] if h["house_id"] == "house-1")["level"]
    assert farm["level"] == LEVEL[farm["safety"]["level"]] == brief["level"]
    assert one["safety"]["vet_contact_advised"] is True and farm["safety"] == brief["safety"]


def test_the_spike_leaves_the_card_when_it_leaves_the_briefing(rig):
    _spike(rig, 9)  # outside the week
    brief = _brief(rig)
    assert _item(brief) is None
    one = _status(rig, house="shed 1")
    assert one["level"] == "ok" and "is doing well" in one["text_en"]
    assert all(f["code"] != "recent_logged_spike" for f in one["houses"][0]["findings"])


def test_a_small_earlier_count_is_not_a_spike_on_either_surface(rig):
    _spike(rig, 2, deaths=1)
    assert _item(_brief(rig)) is None
    one = _status(rig, house="shed 1")
    assert one["level"] == "ok" and one["safety"]["level"] == "OK"


def test_the_numbers_spoken_are_in_the_values(rig):
    _spike(rig, 3)
    finding = next(
        f for f in _status(rig, house="shed 1")["houses"][0]["findings"] if f["code"] == "recent_logged_spike"
    )
    assert finding["values"]["deaths"] == 60 and finding["values"]["days_ago"] == 3


def test_the_sentence_is_exactly_the_one_the_briefing_has_always_used():
    from clucktalk.server.tools.farm_status import recent_spike_text

    assert recent_spike_text(60, 2, 1).en == "60 birds died yesterday, against about 2 a day the week before."
    assert recent_spike_text(60, 0, 3).en == "60 birds died 3 days ago, after hardly any deaths the week before."
    assert recent_spike_text(60, 2, 1).te.startswith("నిన్న 60 కోళ్లు చనిపోయాయి;")
