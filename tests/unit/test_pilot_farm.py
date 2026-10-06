"""The pilot farm file (Step 51 part A): the farmer's real houses, nothing else. Strict: unknown fields (names,
coordinates) are refused, and a bad file is a loud error, never a fallback to the demo seed."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from clucktalk.pilot import PilotFarmError, build_pilot_farm, load_pilot_farm_file

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "docs" / "pilot_farm.example.json"
TODAY = date(2026, 10, 9)


def good() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def write(tmp_path, data) -> Path:
    p = tmp_path / "farm.json"
    p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return p


def test_the_example_file_builds_a_farm_with_no_records_at_all():
    farm = build_pilot_farm(load_pilot_farm_file(EXAMPLE), TODAY)
    assert farm.is_fictional is False
    assert [h.number for h in farm.houses] == [1, 2]
    assert all(h.records == () for h in farm.houses)
    assert farm.feed_price_per_kg == Decimal("40")
    assert farm.houses[0].birds_placed == 3000 and farm.houses[0].placed_on == date(2026, 9, 1)
    assert "farm-demo" not in farm.farm_id and "Lakshmi" not in farm.name


def test_the_feed_price_label_is_kept_word_for_word():
    cfg = load_pilot_farm_file(EXAMPLE)
    assert cfg.feed_price_label == "the builder's blend of your three feeds (49, 55 and 24 rupees per kg)"


@pytest.mark.parametrize("field", ["name", "owner_first_name", "latitude", "longitude", "location", "phone"])
def test_names_and_coordinates_are_refused(tmp_path, field):
    data = good()
    data[field] = "x"
    with pytest.raises(PilotFarmError, match="unknown field"):
        load_pilot_farm_file(write(tmp_path, data))


def test_a_house_with_a_name_is_refused(tmp_path):
    data = good()
    data["houses"][0]["name"] = "back shed"
    with pytest.raises(PilotFarmError, match="unknown field"):
        load_pilot_farm_file(write(tmp_path, data))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("houses"),
        lambda d: d.update(houses=[]),
        lambda d: d["houses"][0].update(number=0),
        lambda d: d["houses"][1].update(number=1),
        lambda d: d["houses"][0].update(birds_placed=0),
        lambda d: d["houses"][0].update(birds_placed=True),
        lambda d: d["houses"][0].update(birds_placed="3000"),
        lambda d: d["houses"][0].update(placed_on="01/09/2026"),
        lambda d: d["houses"][0].update(placed_on="2026-02-30"),
        lambda d: d.update(feed_price_per_kg_inr="0"),
        lambda d: d.update(feed_price_per_kg_inr="abc"),
        lambda d: d.update(feed_price_per_kg_inr=40),
        lambda d: d.pop("feed_price_label"),
        lambda d: d.update(feed_price_label=" "),
        lambda d: d.update(supplier_lead_days=-1),
        lambda d: d["houses"][0].update(kind="duck"),
        lambda d: d["houses"][0].update(feed_stock_kg=-1),
    ],
)
def test_every_bad_value_stops_the_load(tmp_path, mutate):
    data = good()
    mutate(data)
    with pytest.raises(PilotFarmError):
        load_pilot_farm_file(write(tmp_path, data))


def test_not_json_not_an_object_and_missing_file(tmp_path):
    for text in ("{", "[]", "null", ""):
        with pytest.raises(PilotFarmError):
            load_pilot_farm_file(write(tmp_path, text))
    with pytest.raises(PilotFarmError, match="not found"):
        load_pilot_farm_file(tmp_path / "nope.json")


def test_a_house_placed_in_the_future_is_refused_when_the_farm_is_built(tmp_path):
    data = good()
    data["houses"][0]["placed_on"] = "2026-12-01"
    with pytest.raises(PilotFarmError, match="future"):
        build_pilot_farm(load_pilot_farm_file(write(tmp_path, data)), TODAY)
