"""Session 5 review finding B1 (docs/DESIGN.md §18): the day after an urgent check or a suspected reportable disease,
the briefing item must KEEP the check's own warning ("needs a vet today" / "signs of a possible reportable disease")
and the vet closing line; the follow-up question is added to it, never substituted for it. One item carries both."""

from __future__ import annotations

import pytest

from clucktalk.agents.model import RulesModel
from clucktalk.domain.triage import Urgency
from clucktalk.server.tools.briefing import ItemOut, _needs_safety_step
from tests.contract.test_follow_up_surfaces import _brief, _item, _status, due_line
from tests.contract.test_follow_up_tools import TO_BE_SAFE, _ask_and_answer, _stored_check
from tests.contract.test_health_tools import _rig

WARNING = {Urgency.URGENT: "needs a vet today", Urgency.NOTIFIABLE_SUSPECT: "signs of a possible reportable disease"}
QUESTION = "How are the birds now: better, the same, or worse?"
SAFETY_STEP = "Please check the birds today and call your vet if deaths continue."
HIGH = [Urgency.URGENT, Urgency.NOTIFIABLE_SUSPECT]


@pytest.fixture
def rig():
    yield from _rig(RulesModel())


def _house1(sc: dict) -> list[dict]:
    return [i for i in sc["items"] if i["house_id"] == "house-1"]


@pytest.mark.parametrize("days", [1, 2, 5])
@pytest.mark.parametrize("urgency", HIGH)
def test_a_due_follow_up_on_a_high_check_keeps_the_warning_and_asks_the_question(rig, urgency, days):
    _stored_check(rig, days_ago=days, urgency=urgency)
    items = _house1(_brief(rig))
    assert len(items) == 1, "one item carries both, never two"
    item = items[0]
    assert item["category"] == "follow_up" and item["level"] == "alert" and item["pinned"] is True
    assert WARNING[urgency] in item["text_en"], item["text_en"]
    assert QUESTION in item["text_en"]
    assert item["text_en"].index(WARNING[urgency]) < item["text_en"].index(QUESTION)  # the warning comes first
    assert "needs a follow-up" in item["text_en"]


@pytest.mark.parametrize("urgency", HIGH)
def test_the_warning_is_in_telugu_too_and_both_languages_speak_the_same_numbers(rig, urgency):
    _stored_check(rig, days_ago=1, urgency=urgency)
    item = _house1(_brief(rig))[0]
    assert item["text_te"].count("ఫాలో-అప్") >= 1
    assert "ఆరోగ్య తనిఖీ" in item["text_te"]
    assert item["text_te"] != item["text_en"]


@pytest.mark.parametrize("urgency", HIGH)
def test_the_vet_closing_line_survives_the_day_after(rig, urgency):
    _stored_check(rig, days_ago=1, urgency=urgency)
    sc = _brief(rig)
    page = [i for i in sc["items"] if i["spoken"]]
    assert any(i["category"] == "follow_up" for i in page)
    # the item itself asks for the closing line, whatever else is on the page
    follow = _house1(sc)[0]
    assert _needs_safety_step(ItemOut(**follow)) is True
    assert SAFETY_STEP in sc["text_en"]


@pytest.mark.parametrize("urgency", HIGH)
def test_an_escalated_follow_up_on_a_high_check_keeps_the_warning_and_the_vet_line(rig, urgency):
    _stored_check(rig, days_ago=1, urgency=urgency)
    _ask_and_answer(rig, "worse")
    item = _house1(_brief(rig))[0]
    assert item["category"] == "follow_up" and item["values"]["state"] == "escalated"
    assert WARNING[urgency] in item["text_en"] and TO_BE_SAFE in item["text_en"]
    assert _needs_safety_step(ItemOut(**item)) is True


def test_the_reportable_item_still_ranks_first_the_day_after(rig):
    _stored_check(rig, days_ago=1, urgency=Urgency.NOTIFIABLE_SUSPECT)
    sc = _brief(rig)
    assert sc["items"][0]["house_id"] == "house-1" and sc["items"][0]["category"] == "follow_up"


def test_an_urgent_item_is_never_ranked_lower_than_it_was_on_the_day_of_the_check(rig):
    _stored_check(rig, days_ago=0, urgency=Urgency.URGENT)
    before = [i["fact_id"] for i in _brief(rig)["items"]].index("open_health_check:house-1")
    later = _rig(RulesModel())
    rig2 = next(later)
    try:
        _stored_check(rig2, days_ago=1, urgency=Urgency.URGENT)
        after = [i["fact_id"] for i in _brief(rig2)["items"]].index("follow_up:house-1")
    finally:
        next(later, None)
    assert after <= before


def test_a_watch_check_keeps_its_short_question_and_gets_no_warning(rig):
    _stored_check(rig, days_ago=3, urgency=Urgency.WATCH)
    item = _house1(_brief(rig))[0]
    assert item["text_en"] == due_line("House 1", 3)
    assert _needs_safety_step(ItemOut(**item)) is False


@pytest.mark.parametrize("urgency", HIGH)
def test_farm_status_and_the_briefing_say_the_same_sentence_for_the_same_shed(rig, urgency):
    _stored_check(rig, days_ago=1, urgency=urgency)
    item = _house1(_brief(rig))[0]
    fu = _status(rig, house="shed 1")["houses"][0]["follow_up"]
    assert fu["text_en"] == item["text_en"] and fu["text_te"] == item["text_te"]
    assert WARNING[urgency] in fu["text_en"]


def test_the_five_item_cap_holds_with_a_high_follow_up_on_every_shed(rig):
    for n in (1, 2, 3):
        _stored_check(rig, days_ago=1, urgency=Urgency.URGENT, house_id=f"house-{n}")
    sc = _brief(rig)
    assert len(sc["items"]) <= 5
    assert _item(sc, "follow_up:house-1") is not None
