"""The numbers on the follow-up cards are the spoken numbers (docs/DESIGN.md §6, §14, §18).

The cards show the sentence the voice says, taken verbatim from structuredContent (no arithmetic on the card; see
tests/unit/test_cards_follow_up.py). So this file proves the data side: for every state the card can show, the
sentence the card prints is the sentence inside the spoken answer, and its days-since number is the real number of
days and the same number the briefing item and the status field carry."""

from __future__ import annotations

import re

import pytest

from clucktalk.agents.model import RulesModel
from clucktalk.domain.triage import Urgency
from tests.contract.test_follow_up_surfaces import (
    _ask_and_answer,
    _brief,
    _item,
    _status,
    _store_check,
    _stored_check,
)
from tests.contract.test_health_tools import _rig


@pytest.fixture
def rig():
    yield from _rig(RulesModel())


DAYS = re.compile(r"\b(\d+) days?\b")


def _days_in(sentence: str) -> int:
    (found,) = DAYS.findall(sentence)
    return int(found)


def _make_due(rig):
    _stored_check(rig)


def _make_escalated(rig):
    _stored_check(rig)
    _ask_and_answer(rig, "worse")


def _make_lapsed(rig):
    _store_check(rig.source, days_ago=12, urgency=Urgency.WATCH)


@pytest.mark.parametrize(
    ("make", "state", "days"), [(_make_due, "due", 3), (_make_escalated, "escalated", 3), (_make_lapsed, "lapsed", 12)]
)
def test_the_status_chip_prints_the_spoken_sentence_and_its_number_is_the_real_days(rig, make, state, days):
    make(rig)
    sc = _status(rig, house="shed 1")
    fu = sc["houses"][0]["follow_up"]
    assert fu["state"] == state and fu["text_en"] and fu["text_te"]
    assert fu["text_en"] in sc["text_en"]  # what the chip prints is what is spoken
    assert _days_in(fu["text_en"]) == fu["days_ago"] == days
    assert str(days) in fu["text_te"]  # the Telugu sentence carries the same number


@pytest.mark.parametrize(("make", "state", "days"), [(_make_due, "due", 3), (_make_escalated, "escalated", 3)])
def test_the_briefing_slide_prints_the_item_sentence_and_its_number_is_the_real_days(rig, make, state, days):
    make(rig)
    sc = _brief(rig)
    item = _item(sc, "follow_up:house-1")
    assert item is not None and item["category"] == "follow_up" and item["values"]["state"] == state
    assert _days_in(item["text_en"]) == item["values"]["days_ago"] == days
    assert str(days) in item["text_te"]
    # the same sentence the status chip prints for that shed
    status_fu = _status(rig, house="shed 1")["houses"][0]["follow_up"]
    assert status_fu["text_en"] == item["text_en"] and status_fu["text_te"] == item["text_te"]
    if item["spoken"]:
        assert item["text_en"] in sc["text_en"]


def test_the_card_text_for_a_shed_without_a_chip_has_no_follow_up_field_value(rig):
    sc = _status(rig)
    assert all(h["follow_up"] is None for h in sc["houses"])
