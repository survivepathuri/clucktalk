"""A typed paper rate ("paper rate 160", the Telugu words for it) reaches plan_sale as the live_price_per_kg argument,
in English and in Telugu. The page keeps no sale conversation between turns, so a bare number is NOT understood (the
ask line gives an example the matchers accept instead)."""

from __future__ import annotations

import pytest

from clucktalk.simulator.intents import match
from clucktalk.simulator.intents_te import match_te

ENGLISH = ["paper rate 160", "today paper rate is 160", "sell, paper rate 160", "Paper Rate 160 today", "rate 160"]
TELUGU = [
    "ఈరోజు పేపర్ రేటు 160",
    "పేపర్ రేటు 160",
    "ఈరోజు రేటు 160",
    "రేటు 160 ఉంది",
    "పేపర్ రేట్ 160",
    "ఈరోజు పేపర్ రేట్ 160",
    "ఈరోజు పేపర్ రేటు ౧౬౦",
    "ఎప్పుడు అమ్మాలి, పేపర్ రేటు 160",
    "paper rate 160",
    "today paper rate is 160",
]


@pytest.mark.parametrize("text", ENGLISH)
def test_english_paper_rate_phrases_give_the_sale_plan_with_the_rate(text):
    intent = match(text)
    assert intent is not None and intent.tool == "plan_sale"
    assert intent.arguments == {"live_price_per_kg": 160.0}


@pytest.mark.parametrize("text", TELUGU)
def test_telugu_paper_rate_phrases_give_the_sale_plan_with_the_rate(text):
    result = match_te(text)
    assert result.kind == "intent", (text, result)
    assert result.intent.tool == "plan_sale"
    assert result.intent.arguments == {"live_price_per_kg": 160.0}


def test_a_shed_and_a_rate_keep_both():
    result = match_te("షెడ్ 2 పేపర్ రేటు 160")
    assert result.intent is not None and result.intent.tool == "plan_sale"
    assert result.intent.arguments == {"house": "shed 2", "live_price_per_kg": 160.0}


@pytest.mark.parametrize("text", ["160", "౧౬౦", "ఈరోజు 160"])
def test_a_bare_number_is_not_understood_because_the_page_keeps_no_sale_state(text):
    assert match_te(text).kind == "none"
    assert match(text) is None


@pytest.mark.parametrize("text", ["పేపర్ రేటు 160 170", "రేటు 160 మరియు 170", "పేపర్ రేటు 160 షెడ్ 2 లో 3"])
def test_two_numbers_next_to_a_rate_are_never_guessed(text):
    assert match_te(text).kind == "none"


def test_a_rate_word_without_a_number_is_not_a_sale_question():
    assert match_te("ఈరోజు పేపర్ రేటు").kind == "none"


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("ఫారం ఎలా ఉంది", "status"),
        ("ఈరోజు బ్రీఫింగ్", "briefing"),
        ("సహాయం", "help"),
        ("ఎప్పుడు అమ్మాలి", "sale"),
        ("షెడ్ 2 లో 3 చనిపోయాయి", "deaths"),
    ],
)
def test_other_telugu_phrases_route_as_before(text, rule):
    assert match_te(text).rule == rule


def test_a_death_count_never_becomes_a_rate():
    result = match_te("షెడ్ 2 లో 3 కోళ్లు చనిపోయాయి")
    assert result.intent is not None and result.intent.tool == "log_daily_record"
    assert "live_price_per_kg" not in result.intent.arguments


def test_not_understood_phrases_stay_not_understood():
    for text in ("ఫీడ్ ఎంత ఉంది", "ఈరోజు మందు ఇవ్వాలా"):
        assert match_te(text).kind == "none"
