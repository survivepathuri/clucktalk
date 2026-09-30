"""Daily Briefing domain (docs/DESIGN.md §18): the fact collectors, the rules order, the closed-list ranking and its
safety floor. Pure functions, hand-built houses; expected values are computed from the definitions in
clucktalk.domain.thresholds (spike = at least 3x the trailing 7-day average and at least 3 birds), not copied from
code output."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from clucktalk.domain.briefing import (
    MAX_ITEMS,
    RECENT_CHECK_DAYS,
    RECENT_SPIKE_DAYS,
    SALE_WINDOW_DAYS,
    SPOKEN_ITEMS,
    Category,
    Fact,
    InvalidRanking,
    apply_order,
    collect_facts,
    fingerprint,
    ranking_schema,
    rules_order,
    validate_ranking,
)
from clucktalk.domain.models import DailyRecord, House, HouseKind
from clucktalk.domain.reference import curve_for
from clucktalk.domain.sale import plan_sale
from clucktalk.domain.status import Level
from clucktalk.domain.triage import (
    CheckStatus,
    Floor,
    HealthCheck,
    TriageInput,
    TriageResult,
    Urgency,
)
from tests.unit.helpers import D0, farm_with

IST = timezone(timedelta(hours=5, minutes=30))


def _house(
    number: int = 1,
    days: int = 15,
    deaths: dict[int, int] | None = None,
    start_age: int = 0,
    kind: HouseKind = HouseKind.BROILER,
    stock_kg: float = 100_000.0,
    empty: bool = False,
) -> House:
    """Records on days D0 .. D0+days-1, one death a day unless ``deaths`` (by day index) says otherwise."""
    deaths = deaths or {}
    records = () if empty else tuple(
        DailyRecord(D0 + timedelta(days=i), deaths.get(i, 1), 30.0, eggs=800 if kind is HouseKind.LAYER else None)
        for i in range(days)
    )  # fmt: skip
    return House(
        house_id=f"house-{number}",
        number=number,
        kind=kind,
        breed="Ross 308" if kind is HouseKind.BROILER else "BV-300",
        placed_on=D0,
        birds_placed=1000,
        age_at_placement_days=start_age if kind is HouseKind.BROILER else 200,
        feed_stock_kg=stock_kg,
        records=records,
    )


def _facts(house: House, as_of: date, checks=None, logged=frozenset()) -> dict[str, Fact]:
    farm = farm_with(house)
    return {f.category.value: f for f in collect_facts(farm, as_of, checks or {}, logged)}


def _check(house_id: str, urgency: Urgency, created: datetime, status: CheckStatus = CheckStatus.READY) -> HealthCheck:
    inp = TriageInput(
        house_id, "House 1", "షెడ్ 1", "Ross 308", 10, 900, (), None, None, None, None, None, False, None, None
    )
    result = None
    if status is CheckStatus.READY:
        result = TriageResult(urgency, (), ("x",), "rules", None, None)
    return HealthCheck(
        "chk_" + "0" * 16, "farm-test", house_id, created, status, inp, Floor(urgency, ()), result, created
    )


# -- recent_logged_spike: the "three days later" recall --------------------------------------------------------------
def test_a_spike_four_days_ago_is_recalled_and_pinned():
    # Day index 10 has 60 deaths after seven days of 1: 60 >= 3 x 1.0 and >= 3 birds, so it is a spike.
    house = _house(deaths={10: 60})
    as_of = D0 + timedelta(days=14)
    facts = _facts(house, as_of)
    f = facts["recent_logged_spike"]
    assert f.pinned and f.level is Level.ALERT and f.house_id == "house-1"
    assert f.values["deaths"] == 60 and f.values["days_ago"] == 4
    assert f.values["baseline_daily_avg"] == 1.0
    assert f.values["day"] == (D0 + timedelta(days=10)).isoformat()
    assert "mortality_spike" not in facts  # today's own count (1) is not a spike


def test_the_recall_window_is_the_trailing_seven_days():
    as_of = D0 + timedelta(days=14)
    assert RECENT_SPIKE_DAYS == 7
    six_ago = _facts(_house(deaths={8: 60}), as_of)  # 14 - 8 = 6 days ago: still inside
    assert six_ago["recent_logged_spike"].values["days_ago"] == 6
    seven_ago = _facts(_house(deaths={7: 60}), as_of)  # 7 days ago: outside
    assert "recent_logged_spike" not in seven_ago
    assert "recent_logged_spike" not in _facts(_house(days=21, deaths={10: 60}), D0 + timedelta(days=20))


def test_a_spike_on_the_latest_day_is_the_mortality_spike_not_a_recall():
    house = _house(deaths={14: 60})
    facts = _facts(house, D0 + timedelta(days=14))
    assert facts["mortality_spike"].pinned and facts["mortality_spike"].level is Level.ALERT
    assert "recent_logged_spike" not in facts


def test_only_the_most_recent_spike_is_recalled():
    house = _house(days=20, deaths={9: 50, 13: 80})
    f = _facts(house, D0 + timedelta(days=19))["recent_logged_spike"]
    assert f.values["deaths"] == 80 and f.values["days_ago"] == 6


def test_a_calm_house_has_no_health_fact():
    facts = _facts(_house(), D0 + timedelta(days=14))
    assert not {"mortality_spike", "recent_logged_spike", "open_health_check"} & set(facts)


# -- open_health_check: an earlier triage that still matters ---------------------------------------------------------
def test_an_urgent_check_from_two_days_ago_is_pinned():
    as_of = D0 + timedelta(days=14)
    created = datetime.combine(as_of - timedelta(days=2), datetime.min.time(), tzinfo=IST).replace(hour=9)
    f = _facts(_house(), as_of, {"house-1": _check("house-1", Urgency.URGENT, created)})["open_health_check"]
    assert f.pinned and f.level is Level.ALERT and f.severity == 2
    assert f.values == {"urgency": "urgent", "days_ago": 2}


def test_a_notifiable_check_outranks_every_other_alert():
    as_of = D0 + timedelta(days=14)
    created = datetime.combine(as_of, datetime.min.time(), tzinfo=IST).replace(hour=9)
    f = _facts(_house(), as_of, {"house-1": _check("house-1", Urgency.NOTIFIABLE_SUSPECT, created)})
    assert f["open_health_check"].severity == 3 and f["open_health_check"].pinned


def test_only_recent_finished_checks_that_were_not_routine_count():
    as_of = D0 + timedelta(days=14)
    at = lambda days: datetime.combine(as_of - timedelta(days=days), datetime.min.time(), tzinfo=IST)  # noqa: E731
    assert RECENT_CHECK_DAYS == 3
    house = _house()
    assert "open_health_check" in _facts(house, as_of, {"house-1": _check("house-1", Urgency.URGENT, at(3))})
    assert "open_health_check" not in _facts(house, as_of, {"house-1": _check("house-1", Urgency.URGENT, at(4))})
    assert "open_health_check" not in _facts(house, as_of, {"house-1": _check("house-1", Urgency.ROUTINE, at(0))})
    analyzing = _check("house-1", Urgency.URGENT, at(0), CheckStatus.ANALYZING)
    assert "open_health_check" not in _facts(house, as_of, {"house-1": analyzing})
    failed = _check("house-1", Urgency.URGENT, at(0), CheckStatus.FAILED)
    assert "open_health_check" not in _facts(house, as_of, {"house-1": failed})


def test_a_watch_check_is_listed_but_not_pinned():
    as_of = D0 + timedelta(days=14)
    created = datetime.combine(as_of, datetime.min.time(), tzinfo=IST)
    f = _facts(_house(), as_of, {"house-1": _check("house-1", Urgency.WATCH, created)})["open_health_check"]
    assert f.level is Level.WATCH and not f.pinned and f.severity == 1


# -- sale window: simulated, only near the end of the flock's life ---------------------------------------------------
def test_sale_window_appears_only_when_the_best_day_is_within_three_days():
    assert SALE_WINDOW_DAYS == 3
    max_day = curve_for("Ross 308").max_day  # 56
    late = _house(days=7, start_age=max_day - 7)  # the last record is at age max_day - 1: one day of horizon left
    as_of = D0 + timedelta(days=6)
    plan = plan_sale(farm_with(late), late, as_of)
    assert plan.best_day_index <= SALE_WINDOW_DAYS  # premise: this flock's best sale day is at most a day away
    f = _facts(late, as_of)["sale_window"]
    assert f.simulated is True and not f.pinned and f.level is Level.WATCH
    assert f.values["best_day_index"] == plan.best_day_index
    assert f.values["best_day"] == plan.days[plan.best_day_index].day.isoformat()

    early = _house(days=7, start_age=4)  # age 10: growth still pays, the best day is at the far end
    early_as_of = D0 + timedelta(days=6)
    assert plan_sale(farm_with(early), early, early_as_of).best_day_index > SALE_WINDOW_DAYS  # premise
    assert "sale_window" not in _facts(early, early_as_of)


def test_layers_have_no_sale_window():
    facts = _facts(_house(kind=HouseKind.LAYER), D0 + timedelta(days=14))
    assert "sale_window" not in facts


def test_a_sale_fact_never_carries_money():
    max_day = curve_for("Ross 308").max_day
    late = _house(days=7, start_age=max_day - 7)
    f = _facts(late, D0 + timedelta(days=6))["sale_window"]
    assert set(f.values) == {"best_day_index", "best_day"}  # a day, never a rupee figure (Simulated)


# -- farm-level and unusable-house facts -----------------------------------------------------------------------------
def test_not_logged_today_is_one_farm_fact_naming_the_houses():
    farm = farm_with(_house(1), _house(2), _house(3))
    as_of = D0 + timedelta(days=14)
    facts = {f.category: f for f in collect_facts(farm, as_of, {}, frozenset({"house-2"}))}
    f = facts[Category.NOT_LOGGED_TODAY]
    assert f.house_id is None and f.level is Level.OK and not f.pinned
    assert f.values == {"count": 2, "numbers": [1, 3]}
    none_missing = collect_facts(farm, as_of, {}, frozenset({"house-1", "house-2", "house-3"}))
    assert Category.NOT_LOGGED_TODAY not in {x.category for x in none_missing}


def test_a_house_that_cannot_be_checked_is_said_not_hidden():
    farm = farm_with(_house(1, empty=True))
    facts = collect_facts(farm, D0 + timedelta(days=14), {}, frozenset())
    f = next(x for x in facts if x.category is Category.NOT_CHECKED)
    assert f.level is Level.WATCH and f.house_id == "house-1"
    assert f.values["message_en"] and f.values["message_te"]


# -- rules order -----------------------------------------------------------------------------------------------------
def _fact(fid: str, cat: Category, level: Level, *, pinned=False, severity=None, number=1, tiebreak=0.0) -> Fact:
    return Fact(
        fact_id=fid,
        category=cat,
        level=level,
        severity=int(level) if severity is None else severity,
        pinned=pinned,
        house_id=None if number is None else f"house-{number}",
        number=number,
        values={},
        tiebreak=tiebreak,
    )


def test_rules_order_pins_health_first_then_by_level_then_category_then_house():
    facts = [
        _fact("a", Category.FEED_STOCK_LOW, Level.WATCH, number=1, tiebreak=4),
        _fact("b", Category.WEIGHT_BELOW_TARGET, Level.ALERT, number=3),  # an unpinned ALERT still ranks below health
        _fact("c", Category.MORTALITY_SPIKE, Level.ALERT, pinned=True, number=2),
        _fact("d", Category.NOT_LOGGED_TODAY, Level.OK, number=None),
        _fact("e", Category.OPEN_HEALTH_CHECK, Level.ALERT, pinned=True, severity=3, number=3),
        _fact("f", Category.FEED_STOCK_LOW, Level.WATCH, number=2, tiebreak=0),
    ]
    order = [f.fact_id for f in rules_order(facts)]
    assert order == ["e", "c", "b", "f", "a", "d"]  # notifiable, spike, ALERT, stock 0 days before 4 days, reminder
    assert [f.fact_id for f in rules_order(list(reversed(facts)))] == order  # input order never matters


def test_a_pinned_fact_outranks_an_unpinned_alert_whatever_its_own_level():
    """Pinning, not severity, is what puts health first: a pinned WATCH still sits above an unpinned ALERT."""
    facts = [
        _fact("alert", Category.WEIGHT_BELOW_TARGET, Level.ALERT, number=1),
        _fact("pinned", Category.CUM_MORTALITY_HIGH, Level.WATCH, pinned=True, number=2),
    ]
    assert [f.fact_id for f in rules_order(facts)] == ["pinned", "alert"]


def test_apply_order_never_moves_a_pinned_fact_and_keeps_every_fact():
    facts = rules_order(
        [
            _fact("p1", Category.MORTALITY_SPIKE, Level.ALERT, pinned=True),
            _fact("x", Category.FEED_STOCK_LOW, Level.WATCH),
            _fact("y", Category.WEIGHT_BELOW_TARGET, Level.WATCH),
            _fact("z", Category.NOT_LOGGED_TODAY, Level.OK, number=None),
        ]
    )
    ids = lambda ordered: [f.fact_id for f in ordered]  # noqa: E731
    assert ids(apply_order(facts, ("z", "y", "x"))) == ["p1", "z", "y", "x"]
    assert ids(facts) == ["p1", "y", "x", "z"]  # rules order: weight ranks before feed stock (category order)
    assert ids(apply_order(facts, ("x",))) == ["p1", "x", "y", "z"]  # the rest keep their rules order
    assert ids(apply_order(facts, ("p1", "z", "z", "nope"))) == ["p1", "z", "y", "x"]  # unknown/pinned/dupes ignored
    assert ids(apply_order(facts, ())) == ids(facts)


# -- the closed-list ranking -----------------------------------------------------------------------------------------
def test_ranking_schema_is_one_array_of_allowed_ids_and_nothing_else():
    schema = ranking_schema(["b", "a"])
    assert schema["type"] == "object" and schema["required"] == ["order"]
    assert schema["additionalProperties"] is False and list(schema["properties"]) == ["order"]
    items = schema["properties"]["order"]
    assert items["items"]["enum"] == ["b", "a"] and items["uniqueItems"] is True and items["maxItems"] == 2


@pytest.mark.parametrize(
    "data",
    [
        {"order": ["a", "a"]},  # duplicate
        {"order": ["a", "zzz"]},  # an id outside the list (pinned ids are never on it)
        {"order": "a"},  # not a list
        {"order": [1]},  # not a string
        {"order": ["a"], "note": "free text"},  # an extra field
        {},  # missing
        ["a"],  # not an object
        None,
    ],
)
def test_a_bad_ranking_is_rejected(data):
    with pytest.raises(InvalidRanking):
        validate_ranking(data, frozenset({"a", "b"}))


def test_a_good_ranking_is_accepted_even_when_partial_or_empty():
    assert validate_ranking({"order": ["b", "a"]}, frozenset({"a", "b"})) == ("b", "a")
    assert validate_ranking({"order": ["b"]}, frozenset({"a", "b"})) == ("b",)
    assert validate_ranking({"order": []}, frozenset({"a", "b"})) == ()


def test_fingerprint_changes_with_any_number_and_not_with_input_order():
    a = _fact("a", Category.FEED_STOCK_LOW, Level.WATCH)
    b = _fact("b", Category.WEIGHT_BELOW_TARGET, Level.WATCH)
    assert fingerprint([a, b]) == fingerprint([b, a])
    changed = Fact(**{**a.__dict__, "values": {"days_covered": 1}})
    assert fingerprint([changed, b]) != fingerprint([a, b])
    assert fingerprint([a]) != fingerprint([a, b])


def test_the_item_caps_are_the_alexa_voice_rule():
    assert (MAX_ITEMS, SPOKEN_ITEMS) == (5, 3)
