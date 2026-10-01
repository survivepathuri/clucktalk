"""Session 5 review finding H3, approved 2026-10-01, over real HTTP: an urgent or reportable follow-up stays visible
(briefing and farm status, still one item carrying the warning plus the question) until it is closed, a newer check of
equal or higher urgency exists, the vet handoff is confirmed or it lapses; a newer LOWER check never hides it; a
"worse", "same" or "not sure" for it is always accepted (no "health check waiting" refusal); and an answer attaches to
the open check of the highest urgency (the newest among equals)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from clucktalk.agents.model import RulesModel
from clucktalk.domain.triage import (
    CheckStatus,
    Floor,
    HealthCheck,
    Sign,
    TriageInput,
    TriageResult,
    Urgency,
    new_check_id,
)
from clucktalk.server.farm_state import IST
from tests.contract.test_follow_up_surfaces import _brief, _handoff, _status
from tests.contract.test_follow_up_tools import TO_BE_SAFE, _ask_and_answer, _store_check
from tests.contract.test_health_tools import _rig

WARNING = {Urgency.URGENT: "needs a vet today", Urgency.NOTIFIABLE_SUSPECT: "signs of a possible reportable disease"}
QUESTION = "How are the birds now: better, the same, or worse?"
HIGH = (Urgency.URGENT, Urgency.NOTIFIABLE_SUSPECT)


@pytest.fixture
def rig():
    yield from _rig(RulesModel())


def _check_at(rig, urgency: Urgency, *, days_ago: int, hour: int = 10) -> str:
    """A stored check ``days_ago`` days before the rig's today, at ``hour`` (two checks on one day need two hours)."""
    at = datetime(2026, 9, 29, hour, 0, tzinfo=IST) - timedelta(days=days_ago)
    inp = TriageInput("house-1", "House 1", "షెడ్ 1", "Ross 308", 40, 900, (Sign.COUGHING,), None, None, None,
                      2, 1.0, False, None, at.date().isoformat())  # fmt: skip
    check = HealthCheck(new_check_id(), rig.source.farm_id, "house-1", at, CheckStatus.READY, inp, Floor(urgency, ()),
                        TriageResult(urgency, (), (), "rules", None, None), at)  # fmt: skip
    rig.source.store.add_health_check(check)
    return check.check_id


def _item(rig):
    return next((i for i in _brief(rig)["items"] if i["house_id"] == "house-1"), None)


# -- the review's reproduction ---------------
@pytest.mark.parametrize("newer", [Urgency.ROUTINE, Urgency.WATCH])
@pytest.mark.parametrize("urgency", HIGH)
def test_the_review_reproduction_an_urgent_check_yesterday_and_a_lower_one_today(rig, urgency, newer):
    old = _check_at(rig, urgency, days_ago=1)
    _check_at(rig, newer, days_ago=0)
    item = _item(rig)
    assert item is not None and item["category"] == "follow_up" and item["level"] == "alert", item
    assert WARNING[urgency] in item["text_en"] and QUESTION in item["text_en"]
    house = _status(rig, house="shed 1")["houses"][0]
    assert house["follow_up"]["state"] == "due" and house["follow_up"]["check_id"] == old
    assert house["level"] == "alert"
    first, second = _ask_and_answer(rig, "worse")
    ask, done = first["structuredContent"], second["structuredContent"]
    assert first.get("isError") in (None, False) and ask["check_id"] == old
    assert TO_BE_SAFE in ask["text_en"] and TO_BE_SAFE in done["text_en"]
    assert done["status"] == "changed" and done["state"] == "escalated"
    assert "no health check waiting" not in (ask["text_en"] + done["text_en"]).lower()


@pytest.mark.parametrize("outcome", ["same", "not_sure", "worse"])
def test_every_not_better_answer_is_accepted_while_a_lower_check_exists(rig, outcome):
    _check_at(rig, Urgency.URGENT, days_ago=1)
    _check_at(rig, Urgency.WATCH, days_ago=0)
    first, second = _ask_and_answer(rig, outcome)
    assert second["structuredContent"]["status"] == "changed"
    assert TO_BE_SAFE in second["structuredContent"]["text_en"]


def test_the_escalation_stays_visible_after_the_answer_while_only_lower_checks_exist(rig):
    _check_at(rig, Urgency.URGENT, days_ago=1)
    _check_at(rig, Urgency.ROUTINE, days_ago=0)
    _ask_and_answer(rig, "worse")
    item = _item(rig)
    assert item["values"]["state"] == "escalated" and WARNING[Urgency.URGENT] in item["text_en"]
    assert _status(rig, house="shed 1")["houses"][0]["level"] == "alert"


# -- on the day of the check, before the follow-up is due ----------
@pytest.mark.parametrize("newer", [Urgency.ROUTINE, Urgency.WATCH])
def test_an_urgent_check_made_this_morning_is_still_in_the_briefing_after_a_lower_one_this_afternoon(rig, newer):
    _check_at(rig, Urgency.URGENT, days_ago=0, hour=9)
    _check_at(rig, newer, days_ago=0, hour=11)
    item = _item(rig)
    assert item is not None and item["category"] == "open_health_check"
    assert WARNING[Urgency.URGENT] in item["text_en"] and item["values"]["urgency"] == "urgent"
    assert _status(rig, house="shed 1")["houses"][0]["level"] == "alert"


# -- what still ends it ---------------
@pytest.mark.parametrize("newer", [Urgency.URGENT, Urgency.NOTIFIABLE_SUSPECT])
def test_a_newer_check_of_equal_or_higher_urgency_takes_the_follow_up_over(rig, newer):
    _check_at(rig, Urgency.URGENT, days_ago=3)
    _check_at(rig, newer, days_ago=0)
    item = _item(rig)
    assert item["category"] == "open_health_check"  # the newer check is the one shown, with its own warning
    assert item["values"]["urgency"] == newer.code


def test_better_closes_it_even_with_a_lower_check_present_and_never_lowers_the_urgency(rig):
    old = _check_at(rig, Urgency.URGENT, days_ago=1)
    _check_at(rig, Urgency.ROUTINE, days_ago=0)
    _, second = _ask_and_answer(rig, "better")
    sc = second["structuredContent"]
    assert sc["state"] == "closed" and sc["urgency"] == "urgent" and sc["check_id"] == old


def test_a_confirmed_vet_handoff_ends_it(rig):
    _store_check(rig.source, days_ago=1, urgency=Urgency.URGENT)
    _handoff(rig)  # the handoff is for the shed's newest check: the urgent one, before any lower check exists
    _check_at(rig, Urgency.ROUTINE, days_ago=0)
    assert _status(rig, house="shed 1")["houses"][0]["follow_up"] is None


def test_it_lapses_by_the_existing_seven_day_rule_even_with_a_lower_check_present(rig):
    _check_at(rig, Urgency.URGENT, days_ago=12)
    _check_at(rig, Urgency.ROUTINE, days_ago=0)
    assert _status(rig, house="shed 1")["houses"][0]["follow_up"]["state"] == "lapsed"
    assert _item(rig) is None


# -- which check an answer attaches to ---------------
def test_an_answer_attaches_to_the_highest_urgency_open_check_not_the_newest(rig):
    urgent = _check_at(rig, Urgency.URGENT, days_ago=3)
    _check_at(rig, Urgency.WATCH, days_ago=1)  # newer, lower, its own follow-up not due yet
    first, _ = _ask_and_answer(rig, "worse")
    assert first["structuredContent"]["check_id"] == urgent


def test_among_checks_of_equal_urgency_the_newest_is_answered(rig):
    _check_at(rig, Urgency.WATCH, days_ago=5)
    newest = _check_at(rig, Urgency.WATCH, days_ago=4)
    first, _ = _ask_and_answer(rig, "worse")
    assert first["structuredContent"]["check_id"] == newest


def test_a_named_check_is_still_the_one_answered(rig):
    old = _check_at(rig, Urgency.URGENT, days_ago=3)
    _check_at(rig, Urgency.WATCH, days_ago=1)
    first, _ = _ask_and_answer(rig, "same", check_id=old)
    assert first["structuredContent"]["check_id"] == old
