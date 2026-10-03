"""Review finding M5 (Step 47C): an UNANSWERED follow-up of an urgent check or a suspected reportable disease, with no
confirmed vet handoff, does not lapse silently on day 8: it stays visible as ESCALATED (the existing reason code) until
an answer closes it, a vet handoff is confirmed, or a newer check of equal or higher urgency exists. A watch check's
follow-up keeps the 7-day lapse."""

from __future__ import annotations

from datetime import timedelta

import pytest

from clucktalk.domain.follow_up import (
    FOLLOW_UP_LAPSE_AFTER_DUE_DAYS,
    EscalationReason,
    FollowUpState,
    Outcome,
    due_after_days,
)
from clucktalk.domain.triage import Urgency
from tests.unit.test_follow_up_domain import CHECK_DAY, _answer, _check, _state

S, O = FollowUpState, Outcome  # noqa: E741
HIGH = (Urgency.URGENT, Urgency.NOTIFIABLE_SUSPECT)


def _lapse_day(urgency: Urgency) -> int:
    """The first day (after the check) on which the old rule said LAPSED."""
    return due_after_days(urgency) + FOLLOW_UP_LAPSE_AFTER_DUE_DAYS + 1


@pytest.mark.parametrize("urgency", HIGH)
def test_an_unanswered_urgent_or_reportable_follow_up_escalates_instead_of_lapsing(urgency):
    check = _check(urgency)
    day = CHECK_DAY + timedelta(days=_lapse_day(urgency))
    before = _state(check, today=day - timedelta(days=1))
    assert before.state is S.DUE  # unchanged: the last day it is still only asked about
    fup = _state(check, today=day)
    assert fup.state is S.ESCALATED and fup.reasons == (EscalationReason.REPORTABLE_WITHOUT_VET_HANDOFF,)
    assert fup.urgency is urgency and fup.outcome is None and fup.handed_off is False


@pytest.mark.parametrize("urgency", HIGH)
@pytest.mark.parametrize("extra_days", [0, 1, 6, 30, 365])
def test_it_stays_escalated_however_long_nobody_answers(urgency, extra_days):
    check = _check(urgency)
    fup = _state(check, today=CHECK_DAY + timedelta(days=_lapse_day(urgency) + extra_days))
    assert fup.state is S.ESCALATED


@pytest.mark.parametrize("urgency", [Urgency.WATCH])
def test_a_watch_follow_up_keeps_the_seven_day_lapse(urgency):
    check = _check(urgency)
    day = CHECK_DAY + timedelta(days=_lapse_day(urgency))
    assert _state(check, today=day).state is S.LAPSED
    assert _state(check, today=day + timedelta(days=400)).state is S.LAPSED


@pytest.mark.parametrize("urgency", HIGH)
def test_a_vet_handoff_ends_it(urgency):
    check = _check(urgency)
    day = CHECK_DAY + timedelta(days=_lapse_day(urgency) + 3)
    fup = _state(check, today=day, handed=[check.check_id])
    assert fup.state is not S.ESCALATED and fup.reasons == ()
    assert fup.state in (S.LAPSED, S.SUPERSEDED)  # handled by the handoff; never a fresh escalation


@pytest.mark.parametrize("urgency", HIGH)
def test_a_better_answer_closes_an_urgent_one_and_the_reportable_one_stays_for_the_vet(urgency):
    check = _check(urgency)
    day = CHECK_DAY + timedelta(days=_lapse_day(urgency) + 3)
    fup = _state(check, [_answer(check, O.BETTER)], today=day)
    if urgency is Urgency.NOTIFIABLE_SUSPECT:
        assert fup.state is S.ESCALATED and fup.reasons == (EscalationReason.REPORTABLE_WITHOUT_VET_HANDOFF,)
    else:
        assert fup.state is S.CLOSED and fup.reasons == ()


@pytest.mark.parametrize("said", [O.SAME, O.WORSE, O.NOT_SURE])
@pytest.mark.parametrize("urgency", HIGH)
def test_a_not_better_answer_still_escalates_with_its_own_reason(urgency, said):
    check = _check(urgency)
    day = CHECK_DAY + timedelta(days=_lapse_day(urgency) + 3)
    fup = _state(check, [_answer(check, said)], today=day)
    assert fup.state is S.ESCALATED and fup.outcome is said


@pytest.mark.parametrize("urgency", HIGH)
def test_a_newer_check_of_equal_or_higher_urgency_takes_it_over_but_a_lower_one_does_not(urgency):
    check = _check(urgency)
    day = CHECK_DAY + timedelta(days=_lapse_day(urgency) + 2)
    lower = _check(Urgency.ROUTINE, day=day - timedelta(days=1))
    same = _check(urgency, day=day - timedelta(days=1))
    assert _state(check, today=day, others=[lower, check]).state is S.ESCALATED
    assert _state(check, today=day, others=[same, check]).state is S.SUPERSEDED


@pytest.mark.parametrize("urgency", HIGH)
def test_before_the_lapse_day_nothing_changes(urgency):
    check = _check(urgency)
    for days in range(0, _lapse_day(urgency)):
        state = _state(check, today=CHECK_DAY + timedelta(days=days)).state
        assert state in (S.SCHEDULED, S.DUE), days
