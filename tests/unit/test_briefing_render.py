"""The briefing's sentences (clucktalk.server.tools.briefing._render): every item is a template filled from the fact's
own values, in English and Telugu, with the same numbers, no money and no treatment words. The demo farm cannot reach
every branch (no sale window, no unusable house), so these build the facts by hand."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

import pytest

from clucktalk.domain.briefing import Category, collect_facts
from clucktalk.domain.models import DailyRecord, House, HouseKind
from clucktalk.domain.reference import curve_for
from clucktalk.domain.triage import CheckStatus, Floor, HealthCheck, TriageInput, TriageResult, Urgency
from clucktalk.server.tools.briefing import _render
from clucktalk.server.tools.records import DOSE_PATTERN
from tests.crossmodal import spoken_numbers
from tests.unit.helpers import D0, farm_with

IST = timezone(timedelta(hours=5, minutes=30))
TREATMENT = re.compile(
    r"\b(?:antibiotics?|medicines?|medication|drugs?|dosage|vaccinat\w*|injections?)\b|₹", re.IGNORECASE
)


def _house(number=1, days=7, start_age=0, deaths=None, empty=False) -> House:
    deaths = deaths or {}
    records = () if empty else tuple(
        DailyRecord(D0 + timedelta(days=i), deaths.get(i, 1), 30.0) for i in range(days)
    )  # fmt: skip
    return House(f"house-{number}", number, HouseKind.BROILER, "Ross 308", D0, 1000, start_age, 100_000.0, records)


def _check(house_id: str, urgency: Urgency, at: datetime) -> HealthCheck:
    inp = TriageInput(
        house_id, "House 1", "షెడ్ 1", "Ross 308", 10, 900, (), None, None, None, None, None, False, None, None
    )
    result = TriageResult(urgency, (), ("x",), "rules", None, None)
    return HealthCheck(
        "chk_" + "0" * 16, "farm-test", house_id, at, CheckStatus.READY, inp, Floor(urgency, ()), result, at
    )


def _texts(house: House, as_of: date, checks=None, logged=frozenset()):
    farm = farm_with(house)
    return {f.category: (f, *_render(f, farm)) for f in collect_facts(farm, as_of, checks or {}, logged)}


def _assert_clean(text, values, item_number=None):
    for t in (text.en, text.te):
        assert t.strip()
        assert not DOSE_PATTERN.search(t), t
        assert not TREATMENT.search(t), t
    en_numbers = sorted(spoken_numbers(text.en, set()))
    assert en_numbers == sorted(spoken_numbers(text.te, set())), (text.en, text.te)
    backed = {float(v) for v in _flatten(values)} | ({float(item_number)} if item_number is not None else set())
    assert set(en_numbers) <= backed, (text.en, values)


def _flatten(v):
    if isinstance(v, dict):
        for x in v.values():
            yield from _flatten(x)
    elif isinstance(v, list):
        for x in v:
            yield from _flatten(x)
    elif isinstance(v, int | float) and not isinstance(v, bool):
        yield v


def test_the_sale_item_names_a_day_says_simulated_and_shows_no_rupees():
    late = _house(days=7, start_age=curve_for("Ross 308").max_day - 7)
    fact, text, values = _texts(late, D0 + timedelta(days=6))[Category.SALE_WINDOW]
    assert "simulated estimate" in text.en and "sell-day plan" in text.en
    assert "అంచనా" in text.te
    assert set(values) == {"best_day_index", "best_day"} and fact.simulated
    _assert_clean(text, values, item_number=1)


@pytest.mark.parametrize(("index", "phrase"), [(0, "today"), (1, "tomorrow"), (2, "in 2 days"), (3, "in 3 days")])
def test_the_sale_day_is_said_the_way_a_farmer_says_it(index, phrase):
    from clucktalk.domain.briefing import Fact
    from clucktalk.domain.status import Level

    house = _house()
    fact = Fact("sale_window:house-1", Category.SALE_WINDOW, Level.WATCH, 1, False, "house-1", 1,
                {"best_day_index": index, "best_day": "2026-10-01"}, simulated=True)  # fmt: skip
    text, values = _render(fact, farm_with(house))
    assert phrase in text.en and values["best_day_index"] == index
    _assert_clean(text, values, item_number=1)


def test_an_open_health_check_is_reported_in_words_with_no_diagnosis_and_a_pointer_to_the_result():
    as_of = D0 + timedelta(days=6)
    for urgency, words in (
        (Urgency.URGENT, "needs a vet today"),
        (Urgency.NOTIFIABLE_SUSPECT, "signs of a possible reportable disease"),
        (Urgency.WATCH, "watch closely today"),
    ):
        at = datetime.combine(as_of - timedelta(days=2), datetime.min.time(), tzinfo=IST)
        fact, text, values = _texts(_house(), as_of, {"house-1": _check("house-1", urgency, at)})[
            Category.OPEN_HEALTH_CHECK
        ]
        assert words in text.en and "2 days ago" in text.en and "health check result" in text.en
        assert values == {"urgency": urgency.code, "days_ago": 2}
        _assert_clean(text, values, item_number=1)


def test_a_recalled_spike_says_how_long_ago_and_against_what():
    house = _house(days=15, deaths={10: 60})
    fact, text, values = _texts(house, D0 + timedelta(days=14))[Category.RECENT_LOGGED_SPIKE]
    assert text.en == "House 1: 60 birds died 4 days ago, against about 1 a day the week before."
    assert values == {"deaths": 60, "baseline_per_day": 1, "days_ago": 4}
    _assert_clean(text, values, item_number=1)
    yesterday = _texts(_house(days=15, deaths={13: 60}), D0 + timedelta(days=14))[Category.RECENT_LOGGED_SPIKE]
    assert "died yesterday" in yesterday[1].en


def test_a_spike_after_a_calm_week_says_so_instead_of_dividing_by_zero():
    house = House("house-1", 1, HouseKind.BROILER, "Ross 308", D0, 1000, 0, 100_000.0,
                  tuple(DailyRecord(D0 + timedelta(days=i), 60 if i == 10 else 0, 30.0)
                        for i in range(15)))  # fmt: skip
    fact, text, values = _texts(house, D0 + timedelta(days=14))[Category.RECENT_LOGGED_SPIKE]
    assert "after hardly any deaths the week before" in text.en and values["baseline_per_day"] == 0
    _assert_clean(text, values, item_number=1)


def test_not_logged_today_names_the_houses_in_both_languages():
    farm = farm_with(_house(1), _house(2), _house(3))
    facts = collect_facts(farm, D0 + timedelta(days=6), {}, frozenset({"house-2"}))
    fact = next(f for f in facts if f.category is Category.NOT_LOGGED_TODAY)
    text, values = _render(fact, farm)
    assert text.en == "No entry yet today for House 1 and House 3."
    assert "షెడ్ 1" in text.te and "షెడ్ 3" in text.te
    _assert_clean(text, values)


def test_a_house_that_could_not_be_checked_is_named_and_said():
    farm = farm_with(_house(1, empty=True))
    fact = next(
        f for f in collect_facts(farm, D0 + timedelta(days=6), {}, frozenset()) if f.category is Category.NOT_CHECKED
    )
    text, values = _render(fact, farm)
    assert "House 1" in text.en and "షెడ్ 1" in text.te and values == {}


def test_feed_intake_is_short_for_the_ear_and_never_dose_shaped():
    house = House("house-1", 1, HouseKind.BROILER, "Ross 308", D0, 1000, 0, 100_000.0,
                  tuple(DailyRecord(D0 + timedelta(days=i), 1, 60.0 if i < 14 else 30.0)
                        for i in range(15)))  # fmt: skip
    farm = farm_with(house)  # feed halves on the last day: well under 85% of the recent level
    facts = {f.category: f for f in collect_facts(farm, D0 + timedelta(days=14), {}, frozenset())}
    text, values = _render(facts[Category.FEED_INTAKE_DROP], farm)
    assert re.fullmatch(r"House 1: Birds ate \d+% less than expected\.", text.en)
    assert list(values) == ["drop_pct"]
    _assert_clean(text, values, item_number=1)
