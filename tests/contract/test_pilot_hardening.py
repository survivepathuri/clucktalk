"""Step 51 part D: the pilot Simulator's hardening, over real HTTP. A bearer token is required for every API call
(constant-time compare), the real hostname and its https origin are allowed and nothing else, bodies are small, requests
are rate limited, sessions are capped, a kill switch pauses everything but the health check, and the logs hold no
utterance, shed name or token. Anonymous counters hold numbers only."""

from __future__ import annotations

import hmac
import json
import logging
import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import httpx2
import pytest
import uvicorn

from clucktalk.pilot import load_pilot_farm_file
from clucktalk.server.farm_state import IST, PilotFarmSource
from clucktalk.simulator import app as sim_app
from clucktalk.simulator.app import SimulatorSettings, build_app
from clucktalk.simulator.mcp_client import McpClient
from clucktalk.usage import UsageCounters
from tests.contract.conftest import _free_port, _start

ROOT = Path(__file__).resolve().parents[2]
TODAY = date(2026, 10, 9)
NOW = datetime(2026, 10, 9, 8, 0, tzinfo=IST)
TOKEN = "t" * 12 + "pilot-secret-token-0123456789"
OTHER = "o" * 12 + "other-secret-token-0123456789"
SESSION = "session-aaaaaaaaaaaaaaaa"


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class Rig:
    def __init__(self, base: str, settings: SimulatorSettings, clock: FakeClock, source: PilotFarmSource) -> None:
        self.base, self.settings, self.clock, self.source = base, settings, clock, source

    def headers(self, token: str | None = TOKEN, **extra: str) -> dict[str, str]:
        h = {"origin": self.base}
        if token:
            h["authorization"] = f"Bearer {token}"
        h.update(extra)
        return h

    def turn(self, token: str | None = TOKEN, session: str = SESSION, **body):
        return httpx2.post(
            self.base + "/api/turn",
            json={"device": "dot", "lang": "te", "session": session, **body},
            headers=self.headers(token),
            timeout=20,
        )


def start(tmp_path: Path, **overrides) -> Iterator[Rig]:
    source = PilotFarmSource(
        load_pilot_farm_file(ROOT / "docs" / "pilot_farm.example.json"), clock=lambda: TODAY, now=lambda: NOW
    )
    mcp, stop_mcp = _start({}, source=source)
    port = _free_port()
    fields = {
        "port": port,
        "mcp_url": mcp.url,
        "auth_token": None,
        "mode": "pilot",
        "tokens": (TOKEN,),
        "usage_path": tmp_path / "usage.json",
        "disabled_file": tmp_path / "DISABLED",
    }
    settings = SimulatorSettings(**{**fields, **overrides})
    clock = FakeClock()
    uv = uvicorn.Server(
        uvicorn.Config(
            build_app(settings, McpClient(settings.mcp_url, None), clock=clock),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not uv.started:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    yield Rig(f"http://127.0.0.1:{port}", settings, clock, source)
    uv.should_exit = True
    thread.join(timeout=10)
    stop_mcp()


@pytest.fixture
def rig(tmp_path):
    yield from start(tmp_path)


# -- auth ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/api/state", "/api/pilot/ui", "/api/resource?uri=ui://x"])
def test_every_api_get_needs_the_token(rig, path):
    assert httpx2.get(rig.base + path, timeout=10).status_code == 401
    assert httpx2.get(rig.base + path, headers={"authorization": f"Bearer {OTHER}"}, timeout=10).status_code == 401
    assert (
        httpx2.get(rig.base + "/api/state", headers={"authorization": f"Bearer {TOKEN}"}, timeout=10).status_code == 200
    )


def test_a_turn_needs_the_token_and_nothing_is_called_without_it(rig):
    assert rig.turn(token=None, utterance="x").status_code == 401
    assert rig.turn(token=OTHER, utterance="x").status_code == 401
    assert rig.turn(token="", utterance="x").status_code == 401
    assert rig.turn(utterance="ఫారం ఎలా ఉంది").status_code == 200


@pytest.mark.parametrize(
    "value",
    [
        "",
        "Bearer",
        f"Basic {TOKEN}",
        TOKEN,
        f"Bearer  {TOKEN} x",
        f"bearer {TOKEN}",
        f"BEARER {TOKEN}",
        f"bearer {TOKEN.upper()}",
    ],
)
def test_only_the_exact_bearer_form_is_accepted(rig, value):
    r = httpx2.get(rig.base + "/api/state", headers={"authorization": value}, timeout=10)
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    assert TOKEN not in r.text


def test_the_unauthorised_answer_says_nothing_about_why(rig):
    a = httpx2.get(rig.base + "/api/state", timeout=10)
    b = httpx2.get(rig.base + "/api/state", headers={"authorization": f"Bearer {OTHER}"}, timeout=10)
    assert a.status_code == b.status_code == 401 and a.json() == b.json() == {"error": "unauthorized"}


def test_the_page_its_files_and_the_health_check_are_public_and_carry_no_data(rig):
    assert httpx2.get(rig.base + "/", timeout=10).status_code == 200
    assert httpx2.get(rig.base + "/static/pilot.js", timeout=10).status_code == 200
    health = httpx2.get(rig.base + "/healthz", timeout=10)
    assert health.status_code == 200 and health.json() == {"status": "ok", "mode": "pilot"}


def test_the_token_is_compared_in_constant_time_against_every_configured_token(tmp_path, monkeypatch):
    calls: list[tuple[bytes, bytes]] = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(sim_app.hmac, "compare_digest", spy)
    for r in start(tmp_path, tokens=(TOKEN, OTHER)):
        r_ok = httpx2.get(r.base + "/api/state", headers={"authorization": f"Bearer {TOKEN}"}, timeout=10)
        assert r_ok.status_code == 200
        assert len(calls) == 2, "the first token matched, but the second was still compared (no early exit)"
        calls.clear()
        r_bad = httpx2.get(r.base + "/api/state", headers={"authorization": "Bearer nope"}, timeout=10)
        assert r_bad.status_code == 401 and len(calls) == 2


# -- host and origin -------------------------------------------------------------------------------------------------
def test_the_real_hostname_and_its_https_origin_are_allowed_and_nothing_else(tmp_path):
    for r in start(tmp_path, public_origin="https://pilot.example.org"):
        ok = httpx2.post(
            r.base + "/api/turn",
            json={"device": "dot", "lang": "te", "session": SESSION, "utterance": "సహాయం"},
            headers={
                "host": "pilot.example.org",
                "origin": "https://pilot.example.org",
                "authorization": f"Bearer {TOKEN}",
            },
            timeout=20,
        )
        assert ok.status_code == 200
        wrong_origin = httpx2.post(
            r.base + "/api/turn",
            json={"utterance": "x", "session": SESSION},
            headers={"host": "pilot.example.org", "origin": "https://evil.example", "authorization": f"Bearer {TOKEN}"},
            timeout=20,
        )
        assert wrong_origin.status_code == 403
        wrong_host = httpx2.get(
            r.base + "/api/state", headers={"host": "evil.example", "authorization": f"Bearer {TOKEN}"}, timeout=10
        )
        assert wrong_host.status_code == 421
        http_origin = httpx2.post(
            r.base + "/api/turn",
            json={"utterance": "x", "session": SESSION},
            headers={
                "host": "pilot.example.org",
                "origin": "http://pilot.example.org",
                "authorization": f"Bearer {TOKEN}",
            },
            timeout=20,
        )
        assert http_origin.status_code == 403  # the public origin is https only


def test_without_a_public_origin_only_loopback_hosts_work(rig):
    r = httpx2.get(
        rig.base + "/api/state", headers={"host": "pilot.example.org", "authorization": f"Bearer {TOKEN}"}, timeout=10
    )
    assert r.status_code == 421


# -- size and rate ---------------------------------------------------------------------------------------------------
def test_a_big_body_is_refused_with_413_whether_or_not_it_says_how_big(rig):
    big = json.dumps({"utterance": "a" * 20000, "session": SESSION, "lang": "te"})
    r = httpx2.post(
        rig.base + "/api/turn", content=big, headers={**rig.headers(), "content-type": "application/json"}, timeout=20
    )
    assert r.status_code == 413

    def chunks():
        for _ in range(40):
            yield b"x" * 1024

    r = httpx2.post(
        rig.base + "/api/turn",
        content=chunks(),
        headers={**rig.headers(), "content-type": "application/json"},
        timeout=20,
    )
    assert r.status_code == 413
    assert rig.turn(utterance="సహాయం").status_code == 200  # a normal request still works


def test_requests_are_rate_limited_per_token_and_recover_after_a_minute(tmp_path):
    for r in start(tmp_path, rate_per_minute=5, tokens=(TOKEN, OTHER)):
        statuses = [
            httpx2.get(r.base + "/api/state", headers={"authorization": f"Bearer {TOKEN}"}, timeout=10).status_code
            for _ in range(7)
        ]
        assert statuses == [200] * 5 + [429] * 2
        limited = httpx2.get(r.base + "/api/state", headers={"authorization": f"Bearer {TOKEN}"}, timeout=10)
        assert limited.headers["retry-after"].isdigit() and 1 <= int(limited.headers["retry-after"]) <= 60
        other = httpx2.get(r.base + "/api/state", headers={"authorization": f"Bearer {OTHER}"}, timeout=10)
        assert other.status_code == 200  # another farmer's token has its own allowance
        r.clock.t += 61
        assert (
            httpx2.get(r.base + "/api/state", headers={"authorization": f"Bearer {TOKEN}"}, timeout=10).status_code
            == 200
        )


def test_wrong_tokens_are_limited_too_so_guessing_is_slow(tmp_path):
    for r in start(tmp_path, rate_per_minute=60):
        codes = [
            httpx2.get(r.base + "/api/state", headers={"authorization": f"Bearer wrong{i}"}, timeout=10).status_code
            for i in range(25)
        ]
        assert codes[:20] == [401] * 20 and set(codes[20:]) == {429}
        assert (
            httpx2.get(r.base + "/api/state", headers={"authorization": f"Bearer {TOKEN}"}, timeout=10).status_code
            == 200
        )


# -- sessions --------------------------------------------------------------------------------------------------------
def test_the_number_of_sessions_is_capped_and_idle_ones_are_dropped(tmp_path):
    for r in start(tmp_path, max_sessions=3, rate_per_minute=1000):
        ids = [f"session-{c}{c}{c}{c}{c}{c}{c}{c}{c}{c}{c}{c}{c}{c}{c}{c}" for c in "abcd"]
        codes = [r.turn(session=i, utterance="సహాయం").status_code for i in ids]
        assert codes == [200, 200, 200, 503]
        assert r.turn(session=ids[0], utterance="సహాయం").status_code == 200  # an existing session is never refused
        r.clock.t += 3601  # every session has been idle for more than an hour
        assert r.turn(session=ids[3], utterance="సహాయం").status_code == 200


# -- kill switch -----------------------------------------------------------------------------------------------------
def test_the_kill_switch_file_pauses_everything_but_the_health_check_and_resumes(rig):
    flag = rig.settings.disabled_file
    assert rig.turn(utterance="సహాయం").status_code == 200
    flag.write_text("paused", encoding="utf-8")
    assert rig.turn(utterance="సహాయం").status_code == 503
    assert httpx2.get(rig.base + "/", timeout=10).status_code == 503
    assert (
        httpx2.get(rig.base + "/api/state", headers={"authorization": f"Bearer {TOKEN}"}, timeout=10).status_code == 503
    )
    health = httpx2.get(rig.base + "/healthz", timeout=10)
    assert health.status_code == 200 and health.json() == {"status": "disabled", "mode": "pilot"}
    flag.unlink()
    assert rig.turn(utterance="సహాయం").status_code == 200


def test_the_kill_switch_variable_is_read_at_request_time(rig, monkeypatch):
    monkeypatch.setenv("CLUCKTALK_DISABLED", "true")
    assert rig.turn(utterance="సహాయం").status_code == 503
    monkeypatch.setenv("CLUCKTALK_DISABLED", "false")
    assert rig.turn(utterance="సహాయం").status_code == 200
    monkeypatch.delenv("CLUCKTALK_DISABLED")
    assert rig.turn(utterance="సహాయం").status_code == 200


def test_a_paused_turn_changes_nothing(rig):
    rig.settings.disabled_file.write_text("x", encoding="utf-8")
    r = rig.turn(utterance="షెడ్ 1 లో 3 కోళ్లు చనిపోయాయి")
    assert r.status_code == 503 and rig.source.store.records(rig.source.farm_id, "house-1") == ()


# -- logs ------------------------------------------------------------------------------------------------------------
def test_the_logs_hold_no_utterance_no_shed_name_and_no_token(rig, caplog):
    caplog.set_level(logging.DEBUG)
    utterance = "షెడ్ 1 లో 7 కోళ్లు చనిపోయాయి"
    assert rig.turn(utterance=utterance).status_code == 200
    assert rig.turn(utterance="అవును").status_code == 200
    assert rig.turn(token=OTHER, utterance=utterance).status_code == 401
    assert (
        httpx2.get(rig.base + "/api/pilot/ui", headers={"authorization": f"Bearer {TOKEN}"}, timeout=10).status_code
        == 200
    )
    text = "\n".join(f"{r.name}: {r.getMessage()}" for r in caplog.records)
    for secret in (utterance, "చనిపోయ", "కోళ్లు", TOKEN, OTHER, TOKEN[:16], "shed 1", "house-1", SESSION):
        assert secret not in text, f"{secret!r} reached a log line"


# -- counters --------------------------------------------------------------------------------------------------------
def test_counters_count_days_confirmations_cancellations_records_and_alerts_and_hold_no_personal_data(rig):
    rig.turn(utterance="షెడ్ 1 లో 3 కోళ్లు చనిపోయాయి")
    rig.turn(utterance="అవును")  # confirmed and saved
    rig.turn(utterance="షెడ్ 2 లో 4 కోళ్లు చనిపోయాయి")
    rig.turn(utterance="వద్దు")  # cancelled
    rig.turn(utterance="షెడ్ 1 ఎలా ఉంది")  # a status answer
    data = json.loads(rig.settings.usage_path.read_text(encoding="utf-8"))
    assert data["records_confirmed"] == 1 and data["confirmations"] == 1 and data["cancellations"] == 1
    assert data["days_used"] == [TODAY.isoformat()] or len(data["days_used"]) == 1
    assert set(data) == {"days_used", "records_confirmed", "alerts_shown", "confirmations", "cancellations"}
    assert set(data["alerts_shown"]) == {"watch", "alert"}
    raw = rig.settings.usage_path.read_text(encoding="utf-8")
    for secret in ("shed", "house", "చనిపోయ", TOKEN, SESSION):
        assert secret not in raw


def test_counters_survive_a_restart_and_a_damaged_file_is_not_silently_reset(tmp_path):
    path = tmp_path / "usage.json"
    first = UsageCounters(path, today=lambda: TODAY)
    first.record_turn()
    first.record_answer("yes", applied_record=True)
    again = UsageCounters(path, today=lambda: TODAY)
    assert again.snapshot()["records_confirmed"] == 1 and again.snapshot()["days_used"] == [TODAY.isoformat()]
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ValueError, match="usage"):
        UsageCounters(path, today=lambda: TODAY)
    assert path.read_text(encoding="utf-8") == "{ not json"  # left for the builder to look at, never overwritten


def test_an_alert_is_counted_when_the_farmer_is_shown_one(tmp_path):
    counters = UsageCounters(tmp_path / "u.json", today=lambda: TODAY)
    counters.record_result("get_farm_status", {"level": "alert"})
    counters.record_result("get_daily_briefing", {"level": "watch"})
    counters.record_result("get_farm_status", {"level": "ok"})
    counters.record_result("get_help", {"level": "alert"})  # not a status answer: not counted
    counters.record_result("get_farm_status", {"level": "unknown"})
    assert counters.snapshot()["alerts_shown"] == {"watch": 1, "alert": 1}


def test_settings_replace_keeps_the_new_fields():
    base = SimulatorSettings(port=1, mcp_url="http://x", auth_token=None)
    assert replace(base, tokens=("a",)).tokens == ("a",)


def test_the_developer_page_is_not_served_when_a_token_is_required(rig):
    assert httpx2.get(rig.base + "/desktop", timeout=10).status_code == 404


def test_only_a_saved_record_counts_as_a_record_not_every_yes(tmp_path):
    counters = UsageCounters(tmp_path / "u.json", today=lambda: TODAY)
    counters.record_answer("yes", applied_record=False)  # for example a health check started
    assert counters.snapshot()["confirmations"] == 1 and counters.snapshot()["records_confirmed"] == 0
    counters.record_answer("yes", applied_record=True)
    assert counters.snapshot()["records_confirmed"] == 1
    counters.record_answer("maybe", applied_record=True)  # not an answer: nothing counted
    assert counters.snapshot()["confirmations"] == 2 and counters.snapshot()["cancellations"] == 0


def test_a_confirmed_health_check_is_a_confirmation_but_not_a_record(rig):
    rig.turn(chip="health", params={"house": 1, "signs": ["coughing"]})
    rig.turn(chip="yes")
    data = json.loads(rig.settings.usage_path.read_text(encoding="utf-8"))
    assert data["confirmations"] == 1 and data["records_confirmed"] == 0


def test_a_yes_that_only_asks_the_add_or_replace_question_again_is_not_counted_as_a_confirmation(rig):
    rig.turn(utterance="షెడ్ 1 లో 3 కోళ్లు చనిపోయాయి")
    rig.turn(chip="yes")
    rig.turn(utterance="షెడ్ 1 లో 2 కోళ్లు చనిపోయాయి")
    rig.turn(chip="yes")  # not an answer to the question: nothing was confirmed
    data = json.loads(rig.settings.usage_path.read_text(encoding="utf-8"))
    assert data["confirmations"] == 1 and data["records_confirmed"] == 1
    rig.turn(chip="add")
    data = json.loads(rig.settings.usage_path.read_text(encoding="utf-8"))
    assert data["confirmations"] == 2 and data["records_confirmed"] == 2
