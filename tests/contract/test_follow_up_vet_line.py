"""Session 5 review finding H4 (docs/DESIGN.md §18): every not-better outcome (worse, the same, not sure, or "better"
recorded as not better because of a death spike) ends with "To be safe, contact your vet or doctor.": in the read-back
and after the "yes", even after a vet handoff and even when a newer check of equal or higher urgency exists. "Done."
alone is never spoken for a not-better outcome."""

from __future__ import annotations

import pytest

from clucktalk.agents.model import RulesModel
from clucktalk.domain.triage import Urgency
from tests.contract.test_follow_up_surfaces import _advance, _handoff
from tests.contract.test_follow_up_tools import (
    DONE,
    OFFER,
    TO_BE_SAFE,
    _ask_and_answer,
    _log_spike,
    _store_check,
    _stored_check,
)
from tests.contract.test_health_tools import _rig

NOT_BETTER = ["worse", "same", "not_sure"]


@pytest.fixture
def rig():
    yield from _rig(RulesModel())


def _plain(rig) -> None:
    _stored_check(rig)  # a watch check three days ago: due today


def _after_handoff(rig) -> None:
    _stored_check(rig, days_ago=3, urgency=Urgency.URGENT)
    _handoff(rig)
    _advance(rig, 5)


def _newer_equal_check_after_handoff(rig) -> None:
    _stored_check(rig, days_ago=3, urgency=Urgency.URGENT)
    _handoff(rig)
    _store_check(rig.source, days_ago=0, urgency=Urgency.URGENT)  # a newer check of equal urgency, today
    _advance(rig, 5)


def _newer_higher_check_after_handoff(rig) -> None:
    _stored_check(rig, days_ago=3, urgency=Urgency.URGENT)
    _handoff(rig)
    _store_check(rig.source, days_ago=0, urgency=Urgency.NOTIFIABLE_SUSPECT)  # a newer, higher check, today
    _advance(rig, 5)


SCENARIOS = {
    "plain": _plain,
    "after_handoff": _after_handoff,
    "newer_equal_check": _newer_equal_check_after_handoff,
    "newer_higher_check": _newer_higher_check_after_handoff,
}


@pytest.mark.parametrize("scenario", list(SCENARIOS))
@pytest.mark.parametrize("outcome", NOT_BETTER)
def test_a_not_better_outcome_always_ends_with_the_vet_line_read_back_and_saved(rig, scenario, outcome):
    SCENARIOS[scenario](rig)
    first, second = _ask_and_answer(rig, outcome)
    ask, done = first["structuredContent"], second["structuredContent"]
    assert TO_BE_SAFE in ask["text_en"], ask["text_en"]
    assert done["status"] == "changed"
    assert TO_BE_SAFE in done["text_en"], done["text_en"]
    assert done["text_en"] != DONE, "'Done.' alone is never spoken for a not-better outcome"
    assert done["text_en"].startswith(DONE) and done["text_en"].index(TO_BE_SAFE) > 0
    assert done["text_te"] != done["text_en"]


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_the_vet_line_is_spoken_again_when_the_yes_is_repeated(rig, scenario):
    SCENARIOS[scenario](rig)
    first, second = _ask_and_answer(rig, "worse")
    pid = first["structuredContent"]["proposal_id"]
    again = rig.call("report_health_follow_up", house="shed 1", outcome="worse", proposal_id=pid, answer="yes")
    sc = again["structuredContent"]
    assert sc["replayed"] is True
    assert TO_BE_SAFE in sc["text_en"] and sc["text_en"] != DONE


def test_a_second_handoff_is_still_never_offered_but_the_vet_line_is_spoken(rig):
    _after_handoff(rig)
    _, second = _ask_and_answer(rig, "worse")
    sc = second["structuredContent"]
    assert sc["handoff_offered"] is False and OFFER not in sc["text_en"]
    assert TO_BE_SAFE in sc["text_en"]


def test_better_recorded_as_not_better_because_of_a_spike_still_gets_the_vet_line(rig):
    _stored_check(rig)
    _log_spike(rig)
    first, second = _ask_and_answer(rig, "better")
    assert TO_BE_SAFE in first["structuredContent"]["text_en"]
    assert TO_BE_SAFE in second["structuredContent"]["text_en"]
    assert second["structuredContent"]["text_en"] != DONE


def test_a_plain_better_gets_no_vet_line(rig):
    _plain(rig)
    first, second = _ask_and_answer(rig, "better")
    assert TO_BE_SAFE not in first["structuredContent"]["text_en"]
    assert second["structuredContent"]["text_en"] == DONE


def test_a_better_after_a_handoff_only_closes_and_gets_no_vet_line(rig):
    _after_handoff(rig)
    _, second = _ask_and_answer(rig, "better")
    assert second["structuredContent"]["text_en"] == DONE


def test_a_no_to_the_read_back_saves_nothing_and_does_not_say_done(rig):
    _after_handoff(rig)
    first, second = _ask_and_answer(rig, "worse", answer="no")
    assert second["structuredContent"]["status"] == "cancelled"
    assert DONE not in second["structuredContent"]["text_en"]
