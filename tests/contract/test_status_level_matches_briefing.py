"""Session 5 review finding H1 (docs/DESIGN.md §18): a shed's level on the farm status (and so the tile and the farm
badge) accounts for the shed's open health check and its follow-up, and equals the briefing's level for the same shed
and day. The spoken line never says "doing well" while the level is not OK.

Spec: an urgent check or a suspected reportable disease means ALERT; a watch check means at least WATCH; an escalated
follow-up means ALERT; a due follow-up means at least WATCH."""

from __future__ import annotations

import pytest

from clucktalk.agents.model import RulesModel
from clucktalk.domain.follow_up import FOLLOW_UP_AFTER_URGENT_DAYS, FOLLOW_UP_AFTER_WATCH_DAYS
from clucktalk.domain.triage import Urgency
from clucktalk.server.tools.briefing import ItemOut, _needs_safety_step
from tests.contract.test_follow_up_surfaces import _brief, _status
from tests.contract.test_follow_up_tools import _ask_and_answer, _stored_check
from tests.contract.test_health_tools import _rig

RANK = {"ok": 0, "info": 0, "watch": 1, "alert": 2}
DOING_WELL = "House 1 is doing well."
SAFETY_STEP = "Please check the birds today and call your vet if deaths continue."
HIGH = (Urgency.URGENT, Urgency.NOTIFIABLE_SUSPECT)


@pytest.fixture
def rig():
    yield from _rig(RulesModel())


def _due_day(urgency: Urgency) -> int:
    return FOLLOW_UP_AFTER_URGENT_DAYS if urgency >= Urgency.URGENT else FOLLOW_UP_AFTER_WATCH_DAYS


def _briefing_level(rig, house_id: str = "house-1") -> str:
    sc = _brief(rig)
    levels = [RANK[i["level"]] for i in sc["items"] if i["house_id"] == house_id]
    return {0: "ok", 1: "watch", 2: "alert"}[max(levels, default=0)]


def _house_status(rig) -> dict:
    return _status(rig, house="shed 1")["houses"][0]


def _farm_house1(rig) -> dict:
    return next(h for h in _status(rig)["houses"] if h["house_id"] == "house-1")


def _check_levels(rig) -> None:
    one = _house_status(rig)
    whole = _farm_house1(rig)
    assert one["level"] == whole["level"] == _briefing_level(rig), (one["level"], whole["level"], _briefing_level(rig))
    if one["level"] != "ok":
        assert DOING_WELL not in _status(rig, house="shed 1")["text_en"]
        assert DOING_WELL not in _status(rig)["text_en"]


# -- every urgency on every day of a follow-up's life: the status level is the briefing's level ----------------------
@pytest.mark.parametrize("days_ago", [0, 1, 2, 3, 5, 9, 12, 20])
@pytest.mark.parametrize("urgency", list(Urgency))
def test_the_status_level_equals_the_briefing_level_for_every_urgency_and_day(rig, urgency, days_ago):
    _stored_check(rig, days_ago=days_ago, urgency=urgency)
    _check_levels(rig)


@pytest.mark.parametrize("outcome", ["better", "same", "worse", "not_sure"])
@pytest.mark.parametrize("urgency", [Urgency.WATCH, *HIGH])
def test_the_status_level_equals_the_briefing_level_after_every_answer(rig, urgency, outcome):
    _stored_check(rig, days_ago=_due_day(urgency), urgency=urgency)
    _ask_and_answer(rig, outcome)
    _check_levels(rig)


def test_the_status_level_equals_the_briefing_level_after_a_vet_handoff(rig):
    _stored_check(rig, days_ago=1, urgency=Urgency.URGENT)
    ask = rig.call("prepare_vet_handoff", house="shed 1")["structuredContent"]
    rig.call("prepare_vet_handoff", house="shed 1", proposal_id=ask["proposal_id"], answer="yes")
    _check_levels(rig)


# -- the spec's floors ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("days_ago", [0, 1, 2])
@pytest.mark.parametrize("urgency", HIGH)
def test_an_urgent_or_reportable_check_is_alert_on_the_status(rig, urgency, days_ago):
    _stored_check(rig, days_ago=days_ago, urgency=urgency)
    assert _house_status(rig)["level"] == "alert"
    assert _farm_house1(rig)["level"] == "alert"


def test_a_reportable_check_stays_alert_for_the_whole_week_until_a_vet_handoff(rig):
    _stored_check(rig, days_ago=6, urgency=Urgency.NOTIFIABLE_SUSPECT)
    assert _house_status(rig)["level"] == "alert"


def test_a_watch_check_is_at_least_watch_on_the_status(rig):
    _stored_check(rig, days_ago=0, urgency=Urgency.WATCH)
    assert _house_status(rig)["level"] == "watch"


@pytest.mark.parametrize("urgency", [Urgency.WATCH, *HIGH])
def test_a_due_follow_up_is_at_least_watch_on_the_status(rig, urgency):
    _stored_check(rig, days_ago=_due_day(urgency), urgency=urgency)
    h = _house_status(rig)
    assert h["follow_up"]["state"] == "due"
    assert RANK[h["level"]] >= RANK["watch"]


@pytest.mark.parametrize("urgency", [Urgency.WATCH, *HIGH])
def test_an_escalated_follow_up_is_alert_on_the_status(rig, urgency):
    _stored_check(rig, days_ago=_due_day(urgency), urgency=urgency)
    _ask_and_answer(rig, "worse")
    h = _house_status(rig)
    assert h["follow_up"]["state"] == "escalated" and h["level"] == "alert"


def test_a_routine_check_changes_nothing(rig):
    _stored_check(rig, days_ago=0, urgency=Urgency.ROUTINE)
    assert _house_status(rig)["level"] == "ok"


def test_a_shed_with_no_check_is_still_doing_well(rig):
    h = _house_status(rig)
    assert h["level"] == "ok" and DOING_WELL in _status(rig, house="shed 1")["text_en"]


# -- the spoken line ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("urgency", [Urgency.WATCH, *HIGH])
def test_the_spoken_line_says_why_the_shed_is_not_ok(rig, urgency):
    _stored_check(rig, days_ago=0, urgency=urgency)
    text = _status(rig, house="shed 1")["text_en"]
    assert "your health check earlier today said:" in text, text
    assert DOING_WELL not in text


@pytest.mark.parametrize("urgency", HIGH)
def test_an_urgent_status_carries_the_vet_closing_line(rig, urgency):
    _stored_check(rig, days_ago=0, urgency=urgency)
    assert SAFETY_STEP in _status(rig, house="shed 1")["text_en"]
    assert SAFETY_STEP in _status(rig)["text_en"]


def test_a_watch_status_has_no_vet_closing_line_from_the_check(rig):
    _stored_check(rig, days_ago=0, urgency=Urgency.WATCH)
    assert SAFETY_STEP not in _status(rig, house="shed 1")["text_en"]


def test_the_farm_badge_is_the_worst_shed(rig):
    _stored_check(rig, days_ago=0, urgency=Urgency.URGENT, house_id="house-1")
    assert _status(rig)["level"] == "alert"


def test_the_item_helper_used_by_the_briefing_still_agrees(rig):
    _stored_check(rig, days_ago=0, urgency=Urgency.URGENT)
    item = next(i for i in _brief(rig)["items"] if i["house_id"] == "house-1")
    assert _needs_safety_step(ItemOut(**item)) is True
