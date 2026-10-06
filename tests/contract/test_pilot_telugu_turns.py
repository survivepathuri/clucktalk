"""Step 51 part C: the Simulator's pilot turns in Telugu, over real HTTP, against the real MCP tools on the pilot farm.

Every write is read back and confirmed first (a tap or a typed yes); a stray yes with nothing waiting does nothing;
chips never touch the text matcher; each browser session has its own conversation; the English path is unchanged."""

from __future__ import annotations

import threading
import time
from datetime import date, datetime
from pathlib import Path

import httpx2
import pytest
import uvicorn

from clucktalk.i18n.pilot import HOST_NOT_STARTED, NOT_UNDERSTOOD, NOTHING_PENDING
from clucktalk.pilot import load_pilot_farm_file
from clucktalk.server.farm_state import IST, PilotFarmSource
from clucktalk.simulator import app as sim_app
from clucktalk.simulator.app import SimulatorSettings, build_app
from clucktalk.simulator.mcp_client import McpClient
from tests.contract.conftest import _free_port, _start

ROOT = Path(__file__).resolve().parents[2]
TODAY = date(2026, 10, 9)
NOW = datetime(2026, 10, 9, 8, 0, tzinfo=IST)
A = "session-aaaaaaaaaaaaaaaa"
B = "session-bbbbbbbbbbbbbbbb"


class Spy(McpClient):
    calls: list[tuple[str, dict]]

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.calls = []

    async def request(self, method, params=None):
        if method == "tools/call":
            self.calls.append((params["name"], dict(params["arguments"])))
        return await super().request(method, params)


class Rig:
    def __init__(self, source, spy, base):
        self.source, self.spy, self.base = source, spy, base

    def post(self, path, body, origin=True):
        headers = {"origin": self.base} if origin else {}
        return httpx2.post(self.base + path, json=body, headers=headers, timeout=20)

    def turn(self, session=A, **body):
        r = self.post("/api/turn", {"device": "dot", "session": session, **body})
        assert r.status_code == 200, r.text
        return r.json()


@pytest.fixture
def rig():
    source = PilotFarmSource(
        load_pilot_farm_file(ROOT / "docs" / "pilot_farm.example.json"), clock=lambda: TODAY, now=lambda: NOW
    )
    mcp, stop_mcp = _start({}, source=source)
    port = _free_port()
    settings = SimulatorSettings(port=port, mcp_url=mcp.url, auth_token=None, mode="pilot")
    spy = Spy(settings.mcp_url, None)
    uv = uvicorn.Server(uvicorn.Config(build_app(settings, spy), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not uv.started:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    yield Rig(source, spy, f"http://127.0.0.1:{port}")
    uv.should_exit = True
    thread.join(timeout=10)
    stop_mcp()


def stored(rig, house="house-1"):
    return rig.source.store.records(rig.source.farm_id, house)


def test_a_session_is_required_in_pilot_mode(rig):
    for body in (
        {"utterance": "x"},
        {"utterance": "x", "session": "short"},
        {"utterance": "x", "session": "bad token!!!!!!!!!!!!"},
    ):
        assert rig.post("/api/turn", body).status_code == 400


def test_telugu_deaths_are_read_back_first_and_saved_only_after_a_yes(rig):
    out = rig.turn(utterance="షెడ్ 1 లో 3 కోళ్లు చనిపోయాయి", lang="te")
    assert out["intent"]["tool"] == "log_daily_record" and out["awaiting_answer"] is True
    assert out["speech_te"].strip() and out["speech_te"] != out["speech"]
    assert rig.spy.calls == [("log_daily_record", {"house": "shed 1", "deaths": 3})]  # no proposal_id, no answer
    assert stored(rig) == ()  # nothing saved by the read-back
    done = rig.turn(utterance="అవును", lang="te")
    assert done["intent"]["arguments"]["answer"] == "yes" and "proposal_id" in done["intent"]["arguments"]
    assert [r.deaths for r in stored(rig)] == [3]


def test_a_tap_on_the_yes_button_is_the_same_as_saying_yes(rig):
    rig.turn(utterance="షెడ్ 1 లో 2 మరణాలు", lang="te")
    rig.turn(chip="yes", lang="te")
    assert [r.deaths for r in stored(rig)] == [2]


def test_no_and_a_tap_on_no_save_nothing(rig):
    rig.turn(utterance="షెడ్ 1 లో 4 కోళ్లు చనిపోయాయి", lang="te")
    out = rig.turn(utterance="వద్దు", lang="te")
    assert stored(rig) == () and out["intent"]["arguments"]["answer"] == "no"
    rig.turn(utterance="షెడ్ 1 లో 4 కోళ్లు చనిపోయాయి", lang="te")
    rig.turn(chip="no", lang="te")
    assert stored(rig) == ()


def test_a_stray_yes_with_nothing_waiting_does_nothing_at_all(rig):
    for utterance in ("అవును", "సరే", "yes"):
        out = rig.turn(utterance=utterance, lang="te")
        assert out["kind"] == "fallback" and out["speech_te"] == NOTHING_PENDING.te
        assert out["intent"] is None
    assert rig.turn(chip="yes", lang="te")["speech_te"] == NOTHING_PENDING.te
    assert [c for c in rig.spy.calls if c[0] != "get_record_book"] == []
    assert stored(rig) == ()


def test_a_new_request_replaces_the_waiting_read_back_so_an_old_yes_cannot_apply(rig):
    rig.turn(utterance="షెడ్ 1 లో 4 కోళ్లు చనిపోయాయి", lang="te")
    rig.turn(utterance="ఫారం ఎలా ఉంది", lang="te")  # the farmer moved on
    out = rig.turn(utterance="అవును", lang="te")
    assert out["kind"] == "fallback" and stored(rig) == ()


def test_the_first_call_of_every_write_has_no_proposal_and_no_answer(rig):
    for utterance in ("షెడ్ 1 లో 1 కోళ్లు చనిపోయాయి", "షెడ్ 2 లో మరణాలు లేవు", "షెడ్ 1 బాగుంది", "షెడ్ 2 అలాగే ఉంది"):
        rig.spy.calls.clear()
        rig.turn(utterance=utterance, lang="te")
        for name, args in rig.spy.calls:
            if name in ("log_daily_record", "report_health_follow_up"):
                assert "proposal_id" not in args and "answer" not in args, (utterance, name, args)
        rig.turn(chip="no", lang="te")  # leave nothing waiting


def test_chips_never_touch_the_text_matcher(rig, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a chip went through a text matcher")

    monkeypatch.setattr(sim_app, "match_te", boom)
    monkeypatch.setattr(sim_app, "match", boom)
    monkeypatch.setattr(sim_app, "yes_no", boom)
    out = rig.turn(chip="help", lang="te")
    assert out["kind"] == "tool" and out["intent"]["tool"] == "get_help"
    out = rig.turn(chip="deaths", params={"house": 1, "count": 2}, lang="te")
    assert out["intent"]["arguments"] == {"house": "shed 1", "deaths": 2} and out["awaiting_answer"] is True
    assert rig.turn(chip="no", lang="te")["kind"] == "tool"


def test_a_bad_chip_or_params_is_refused_without_any_call(rig):
    before = list(rig.spy.calls)
    for body in (
        {"chip": "nope"},
        {"chip": "deaths", "params": {"house": 1}},
        {"chip": "deaths", "params": {"house": 1, "count": -3}},
        {"chip": "health", "params": {"house": 1, "signs": ["made_up"]}},
        {"chip": 5},
        {"chip": "help", "params": []},
    ):
        r = rig.post("/api/turn", {"device": "dot", "session": A, "lang": "te", **body})
        assert r.status_code == 400, body
    assert rig.spy.calls == before


def test_two_sessions_never_share_a_conversation(rig):
    rig.turn(session=A, utterance="షెడ్ 1 లో 5 కోళ్లు చనిపోయాయి", lang="te")
    stray = rig.turn(session=B, utterance="అవును", lang="te")  # B has nothing waiting, whatever A did
    assert stray["kind"] == "fallback" and stored(rig) == ()
    rig.turn(session=A, utterance="అవును", lang="te")
    assert [r.deaths for r in stored(rig)] == [5]


def test_two_sessions_can_both_have_a_read_back_waiting(rig):
    rig.turn(session=A, utterance="షెడ్ 1 లో 1 కోళ్లు చనిపోయాయి", lang="te")
    rig.turn(session=B, utterance="షెడ్ 2 లో 2 కోళ్లు చనిపోయాయి", lang="te")
    assert rig.turn(session=B, utterance="అవును", lang="te")["kind"] == "tool"
    assert [r.deaths for r in stored(rig, "house-2")] == [2]


def test_a_missing_number_or_shed_asks_and_calls_nothing(rig):
    out = rig.turn(utterance="షెడ్ 2 లో కోళ్లు చనిపోయాయి", lang="te")
    assert (
        out["kind"] == "choose"
        and out["choose"] == {"chip": "deaths", "params": {"house": 2}}
        and out["intent"] is None
    )
    out = rig.turn(utterance="3 కోళ్లు చనిపోయాయి", lang="te")
    assert out["choose"] == {"chip": "deaths", "params": {"count": 3}}
    assert [c for c in rig.spy.calls if c[0] == "log_daily_record"] == []


def test_something_not_understood_says_so_in_telugu_and_calls_nothing(rig):
    for text in ("నమస్కారం", "????", "షెడ్ 2 లో రెండు మూడు చనిపోయాయి"):
        out = rig.turn(utterance=text, lang="te")
        assert out["kind"] == "fallback" and out["speech_te"] == NOT_UNDERSTOOD.te
    assert [c for c in rig.spy.calls if c[0] == "log_daily_record"] == []


def test_a_health_check_is_read_back_by_the_host_before_it_is_started(rig):
    out = rig.turn(chip="health", params={"house": 1, "signs": ["coughing", "sneezing"]}, lang="te")
    assert out["kind"] == "host_readback" and out["awaiting_answer"] is True
    assert "షెడ్ 1" in out["speech_te"] and "దగ్గు" in out["speech_te"]
    assert [c for c in rig.spy.calls if c[0] == "start_health_check"] == []  # nothing started yet
    done = rig.turn(chip="yes", lang="te")
    assert done["intent"]["tool"] == "start_health_check" and done["kind"] == "tool"
    assert [c[0] for c in rig.spy.calls if c[0] == "start_health_check"] == ["start_health_check"]


def test_declining_the_health_check_starts_nothing(rig):
    rig.turn(chip="health", params={"house": 1, "signs": ["coughing"]}, lang="te")
    out = rig.turn(utterance="వద్దు", lang="te")
    assert out["speech_te"] == HOST_NOT_STARTED.te and out["intent"] is None
    assert [c for c in rig.spy.calls if c[0] == "start_health_check"] == []


def test_the_pilot_page_loads_its_words_and_the_farmers_sheds(rig):
    ui = httpx2.get(rig.base + "/api/pilot/ui", timeout=20).json()
    assert [h["number"] for h in ui["houses"]] == [1, 2] and all(h["label_te"] for h in ui["houses"])
    assert {s["code"] for s in ui["signs"]} >= {"coughing", "sneezing"} and all(s["label_te"] for s in ui["signs"])
    assert list(ui["chips"]) == ["deaths", "no_deaths", "status", "briefing", "health", "sale", "follow_up", "help"]
    assert ui["strings"]["notice"]["te"].strip() and ui["strings"]["badge"]["en"] == "Pilot (real farm, prototype)"
    assert set(ui["outcomes"]) == {"better", "same", "worse"}


def test_the_pilot_page_is_served_at_the_root_with_the_badge_and_no_demo_wording(rig):
    html = httpx2.get(rig.base + "/", timeout=10).text
    assert "Pilot (real farm, prototype)" in html and 'lang="te"' in html
    assert "Demo data" not in html and "mock host" not in html and "fictional" not in html.lower()
    assert "/static/pilot.js" in html
    desk = httpx2.get(rig.base + "/desktop", timeout=10).text
    assert "Pilot (real farm, prototype)" in desk and "Demo data" not in desk


def test_the_english_path_still_works_in_pilot_mode_and_still_reads_back(rig):
    out = rig.turn(utterance="3 birds died in shed 1")
    assert out["intent"]["tool"] == "log_daily_record" and out["awaiting_answer"] is True
    assert stored(rig) == ()
    rig.turn(utterance="yes")
    assert [r.deaths for r in stored(rig)] == [3]


def test_telugu_digits_and_number_words_reach_the_tool_as_numbers(rig):
    rig.turn(utterance="షెడ్ ౧ లో ఇరవై ఐదు కోళ్లు చనిపోయాయి", lang="te")
    assert rig.spy.calls[-1] == ("log_daily_record", {"house": "shed 1", "deaths": 25})


def test_a_chip_never_touches_a_matcher_whatever_language_the_page_says(rig, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a chip went through a text matcher")

    monkeypatch.setattr(sim_app, "match", boom)
    monkeypatch.setattr(sim_app, "match_te", boom)
    for lang in ({}, {"lang": "en"}):
        out = rig.turn(chip="briefing", **lang)
        assert out["kind"] == "tool" and out["intent"]["tool"] == "get_daily_briefing"
