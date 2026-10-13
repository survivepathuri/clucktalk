"""The farmer's own age-banded per-day limit on the farm status and the briefing.

Strictly MORE than his limit for the shed's age raises it to ALERT, with the vet line, and works with no history. The
existing alerts and their words never change; with no ``age_bands`` every answer is byte-identical to what it was."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from clucktalk.agents import demo_ai
from clucktalk.agents.briefing import BriefingRanker
from clucktalk.domain.daily_deaths import AgeBand, DailyDeathsRule
from clucktalk.domain.models import DailyRecord
from clucktalk.pilot import load_pilot_farm_file
from clucktalk.server.daily_deaths import RuleState
from clucktalk.server.farm_state import IST, PilotFarmSource
from clucktalk.server.tools.briefing import build_briefing
from clucktalk.server.tools.farm_status import build_status

PLACED = date(2026, 9, 21)
BANDS = (AgeBand(0, 29, 6), AgeBand(30, None, 3))
NOTE = "check the water and the shed today"
LIMIT = DailyDeathsRule(None, NOTE, False, BANDS)
SENTENCE = (
    "{n} birds died today, more than your own limit of {limit} a day at this age. "
    "By your own rule, take the birds to the vet today; do not wait for the next visit."
)
VET = "Please check the birds today and call your vet if deaths continue."


class Fixed:
    def __init__(self, rule=None, unreadable=False):
        self.state = RuleState(rule, unreadable)

    def current(self):
        return self.state


def make_source(tmp_path, age: int, today: int, base: int | None = 5, birds: int = 4000):
    """One 4000-bird shed placed 2026-09-21; ``base`` deaths on every earlier age (None: no history), ``today`` now."""
    path = tmp_path / "pilot_farm.json"
    path.write_text(
        json.dumps(
            {
                "feed_price_per_kg_inr": "40",
                "feed_price_label": "test",
                "simulated_live_bird_price_per_kg_inr": "90",
                "supplier_lead_days": 2,
                "houses": [
                    {"number": 1, "birds_placed": birds, "placed_on": PLACED.isoformat(), "deaths_before_pilot": 0}
                ],
            }
        ),
        encoding="utf-8",
    )
    day = PLACED + timedelta(days=age)
    source = PilotFarmSource(
        load_pilot_farm_file(path), clock=lambda: day, now=lambda: datetime(day.year, day.month, day.day, 8, tzinfo=IST)
    )
    if base is not None:
        for a in range(age):
            source.store.put_record(source.farm_id, "house-1", DailyRecord(PLACED + timedelta(days=a), base, 100.0))
    source.store.put_record(source.farm_id, "house-1", DailyRecord(day, today, 100.0))
    return source


def asked(source):
    ranker = BriefingRanker(source.store, demo_ai(), source.now)
    return (
        build_status(source, "shed one").model_dump(mode="json"),
        build_status(source, None).model_dump(mode="json"),
        build_briefing(source, ranker).model_dump(mode="json"),
    )


def codes(shed):
    return [f["code"] for f in shed["houses"][0]["findings"] if f["code"] != "no_reference_curve"]


@pytest.mark.parametrize(("age", "today", "limit"), [(20, 7, 6), (35, 4, 3), (29, 7, 6), (30, 4, 3)])
def test_more_than_his_limit_is_an_alert_with_his_sentence_and_the_vet_line(tmp_path, age, today, limit):
    source = make_source(tmp_path, age, today)
    off, _, _ = asked(source)
    assert off["level"] == "ok" and codes(off) == []  # today's behaviour: nothing
    source.deaths_rule = Fixed(LIMIT)
    on, whole, brief = asked(source)
    assert on["level"] == "alert" and codes(on) == ["daily_limit_exceeded"]
    assert on["houses"][0]["findings"][0]["level"] == "alert"
    assert on["houses"][0]["findings"][0]["values"] == {"deaths": today, "limit": limit, "age_days": age}
    sentence = SENTENCE.format(n=today, limit=limit)
    assert sentence in on["text_en"] and sentence in whole["text_en"]
    assert "doing well" not in on["text_en"] and "doing well" not in whole["text_en"]
    assert "needs attention now" in on["text_en"]
    assert "ఈరోజే" in on["text_te"] and "చనిపోయాయి" in on["text_te"]
    assert on["text_en"].count(VET) == 1 and whole["text_en"].count(VET) == 1  # the vet step is spoken once
    assert on["safety"] == {"level": "ALERT", "reason_codes": ["daily_limit_exceeded"], "vet_contact_advised": True}
    item = next(i for i in brief["items"] if i["category"] == "daily_limit_exceeded")
    assert item["level"] == "alert" and item["pinned"] is True and item["text_en"] == f"House 1: {sentence}"
    assert brief["level"] == "alert" and brief["safety"]["vet_contact_advised"] is True
    assert "daily_limit_exceeded" in brief["safety"]["reason_codes"] and brief["text_en"].count(VET) == 1


@pytest.mark.parametrize(("age", "today"), [(29, 6), (30, 3), (20, 6), (35, 3), (5, 0)])
def test_exactly_his_limit_or_less_changes_nothing(tmp_path, age, today):
    source = make_source(tmp_path, age, today)
    base = asked(source)
    source.deaths_rule = Fixed(LIMIT)
    assert asked(source) == base


def test_forty_deaths_with_no_history_is_an_alert_where_the_spike_rule_is_silent(tmp_path):
    source = make_source(tmp_path, 5, 40, base=None)
    off, _, _ = asked(source)
    assert off["level"] == "ok" and codes(off) == []
    source.deaths_rule = Fixed(LIMIT)
    on, _, brief = asked(source)
    assert on["level"] == "alert" and codes(on) == ["daily_limit_exceeded"]
    assert SENTENCE.format(n=40, limit=6) in on["text_en"] and on["safety"]["vet_contact_advised"] is True
    assert brief["level"] == "alert"


def test_a_spike_and_the_limit_on_the_same_day_keep_the_spike_first_and_unchanged(tmp_path):
    source = make_source(tmp_path, 15, 40)
    base_status, base_whole, base_brief = asked(source)
    assert codes(base_status) == ["mortality_spike"] and base_status["level"] == "alert"
    source.deaths_rule = Fixed(LIMIT)
    on, whole, brief = asked(source)
    assert codes(on) == ["mortality_spike", "daily_limit_exceeded"]
    assert on["houses"][0]["findings"][0] == base_status["houses"][0]["findings"][0]  # the spike is untouched
    spike_text = "40 birds died today, against about 5 a day this past week."
    assert spike_text in on["text_en"] and spike_text in whole["text_en"]
    assert SENTENCE.format(n=40, limit=6) in on["text_en"] and SENTENCE.format(n=40, limit=6) in whole["text_en"]
    assert on["text_en"].count(VET) == 1 and whole["text_en"].count(VET) == 1
    assert on["safety"]["reason_codes"] == ["mortality_spike", "daily_limit_exceeded"]
    cats = [i["category"] for i in brief["items"]]
    assert "mortality_spike" in cats and "daily_limit_exceeded" in cats
    spike_item = next(i for i in brief["items"] if i["category"] == "mortality_spike")
    assert spike_item == next(i for i in base_brief["items"] if i["category"] == "mortality_spike")
    assert brief["text_en"].count(VET) == 1


def test_the_limit_is_never_a_way_to_lower_a_level(tmp_path):
    for age, today in ((5, 3), (15, 40), (29, 7), (30, 4), (40, 9)):
        source = make_source(tmp_path, age, today)
        base = asked(source)
        source.deaths_rule = Fixed(LIMIT)
        on = asked(source)
        order = {"alert": 0, "watch": 1, "ok": 2}
        assert order[on[0]["level"]] <= order[base[0]["level"]]
        for f in base[0]["houses"][0]["findings"]:
            assert f in on[0]["houses"][0]["findings"], (age, today, f["code"])


def test_his_per_1000_rule_is_not_said_twice_when_the_limit_fires(tmp_path):
    both = DailyDeathsRule(Decimal("2"), NOTE, False, BANDS)
    source = make_source(tmp_path, 15, 12)
    source.deaths_rule = Fixed(both)
    on, _, brief = asked(source)
    assert codes(on) == ["daily_limit_exceeded"]
    assert on["text_en"].count("more than your own limit") == 1
    assert all(i["category"] != "daily_deaths_rule" for i in brief["items"])


def test_his_note_is_not_shown_when_the_limit_fires(tmp_path):
    source = make_source(tmp_path, 20, 7)
    source.deaths_rule = Fixed(LIMIT)
    on, whole, brief = asked(source)
    for out in (on, whole, brief):  # changed on purpose (Commit A): the note is never part of an answer
        assert NOTE not in out["text_en"] and "Your note" not in out["text_en"] and NOTE not in out["text_te"]
    assert VET in on["text_en"]  # the vet line is untouched


def test_no_bands_means_every_answer_is_identical(tmp_path):
    source = make_source(tmp_path, 15, 40)
    base = asked(source)
    source.deaths_rule = Fixed(DailyDeathsRule(None, None, False, ()))
    assert asked(source) == base
    source.deaths_rule = Fixed(None)
    assert asked(source) == base


def test_an_unreadable_rule_file_is_said_and_raises_nothing(tmp_path):
    source = make_source(tmp_path, 20, 7)
    source.deaths_rule = Fixed(None, unreadable=True)
    on, _, _ = asked(source)
    assert "I couldn't read your own daily deaths rule" in on["text_en"] and "daily_limit_exceeded" not in codes(on)
