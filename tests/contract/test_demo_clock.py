"""The demo clock over real HTTP (docs/DESIGN.md §18): no tool can set it, the marker shows only when it is on, and a
restart keeps what is stored."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

from clucktalk.server.farm_state import IST, DemoClock, DemoFarmSource
from clucktalk.store.sqlite import SqliteStore
from tests.contract.conftest import _start

REAL = datetime(2026, 9, 29, 10, 0, tzinfo=IST)
MARKER_KEY = "clucktalk/demo_clock"
FORBIDDEN_NAMES = re.compile(r"clock|demo|days_later|as_of|today|\bnow\b|offset", re.IGNORECASE)


def _server(days: int, store=None):
    clock = DemoClock(days, real_now=lambda: REAL)
    source = DemoFarmSource(demo_clock=clock, store=store)
    srv, stop = _start({}, source=source)
    sid, _ = srv.initialize()
    return srv, sid, source, stop


def _call(srv, sid, name, **arguments):
    return srv.call(sid, "tools/call", {"name": name, "arguments": arguments})["result"]


def _checks(source):
    return [(c.check_id, c.created_at) for c in source.store.recent_health_checks(source.farm_id, "house-1", date.min)]


def test_no_tool_name_or_argument_can_set_the_clock():
    srv, sid, _, stop = _server(0)
    try:
        tools = srv.call(sid, "tools/list")["result"]["tools"]
        assert len(tools) >= 13
        for tool in tools:
            assert not FORBIDDEN_NAMES.search(tool["name"]), tool["name"]
            for prop in tool["inputSchema"].get("properties", {}):
                assert not FORBIDDEN_NAMES.search(prop), (tool["name"], prop)
    finally:
        stop()


def test_an_argument_that_tries_to_set_it_changes_nothing_and_shows_no_marker():
    srv, sid, source, stop = _server(0)
    try:
        result = _call(srv, sid, "get_farm_status", house="shed one", demo_days_later=5)
        assert MARKER_KEY not in (result.get("_meta") or {})
        assert source.demo_clock_days == 0
        assert source.snapshot()[1] == REAL.date()
    finally:
        stop()


def test_nothing_says_demo_clock_when_it_is_off():
    srv, sid, _, stop = _server(0)
    try:
        for name in ("get_farm_status", "get_daily_briefing", "get_help"):
            result = _call(srv, sid, name)
            assert MARKER_KEY not in (result.get("_meta") or {}), name
            assert "demo clock" not in json.dumps(result, ensure_ascii=False).lower(), name
    finally:
        stop()


def test_the_marker_is_on_every_result_when_it_is_on():
    srv, sid, _, stop = _server(3)
    try:
        for name in ("get_farm_status", "get_daily_briefing", "get_help"):
            marker = (_call(srv, sid, name).get("_meta") or {}).get(MARKER_KEY)
            assert marker is not None, name
            assert marker["days_later"] == 3 and marker["label_en"] == "Demo clock: +3 days", name
            assert "+3" in marker["label_te"], name
    finally:
        stop()


def test_one_day_is_singular_and_the_marker_never_enters_structured_content():
    srv, sid, _, stop = _server(1)
    try:
        result = _call(srv, sid, "get_farm_status")
        assert result["_meta"][MARKER_KEY]["label_en"] == "Demo clock: +1 day"
        assert "demo_clock" not in json.dumps(result["structuredContent"])  # the output schema stays closed
    finally:
        stop()


def test_the_clock_only_shifts_today_and_a_restart_keeps_stored_data_unchanged(tmp_path):
    path = tmp_path / "farm.sqlite3"
    store = SqliteStore(path)
    srv, sid, source, stop = _server(0, store)
    try:
        started = _call(srv, sid, "start_health_check", house="shed one", signs=["coughing"])
        assert started.get("isError") in (None, False), started
        before = _checks(source)
        assert len(before) == 1
    finally:
        stop()
    store.close()

    store2 = SqliteStore(path)  # a restart, three days later
    srv, sid, source2, stop = _server(3, store2)
    try:
        briefing = _call(srv, sid, "get_daily_briefing")
        assert "3 days ago" in json.dumps(briefing, ensure_ascii=False), "the briefing asks the follow-up"
        assert _checks(source2) == before
        assert source2.now() == REAL + timedelta(days=3)
    finally:
        stop()
    store2.close()
