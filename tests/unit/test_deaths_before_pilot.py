"""Step 52 part C: deaths_before_pilot, an optional per-house number in the pilot farm file. A house that is already
running when the pilot starts has lost some birds that were never logged here: the number is used for the live birds,
the room for further deaths and the cumulative mortality, and an impossible value stops the start."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from clucktalk.domain.errors import DeathsExceedLiveBirds
from clucktalk.domain.models import DailyRecord
from clucktalk.domain.status import Level, house_status
from clucktalk.pilot import PilotFarmError, build_pilot_farm, load_pilot_farm_file
from clucktalk.server.confirm import ConfirmFlow
from clucktalk.server.farm_state import IST, PilotFarmSource
from clucktalk.server.tools.records import build_log_record

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "docs" / "pilot_farm.example.json"
TODAY = date(2026, 10, 9)
NOW = datetime(2026, 10, 9, 8, 0, tzinfo=IST)


def farm_with(tmp_path, before=None, house=0, **extra):
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    if before is not None:
        data["houses"][house]["deaths_before_pilot"] = before
    data["houses"][house].update(extra)
    path = tmp_path / "farm.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_the_example_file_shows_the_field():
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert all("deaths_before_pilot" in h for h in data["houses"])


def test_it_defaults_to_zero_when_the_file_does_not_say(tmp_path):
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    for h in data["houses"]:
        h.pop("deaths_before_pilot", None)
    path = tmp_path / "farm.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    farm = build_pilot_farm(load_pilot_farm_file(path), TODAY)
    assert [h.deaths_before for h in farm.houses] == [0, 0]
    assert farm.houses[0].live_birds(TODAY) == 3000


def test_live_birds_use_it(tmp_path):
    farm = build_pilot_farm(load_pilot_farm_file(farm_with(tmp_path, 120)), TODAY)
    house = farm.houses[0]
    assert house.deaths_before == 120 and house.live_birds(TODAY) == 3000 - 120


def test_live_birds_use_it_together_with_logged_deaths(tmp_path):
    farm = build_pilot_farm(load_pilot_farm_file(farm_with(tmp_path, 120)), TODAY)
    house = farm.houses[0]
    from dataclasses import replace

    logged = replace(house, records=(DailyRecord(TODAY, 7, 0.0),))
    assert logged.live_birds(TODAY) == 3000 - 120 - 7


def test_cumulative_mortality_uses_it(tmp_path):
    def level(before):
        source = PilotFarmSource(
            load_pilot_farm_file(farm_with(tmp_path, before)), clock=lambda: TODAY, now=lambda: NOW
        )
        source.store.put_record(source.farm_id, "house-1", DailyRecord(TODAY, 1, 0.0))
        status = house_status(source.snapshot()[0].houses[0], TODAY)
        return status.level, status.cum_mortality_pct, status.live_birds

    assert level(0)[0] is Level.OK and level(0)[1] == pytest.approx(0.03, abs=0.01)  # 1 of 3000
    watch_level, pct, live = level(200)  # 201 of 3000 is 6.7 percent: above the general 5 percent line
    assert watch_level is Level.WATCH and pct == pytest.approx(6.7, abs=0.01) and live == 2799


def test_room_for_further_deaths_uses_it(tmp_path):
    source = PilotFarmSource(load_pilot_farm_file(farm_with(tmp_path, 2990)), clock=lambda: TODAY, now=lambda: NOW)
    flow = ConfirmFlow(source.store, source.now)
    with pytest.raises(DeathsExceedLiveBirds) as err:
        build_log_record(source, flow, "shed 1", None, 11, None, None, None, None, None, None)
    assert err.value.values["max_possible"] == 10  # 3000 placed, 2990 gone before the pilot
    ok = build_log_record(source, flow, "shed 1", None, 10, None, None, None, None, None, None)
    assert ok.status == "needs_confirmation"


@pytest.mark.parametrize("bad", [-1, 3001, True, "5", 2.5])
def test_an_out_of_range_or_wrong_type_stops_the_load(tmp_path, bad):
    with pytest.raises(PilotFarmError, match="deaths_before_pilot"):
        load_pilot_farm_file(farm_with(tmp_path, bad))


def test_the_whole_flock_gone_is_allowed_by_the_file_but_the_birds_placed_is_the_limit(tmp_path):
    assert load_pilot_farm_file(farm_with(tmp_path, 3000)).houses[0].deaths_before_pilot == 3000
    with pytest.raises(PilotFarmError):
        load_pilot_farm_file(farm_with(tmp_path, 3001))


def test_it_is_per_house(tmp_path):
    farm = build_pilot_farm(load_pilot_farm_file(farm_with(tmp_path, 40, house=1)), TODAY)
    assert [h.deaths_before for h in farm.houses] == [0, 40]


def test_a_house_cannot_be_built_with_more_gone_than_placed():
    from clucktalk.domain.models import House, HouseKind

    with pytest.raises(ValueError, match="deaths_before"):
        House("house-1", 1, HouseKind.BROILER, "x", date(2026, 9, 1), 100, 0, 0.0, (), 101)
    with pytest.raises(ValueError):
        House(
            "house-1",
            1,
            HouseKind.BROILER,
            "x",
            date(2026, 9, 1),
            100,
            0,
            0.0,
            (DailyRecord(date(2026, 9, 2), 60, 0.0),),
            50,
        )
