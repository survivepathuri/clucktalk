"""The rule-based Telugu intent layer (Step 51 part C): typed Telugu (the farmer's keyboard voice typing), at most 8
actions. Written from the design, not the code. A number it cannot read is never guessed: the answer is "ask again"."""

from __future__ import annotations

import pytest

from clucktalk.simulator.intents import normalise
from clucktalk.simulator.intents_te import (
    Chip,
    chip_intent,
    match_te,
    normalise_te,
    parse_number,
    yes_no_te,
)

# -- the normaliser must keep Telugu (it used to shred it) -----------------------------------------------------------


def test_the_english_normaliser_no_longer_shreds_telugu():
    # Regression: `[^\w\s']` removed every Telugu vowel sign, so "షెడ్ రెండు" came back as consonants only.
    assert normalise("షెడ్ రెండు లో మరణాలు") == "షెడ్ రెండు లో మరణాలు"
    assert normalise("Shed 2, How is it?") == "shed 2 how is it"  # English text is unchanged


def test_the_telugu_normaliser_keeps_vowel_signs_and_converts_telugu_digits():
    assert normalise_te("షెడ్ ౨ లో ౩ కోళ్లు చనిపోయాయి!") == "షెడ్ 2 లో 3 కోళ్లు చనిపోయాయి"
    assert normalise_te("  కోళ్ళు‌నూ   ఫీడ్‍ ") == "కోళ్ళునూ ఫీడ్"  # zero-width joiners dropped, spaces collapsed
    assert normalise_te("అవును।") == "అవును"  # the Telugu danda is punctuation


def test_nfc_makes_the_two_ways_of_typing_the_same_letter_equal():
    assert normalise_te("ై") == normalise_te("ై")  # e + ai length mark = ai


# -- numbers ---------------------------------------------------------------------------------------------------------
GOLDEN = [
    (["3"], 3),
    (["౩"], 3),  # a Telugu digit is converted by normalise_te first; parse_number also accepts it
    (["౧", "౨"], None),  # two digit tokens are two numbers, never one
    (["సున్నా"], 0),
    (["ఒకటి"], 1),
    (["రెండు"], 2),
    (["మూడు"], 3),
    (["పది"], 10),
    (["పదకొండు"], 11),
    (["పంతొమ్మిది"], 19),
    (["ఇరవై"], 20),
    (["ఇరవై", "ఐదు"], 25),
    (["యాభై", "ఒకటి"], 51),
    (["తొంభై", "తొమ్మిది"], 99),
    (["వంద"], 100),
    (["నూట", "ఇరవై"], 120),
    (["నూట", "ఇరవై", "ఐదు"], 125),
    (["రెండు", "వందలు"], 200),
    (["రెండు", "వందల", "యాభై"], 250),
    (["వెయ్యి"], 1000),
    (["రెండు", "వేలు"], 2000),
    (["రెండు", "వేల", "ఐదు", "వందలు"], 2500),
    (["నాలుగు", "వేలు"], 4000),
]


@pytest.mark.parametrize(("tokens", "value"), GOLDEN)
def test_number_golden_cases(tokens, value):
    assert parse_number(tokens) == value


@pytest.mark.parametrize(
    "tokens",
    [
        [],
        ["రెండు", "మూడు"],  # two units are two numbers
        ["ఇరవై", "ముప్పై"],
        ["పది", "ఐదు"],  # ten and five: not a compound
        ["ఇరవై", "వందలు"],  # unclear: refused, never guessed
        ["వందలు", "వందలు"],
        ["వెయ్యి", "వెయ్యి"],
        ["abc"],
        ["రెండు", "కోళ్లు"],
        ["999999"],  # over the cap
    ],
)
def test_a_number_that_cannot_be_read_is_none_never_a_guess(tokens):
    assert parse_number(tokens) is None


# -- the actions -----------------------------------------------------------------------------------------------------
def intent_of(text):
    r = match_te(text)
    assert r.kind == "intent", (text, r)
    return r.intent.tool, r.intent.arguments


@pytest.mark.parametrize(
    ("text", "args"),
    [
        ("షెడ్ 2 లో 3 కోళ్లు చనిపోయాయి", {"house": "shed 2", "deaths": 3}),
        ("షెడ్ రెండు లో మూడు కోళ్లు చనిపోయాయి", {"house": "shed 2", "deaths": 3}),
        ("షెడ్డు ౨ లో ౩ చనిపోయాయి", {"house": "shed 2", "deaths": 3}),
        ("రెండో షెడ్డులో ఐదు కోళ్లు చనిపోయాయి", {"house": "shed 2", "deaths": 5}),
        ("కొట్టం 1 లో ఇరవై ఐదు కోళ్లు చనిపోయాయి", {"house": "shed 1", "deaths": 25}),
        ("షెడ్ 1 లో 12 మరణాలు", {"house": "shed 1", "deaths": 12}),
        ("shed 2 లో 4 చనిపోయాయి", {"house": "shed 2", "deaths": 4}),
        ("షెడ్ 3 లో ఏవీ చనిపోలేదు", {"house": "shed 3", "deaths": 0}),
        ("షెడ్ 3 లో మరణాలు లేవు", {"house": "shed 3", "deaths": 0}),
        ("షెడ్ 1 లో సున్నా కోళ్లు చనిపోయాయి", {"house": "shed 1", "deaths": 0}),
    ],
)
def test_logging_deaths(text, args):
    tool, got = intent_of(text)
    assert tool == "log_daily_record" and got == args


def test_the_house_number_is_not_mistaken_for_the_count_in_either_order():
    assert intent_of("షెడ్ 2 లో 3 కోళ్లు చనిపోయాయి")[1] == {"house": "shed 2", "deaths": 3}
    assert intent_of("3 కోళ్లు చనిపోయాయి షెడ్ 2 లో")[1] == {"house": "shed 2", "deaths": 3}


def test_deaths_without_a_number_asks_which_number_and_never_guesses():
    r = match_te("షెడ్ 2 లో కోళ్లు చనిపోయాయి")
    assert r.kind == "choose" and r.chip is Chip.DEATHS and r.params == {"house": 2}


def test_deaths_without_a_shed_asks_which_shed_and_keeps_the_number():
    r = match_te("3 కోళ్లు చనిపోయాయి")
    assert r.kind == "choose" and r.chip is Chip.DEATHS and r.params == {"count": 3}


@pytest.mark.parametrize("text", ["షెడ్ 2 లో రెండు మూడు చనిపోయాయి", "షెడ్ 2 లో 3 4 చనిపోయాయి", "షెడ్ 1 లో 3 ఇరవై మరణాలు"])
def test_two_numbers_that_do_not_make_one_are_not_understood(text):
    assert match_te(text).kind == "none"


def test_status_briefing_sale_help():
    assert intent_of("షెడ్ 2 ఎలా ఉంది") == ("get_farm_status", {"house": "shed 2"})
    assert intent_of("రెండో షెడ్డు పరిస్థితి ఏంటి") == ("get_farm_status", {"house": "shed 2"})
    assert intent_of("ఫారం ఎలా ఉంది") == ("get_farm_status", {})
    assert intent_of("ఈరోజు బ్రీఫింగ్") == ("get_daily_briefing", {})
    assert intent_of("అమ్మకం ఎప్పుడు") == ("plan_sale", {})
    assert intent_of("షెడ్ 3 కోళ్లు ఎప్పుడు అమ్మాలి") == ("plan_sale", {"house": "shed 3"})
    assert intent_of("షెడ్ 3 అమ్మకం రేటు 95") == ("plan_sale", {"house": "shed 3", "live_price_per_kg": 95.0})
    assert intent_of("సహాయం") == ("get_help", {})
    assert intent_of("నువ్వు ఏమి చేయగలవు") == ("get_help", {})


def test_a_health_check_is_chips_only_it_never_reads_signs_from_free_text():
    r = match_te("షెడ్ 2 లో కోళ్లకు దగ్గు ఉంది ఆరోగ్య పరీక్ష")
    assert r.kind == "choose" and r.chip is Chip.HEALTH and r.params == {"house": 2}
    r = match_te("ఆరోగ్య పరీక్ష")
    assert r.kind == "choose" and r.chip is Chip.HEALTH and r.params == {}


def test_follow_up_outcomes_need_a_shed_and_never_pick_a_better_outcome_on_a_negation():
    assert intent_of("షెడ్ 2 బాగుంది") == ("report_health_follow_up", {"house": "shed 2", "outcome": "better"})
    assert intent_of("షెడ్ 2 అలాగే ఉంది") == ("report_health_follow_up", {"house": "shed 2", "outcome": "same"})
    assert intent_of("షెడ్ 2 అధ్వాన్నంగా ఉంది") == ("report_health_follow_up", {"house": "shed 2", "outcome": "worse"})
    assert match_te("బాగుంది").kind == "choose"  # which shed? asked, not guessed


def test_yes_and_no_are_only_whole_utterances():
    for yes in ("అవును", "అవునండి", "సరే", "అవును!", "yes"):
        assert yes_no_te(yes) == "yes"
    for no in ("వద్దు", "వద్దండి", "కాదు", "రద్దు", "no"):
        assert yes_no_te(no) == "no"
    assert yes_no_te("అవును షెడ్ 2 ఎలా ఉంది") is None  # not a bare answer
    assert yes_no_te("") is None


def test_nothing_matches_gives_none_and_never_raises():
    for text in ("", "   ", "????", "నమస్కారం", "\x00\x01", "a" * 5000, "షెడ్" * 400, "౦౦౦౦౦౦౦౦౦౦౦౦౦"):
        assert match_te(text).kind in ("none", "choose", "intent", "yes", "no")


# -- chips -----------------------------------------------------------------------------------------------------------
def test_chips_build_the_same_intents_without_any_text():
    assert chip_intent("status", {}).arguments == {}
    assert chip_intent("status", {"house": 2}).arguments == {"house": "shed 2"}
    assert chip_intent("briefing", {}).tool == "get_daily_briefing"
    assert chip_intent("sale", {"house": 1}).arguments == {"house": "shed 1"}
    assert chip_intent("help", {}).tool == "get_help"
    deaths = chip_intent("deaths", {"house": 2, "count": 7})
    assert (deaths.tool, deaths.arguments) == ("log_daily_record", {"house": "shed 2", "deaths": 7})
    assert chip_intent("no_deaths", {"house": 3}).arguments == {"house": "shed 3", "deaths": 0}
    health = chip_intent("health", {"house": 1, "signs": ["coughing", "sneezing"]})
    assert health.tool == "start_health_check" and health.arguments["signs"] == ["coughing", "sneezing"]
    follow = chip_intent("follow_up", {"house": 1, "outcome": "worse"})
    assert follow.arguments == {"house": "shed 1", "outcome": "worse"}


@pytest.mark.parametrize(
    ("chip", "params"),
    [
        ("nonsense", {}),
        ("deaths", {"house": 2}),  # no count
        ("deaths", {"house": 2, "count": -1}),
        ("deaths", {"house": 2, "count": 100001}),
        ("deaths", {"house": 2, "count": True}),
        ("deaths", {"house": 2, "count": "3"}),
        ("deaths", {"house": 0, "count": 3}),
        ("deaths", {"house": 100, "count": 3}),
        ("deaths", {"house": "shed 2", "count": 3}),
        ("deaths", {"house": 2, "count": 3, "extra": 1}),
        ("health", {"house": 1, "signs": []}),
        ("health", {"house": 1, "signs": ["made_up"]}),
        ("health", {"house": 1, "signs": ["coughing", "coughing"]}),
        ("follow_up", {"house": 1, "outcome": "cured"}),
        ("status", {"house": -1}),
        ("help", {"house": 1}),
    ],
)
def test_a_chip_with_anything_unexpected_is_refused(chip, params):
    with pytest.raises(ValueError):
        chip_intent(chip, params)
