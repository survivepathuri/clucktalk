"""Session 5 review finding H3, approved 2026-10-01 (docs/DESIGN.md §18): a follow-up for an URGENT check or a
suspected reportable disease stays visible until it is closed by "better" (under the existing safety conditions), a
newer check of EQUAL or HIGHER urgency exists on that house, the vet handoff for that check is confirmed, or it lapses
by the existing 7-day rule. A newer LOWER-urgency check never hides it, on the briefing or on the farm status. The
domain rule (``follow_up_state``) and the briefing rule (``_check_to_show``) change together and are tested together."""

from __future__ import annotations

from datetime import timedelta

import pytest

from clucktalk.domain.briefing import _check_to_show
from clucktalk.domain.follow_up import FOLLOW_UP_AFTER_URGENT_DAYS, FOLLOW_UP_LAPSE_AFTER_DUE_DAYS
from clucktalk.domain.triage import Urgency
from tests.unit.test_follow_up_domain import CHECK_DAY, O, S, _answer, _check, _state

HIGH = (Urgency.URGENT, Urgency.NOTIFIABLE_SUSPECT)
LOWER = {
    Urgency.URGENT: (Urgency.ROUTINE, Urgency.WATCH),
    Urgency.NOTIFIABLE_SUSPECT: (Urgency.ROUTINE, Urgency.WATCH, Urgency.URGENT),
}
DUE = CHECK_DAY + timedelta(days=FOLLOW_UP_AFTER_URGENT_DAYS)
LAPSED = DUE + timedelta(days=FOLLOW_UP_LAPSE_AFTER_DUE_DAYS + 1)


@pytest.mark.parametrize("urgency", HIGH)
def test_a_newer_lower_check_never_hides_a_due_follow_up(urgency):
    old = _check(urgency)
    for lower in LOWER[urgency]:
        newer = _check(lower, day=CHECK_DAY + timedelta(days=1))
        assert _state(old, today=DUE + timedelta(days=1), others=[old, newer]).state is S.DUE, lower


def test_a_newer_lower_check_never_hides_an_urgent_follow_up_that_is_scheduled_or_lapsed():
    old = _check(Urgency.URGENT)
    newer = _check(Urgency.ROUTINE, day=CHECK_DAY, hour=11)
    assert _state(old, today=CHECK_DAY, others=[old, newer]).state is S.SCHEDULED
    assert _state(old, today=LAPSED, others=[old, newer]).state is S.LAPSED


@pytest.mark.parametrize("urgency", HIGH)
def test_a_newer_check_of_equal_or_higher_urgency_does_hide_it(urgency):
    old = _check(urgency)
    for level in (u for u in Urgency if u >= urgency):
        newer = _check(level, day=CHECK_DAY + timedelta(days=1))
        fup = _state(old, today=DUE + timedelta(days=1), others=[old, newer])
        # a reportable suspect keeps its own rule: only a newer reportable suspect that is not yet handed to a vet
        assert fup.state is S.SUPERSEDED, (urgency, level)


def test_an_urgent_follow_up_closed_by_better_is_closed_and_the_vet_handoff_ends_it():
    old = _check(Urgency.URGENT)
    newer = _check(Urgency.ROUTINE, day=CHECK_DAY + timedelta(days=1))
    today = DUE + timedelta(days=1)
    assert _state(old, [_answer(old, O.BETTER)], today=today, others=[old, newer]).state is S.CLOSED
    assert _state(old, today=today, handed=[old.check_id], others=[old, newer]).state is S.SUPERSEDED


def test_a_watch_follow_up_is_still_replaced_by_any_newer_check():
    old = _check(Urgency.WATCH)
    newer = _check(Urgency.ROUTINE, day=CHECK_DAY + timedelta(days=1))
    assert _state(old, today=CHECK_DAY + timedelta(days=4), others=[old, newer]).state is S.SUPERSEDED


def test_an_urgent_answer_after_a_lower_check_is_taken_as_worse_and_escalates():
    old = _check(Urgency.URGENT)
    newer = _check(Urgency.ROUTINE, day=CHECK_DAY + timedelta(days=1))
    fup = _state(old, [_answer(old, O.WORSE)], today=DUE + timedelta(days=2), others=[old, newer])
    assert fup.state is S.ESCALATED and fup.urgency is Urgency.URGENT


# -- the briefing's own rule: on the day of the check (before the follow-up is due) a newer lower check hides nothing --
@pytest.mark.parametrize("lower", [Urgency.ROUTINE, Urgency.WATCH])
def test_the_briefing_still_shows_an_urgent_check_made_earlier_today_after_a_newer_lower_check(lower):
    urgent = _check(Urgency.URGENT, hour=9)
    newer = _check(lower, hour=11)
    shown = _check_to_show(CHECK_DAY, newer, [newer, urgent], frozenset())
    assert shown is not None and shown.check_id == urgent.check_id


def test_the_briefing_shows_the_newer_check_when_it_is_urgent_too_and_the_old_one_is_not_urgent():
    urgent_old = _check(Urgency.URGENT, hour=9)
    urgent_new = _check(Urgency.URGENT, hour=11)
    assert _check_to_show(CHECK_DAY, urgent_new, [urgent_new, urgent_old], frozenset()).check_id == urgent_new.check_id
    watch_old = _check(Urgency.WATCH, hour=9)
    assert _check_to_show(CHECK_DAY, urgent_new, [urgent_new, watch_old], frozenset()).check_id == urgent_new.check_id
    routine_new = _check(Urgency.ROUTINE, hour=11)
    assert _check_to_show(CHECK_DAY, routine_new, [routine_new, watch_old], frozenset()) is None  # watch: unchanged


def test_the_briefing_stops_showing_the_urgent_check_after_three_days_like_any_other():
    urgent = _check(Urgency.URGENT, hour=9)
    newer = _check(Urgency.ROUTINE, hour=11)
    later = CHECK_DAY + timedelta(days=4)
    assert _check_to_show(later, newer, [newer, urgent], frozenset()) is None


def test_a_newer_reportable_check_already_handed_to_a_vet_takes_an_older_urgent_check_over():
    """The follow-up says SUPERSEDED for it (a newer check of higher urgency); the briefing must say the same."""
    urgent = _check(Urgency.URGENT, hour=9)
    reportable = _check(Urgency.NOTIFIABLE_SUSPECT, hour=11)
    handed = frozenset([reportable.check_id])
    assert _check_to_show(CHECK_DAY, reportable, [reportable, urgent], handed) is None
    assert _state(urgent, today=DUE, others=[urgent, reportable]).state is S.SUPERSEDED
