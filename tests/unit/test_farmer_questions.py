"""The Questions button: every answer is built only from the farmer's own ``farmer_schedule`` and his sheds' placement
dates. Day arithmetic (his day N = age N-1), a question is hidden when its data is absent, the note is never shown, and
no answer ever claims to be confirmed or expert."""

from __future__ import annotations

import copy
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from clucktalk.pilot import PilotFarmError, load_pilot_farm_file, parse_pilot_farm
from clucktalk.simulator import questions as q

ROOT = Path(__file__).resolve().parents[2]
BASE = json.loads((ROOT / "docs" / "pilot_farm.example.json").read_text(encoding="utf-8"))
TODAY = date(2026, 10, 9)
FULL = {
    "vaccination_farmer_days": [5, 11, 20],
    "weigh_from_farmer_day": 40,
    "weight_ok_above_kg_at_day_40": 2.0,
    "spray_water_above_c": 30,
    "heat_lights_first_days": 5,
    "vet_visit_every_days": 2,
    "normal_feed_per_bird_kg_45d": 3.5,
    "normal_weight_kg_45d": 2.2,
    "note": "DEVELOPER-ONLY-NOTE relayed by the builder",
    "is_example": True,
}
PREFIX_EN, PREFIX_TE = "As you told us:", "మీరు చెప్పినట్లు:"


def farm(day=7, age0=0, schedule=None, houses=None):
    data = copy.deepcopy(BASE)
    data["houses"] = houses or [
        {
            "number": 1,
            "birds_placed": 1000,
            "placed_on": (TODAY - timedelta(days=day - 1 - age0)).isoformat(),
            "age_at_placement_days": age0,
        }
    ]
    data["farmer_schedule"] = copy.deepcopy(FULL if schedule is None else schedule)
    return parse_pilot_farm(data)


def say(question, **kw):
    out = q.answer(farm(**kw), TODAY, question)
    assert out is not None
    return out


def test_the_example_file_has_a_schedule_marked_as_an_example_and_every_question_is_offered():
    config = load_pilot_farm_file(ROOT / "docs" / "pilot_farm.example.json")
    assert config.schedule is not None and config.schedule.is_example is True
    assert q.available(config.schedule) == list(range(1, 11))


def test_a_farm_with_no_schedule_offers_nothing_and_answers_nothing():
    data = copy.deepcopy(BASE)
    data.pop("farmer_schedule")
    config = parse_pilot_farm(data)
    assert config.schedule is None and q.available(None) == []
    assert q.answer(config, TODAY, 1) is None


@pytest.mark.parametrize(("day", "age0"), [(1, 0), (7, 0), (45, 0), (7, 3), (30, 29)])
def test_the_farmer_day_is_the_repository_age_plus_one(day, age0):
    spec = farm(day, age0).houses[0]
    assert q.farmer_day(spec.placed_on, spec.age_at_placement_days, TODAY) == day
    assert f"{day}వ రోజు" in say(1, day=day, age0=age0).te


def test_every_answer_starts_with_as_you_told_us_in_both_languages():
    for question in range(1, 11):
        out = say(question)
        assert out.en.startswith(PREFIX_EN) and out.te.startswith(PREFIX_TE), question


def test_q1_each_shed_has_its_own_day_and_a_shed_not_yet_placed_is_left_out():
    houses = [
        {"number": 1, "birds_placed": 100, "placed_on": "2026-10-01"},
        {"number": 2, "birds_placed": 100, "placed_on": "2026-10-09"},
        {"number": 3, "birds_placed": 100, "placed_on": "2026-10-20"},
    ]
    out = say(1, houses=houses)
    assert out.en == "As you told us: shed 1: day 9. shed 2: day 1."
    assert out.te == "మీరు చెప్పినట్లు: షెడ్ 1: 9వ రోజు. షెడ్ 2: 1వ రోజు."
    only_future = [{"number": 3, "birds_placed": 100, "placed_on": "2026-10-20"}]
    assert say(1, houses=only_future).en == "As you told us: No shed has birds now."


def test_layer_sheds_are_not_given_broiler_days():
    houses = [{"number": 1, "birds_placed": 100, "placed_on": "2026-10-01", "kind": "layer", "breed": "ISA"}]
    assert say(1, houses=houses).en == "As you told us: No shed has birds now."


@pytest.mark.parametrize(
    ("day", "expect"),
    [
        (7, "shed 1: next vaccination on day 11, in 4 days."),
        (5, "shed 1: next vaccination is today, day 5."),
        (12, "shed 1: next vaccination on day 20, in 8 days."),
        (21, "shed 1: the vaccination days you told us are all over."),
    ],
)
def test_q2_the_next_vaccination_day_and_the_days_left(day, expect):
    assert say(2, day=day).en == f"{PREFIX_EN} {expect}"


def test_q2_te_wording():
    assert say(2, day=7).te == "మీరు చెప్పినట్లు: షెడ్ 1: తదుపరి టీకా 11వ రోజున, 4 రోజుల్లో."


@pytest.mark.parametrize(("day", "yes"), [(5, True), (11, True), (20, True), (6, False), (1, False), (30, False)])
def test_q3_vaccination_today_is_yes_only_on_his_listed_days(day, yes):
    out = say(3, day=day)
    assert ("yes, vaccination today" in out.en) is yes and ("no vaccination today" in out.en) is not yes
    assert ("అవును" in out.te) is yes


def test_q4_weigh_from_and_the_weight_he_called_good():
    out = say(4)
    assert out.en == "As you told us: Weigh the birds from day 40. On day 40, above 2 kg is good."
    assert out.te == ("మీరు చెప్పినట్లు: 40వ రోజు నుంచి కోళ్లను తూకం వేయండి. 40వ రోజున 2 కిలోల కంటే ఎక్కువ ఉంటే బాగుంది.")
    partial = {k: v for k, v in FULL.items() if k != "weight_ok_above_kg_at_day_40"}
    assert say(4, schedule=partial).en == "As you told us: Weigh the birds from day 40."


def test_q5_spray_water_degree_is_his_number_without_a_trailing_zero():
    assert say(5).en == "As you told us: Spray water when it is hotter than 30 degrees."
    assert "32.5 degrees" in say(5, schedule={**FULL, "spray_water_above_c": 32.5}).en


@pytest.mark.parametrize(("day", "within"), [(1, True), (5, True), (6, False), (30, False)])
def test_q6_the_heat_lights_say_whether_he_is_still_within(day, within):
    out = say(6, day=day)
    assert ("keep them on" in out.en) is within and ("those days are over" in out.en) is not within
    assert (("ఇంకా ఉంచాలి" in out.te) is within) and (("అయిపోయాయి" in out.te) is not within)


def test_q7_the_doctor_every_n_days_as_told():
    assert say(7).en == "As you told us: The doctor comes every 2 days."
    assert say(7).te == "మీరు చెప్పినట్లు: డాక్టర్ 2 రోజులకు ఒకసారి వస్తారు."
    assert say(7, schedule={**FULL, "vet_visit_every_days": 1}).en == "As you told us: The doctor comes every day."


def test_q8_and_q9_his_figures_for_day_45():
    assert say(8).en == "As you told us: One bird eats about 3.5 kg of feed in all by day 45."
    assert say(9).en == "As you told us: On day 45 the weight should be about 2.2 kg."
    assert "3.5 కిలోల దాణా" in say(8).te and "2.2 కిలోలు" in say(9).te


@pytest.mark.parametrize(("day", "age0", "due"), [(7, 0, "16-11-2026"), (45, 0, "09-10-2026"), (7, 3, "16-11-2026")])
def test_q10_the_date_of_day_45_comes_from_the_placement_date(day, age0, due):
    assert say(10, day=day, age0=age0).en == f"{PREFIX_EN} shed 1: day 45 is on {due}."


@pytest.mark.parametrize(
    ("missing", "hidden"),
    [
        ("vaccination_farmer_days", {2, 3}),
        ("weigh_from_farmer_day", {4}),
        ("spray_water_above_c", {5}),
        ("heat_lights_first_days", {6}),
        ("vet_visit_every_days", {7}),
        ("normal_feed_per_bird_kg_45d", {8}),
        ("normal_weight_kg_45d", {9}),
    ],
)
def test_a_question_whose_data_is_absent_is_hidden_and_refused(missing, hidden):
    config = farm(schedule={k: v for k, v in FULL.items() if k != missing})
    shown = set(q.available(config.schedule))
    assert hidden.isdisjoint(shown) and shown == set(range(1, 11)) - hidden
    assert all(q.answer(config, TODAY, h) is None for h in hidden)


def test_day_45_question_stays_while_either_45_day_figure_is_given_and_goes_with_both():
    only_weight = {k: v for k, v in FULL.items() if k != "normal_feed_per_bird_kg_45d"}
    assert 10 in q.available(farm(schedule=only_weight).schedule)
    neither = {k: v for k, v in only_weight.items() if k != "normal_weight_kg_45d"}
    assert 10 not in q.available(farm(schedule=neither).schedule)


def test_the_labels_are_the_farmers_ten_questions_in_order():
    labels = q.labels(farm().schedule)
    assert [x["id"] for x in labels] == list(range(1, 11))
    assert labels[0]["te"] == "ఈరోజు ఎన్నో రోజు?" and labels[9]["te"] == "45వ రోజు ఎప్పుడు?"


def test_an_unknown_question_number_is_refused():
    config = farm()
    assert q.answer(config, TODAY, 0) is None and q.answer(config, TODAY, 11) is None


def test_the_developer_note_is_never_in_any_answer_or_label():
    config = farm()
    answers = [q.answer(config, TODAY, n) for n in range(1, 11)]
    seen = json.dumps([[a.en, a.te] for a in answers if a] + q.labels(config.schedule), ensure_ascii=False)
    assert "DEVELOPER-ONLY-NOTE" not in seen and "relayed" not in seen


def test_no_answer_says_confirmed_or_expert_or_advises():
    config = farm()
    for n in range(1, 11):
        out = q.answer(config, TODAY, n)
        text = (out.en + " " + out.te).lower()
        for word in ("confirm", "expert", "verified", "recommend", "advice", "నిర్ధార", "నిపుణ"):
            assert word not in text, (n, word)


@pytest.mark.parametrize(
    "bad",
    [
        {"unknown": 1},
        {"note": "only a note"},
        {},
        {"vaccination_farmer_days": []},
        {"vaccination_farmer_days": [5, 5]},
        {"vaccination_farmer_days": [0]},
        {"vaccination_farmer_days": "5"},
        {"weigh_from_farmer_day": 0},
        {"weigh_from_farmer_day": True},
        {"spray_water_above_c": -1},
        {"spray_water_above_c": "30"},
        {"heat_lights_first_days": 2.5},
        {"vet_visit_every_days": 0},
        {"normal_weight_kg_45d": 0},
        {"normal_feed_per_bird_kg_45d": float("nan")},
        {"spray_water_above_c": 30, "is_example": "yes"},
        {"spray_water_above_c": 30, "note": "x" * 201},
    ],
)
def test_a_bad_schedule_stops_the_load_loudly(bad):
    data = copy.deepcopy(BASE)
    data["farmer_schedule"] = bad
    with pytest.raises(PilotFarmError, match="farmer_schedule"):
        parse_pilot_farm(data)


def test_the_schedule_must_be_an_object():
    data = copy.deepcopy(BASE)
    data["farmer_schedule"] = [1, 2]
    with pytest.raises(PilotFarmError, match="farmer_schedule"):
        parse_pilot_farm(data)
