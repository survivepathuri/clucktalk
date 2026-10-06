"""overlay_house_records(add_missing=...): the demo overlay only replaces seeded days (unchanged); the pilot
overlay also adds days the house has no record for, so a pilot farm (no seed records) keeps what the farmer logged."""

from __future__ import annotations

from datetime import date

from clucktalk.domain.models import DailyRecord, House, HouseKind
from clucktalk.domain.records import overlay_house_records

PLACED = date(2026, 9, 1)


def house(records=()):
    return House("house-1", 1, HouseKind.BROILER, "x", PLACED, 1000, 0, 0.0, tuple(records))


def rec(day, deaths=1):
    return DailyRecord(day=day, deaths=deaths, feed_kg=0.0)


def test_default_drops_a_logged_day_the_house_does_not_have():
    h = house()
    assert overlay_house_records(h, {date(2026, 9, 5): rec(date(2026, 9, 5))}) == h


def test_add_missing_adds_it_and_keeps_days_sorted():
    h = house([rec(date(2026, 9, 7), 3)])
    out = overlay_house_records(h, {date(2026, 9, 5): rec(date(2026, 9, 5), 2)}, add_missing=True)
    assert [r.day for r in out.records] == [date(2026, 9, 5), date(2026, 9, 7)]


def test_add_missing_still_leaves_out_a_day_before_placement():
    h = house()
    out = overlay_house_records(h, {date(2026, 8, 30): rec(date(2026, 8, 30))}, add_missing=True)
    assert out == h


def test_a_logged_day_replaces_a_seeded_day_in_both_modes():
    d = date(2026, 9, 5)
    h = house([rec(d, 1)])
    for flag in (False, True):
        assert overlay_house_records(h, {d: rec(d, 4)}, add_missing=flag).records[0].deaths == 4
