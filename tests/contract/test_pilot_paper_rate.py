"""The pilot farm with no verified growth standard (placeholder breed "flock"): the farmer's own price rule, and a quiet
limitation. Everything here is what the FARMER can see; developer-facing data may keep the technical reason."""

from __future__ import annotations

import copy
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from clucktalk.agents import AiServices
from clucktalk.agents.model import RulesModel
from clucktalk.pilot import parse_pilot_farm
from clucktalk.server.farm_state import IST, PilotFarmSource
from tests.contract.conftest import _start
from tests.contract.test_health_tools import ManualRunner

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = json.loads((ROOT / "docs" / "pilot_farm.example.json").read_text(encoding="utf-8"))
TODAY = date(2026, 10, 9)
NOW = datetime(2026, 10, 9, 8, 0, tzinfo=IST)
BANNED = ("verified growth standard", "flock target", "flock", "Simulated", "simulated")
FEED_LINE_EN = "Feed planning is not part of this pilot yet."
FEED_LINE_TE = "ఈ పైలట్ లో ఫీడ్ లెక్క ఇంకా లేదు."
ASK_EN = "Tell me today's paper rate, like: paper rate 160, and I will work out your price."
BAD_RATE_EN = "That paper rate does not look right. Tell me today's paper rate in rupees per kg, like: paper rate 160."


def make(delta="20", drop_simulated=True, **house_changes):
    data = copy.deepcopy(EXAMPLE)
    if delta is None:
        data.pop("sale_price_below_paper_rate_inr", None)
    else:
        data["sale_price_below_paper_rate_inr"] = delta
    if drop_simulated and delta is not None:
        data.pop("simulated_live_bird_price_per_kg_inr")
    for house in data["houses"]:
        house.update(house_changes)
    source = PilotFarmSource(parse_pilot_farm(data), clock=lambda: TODAY, now=lambda: NOW)
    srv, stop = _start({}, source=source, ai=AiServices(model=RulesModel(), budget=None, runner=ManualRunner()))
    sid, _ = srv.initialize()

    class P:
        pass

    p = P()
    p.source = source

    def call(name, **args):
        return srv.call(sid, "tools/call", {"name": name, "arguments": args})["result"]

    p.call, p.stop = call, stop
    return p


@pytest.fixture
def pilot():
    p = make()
    yield p
    p.stop()


def texts(result):
    sc = result["structuredContent"]
    return sc["text_en"], sc["text_te"]


def assert_quiet(*strings):
    for s in strings:
        for word in BANNED:
            assert word not in s, (word, s)


def test_paper_rate_160_gives_the_farmers_price_140_in_both_languages(pilot):
    en, te = texts(pilot.call("plan_sale", live_price_per_kg=160))
    assert "Your price today: ₹140 per kg (paper rate ₹160 minus ₹20, your own rule)." in en
    assert "₹140" in te and "₹160" in te and "₹20" in te
    assert_quiet(en, te)


def test_a_single_shed_question_with_the_rate_gives_the_same_line(pilot):
    en, _ = texts(pilot.call("plan_sale", house="shed 1", live_price_per_kg=160))
    assert "Your price today: ₹140 per kg (paper rate ₹160 minus ₹20, your own rule)." in en


def test_a_decimal_paper_rate_keeps_its_paise(pilot):
    en, _ = texts(pilot.call("plan_sale", live_price_per_kg=161.5))
    assert "Your price today: ₹141.50 per kg (paper rate ₹161.50 minus ₹20, your own rule)." in en


def test_no_rate_stated_asks_once_and_shows_no_number(pilot):
    for args in ({}, {"house": "shed 2"}):
        en, te = texts(pilot.call("plan_sale", **args))
        assert ASK_EN in en and "₹" not in en
        assert te and "₹" not in te
        assert_quiet(en, te)


def test_a_paper_rate_not_above_the_delta_never_shows_a_price(pilot):
    en, _ = texts(pilot.call("plan_sale", live_price_per_kg=20))
    assert ASK_EN in en and "Your price today" not in en


def test_the_ask_line_gives_an_example_in_both_languages_that_the_typed_matchers_accept(pilot):
    from clucktalk.simulator.intents import match
    from clucktalk.simulator.intents_te import match_te

    en, te = texts(pilot.call("plan_sale"))
    assert "paper rate 160" in en and "పేపర్ రేటు 160" in te
    assert match("paper rate 160").arguments == {"live_price_per_kg": 160.0}
    assert match_te("ఈరోజు పేపర్ రేటు 160").intent.arguments == {"live_price_per_kg": 160.0}


@pytest.mark.parametrize("rate", [0.5, 1001, 5000, 100000])  # 0 and below: the tool schema refuses (gt=0)
def test_a_rate_outside_1_to_1000_gets_one_short_line_never_a_price(pilot, rate):
    en, te = texts(pilot.call("plan_sale", live_price_per_kg=rate))
    assert BAD_RATE_EN in en and "Your price today" not in en and "₹" not in en
    assert te and "₹" not in te
    assert_quiet(en, te)


@pytest.mark.parametrize(("rate", "shown"), [(21, "₹21"), (1000, "₹1,000")])
def test_the_ends_of_the_range_are_accepted(pilot, rate, shown):
    en, _ = texts(pilot.call("plan_sale", live_price_per_kg=rate))
    assert f"paper rate {shown} minus ₹20" in en


def test_typed_phrases_end_to_end_give_his_price(pilot):
    from clucktalk.simulator.intents import match
    from clucktalk.simulator.intents_te import match_te

    intents = [match(t) for t in ("paper rate 160", "today paper rate is 160", "sell, paper rate 160")]
    intents += [match_te(t).intent for t in ("ఈరోజు పేపర్ రేటు 160", "పేపర్ రేట్ 160", "రేటు 160 ఉంది")]
    for intent in intents:
        assert intent is not None and intent.tool == "plan_sale"
        en, te = texts(pilot.call(intent.tool, **intent.arguments))
        assert "Your price today: ₹140 per kg (paper rate ₹160 minus ₹20, your own rule)." in en
        assert_quiet(en, te)


def test_without_the_delta_field_the_sale_answer_is_the_quiet_limitation_not_a_price():
    p = make(delta=None)
    try:
        for args in ({}, {"live_price_per_kg": 160}, {"live_price_per_kg": 5000}):
            en, te = texts(p.call("plan_sale", **args))
            assert "Your price today" not in en and "₹140" not in en
            assert "Sale planning is not part of this pilot yet." in en and BAD_RATE_EN not in en
            assert_quiet(en, te)
    finally:
        p.stop()


def test_a_direct_feed_question_gets_one_plain_line(pilot):
    for args in ({}, {"house": "shed 1"}):
        en, te = texts(pilot.call("plan_feed", **args))
        assert FEED_LINE_EN in en and FEED_LINE_TE in te
        assert en.count(FEED_LINE_EN) == 1, en
        assert_quiet(en, te)


def log_deaths(pilot, house, deaths):
    first = pilot.call("log_daily_record", house=house, deaths=deaths)["structuredContent"]
    done = pilot.call("log_daily_record", house=house, deaths=deaths, proposal_id=first["proposal_id"], answer="yes")
    assert done["structuredContent"]["status"] == "changed", done


def test_status_and_briefing_say_nothing_about_the_missing_growth_standard(pilot):
    log_deaths(pilot, "shed 1", 1)
    log_deaths(pilot, "shed 2", 1)
    for args in ({}, {"house": "shed 1"}):
        status = pilot.call("get_farm_status", **args)
        assert_quiet(*texts(status))
        findings = [f for h in status["structuredContent"]["houses"] for f in h["findings"]]
        assert "no_reference_curve" not in [f["code"] for f in findings]
    assert_quiet(*texts(pilot.call("get_daily_briefing")))


def test_a_breed_with_a_verified_curve_keeps_its_old_behaviour():
    p = make(delta="20", drop_simulated=False, breed="Ross 308")
    try:
        log_deaths(p, "shed 1", 1)
        sale = p.call("plan_sale", house="shed 1", live_price_per_kg=160)
        assert "Your price today" not in texts(sale)[0]
        assert sale["structuredContent"]["plans"][0]["breed"] == "Ross 308"
        assert FEED_LINE_EN not in texts(p.call("plan_feed", house="shed 1"))[0]
    finally:
        p.stop()


def test_a_named_breed_with_no_curve_keeps_the_technical_message():
    p = make(delta="20", drop_simulated=False, breed="Desi cross")
    try:
        feed = json.dumps(p.call("plan_feed", house="shed 1"), ensure_ascii=False)
        assert FEED_LINE_EN not in feed and "growth standard for Desi cross" in feed
    finally:
        p.stop()
