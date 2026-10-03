"""Review finding M5 (Step 47C), over real HTTP: an unanswered follow-up of an urgent check or a suspected reportable
disease with no confirmed vet handoff does not disappear on day 8. The briefing, the farm status (one shed and the
whole farm) and the follow-up tool agree on it for every day of its life; a watch check keeps the 7-day lapse."""

from __future__ import annotations

import pytest

from clucktalk.agents.model import RulesModel
from clucktalk.domain.triage import Urgency
from tests.contract.test_follow_up_surfaces import _brief, _handoff, _status
from tests.contract.test_follow_up_tools import TO_BE_SAFE, _ask_and_answer, _stored_check
from tests.contract.test_health_tools import _rig

HIGH = (Urgency.URGENT, Urgency.NOTIFIABLE_SUSPECT)
WARNING = {Urgency.URGENT: "needs a vet today", Urgency.NOTIFIABLE_SUSPECT: "signs of a possible reportable disease"}
LATE_DAYS = [9, 10, 11, 12, 20, 60]  # an urgent check lapses on day 9 under the old rule (due day 1 + 7 days + 1)
RANK = {"ok": 0, "info": 0, "watch": 1, "alert": 2}


@pytest.fixture
def rig():
    yield from _rig(RulesModel())


def _item(rig):
    return next((i for i in _brief(rig)["items"] if i["house_id"] == "house-1"), None)


def _house(rig) -> dict:
    return _status(rig, house="shed 1")["houses"][0]


def _farm_house(rig) -> dict:
    return next(h for h in _status(rig)["houses"] if h["house_id"] == "house-1")


@pytest.mark.parametrize("days_ago", LATE_DAYS)
@pytest.mark.parametrize("urgency", HIGH)
def test_an_unanswered_follow_up_stays_on_the_briefing_and_the_status_after_the_lapse_day(rig, urgency, days_ago):
    check = _stored_check(rig, days_ago=days_ago, urgency=urgency)
    item = _item(rig)
    assert item is not None and item["category"] == "follow_up" and item["level"] == "alert", item
    assert item["values"]["state"] == "escalated"
    assert WARNING[urgency] in item["text_en"] and TO_BE_SAFE in item["text_en"]
    one, whole = _house(rig), _farm_house(rig)
    assert one["follow_up"]["state"] == whole["follow_up"]["state"] == "escalated"
    assert one["follow_up"]["check_id"] == check and one["level"] == whole["level"] == "alert"
    assert "doing well" not in _status(rig, house="shed 1")["text_en"]


@pytest.mark.parametrize("days_ago", [8, 9, 10, 11, 12, 20])
def test_a_watch_follow_up_keeps_the_seven_day_lapse(rig, days_ago):
    _stored_check(rig, days_ago=days_ago, urgency=Urgency.WATCH)
    fup = _house(rig)["follow_up"]
    assert fup["state"] == ("due" if days_ago <= 10 else "lapsed")
    assert (_item(rig) is not None) == (days_ago <= 10) or days_ago > 10


@pytest.mark.parametrize("urgency", HIGH)
def test_a_vet_handoff_ends_the_escalation(rig, urgency):
    _stored_check(rig, days_ago=12, urgency=urgency)
    assert _house(rig)["follow_up"]["state"] == "escalated"
    _handoff(rig)
    assert _house(rig)["follow_up"]["state"] != "escalated"


def test_a_newer_check_of_equal_urgency_takes_it_over_and_a_lower_one_does_not(rig):
    _stored_check(rig, days_ago=12, urgency=Urgency.URGENT)
    _stored_check(rig, days_ago=1, urgency=Urgency.ROUTINE)
    assert _house(rig)["follow_up"]["state"] == "escalated"
    new = _stored_check(rig, days_ago=1, urgency=Urgency.URGENT)
    fup = _house(rig)["follow_up"]
    assert fup["check_id"] == new and fup["state"] == "due"


@pytest.mark.parametrize("outcome", ["same", "worse", "not_sure"])
def test_a_not_better_answer_is_accepted_late_and_ends_with_the_vet_line(rig, outcome):
    _stored_check(rig, days_ago=12, urgency=Urgency.URGENT)
    first, second = _ask_and_answer(rig, outcome)
    assert second["structuredContent"]["status"] == "changed"
    assert TO_BE_SAFE in second["structuredContent"]["text_en"]


def test_a_better_answer_closes_an_urgent_one_late(rig):
    _stored_check(rig, days_ago=12, urgency=Urgency.URGENT)
    _ask_and_answer(rig, "better")
    assert _house(rig)["follow_up"]["state"] == "closed"


def test_a_better_answer_does_not_close_an_unhanded_reportable_one(rig):
    _stored_check(rig, days_ago=12, urgency=Urgency.NOTIFIABLE_SUSPECT)
    _ask_and_answer(rig, "better")
    assert _house(rig)["follow_up"]["state"] == "escalated"


# -- the consistency sweep: every urgency on every day, no answer ----------------------------------------------------
@pytest.mark.parametrize("days_ago", list(range(0, 16)) + [30, 90])
@pytest.mark.parametrize("urgency", list(Urgency))
def test_briefing_status_and_follow_up_agree_for_every_urgency_and_day(rig, urgency, days_ago):
    _stored_check(rig, days_ago=days_ago, urgency=urgency)
    item, one, whole = _item(rig), _house(rig), _farm_house(rig)
    brief_level = max([RANK[i["level"]] for i in _brief(rig)["items"] if i["house_id"] == "house-1"], default=0)
    assert RANK[one["level"]] == RANK[whole["level"]] == brief_level, (one["level"], whole["level"], brief_level)
    fup = one["follow_up"]
    assert (fup or {}).get("state") == (whole["follow_up"] or {}).get("state")
    if urgency in HIGH:  # never silent, on any day, until closed / handed off / taken over
        assert brief_level == 2 and item is not None
        assert fup is not None and fup["state"] in ("scheduled", "due", "escalated")
    if urgency is Urgency.WATCH and days_ago >= 11:
        assert fup is not None and fup["state"] == "lapsed"


@pytest.mark.parametrize("urgency", HIGH)
def test_on_day_eight_it_is_still_only_a_question(rig, urgency):
    _stored_check(rig, days_ago=8, urgency=urgency)
    assert _house(rig)["follow_up"]["state"] == "due"
