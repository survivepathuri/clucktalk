"""The Questions button over real HTTP on the pilot host: the page is told only the questions whose data the farmer
gave, a tapped question is answered from his own schedule (no tool call, no model), every answer starts with "As you
told us:" and never says confirmed or expert, and anything that is not an offered question is refused."""

from __future__ import annotations

import copy
import json
import threading
import time
from datetime import date, datetime
from pathlib import Path

import httpx2
import pytest
import uvicorn

from clucktalk.pilot import load_pilot_farm_file
from clucktalk.server.farm_state import IST, PilotFarmSource
from clucktalk.simulator import app as sim_app
from clucktalk.simulator.app import SimulatorSettings, build_app
from tests.contract.conftest import _free_port, _start
from tests.contract.test_pilot_telugu_turns import Rig, Spy

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "docs" / "pilot_farm.example.json"
TODAY = date(2026, 10, 9)
NOW = datetime(2026, 10, 9, 8, 0, tzinfo=IST)


def start(tmp_path, monkeypatch, drop=()):
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    schedule = copy.deepcopy(data["farmer_schedule"])
    for key in drop:
        schedule.pop(key)
    data["farmer_schedule"] = schedule
    farm_file = tmp_path / "farm.json"
    farm_file.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(sim_app, "today_ist", lambda: TODAY)
    source = PilotFarmSource(load_pilot_farm_file(farm_file), clock=lambda: TODAY, now=lambda: NOW)
    mcp, stop_mcp = _start({}, source=source)
    port = _free_port()
    settings = SimulatorSettings(port=port, mcp_url=mcp.url, auth_token=None, mode="pilot", farm_path=farm_file)
    spy = Spy(settings.mcp_url, None)
    uv = uvicorn.Server(uvicorn.Config(build_app(settings, spy), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not uv.started:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    return Rig(source, spy, f"http://127.0.0.1:{port}"), uv, thread, stop_mcp


@pytest.fixture
def rig(tmp_path, monkeypatch):
    r, uv, thread, stop = start(tmp_path, monkeypatch)
    yield r
    uv.should_exit = True
    thread.join(timeout=10)
    stop()


def ui(r):
    return httpx2.get(r.base + "/api/pilot/ui", timeout=20).json()


def test_the_page_is_offered_the_ten_questions_and_a_button_word(rig):
    body = ui(rig)
    assert [q["id"] for q in body["questions"]] == list(range(1, 11))
    assert body["strings"]["questions"]["te"] == "ప్రశ్నలు"
    assert body["questions"][1]["te"] == "తదుపరి టీకా ఎప్పుడు?"


def test_a_tapped_question_is_answered_from_his_schedule_with_no_tool_call(rig):
    before = len(rig.spy.calls)
    out = rig.turn(chip="question", params={"id": 7}, lang="te")
    assert out["kind"] == "answer" and out["is_error"] is False
    assert out["speech"] == "As you told us: The doctor comes every 3 days."
    assert out["speech_te"] == "మీరు చెప్పినట్లు: డాక్టర్ 3 రోజులకు ఒకసారి వస్తారు."
    assert len(rig.spy.calls) == before  # nothing was asked of any tool, so no model either


def test_the_example_farm_answers_per_shed_with_todays_farmer_day(rig):
    out = rig.turn(chip="question", params={"id": 1}, lang="te")
    # shed 1 was placed 2026-09-01 (day 39 on 9 October), shed 2 on 2026-09-10 (day 30)
    assert out["speech"] == "As you told us: shed 1: day 39. shed 2: day 30."


def test_every_offered_question_answers_and_none_claims_confirmed_or_expert(rig):
    for q in ui(rig)["questions"]:
        out = rig.turn(chip="question", params={"id": q["id"]}, lang="te")
        assert out["speech"].startswith("As you told us:") and out["speech_te"].startswith("మీరు చెప్పినట్లు:")
        text = (out["speech"] + out["speech_te"]).lower()
        assert "confirm" not in text and "expert" not in text and "note" not in text, q["id"]
        assert "EXAMPLE ONLY" not in out["speech"] and "invented numbers" not in out["speech"]


@pytest.mark.parametrize("params", [{"id": 0}, {"id": 11}, {"id": "2"}, {"id": True}, {"id": 2.5}, {}, {"id": None}])
def test_anything_that_is_not_an_offered_question_is_refused(rig, params):
    r = rig.post(
        "/api/turn", {"device": "dot", "session": "session-aaaaaaaaaaaaaaaa", "chip": "question", "params": params}
    )
    assert r.status_code == 400 and "not one of the offered questions" in r.json()["error"]


def test_a_question_whose_data_is_absent_is_not_offered_and_is_refused(tmp_path, monkeypatch):
    r, uv, thread, stop = start(tmp_path, monkeypatch, drop=("spray_water_above_c",))
    try:
        assert 5 not in [q["id"] for q in ui(r)["questions"]]
        bad = r.post(
            "/api/turn",
            {"device": "dot", "session": "session-aaaaaaaaaaaaaaaa", "chip": "question", "params": {"id": 5}},
        )
        assert bad.status_code == 400
    finally:
        uv.should_exit = True
        thread.join(timeout=10)
        stop()


def test_without_a_schedule_no_questions_are_offered(tmp_path, monkeypatch):
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data.pop("farmer_schedule")
    farm_file = tmp_path / "farm.json"
    farm_file.write_text(json.dumps(data), encoding="utf-8")
    source = PilotFarmSource(load_pilot_farm_file(farm_file), clock=lambda: TODAY, now=lambda: NOW)
    mcp, stop_mcp = _start({}, source=source)
    port = _free_port()
    settings = SimulatorSettings(port=port, mcp_url=mcp.url, auth_token=None, mode="pilot", farm_path=farm_file)
    uv = uvicorn.Server(
        uvicorn.Config(
            build_app(settings, Spy(settings.mcp_url, None)), host="127.0.0.1", port=port, log_level="warning"
        )
    )
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    while not uv.started:
        time.sleep(0.02)
    try:
        assert httpx2.get(f"http://127.0.0.1:{port}/api/pilot/ui", timeout=20).json()["questions"] == []
    finally:
        uv.should_exit = True
        thread.join(timeout=10)
        stop_mcp()
