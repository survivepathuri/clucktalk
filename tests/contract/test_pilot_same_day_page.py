"""Step 52 part A through the Simulator: the add-or-replace question in Telugu, the two big buttons (chips), typed
add or replace words, a plain yes that does not answer it, and the pilot status sentence."""

# ruff: noqa: F811  (the pilot rig is a fixture imported from the Telugu turns tests and used by name)
from __future__ import annotations

import json
from pathlib import Path

import httpx2

from clucktalk.i18n.pilot import BUTTON_ADD, BUTTON_REPLACE, NOTHING_PENDING
from tests.contract.test_pilot_telugu_turns import rig, stored  # noqa: F401  (the shared pilot rig fixture)

ROOT = Path(__file__).resolve().parents[2]


def first_log(rig, n=3):
    rig.turn(utterance=f"షెడ్ 1 లో {n} కోళ్లు చనిపోయాయి", lang="te")
    rig.turn(chip="yes", lang="te")


def test_the_second_log_asks_in_telugu_with_both_numbers_and_the_page_gets_the_choice(rig):
    first_log(rig, 3)
    out = rig.turn(utterance="షెడ్ 1 లో 2 కోళ్లు చనిపోయాయి", lang="te")
    assert out["awaiting_answer"] is True and out["kind"] == "tool"
    sc = out["result"]["structuredContent"]
    assert sc["choice"] == {"existing_deaths": 3, "new_deaths": 2, "total_if_added": 5}
    assert "3" in out["speech_te"] and "2" in out["speech_te"] and "5" in out["speech_te"]
    assert [r.deaths for r in stored(rig)] == [3]  # asking saved nothing


def test_the_add_button_adds_and_the_replace_button_replaces(rig):
    first_log(rig, 3)
    rig.turn(utterance="షెడ్ 1 లో 2 కోళ్లు చనిపోయాయి", lang="te")
    done = rig.turn(chip="add", lang="te")
    assert done["kind"] == "tool" and [r.deaths for r in stored(rig)] == [5]
    rig.turn(utterance="షెడ్ 1 లో 1 కోళ్లు చనిపోయాయి", lang="te")
    rig.turn(chip="replace", lang="te")
    assert [r.deaths for r in stored(rig)] == [1]


def test_a_plain_yes_typed_or_tapped_does_not_answer_it_and_the_question_stays(rig):
    first_log(rig, 3)
    rig.turn(utterance="షెడ్ 1 లో 2 కోళ్లు చనిపోయాయి", lang="te")
    for answer in ({"utterance": "అవును"}, {"chip": "yes"}):
        out = rig.turn(lang="te", **answer)
        assert out["awaiting_answer"] is True and out["result"]["structuredContent"]["choice"] is not None
        assert [r.deaths for r in stored(rig)] == [3]
    assert rig.turn(chip="add", lang="te")["kind"] == "tool" and [r.deaths for r in stored(rig)] == [5]


def test_typed_add_and_replace_words_are_whole_message_answers(rig):
    first_log(rig, 3)
    rig.turn(utterance="షెడ్ 1 లో 2 కోళ్లు చనిపోయాయి", lang="te")
    rig.turn(utterance="కలపండి", lang="te")
    assert [r.deaths for r in stored(rig)] == [5]
    rig.turn(utterance="షెడ్ 1 లో 4 కోళ్లు చనిపోయాయి", lang="te")
    rig.turn(utterance="మార్చండి", lang="te")
    assert [r.deaths for r in stored(rig)] == [4]


def test_add_or_replace_with_nothing_waiting_does_nothing_and_calls_no_tool(rig):
    before = list(rig.spy.calls)
    for utterance in ("కలపండి", "మార్చండి"):
        out = rig.turn(utterance=utterance, lang="te")
        assert out["kind"] == "fallback" and out["speech_te"] == NOTHING_PENDING.te
    for chip in ("add", "replace"):
        assert rig.turn(chip=chip, lang="te")["speech_te"] == NOTHING_PENDING.te
    assert rig.spy.calls == before and stored(rig) == ()


def test_add_with_only_a_health_read_back_waiting_does_not_start_the_health_check(rig):
    rig.turn(chip="health", params={"house": 1, "signs": ["coughing"]}, lang="te")
    out = rig.turn(chip="add", lang="te")
    assert out["speech_te"] == NOTHING_PENDING.te
    assert [c for c in rig.spy.calls if c[0] == "start_health_check"] == []


def test_no_cancels_the_question_and_keeps_the_old_record(rig):
    first_log(rig, 3)
    rig.turn(utterance="షెడ్ 1 లో 2 కోళ్లు చనిపోయాయి", lang="te")
    rig.turn(chip="no", lang="te")
    assert [r.deaths for r in stored(rig)] == [3]
    assert rig.turn(chip="add", lang="te")["kind"] == "fallback"  # nothing left to answer


def test_a_total_above_the_birds_is_refused_at_the_add_tap_and_replace_works_after_asking_again(rig):
    first_log(rig, 2900)
    rig.turn(utterance="షెడ్ 1 లో 200 కోళ్లు చనిపోయాయి", lang="te")
    out = rig.turn(chip="add", lang="te")
    assert out["is_error"] is True and [r.deaths for r in stored(rig)] == [2900]
    assert rig.turn(chip="replace", lang="te")["kind"] == "fallback"  # the refusal ended that question
    rig.turn(utterance="షెడ్ 1 లో 200 కోళ్లు చనిపోయాయి", lang="te")  # the farmer says it again, then chooses replace
    assert rig.turn(chip="replace", lang="te")["kind"] == "tool" and [r.deaths for r in stored(rig)] == [200]


def test_the_first_log_of_the_day_still_shows_yes_and_no_only(rig):
    out = rig.turn(utterance="షెడ్ 2 లో 4 కోళ్లు చనిపోయాయి", lang="te")
    assert out["awaiting_answer"] is True and "choice" not in out["result"]["structuredContent"]


def test_the_page_words_for_the_two_buttons_come_from_the_server(rig):
    ui = httpx2.get(rig.base + "/api/pilot/ui", timeout=20).json()
    assert ui["strings"]["add"] == {"en": BUTTON_ADD.en, "te": BUTTON_ADD.te}
    assert ui["strings"]["replace"] == {"en": BUTTON_REPLACE.en, "te": BUTTON_REPLACE.te}


def test_the_pilot_status_says_no_alert_from_my_checks_and_never_doing_well(rig):
    first_log(rig, 1)
    out = rig.turn(utterance="షెడ్ 1 ఎలా ఉంది", lang="te")
    sc = out["result"]["structuredContent"]
    assert "has no alert from the checks I can make." in sc["text_en"] and "doing well" not in sc["text_en"]
    assert "బాగుంది" not in sc["text_te"]
    assert json.dumps(sc["houses"][0]["summary_en"]).count("doing well") == 0
