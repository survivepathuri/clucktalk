"""daily_deaths_rule.json with ``age_bands`` (the farmer's own per-day limit by age). Strict like the rest of the file:
a bad file is a loud error, and a file without ``age_bands`` reads exactly as it did."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from clucktalk.domain.daily_deaths import AgeBand
from clucktalk.server.daily_deaths import DeathsRuleError, load_deaths_rule, parse_rule

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "docs" / "daily_deaths_limit.example.json"
TABLE = [{"from_day": 0, "to_day": 29, "max_deaths_per_day": 6}, {"from_day": 30, "max_deaths_per_day": 3}]


def test_the_farmers_table_parses_to_two_bands_and_no_per_1000_number():
    rule = parse_rule({"age_bands": TABLE, "note": "n", "is_example": False})
    assert rule.age_bands == (AgeBand(0, 29, 6), AgeBand(30, None, 3))
    assert rule.per_1000_live is None and rule.note == "n" and rule.is_example is False


def test_both_fields_can_be_given():
    rule = parse_rule({"per_1000_live": 2, "age_bands": TABLE})
    assert rule.per_1000_live == Decimal("2") and len(rule.age_bands) == 2


def test_a_file_without_bands_reads_exactly_as_before():
    rule = parse_rule({"per_1000_live": 2, "note": "x", "is_example": True})
    assert rule.age_bands == () and rule.per_1000_live == Decimal("2")


def test_a_comment_is_allowed_kept_out_of_the_rule_and_limited():
    rule = parse_rule({"age_bands": TABLE, "comment": "he counts the arrival day as day 1"})
    assert not hasattr(rule, "comment") and rule.note is None
    with pytest.raises(DeathsRuleError):
        parse_rule({"age_bands": TABLE, "comment": "x" * 301})
    with pytest.raises(DeathsRuleError):
        parse_rule({"age_bands": TABLE, "comment": 5})


def test_the_example_file_has_the_farmers_table_marked_as_an_example_and_loads():
    rule = load_deaths_rule(EXAMPLE)
    assert rule is not None and rule.is_example is True
    assert rule.age_bands == (AgeBand(0, 29, 6), AgeBand(30, None, 3))
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert "example" in data["comment"].lower() and "day 1" in data["comment"] and "age 30" in data["comment"]
    assert "every shed" in data["comment"].lower()


def _bands(*bands):
    return {"age_bands": list(bands)}


def b(frm, to, mx):
    d = {"from_day": frm, "max_deaths_per_day": mx}
    if to is not None:
        d["to_day"] = to
    return d


@pytest.mark.parametrize(
    "data",
    [
        {},  # neither field
        {"note": "only a note"},
        {"age_bands": []},  # empty list
        {"age_bands": "x"},
        {"age_bands": {"from_day": 0}},
        {"age_bands": [b(0, 9, 6)] * 5},  # more than 4 bands
        _bands(b(0, 9, 0)),  # a limit must be positive
        _bands(b(0, 9, -1)),
        _bands(b(0, 9, 10001)),  # above the sanity ceiling
        _bands(b(0, 9, 2.5)),
        _bands(b(0, 9, True)),
        _bands(b(0, 9, "6")),
        _bands(b(-1, 9, 6)),
        _bands(b(True, 9, 6)),
        _bands(b(0.5, 9, 6)),
        _bands(b(5, 4, 6)),  # to_day before from_day
        _bands(b(0, 9, 6), b(9, None, 3)),  # overlap on day 9
        _bands(b(0, 20, 6), b(10, None, 3)),  # overlap
        _bands(b(30, None, 3), b(0, 29, 6)),  # not in order
        _bands(b(0, None, 6), b(30, None, 3)),  # an open end that is not the last band
        _bands({"from_day": 0, "to_day": 9}),  # no limit
        _bands({"to_day": 9, "max_deaths_per_day": 6}),  # no from_day
        _bands({"from_day": 0, "to_day": 9, "max_deaths_per_day": 6, "extra": 1}),
        _bands("x"),
        {"age_bands": TABLE, "unknown": 1},
        {"age_bands": TABLE, "per_1000_live": 0},  # an invalid number is still invalid beside the bands
        {"age_bands": TABLE, "is_example": "yes"},
        {"age_bands": TABLE, "note": 5},
    ],
)
def test_every_bad_bands_file_is_refused(data):
    with pytest.raises(DeathsRuleError):
        parse_rule(data)


def test_adjacent_bands_and_a_gap_are_fine_and_a_single_band_is_fine():
    assert len(parse_rule(_bands(b(0, 9, 6), b(10, 19, 5))).age_bands) == 2
    assert len(parse_rule(_bands(b(0, 9, 6), b(20, None, 3))).age_bands) == 2  # days 10 to 19 have no limit
    assert parse_rule(_bands(b(0, None, 6))).age_bands == (AgeBand(0, None, 6),)
    assert parse_rule(_bands(b(5, 5, 1))).age_bands == (AgeBand(5, 5, 1),)  # a one-day band


def test_four_separate_bands_are_fine_and_a_fifth_is_refused():
    four = [b(0, 9, 6), b(10, 19, 5), b(20, 29, 4), b(30, None, 3)]
    assert len(parse_rule(_bands(*four)).age_bands) == 4
    five = [b(0, 9, 6), b(10, 19, 5), b(20, 29, 4), b(30, 39, 3), b(40, None, 2)]
    with pytest.raises(DeathsRuleError, match="1 to 4 bands"):
        parse_rule(_bands(*five))
