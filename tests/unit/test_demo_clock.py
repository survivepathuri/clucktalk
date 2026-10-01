"""The demo clock (docs/DESIGN.md §18): a Simulator/CLI/env setting that shifts the farmer's "today" for the video and
the golden cases. Never a tool, never in live mode, never changes stored data."""

from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path

import pytest

from clucktalk.config import ConfigError, load_settings
from clucktalk.server.farm_state import IST, DemoClock, DemoFarmSource

REAL = datetime(2026, 9, 29, 10, 0, tzinfo=IST)
SRC = Path(__file__).resolve().parents[2] / "src" / "clucktalk"


def test_a_clock_that_is_off_is_exactly_real_time():
    clock = DemoClock(0, real_now=lambda: REAL)
    assert clock.now() == REAL and clock.today() == REAL.date() and clock.days_later == 0


def test_the_clock_shifts_today_and_now_by_whole_days():
    clock = DemoClock(3, real_now=lambda: REAL)
    assert clock.today() == datetime(2026, 10, 2).date()
    assert clock.now() == datetime(2026, 10, 2, 10, 0, tzinfo=IST)


def test_the_days_can_be_moved_in_process_for_the_eval_runner():
    clock = DemoClock(0, real_now=lambda: REAL)
    clock.set_days_later(2)
    assert clock.today() == datetime(2026, 10, 1).date() and clock.days_later == 2


@pytest.mark.parametrize("bad", [-1, 31, 1.5, True])
def test_the_days_must_be_a_whole_number_from_zero_to_thirty(bad):
    with pytest.raises(ValueError, match="0 to 30"):
        DemoClock(bad)
    with pytest.raises(ValueError, match="0 to 30"):
        DemoClock(0).set_days_later(bad)


def test_a_source_without_a_demo_clock_reports_zero_days():
    assert DemoFarmSource().demo_clock_days == 0


def test_a_source_with_a_demo_clock_uses_it_for_today_and_now():
    clock = DemoClock(3, real_now=lambda: REAL)
    source = DemoFarmSource(demo_clock=clock)
    assert source.demo_clock_days == 3
    assert source.snapshot()[1] == datetime(2026, 10, 2).date()
    assert source.now() == datetime(2026, 10, 2, 10, 0, tzinfo=IST)
    clock.set_days_later(0)
    assert source.demo_clock_days == 0


def test_the_default_is_off():
    assert load_settings({"MOCK_BEDROCK": "true"}).demo_days_later == 0


def test_the_env_var_turns_it_on_in_demo_mode():
    assert load_settings({"MOCK_BEDROCK": "true", "CLUCKTALK_DEMO_DAYS_LATER": "3"}).demo_days_later == 3


@pytest.mark.parametrize("env", [{}, {"MOCK_BEDROCK": "false"}])
def test_live_mode_refuses_the_demo_clock_with_a_clear_error(env):
    with pytest.raises(ConfigError, match="CLUCKTALK_DEMO_DAYS_LATER.*MOCK_BEDROCK=true"):
        load_settings({**env, "CLUCKTALK_DEMO_DAYS_LATER": "3"})


@pytest.mark.parametrize("bad", ["x", "-1", "31", "1.5"])
def test_a_malformed_value_fails_loudly(bad):
    with pytest.raises(ConfigError, match="CLUCKTALK_DEMO_DAYS_LATER"):
        load_settings({"MOCK_BEDROCK": "true", "CLUCKTALK_DEMO_DAYS_LATER": bad})


def test_zero_in_live_mode_is_not_a_demo_clock():
    assert load_settings({"CLUCKTALK_DEMO_DAYS_LATER": "0"}).demo_days_later == 0


def test_real_time_is_read_in_one_place_only():
    """Only ``now_ist`` in farm_state reads the system clock; everything else gets time injected."""
    readers = {("datetime", "now"), ("date", "today"), ("datetime", "utcnow"), ("time", "time"), ("time", "time_ns")}
    offenders = []
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                owner = node.func.value
                name = owner.id if isinstance(owner, ast.Name) else getattr(owner, "attr", "")
                if (name, node.func.attr) in readers:
                    offenders.append((path.relative_to(SRC).as_posix(), node.lineno))
    assert [file for file, _ in offenders] == ["server/farm_state.py"], offenders
