"""Daily Briefing facts for the follow-up (docs/DESIGN.md §18): an escalated follow-up still shows when the
briefing's own health-check rule hid its check, it replaces that shed's open health-check item (never a duplicate),
it is never lower in priority than the check was, and a due unanswered follow-up is a pinned question. Pure
functions, hand-built houses; the number of days since the check comes from the date passed in."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime

import pytest

from clucktalk.domain.briefing import (
    HEALTH_CATEGORIES,
    NOTIFIABLE_SEVERITY,
    URGENT_CHECK_SEVERITY,
    Category,
    Fact,
    collect_facts,
    fingerprint,
    rules_order,
)
from clucktalk.domain.follow_up import (
    EscalationReason,
    FollowUp,
    FollowUpAnswer,
    FollowUpState,
    Outcome,
    follow_up_state,
    new_answer_id,
)
from clucktalk.domain.models import DailyRecord, House, HouseKind
from clucktalk.domain.status import Level
from clucktalk.domain.triage import CheckStatus, Floor, HealthCheck, TriageInput, TriageResult, Urgency, new_check_id
from tests.unit.helpers import D0, farm_with

IST = timezone(timedelta(hours=5, minutes=30))
AS_OF = D0 + timedelta(days=14)
S = FollowUpState


def _house(number: int = 1, days: int = 20) -> House:
    records = tuple(DailyRecord(D0 + timedelta(days=i), 1, 30.0) for i in range(days))
    return House(f"house-{number}", number, HouseKind.BROILER, "Ross 308", D0, 1000, 0, 100_000.0, records)


def _check(urgency: Urgency, day_offset: int, house_id: str = "house-1") -> HealthCheck:
    at = datetime.combine(D0 + timedelta(days=day_offset), dtime(10, 0), tzinfo=IST)
    inp = TriageInput(
        house_id, "House 1", "షెడ్ 1", "Ross 308", 10, 900, (), None, None, None, None, None, False, None, None
    )
    result = TriageResult(urgency, (), ("x",), "rules", None, None)
    return HealthCheck(
        new_check_id(), "farm-test", house_id, at, CheckStatus.READY, inp, Floor(urgency, ()), result, at
    )


def _said(check: HealthCheck, said: Outcome, day_offset: int) -> FollowUpAnswer:
    at = datetime.combine(D0 + timedelta(days=day_offset), dtime(11, 0), tzinfo=IST)
    return FollowUpAnswer(
        new_answer_id(), "farm-test", check.house_id, check.check_id, said, False, "prop_" + "a" * 16, at
    )


def _fup(check: HealthCheck, answers=(), as_of: date = AS_OF, others=(), house: House | None = None) -> FollowUp:
    return follow_up_state(check, tuple(answers), frozenset(), house or _house(), as_of, tuple(others) or (check,))


def _facts(house: House, as_of: date, *, latest=None, recent=(), follow_up=None) -> dict[str, Fact]:
    checks = {} if latest is None else {house.house_id: latest}
    recents = {house.house_id: tuple(recent)} if recent else {}
    ups = None if follow_up is None else {house.house_id: follow_up}
    return {f.fact_id: f for f in collect_facts(farm_with(house), as_of, checks, frozenset(), recents, follow_ups=ups)}


# -- an escalated follow-up still shows when the briefing hid its check ----------------------------------------------
def test_an_escalated_follow_up_shows_when_a_newer_lower_check_is_the_one_the_briefing_shows():
    old = _check(Urgency.URGENT, 11)  # three days before AS_OF
    newer = _check(Urgency.WATCH, 13)  # lower in urgency: it does not replace the older follow-up
    fup = _fup(old, [_said(old, Outcome.WORSE, 12)], others=[old, newer])
    assert fup.state is S.ESCALATED
    house = _house()
    without = _facts(house, AS_OF, latest=newer, recent=[newer, old])
    assert "open_health_check:house-1" in without and "follow_up:house-1" not in without  # what the briefing showed
    with_it = _facts(house, AS_OF, latest=newer, recent=[newer, old], follow_up=fup)
    f = with_it["follow_up:house-1"]
    assert f.pinned and f.level is Level.ALERT and f.category is Category.FOLLOW_UP and f.house_id == "house-1"
    assert "open_health_check:house-1" not in with_it  # it replaces that shed's open health-check item


def test_an_escalated_follow_up_shows_when_the_check_is_too_old_for_the_briefings_own_rule():
    old = _check(Urgency.WATCH, 9)  # five days before AS_OF: older than the briefing's own three days for a check
    fup = _fup(old, [_said(old, Outcome.SAME, 12)])
    assert fup.state is S.ESCALATED
    house = _house()
    assert "open_health_check:house-1" not in _facts(house, AS_OF, latest=old, recent=[old])
    f = _facts(house, AS_OF, latest=old, recent=[old], follow_up=fup)["follow_up:house-1"]
    assert f.values["days_ago"] == 5 and f.values["state"] == "escalated"


def test_an_escalated_follow_up_replaces_the_open_check_item_it_belongs_to_with_no_duplicate():
    check = _check(Urgency.URGENT, 12)  # two days ago: the briefing would show it as an open check
    fup = _fup(check, [_said(check, Outcome.WORSE, 13)])
    house = _house()
    assert "open_health_check:house-1" in _facts(house, AS_OF, latest=check, recent=[check])
    facts = _facts(house, AS_OF, latest=check, recent=[check], follow_up=fup)
    assert "follow_up:house-1" in facts and "open_health_check:house-1" not in facts
    assert (
        len([i for i in facts if i.endswith(":house-1") and i.split(":")[0] in ("open_health_check", "follow_up")]) == 1
    )


@pytest.mark.parametrize(
    ("urgency", "expected"),
    [
        (Urgency.NOTIFIABLE_SUSPECT, NOTIFIABLE_SEVERITY),
        (Urgency.URGENT, URGENT_CHECK_SEVERITY),
        (Urgency.WATCH, URGENT_CHECK_SEVERITY),
    ],
)
def test_an_escalated_follow_up_is_never_lower_in_priority_than_its_check(urgency, expected):
    check = _check(urgency, 11)
    fup = _fup(check, [_said(check, Outcome.WORSE, 12)])
    f = _facts(_house(), AS_OF, latest=check, recent=[check], follow_up=fup)["follow_up:house-1"]
    assert f.severity == expected and f.level is Level.ALERT


def test_an_escalated_follow_up_is_never_lower_than_the_open_check_item_it_replaces():
    shown = _check(Urgency.NOTIFIABLE_SUSPECT, 13)  # the item the briefing would show (severity 4)
    made_up = FollowUp(  # a watch-level escalation beside it (the domain rules cannot make this; the floor must hold)
        S.ESCALATED, "chk_" + "1" * 16, Urgency.WATCH, D0 + timedelta(days=12), Outcome.WORSE,
        (EscalationReason.SAID_WORSE,), None, False, D0 + timedelta(days=11),
    )  # fmt: skip
    f = _facts(_house(), AS_OF, latest=shown, recent=[shown], follow_up=made_up)["follow_up:house-1"]
    assert f.severity == NOTIFIABLE_SEVERITY


def test_the_follow_up_fact_is_a_health_fact_pinned_above_the_rest():
    assert Category.FOLLOW_UP in HEALTH_CATEGORIES
    check = _check(Urgency.WATCH, 11)
    fup = _fup(check, [_said(check, Outcome.NOT_SURE, 12)])
    facts = collect_facts(farm_with(_house()), AS_OF, {}, frozenset(), {}, follow_ups={"house-1": fup})
    assert facts[0].category is Category.FOLLOW_UP and facts[0].pinned
    assert rules_order(facts)[0].fact_id == "follow_up:house-1"


# -- a due, unanswered follow-up is a pinned question ----------------------------------------------
def test_a_due_unanswered_follow_up_is_a_pinned_question_for_that_shed():
    check = _check(Urgency.WATCH, 11)  # due three days after: AS_OF
    fup = _fup(check)
    assert fup.state is S.DUE
    f = _facts(_house(), AS_OF, latest=check, recent=[check], follow_up=fup)["follow_up:house-1"]
    assert f.pinned and f.level is Level.WATCH and f.severity == int(Level.WATCH)
    assert f.values == {"state": "due", "urgency": "watch", "days_ago": 3}


def test_a_due_follow_up_on_an_urgent_check_keeps_the_checks_own_level_and_priority():
    check = _check(Urgency.URGENT, 12)
    fup = _fup(check)
    assert fup.state is S.DUE
    f = _facts(_house(), AS_OF, latest=check, recent=[check], follow_up=fup)["follow_up:house-1"]
    assert f.level is Level.ALERT and f.severity == URGENT_CHECK_SEVERITY and f.values["urgency"] == "urgent"
    notifiable = _check(Urgency.NOTIFIABLE_SUSPECT, 12)
    g = _facts(_house(), AS_OF, latest=notifiable, recent=[notifiable], follow_up=_fup(notifiable))["follow_up:house-1"]
    assert g.severity == NOTIFIABLE_SEVERITY


def test_a_due_follow_up_replaces_the_open_check_item_even_after_the_briefing_stopped_showing_that_check():
    check = _check(Urgency.WATCH, 8)  # six days ago, still due (lapses after seven more days from day 3)
    fup = _fup(check)
    assert fup.state is S.DUE
    house = _house()
    assert "open_health_check:house-1" not in _facts(house, AS_OF, latest=check, recent=[check])
    assert "follow_up:house-1" in _facts(house, AS_OF, latest=check, recent=[check], follow_up=fup)


def test_the_days_since_the_check_come_from_the_date_passed_in_never_typed():
    check = _check(Urgency.WATCH, 8)
    house = _house()
    for offset in (14, 15, 16, 17):
        as_of = D0 + timedelta(days=offset)
        fup = _fup(check, as_of=as_of)
        f = _facts(house, as_of, latest=check, recent=[check], follow_up=fup)["follow_up:house-1"]
        assert f.values["days_ago"] == offset - 8


@pytest.mark.parametrize("case", ["closed", "lapsed", "superseded", "none"])
def test_other_states_add_no_follow_up_fact(case):
    check = _check(Urgency.WATCH, 13)
    as_of, answers, others = AS_OF, [], [check]
    if case == "closed":
        answers = [_said(check, Outcome.BETTER, 14)]
    elif case == "lapsed":  # due on day 5, still asked until day 12: day 15 is past it
        check, as_of = _check(Urgency.WATCH, 2), D0 + timedelta(days=15)
        others = [check]
    elif case == "superseded":
        others = [check, _check(Urgency.ROUTINE, 14)]
    elif case == "none":
        check = replace(check, status=CheckStatus.ANALYZING, result=None)
        others = [check]
    fup = _fup(check, answers, as_of=as_of, others=others)
    assert fup.state is S(case)
    assert "follow_up:house-1" not in _facts(_house(), as_of, latest=check, recent=[check], follow_up=fup)


def test_a_follow_up_that_is_not_yet_due_adds_nothing():
    check = _check(Urgency.WATCH, 13)  # due on day 16; AS_OF is day 14
    fup = _fup(check)
    assert fup.state is S.SCHEDULED
    assert "follow_up:house-1" not in _facts(_house(), AS_OF, latest=check, recent=[check], follow_up=fup)


# -- nothing else changes --------------------------------------------------------------------------
def test_without_follow_ups_the_facts_are_exactly_what_they_were():
    check = _check(Urgency.URGENT, 12)
    house = _house()
    plain = collect_facts(farm_with(house), AS_OF, {"house-1": check}, frozenset(), {"house-1": (check,)})
    empty = collect_facts(
        farm_with(house), AS_OF, {"house-1": check}, frozenset(), {"house-1": (check,)}, follow_ups={}
    )
    none = collect_facts(
        farm_with(house), AS_OF, {"house-1": check}, frozenset(), {"house-1": (check,)}, follow_ups=None
    )
    assert plain == empty == none and any(f.category is Category.OPEN_HEALTH_CHECK for f in plain)


def test_a_follow_up_for_one_shed_leaves_another_sheds_facts_alone():
    one, two = _house(1), _house(2)
    check = _check(Urgency.WATCH, 11)
    fup = _fup(check, [_said(check, Outcome.WORSE, 12)])
    farm = farm_with(one, two)
    with_it = {f.fact_id for f in collect_facts(farm, AS_OF, {}, frozenset(), {}, follow_ups={"house-1": fup})}
    without = {f.fact_id for f in collect_facts(farm, AS_OF, {}, frozenset(), {})}
    assert with_it - without == {"follow_up:house-1"} and without - with_it == set()


def test_the_fingerprint_changes_when_the_follow_up_state_changes():
    check = _check(Urgency.WATCH, 11)
    house = _house()
    due = collect_facts(farm_with(house), AS_OF, {}, frozenset(), {}, follow_ups={"house-1": _fup(check)})
    worse = _fup(check, [_said(check, Outcome.WORSE, 13)])
    esc = collect_facts(farm_with(house), AS_OF, {}, frozenset(), {}, follow_ups={"house-1": worse})
    assert fingerprint(due) != fingerprint(esc)


def test_no_fact_value_carries_the_internal_word_superseded():
    check = _check(Urgency.URGENT, 11)
    fup = _fup(check, [_said(check, Outcome.WORSE, 12)])
    for f in collect_facts(farm_with(_house()), AS_OF, {}, frozenset(), {}, follow_ups={"house-1": fup}):
        assert "superseded" not in str(f.values)
