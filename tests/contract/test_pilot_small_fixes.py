"""Step 52 part D, the smaller fixes: /healthz says only ok or not ok on a pilot host, an unreachable MCP server is not
described to the client with its internal address, and copying the example deaths rule unchanged does not put
"Demo data." before the farmer's note in pilot mode (the demo still does)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import httpx2

from clucktalk.domain.daily_deaths import DailyDeathsRule
from clucktalk.domain.models import DailyRecord
from clucktalk.pilot import load_pilot_farm_file
from clucktalk.server.farm_state import IST, DemoFarmSource, PilotFarmSource
from clucktalk.server.tools.farm_status import build_status
from clucktalk.simulator.app import SimulatorSettings
from tests.contract.conftest import _free_port
from tests.contract.test_daily_deaths_display import Fixed
from tests.contract.test_pilot_hardening import TOKEN, rig  # noqa: F401  (the shared hardened pilot rig)
from tests.contract.test_simulator import _run

ROOT = Path(__file__).resolve().parents[2]
TODAY = date(2026, 10, 9)
NOW = datetime(2026, 10, 9, 8, 0, tzinfo=IST)
EXAMPLE_RULE = DailyDeathsRule(Decimal("2"), "Example note: replace this with your own words", True)


# -- /healthz --------------------------------------------------------------------------------------------------------
def test_a_pilot_health_check_says_only_ok_and_nothing_else(rig):  # noqa: F811
    r = httpx2.get(rig.base + "/healthz", timeout=10)
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_a_paused_pilot_says_not_ok_with_503_and_no_reason(rig):  # noqa: F811
    rig.settings.disabled_file.write_text("x", encoding="utf-8")
    r = httpx2.get(rig.base + "/healthz", timeout=10)
    assert r.status_code == 503 and r.json() == {"status": "not ok"}
    for word in ("pilot", "disabled", "paused", "demo", "mode"):
        assert word not in r.text.lower()
    rig.settings.disabled_file.unlink()
    assert httpx2.get(rig.base + "/healthz", timeout=10).json() == {"status": "ok"}


def test_an_unhardened_pilot_also_answers_only_ok(tmp_path):
    from tests.contract.test_pilot_hardening import start

    for r in start(tmp_path, tokens=()):
        assert httpx2.get(r.base + "/healthz", timeout=10).json() == {"status": "ok"}


def test_the_demo_health_check_is_unchanged():
    s, stop = _run(
        SimulatorSettings(port=_free_port(), mcp_url=f"http://127.0.0.1:{_free_port()}/mcp", auth_token=None)
    )
    try:
        assert httpx2.get(s.base + "/healthz", timeout=10).json() == {"status": "ok", "mode": "demo"}
    finally:
        stop()


# -- no internal address to the client --------------------------------------------------------------------------------
def _dead_pilot():
    dead = _free_port()  # nothing listens here
    return _run(
        SimulatorSettings(port=_free_port(), mcp_url=f"http://127.0.0.1:{dead}/mcp", auth_token=None, mode="pilot")
    ), dead


def test_an_unreachable_mcp_server_is_not_described_with_its_address_to_a_pilot_client():
    (sim, stop), dead = _dead_pilot()
    try:
        r = httpx2.post(
            sim.base + "/api/turn",
            json={"device": "dot", "lang": "te", "session": "session-aaaaaaaaaaaaaaaa", "chip": "help"},
            headers={"origin": sim.base},
            timeout=30,
        )
        out = r.json()
        assert out["kind"] == "unavailable" and out["is_error"] is True and out["speech_te"]
        blob = r.text
        for leak in (f"{dead}", "127.0.0.1", "http://", "/mcp", "ConnectError", "not reachable"):
            assert leak not in blob, leak
        assert out["detail"] == "the service did not answer"
    finally:
        stop()


def test_the_demo_developer_panel_still_gets_the_full_reason():
    dead = _free_port()
    sim, stop = _run(SimulatorSettings(port=_free_port(), mcp_url=f"http://127.0.0.1:{dead}/mcp", auth_token=None))
    try:
        out = httpx2.post(
            sim.base + "/api/turn", json={"utterance": "how is shed two"}, headers={"origin": sim.base}, timeout=30
        ).json()
        assert out["kind"] == "unavailable" and str(dead) in out["detail"]
    finally:
        stop()


def test_the_pilot_page_data_does_not_leak_it_either():
    (sim, stop), dead = _dead_pilot()
    try:
        r = httpx2.get(sim.base + "/api/pilot/ui", timeout=30)
        assert r.status_code == 200 and r.json()["houses"] == [] and str(dead) not in r.text
    finally:
        stop()


# -- the example deaths rule -----------------------------------------------------------------------------------------
def _pilot_with_deaths():
    source = PilotFarmSource(
        load_pilot_farm_file(ROOT / "docs" / "pilot_farm.example.json"), clock=lambda: TODAY, now=lambda: NOW
    )
    source.store.put_record(source.farm_id, "house-1", DailyRecord(TODAY, 9, 0.0))
    return source


def test_in_pilot_mode_the_example_rule_never_puts_demo_data_before_the_farmers_note():
    source = _pilot_with_deaths()
    source.deaths_rule = Fixed(EXAMPLE_RULE)
    out = build_status(source, "shed 1").model_dump(mode="json")
    assert out["text_en"].endswith("Your note: Example note: replace this with your own words.")
    assert "Demo data" not in out["text_en"] and "డెమో" not in out["text_te"]


def test_in_the_demo_the_example_rule_still_says_demo_data():
    source = DemoFarmSource(clock=lambda: date(2026, 9, 29))
    source.deaths_rule = Fixed(EXAMPLE_RULE)
    out = build_status(source, "shed 2").model_dump(mode="json")
    assert "Demo data. Your note: Example note" in out["text_en"]
