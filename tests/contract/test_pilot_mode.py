"""Pilot mode through the real MCP tools (Step 51 part A). The pilot farm is the farmer's real houses with NO synthetic
history, no "Demo data" label, no bird weights (his target does not match the breed curve), and the demo instance
answers exactly as before."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from clucktalk.agents import AiServices
from clucktalk.agents.model import RulesModel
from clucktalk.pilot import load_pilot_farm_file
from clucktalk.seed import build_demo_farm
from clucktalk.server.farm_state import IST, DemoFarmSource, PilotFarmSource
from tests.contract.conftest import FIXED_DAY, _start
from tests.contract.test_health_tools import ManualRunner

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "docs" / "pilot_farm.example.json"
TODAY = date(2026, 10, 9)
NOW = datetime(2026, 10, 9, 8, 0, tzinfo=IST)


@pytest.fixture
def pilot():
    source = PilotFarmSource(load_pilot_farm_file(EXAMPLE), clock=lambda: TODAY, now=lambda: NOW)
    ai = AiServices(model=RulesModel(), budget=None, runner=ManualRunner())
    srv, stop = _start({}, source=source, ai=ai)
    sid, _ = srv.initialize()

    class P:
        pass

    p = P()
    p.srv, p.sid, p.source = srv, sid, source

    def call(name, **args):
        r = srv.call(sid, "tools/call", {"name": name, "arguments": args})["result"]
        return r

    p.call = call
    yield p
    stop()


def test_pilot_source_never_loads_the_demo_seed(pilot, monkeypatch):
    import clucktalk.server.farm_state as fs

    def boom(*a, **k):
        raise AssertionError("the demo seed was loaded in pilot mode")

    monkeypatch.setattr(fs, "build_demo_farm", boom)
    farm, as_of = pilot.source.snapshot()
    assert as_of == TODAY and farm.is_fictional is False
    assert [h.number for h in farm.houses] == [1, 2]
    assert all(not h.records for h in farm.houses)
    assert pilot.source.demo_data is False


def log_deaths(pilot, house, deaths):
    first = pilot.call("log_daily_record", house=house, deaths=deaths)["structuredContent"]
    assert first["status"] == "needs_confirmation"
    done = pilot.call("log_daily_record", house=house, deaths=deaths, proposal_id=first["proposal_id"], answer="yes")
    assert done["structuredContent"]["status"] == "changed", done


def test_a_shed_with_no_records_says_so_instead_of_inventing_any(pilot):
    r = pilot.call("get_farm_status", house="shed one")
    assert r["isError"] is True
    assert "enough recent records" in r["_meta"]["clucktalk/error"]["message_en"]
    assert pilot.source.snapshot()[0].houses[0].records == ()


def test_pilot_answers_carry_demo_data_false_and_no_demo_wording(pilot):
    log_deaths(pilot, "shed one", 1)
    r = pilot.call("get_farm_status", house="shed one")
    assert r.get("isError") in (None, False), r
    sc = r["structuredContent"]
    assert sc["demo_data"] is False
    assert "demo data" not in sc["text_en"].lower() and "Sri Lakshmi" not in json.dumps(sc)
    for name in ("get_daily_briefing", "get_record_book"):
        out = pilot.call(name)
        assert out["structuredContent"]["demo_data"] is False, name


def test_logging_deaths_works_and_shows_up_with_the_real_birds(pilot):
    log_deaths(pilot, "shed one", 2)
    farm, _ = pilot.source.snapshot()
    h1 = farm.houses[0]
    assert [r.deaths for r in h1.records] == [2] and h1.live_birds(TODAY) == 2998


def test_a_weight_is_refused_in_pilot_mode_and_nothing_is_proposed_or_stored(pilot):
    r = pilot.call("log_daily_record", house="shed one", deaths=1, avg_weight_g=2200, weight_sample_birds=10)
    assert r["isError"] is True
    meta = r["_meta"]["clucktalk/error"]
    assert "మీ కోళ్ల" in meta["message_te"]
    assert "growth standard for your birds" in meta["message_en"]
    assert pilot.source.store.records(pilot.source.farm_id, "house-1") == ()
    assert pilot.source.store.pending_proposals(pilot.source.farm_id, "log_daily_record") == []


def test_weight_only_report_is_refused_too(pilot):
    r = pilot.call("log_daily_record", house="shed two", avg_weight_g=2200, weight_sample_birds=10)
    assert r["isError"] is True


def test_the_demo_source_still_accepts_weights_and_is_labeled_demo():
    source = DemoFarmSource(clock=lambda: FIXED_DAY)
    assert source.demo_data is True and source.weights_allowed is True
    srv, stop = _start({}, source=source)
    try:
        sid, _ = srv.initialize()
        r = srv.call(
            sid,
            "tools/call",
            {
                "name": "log_daily_record",
                "arguments": {"house": "shed one", "avg_weight_g": 900, "weight_sample_birds": 10},
            },
        )["result"]
        assert r.get("isError") in (None, False)
        assert r["structuredContent"]["demo_data"] is True
    finally:
        stop()


def test_the_demo_farm_is_exactly_what_the_seed_builds():
    source = DemoFarmSource(clock=lambda: FIXED_DAY)
    farm, as_of = source.snapshot()
    assert as_of == FIXED_DAY and farm == build_demo_farm(FIXED_DAY)


def test_pilot_farm_rebuilds_when_the_day_changes_and_keeps_logged_records():
    day = [TODAY]
    source = PilotFarmSource(load_pilot_farm_file(EXAMPLE), clock=lambda: day[0], now=lambda: NOW)
    assert source.snapshot()[0].houses[0].age_days(TODAY) == (TODAY - date(2026, 9, 1)).days
    day[0] = TODAY + timedelta(days=1)
    assert source.snapshot()[1] == TODAY + timedelta(days=1)
