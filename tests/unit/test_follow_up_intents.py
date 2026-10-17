"""Simulator host rules for ``report_health_follow_up``: how a farmer says "the shed is better / the same / worse /
I'm not sure now" (English and Hinglish), and what must NOT be taken as a follow-up (docs/DESIGN.md §18)."""

from __future__ import annotations

import pytest

from clucktalk.simulator.intents import match, yes_no

TOOL = "report_health_follow_up"


@pytest.mark.parametrize(
    ("utterance", "house", "outcome"),
    [
        ("Alexa, ask CluckTalk shed 2 is better now", "shed 2", "better"),
        ("shed 2 is better", "shed 2", "better"),
        ("House 1 looks better today", "house 1", "better"),
        ("kotam do is better now", "kotam do", "better"),
        ("shed 3 theek ho gaya", "shed 3", "better"),
        ("shed 3 behtar hai", "shed 3", "better"),
        ("shed 2 is the same", "shed 2", "same"),
        ("shed 2 same as before", "shed 2", "same"),
        ("shed 2 no change", "shed 2", "same"),
        ("shed 2 waisa hi hai", "shed 2", "same"),
        ("shed 2 is not better", "shed 2", "same"),
        ("shed 2 is worse now", "shed 2", "worse"),
        ("Shed 1 is worse", "shed 1", "worse"),
        ("kotam teen worse", "kotam teen", "worse"),
        ("shed 2 aur kharab ho gaya", "shed 2", "worse"),
        ("shed 2 bigad gaya", "shed 2", "worse"),
        ("shed 1 not sure", "shed 1", "not_sure"),
        ("shed 1 I can't tell", "shed 1", "not_sure"),
        ("shed one pata nahi", "shed 1", "not_sure"),
        ("shed 4 maloom nahi", "shed 4", "not_sure"),
        ("shed 2 is not worse", "shed 2", "not_sure"),
    ],
)
def test_how_farmers_say_how_the_shed_is_now(utterance, house, outcome):
    intent = match(utterance)
    assert intent is not None and intent.tool == TOOL, (utterance, intent)
    assert intent.arguments == {"house": house, "outcome": outcome}
    assert intent.rule.startswith("follow-up")


def test_when_two_outcomes_are_said_the_more_worrying_one_is_sent():
    assert match("shed 2 is better but not sure").arguments["outcome"] == "not_sure"
    assert match("shed 2 is the same and worse at night").arguments["outcome"] == "worse"
    assert match("shed 2 better in the morning but worse now").arguments["outcome"] == "worse"


@pytest.mark.parametrize(
    "utterance",
    [
        "it is better now",  # no shed named: the host asks which one, it never guesses
        "worse",
        "how is shed 2",  # a status question, not a report
        "what is the same shed 2 feed",
        "send the shed 2 summary to my vet",
        "shed 2 health check ready",
    ],
)
def test_these_are_not_follow_up_reports(utterance):
    intent = match(utterance)
    assert intent is None or intent.tool != TOOL, (utterance, intent)


def test_signs_of_illness_in_the_same_sentence_still_start_a_health_check():
    """A sick-bird report is never swallowed by a follow-up (the existing rule: signs come first)."""
    for utterance in ("shed 2 is worse, now coughing more", "shed 2 better but swollen heads"):
        intent = match(utterance)
        assert intent is not None and intent.tool == "start_health_check", utterance


def test_a_logged_count_in_the_sentence_is_a_record_not_a_follow_up():
    intent = match("shed 2 worse, 30 died today")
    assert intent is not None and intent.tool == "log_daily_record"


@pytest.mark.parametrize(
    ("word", "answer"),
    [("haan", "yes"), ("avunu", "yes"), ("yes", "yes"), ("nahi", "no"), ("vaddu", "no"), ("no", "no")],
)
def test_the_answer_words_for_the_read_back(word, answer):
    assert yes_no(word) == answer
